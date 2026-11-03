"""Pruebas de la superficie geografica del analisis temporal."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import mapa_calor_cartagena as mapa_geo  # noqa: E402


class MapaCalorCartagenaTest(unittest.TestCase):
    def setUp(self):
        self.catalogo = pd.DataFrame([
            {"id_nodo": "A", "nombre_nodo": "Nodo A", "punto_referencia": "Ref A",
             "barrio": "Centro", "lat": 10.400, "lon": -75.500},
            {"id_nodo": "B", "nombre_nodo": "Nodo B", "punto_referencia": "Ref B",
             "barrio": "Centro", "lat": 10.410, "lon": -75.490},
        ])
        self.datos = pd.DataFrame({
            "id_nodo": ["A", "A", "B"],
            "currentSpeed": [20.0, 40.0, 60.0],
            "freeFlowSpeed": [70.0, 70.0, 75.0],
            "velocidad_ratio": [0.30, 0.50, 0.80],
        })

    def test_resume_los_datos_reales_por_nodo(self):
        salida = mapa_geo.resumir_nodos(self.datos, self.catalogo, "currentSpeed")
        nodo_a = salida.set_index("id_nodo").loc["A"]
        self.assertEqual(nodo_a["vel_actual"], 30.0)
        self.assertEqual(nodo_a["vel_libre"], 70.0)
        self.assertEqual(nodo_a["ratio"], 0.40)
        self.assertEqual(nodo_a["valor"], 30.0)
        self.assertEqual(nodo_a["n_mediciones"], 2)

    def test_cada_indicador_usa_su_valor_correcto(self):
        libre = mapa_geo.resumir_nodos(self.datos, self.catalogo, "freeFlowSpeed")
        fluidez = mapa_geo.resumir_nodos(self.datos, self.catalogo, "velocidad_ratio")
        self.assertEqual(libre.set_index("id_nodo").loc["A", "valor"], 70.0)
        self.assertEqual(fluidez.set_index("id_nodo").loc["A", "valor"], 0.40)

    def test_reutiliza_los_promedios_del_mapa_de_trafico(self):
        promedios = self.catalogo.assign(
            vel_actual=[25.0, 55.0], vel_libre=[70.0, 75.0],
            ratio=[0.35, 0.80], n=[12, 10],
        )
        salida = mapa_geo.preparar_promedios(promedios, "vel_actual")
        self.assertEqual(salida["valor"].tolist(), [25.0, 55.0])
        self.assertEqual(salida["n_mediciones"].tolist(), [12, 10])

    def test_superficie_deja_transparente_lo_que_no_tiene_cobertura(self):
        nodos = mapa_geo.resumir_nodos(self.datos, self.catalogo, "currentSpeed")
        puntos_red = nodos[["lat", "lon"]].to_numpy()
        superficie = mapa_geo.interpolar_superficie(nodos, "currentSpeed", puntos_red)
        alpha = superficie["imagen"][:, :, 3]
        self.assertGreater((alpha > 0).sum(), 0)
        self.assertGreater((alpha == 0).sum(), 0)
        self.assertGreaterEqual(alpha.max(), 240)
        self.assertLess(superficie["celdas_cubiertas"], superficie["celdas_totales"])

    def test_escalas_son_fijas_y_fluidez_coincide_con_mapa_trafico(self):
        actual = mapa_geo.CONFIG_INDICADORES["currentSpeed"]
        libre = mapa_geo.CONFIG_INDICADORES["freeFlowSpeed"]
        self.assertEqual(actual["paradas"], libre["paradas"])
        self.assertEqual((actual["vmin"], actual["vmax"]), (10, 75))
        ratio = mapa_geo.CONFIG_INDICADORES["velocidad_ratio"]
        self.assertEqual(ratio["ticks"], ["0", "0,60", "0,75", "0,90", "1"])
        self.assertEqual(
            ratio["paradas"],
            [(0.00, "#ff1744"), (0.60, "#ff1744"), (0.75, "#ff5a00"),
             (0.90, "#ffb000"), (1.00, "#00c853")],
        )

    def test_red_se_muestrea_fina_y_la_cobertura_no_invade_el_entorno(self):
        red = {"conexiones": [{
            "a": "A", "b": "B",
            "path": [[10.400, -75.500], [10.400, -75.490]],
        }]}
        puntos = mapa_geo._puntos_red(red, self.catalogo)
        distancias = np.hypot(
            np.diff(puntos[:, 0]) * 111_320.0,
            np.diff(puntos[:, 1]) * 109_400.0,
        )
        self.assertGreater(len(puntos), 2)
        self.assertLessEqual(distancias.max(), mapa_geo.PASO_MUESTREO_RED_M + 2)
        self.assertLessEqual(mapa_geo.COBERTURA_RED_M, 180)

    def test_colores_de_fluidez_son_vivos_y_opacos(self):
        ratio = mapa_geo.CONFIG_INDICADORES["velocidad_ratio"]
        rgba = mapa_geo._rgba_valores(
            np.asarray([[0.75]]), ratio["paradas"], ratio["vmin"], ratio["vmax"]
        )[0, 0]
        self.assertEqual(rgba.tolist(), [255, 90, 0, 245])

    def test_leyenda_fluidez_no_genera_nan(self):
        nodos = mapa_geo.resumir_nodos(self.datos, self.catalogo, "velocidad_ratio")
        red = {"conexiones": [{
            "a": "A", "b": "B",
            "path": [[10.400, -75.500], [10.410, -75.490]],
        }]}
        mapa, _ = mapa_geo.construir_mapa(
            nodos, self.catalogo, red, "velocidad_ratio", lambda valor: ("#000", "Prueba")
        )
        contenido = mapa.get_root().render()
        self.assertNotIn(">NaN<", contenido)
        self.assertIn("0,60", contenido)
        self.assertIn("0,75", contenido)
        self.assertIn("0,90", contenido)

    def test_control_de_capas_es_compacto_colapsado_y_abajo(self):
        nodos = mapa_geo.resumir_nodos(self.datos, self.catalogo, "velocidad_ratio")
        mapa, _ = mapa_geo.construir_mapa(
            nodos, self.catalogo, {"conexiones": []}, "velocidad_ratio",
            lambda valor: ("#000", "Prueba"),
        )
        contenido = mapa.get_root().render()
        self.assertIn('"position": "bottomright"', contenido)
        self.assertIn('"collapsed": true', contenido)
        self.assertIn('classList.add("capas-compactas")', contenido)
        self.assertIn('"opacity": 0.96', contenido)


if __name__ == "__main__":
    unittest.main()
