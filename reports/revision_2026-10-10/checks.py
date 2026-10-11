import ast
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(os.environ.get('PROJECT_ROOT', Path.cwd()))
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'dashboard')]
os.environ.update(FUENTE_DASHBOARD='db', DB_HOST='127.0.0.1', DB_USER='manuelesteban', DB_NAME='trafico', PGOPTIONS='-c default_transaction_read_only=on')
import pandas as pd
import config
import db
import descargar_trafico as dt
import google_upload as gu
import rotacion_llaves as rl
import mapa_nodos as mn
import red_nodos as rn

class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historical = db.leer_rango(date(2026,9,1), date(2026,9,30))
        cls.catalog = dt.cargar_nodos(config.NODOS_PATH)
        cls.graph = json.loads((ROOT/'data/red_nodos.json').read_text())

    def test_01_read_only_database(self):
        from sqlalchemy import text
        with db.get_engine().connect() as conn:
            self.assertEqual(conn.execute(text('SHOW transaction_read_only')).scalar(), 'on')
        self.assertGreater(len(self.historical), 1000)

    def test_02_sql_pandas_agreement(self):
        cases = [{}, {'hora_ini':8,'hora_fin':9}, {'mes':9}, {'dia_semana':7}, {'quincena':True}, {'ids':('AER_CRE','TUN_CRE')}, {'mes':8}, {'hora_ini':16,'hora_fin':16}, {'dia_semana':2,'quincena':True,'ids':('AER_CRE',)}]
        for case in cases:
            with self.subTest(case=case):
                filters=dict(fecha_ini=date(2026,9,1),fecha_fin=date(2026,9,30),**case)
                sql=db.promedios_por_nodo(**filters).sort_values('id_nodo').reset_index(drop=True)
                py=mn.promedios_por_nodo_df(self.historical,**filters).sort_values('id_nodo').reset_index(drop=True)
                pd.testing.assert_frame_equal(sql,py,check_dtype=False,check_exact=False,rtol=1e-10,atol=1e-10)

    def test_03_catalog_network_integrity(self):
        ids=set(self.catalog.id_nodo)
        self.assertEqual(len(ids),113)
        self.assertEqual(len(self.catalog),len(ids))
        pairs={p for p in dt.leer_conexiones(config.NODOS_PATH) if set(p) <= ids}
        graph_pairs={(c['a'],c['b']) for c in self.graph['conexiones']}
        self.assertEqual(pairs,graph_pairs)
        for c in self.graph['conexiones']:
            self.assertTrue({c['a'],c['b']} <= ids)
            self.assertGreater(c['d_ab_m'],0)
            self.assertGreater(c['d_ba_m'],0)
            self.assertGreaterEqual(len(c['path']),2)

    def test_04_dijkstra_and_missing_data(self):
        graph={'conexiones':[{'a':'A','b':'B','d_ab_m':1000,'d_ba_m':3000},{'a':'A','b':'C','d_ab_m':200,'d_ba_m':200},{'a':'C','b':'B','d_ab_m':200,'d_ba_m':200}]}
        speeds={n:{'vel_actual':36.,'vel_libre':72.} for n in ['A','B','C']}
        route=rn.ruta_mas_rapida('A','B',graph,speeds)
        self.assertEqual(route['nodos'],['A','C','B'])
        self.assertEqual(route['tiempo_s'],40.)
        self.assertIsNone(rn.ruta_mas_rapida('A','B',graph,{}))
        self.assertIsNone(rn.ruta_mas_rapida('A','A',graph,speeds))

    def test_05_render_maps(self):
        catalog=self.catalog.copy()
        avg=db.promedios_por_nodo(date(2026,9,1),date(2026,9,30))
        data=catalog.merge(avg,on='id_nodo',how='left')
        prom=avg.set_index('id_nodo').to_dict('index')
        classify=lambda v: ('#22c55e','Fluido')
        for metric in ['ratio','vel_actual','vel_libre']:
            m=mn.construir_mapa(data,metric,metric,classify)
            self.assertIn('L.circleMarker',m.get_root().render())
            m=rn.construir_mapa_red(data,self.graph,prom,metric,metric,classify,True,True)
            self.assertIn('L.polyline',m.get_root().render())

    def run_etl(self, keys, response):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp)
            nodes=pd.DataFrame([dict(id_nodo=f'N{i}',nombre_nodo='Nodo',categoria='A',lat=10.4,lon=-75.5,activo_final=True) for i in range(3)])
            calls=[]; frames=[]
            def request(lat,lon,key):
                calls.append(key)
                ok=response(key,calls.count(key))
                return dict(ok=ok,status=200 if ok else 403,data={'flowSegmentData':dict(currentSpeed=20,freeFlowSpeed=40,currentTravelTime=20,freeFlowTravelTime=10)} if ok else None,error=None if ok else 'InsufficientFunds')
            with patch.multiple(config,API_KEYS=keys,API_KEYS_RESERVA=[],VPS_ID='1',RESULTADOS_DIR=temp,SUBIR_A_GOOGLE=True,GUARDAR_EN_DB=False,SUBIR_A_FIRESTORE=False), patch.object(rl,'ESTADO_FILE',temp/'state.json'), patch.object(dt,'cargar_nodos',return_value=nodes), patch.object(dt,'consultar_flow',side_effect=request), patch.object(dt.time,'sleep'), patch.object(dt,'registrar_log'), patch.object(gu,'subir_resultados',side_effect=lambda p,df:frames.append(df.copy()) or {'error':None}), contextlib.redirect_stdout(io.StringIO()):
                code=dt.main()
            return calls,frames[0],json.loads((temp/'state.json').read_text()),code

    def test_06_etl_success_derived_fields(self):
        calls,df,state,code=self.run_etl(['fake_A'],lambda k,n:True)
        self.assertEqual(code,0)
        self.assertTrue(df.ok.all())
        self.assertTrue((df.velocidad_ratio==.5).all())
        self.assertTrue((df.delay_rel_pct==100).all())
        self.assertEqual(state['llaves']['fake_A']['consumo'],3)

    def test_07_failover_preserves_node_when_two_keys_fail(self):
        calls,df,state,code=self.run_etl(['fake_A','fake_B','fake_C'],lambda k,n:k=='fake_B')
        self.assertTrue(df.ok.all(),f'Available fake_B but lost node: calls={calls}; ok={df.ok.tolist()}')

    def test_08_exhausted_key_stays_exhausted_after_earlier_success(self):
        calls,df,state,code=self.run_etl(['fake_A','fake_B'],lambda k,n:k=='fake_B' or n==1)
        self.assertTrue(state['llaves']['fake_A']['agotada'],str(state['llaves']['fake_A']))

    def test_09_sheet_schema_preserves_historical_positions(self):
        calls,df,state,code=self.run_etl(['fake_A'],lambda k,n:True)
        old_columns=[c for c in df.columns if c!='llave_id']
        original_row=['OLD:'+c for c in old_columns]
        service=MagicMock()
        service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value={'values':[old_columns]}
        with patch.object(gu,'build',return_value=service),contextlib.redirect_stdout(io.StringIO()):
            gu.asegurar_encabezados(None,list(df.columns),'fake_sheet')
        columns=service.spreadsheets.return_value.values.return_value.update.call_args.kwargs['body']['values'][0]
        reread=dict(zip(columns,original_row+['']))
        self.assertEqual(reread['velocidad_ratio'],'OLD:velocidad_ratio')

    def test_10_reverse_geometry_is_direction_specific(self):
        c=next(c for c in self.graph['conexiones'] if c['a']=='AER_CRE' and c['b']=='TUN_CRE')
        self.assertFalse(rn._trazo(c,{},True,-1)==c['path'][::-1],f'AB={c["d_ab_m"]}m BA={c["d_ba_m"]}m use identical road geometry')

    def test_11_reserve_and_cooldown(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(rl,'ESTADO_FILE',Path(temp)/'state.json'),patch.multiple(config,API_KEYS=['fake_A'],API_KEYS_RESERVA=['fake_R'],VPS_ID='1'):
            self.assertEqual(rl.siguiente_llave(),'fake_A')
            rl.marcar_agotada('fake_A','InsufficientFunds')
            self.assertEqual(rl.siguiente_llave(),'fake_R')
            s=rl.cargar_estado()
            s['llaves']['fake_A']['agotada_desde']=(datetime.now()-timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
            rl.guardar_estado(s)
            self.assertEqual(rl.siguiente_llave(),'fake_A')

    def test_12_http_failure_classification(self):
        for status,error,expected in [(403,'InsufficientFunds',rl.SIN_CREDITOS),(403,'Forbidden',rl.BLOQUEADA),(401,'',rl.BLOQUEADA),(429,'',rl.LIMITE),(500,'',None),(None,'timeout',None)]:
            self.assertEqual(rl.motivo_descarte(dict(ok=False,status=status,error=error)),expected)

    def test_13_total_capture_failure_returns_nonzero(self):
        calls,df,state,code=self.run_etl(['fake_A'],lambda k,n:False)
        self.assertNotEqual(code,0,'All requests failed but main() reports success to cron')

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Review)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    summary={'tests':result.testsRun,'failures':[{'test':str(t),'detail':d} for t,d in result.failures],'errors':[{'test':str(t),'detail':d} for t,d in result.errors]}
    Path(__file__).with_name('results.json').write_text(json.dumps(summary,indent=2))
    sys.exit(not result.wasSuccessful())
