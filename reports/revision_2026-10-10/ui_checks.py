import contextlib
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import checks
import streamlit as st
from streamlit.testing.v1 import AppTest
import db
import google_upload as gu

ROOT=checks.ROOT
data=db.leer_rango(date(2026,9,23),date(2026,9,30))
snapshot=data[data.consultation_time==data.consultation_time.max()].copy()
results=[]
def check(name,app):
    errors=[e.message for e in app.exception]
    results.append({'case':name,'exceptions':errors})
    print(name, 'PASS' if not errors else errors, flush=True)
    if errors:
        raise RuntimeError(errors)

with patch.object(gu,'cargar_credenciales',return_value=None),patch.object(gu,'leer_sheet',return_value=data),patch.object(db,'leer_datos',return_value=snapshot):
    st.cache_data.clear()
    app=AppTest.from_file(str(ROOT/'dashboard/monitor.py'),default_timeout=30).run()
    check('initial render with historical snapshot',app)
    print('WIDGETS',[(s.key,s.label,s.value) for s in app.selectbox],flush=True)
    print('DATES',[(s.key,s.label,s.value) for s in app.date_input],flush=True)
    app.selectbox(key='mapa_mes').select('Septiembre').run()
    check('map month September',app)
    app.selectbox(key='mapa_franja').select('Hora pico AM (08–09)').run()
    check('morning hours callback',app)
    assert app.slider(key='mapa_horas').value==(8,9)
    app.slider(key='mapa_horas').set_range(10,12).run()
    check('custom hours callback',app)
    assert app.selectbox(key='mapa_franja').value=='Personalizado'
    app.selectbox(key='mapa_dia').select('Lunes').run()
    check('Monday filter',app)
    app.multiselect(key='mapa_nodos').select('AER_CRE').run()
    check('single node',app)
    for label in ['Velocidad actual (km/h)','Velocidad de flujo libre (km/h)']:
        app.selectbox(key='mapa_metrica').select(label).run()
        check(label,app)
    app.selectbox(key='mapa_mes').select('Enero').run()
    check('empty month grey nodes',app)
    assert any('No hay mediciones' in x.value for x in app.info)
    app.button(key='mapa_restablecer').click().run()
    check('reset filters',app)
    assert app.selectbox(key='mapa_mes').value=='Todos'
    assert app.slider(key='mapa_horas').value==(0,23)
    app.selectbox(key='red_origen').select('AER_CRE').run()
    app.selectbox(key='red_destino').select('TUN_CRE').run()
    check('origin destination route',app)
    assert any(m.label=='Distancia total' for m in app.metric)
    print('ROUTE METRICS',[(m.label,m.value) for m in app.metric if m.label in ['Distancia total','Tiempo promedio de viaje','Nodos en la ruta']],flush=True)
    app.selectbox(key='red_destino').select('AER_CRE').run()
    check('same origin destination',app)
    assert any('mismo nodo' in x.value for x in app.info)
    app.selectbox(key='red_mes').select('Enero').run()
    app.selectbox(key='red_destino').select('TUN_CRE').run()
    check('route without observations',app)
    assert any('No hay un camino' in x.value for x in app.warning)
    app.radio(key='red_tipo_ruta').set_value('Corredor').run()
    check('empty corridors',app)
    assert any('Todavia no hay corredores' in x.value for x in app.info)
    for d in app.date_input:
        if d.label=='Desde':
            d.set_value(date(2026,9,30))
        elif d.label=='Hasta':
            d.set_value(date(2026,9,29))
    app.run()
    check('inverted historical range',app)
    assert any("La fecha 'Hasta'" in x.value for x in app.error)
    for d in app.date_input:
        if d.label=='Desde':d.set_value(date(2026,9,23))
        elif d.label=='Hasta':d.set_value(date(2026,9,30))
    app.run()
    for b in app.button:
        if b.label=='📥 Generar reporte HTML':b.click()
    app.run()
    check('HTML report generation',app)
    assert any('Reporte generado' in x.value for x in app.success)

Path(__file__).with_name('ui_results.json').write_text(json.dumps(results,indent=2))
