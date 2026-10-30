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

    def test_superficie_deja_transparente_lo_que_no_tiene_cobertura(self):
        nodos = mapa_geo.resumir_nodos(self.datos, self.catalogo, "currentSpeed")
        puntos_red = nodos[["lat", "lon"]].to_numpy()
        superficie = mapa_geo.interpolar_superficie(nodos, "currentSpeed", puntos_red)
        alpha = superficie["imagen"][:, :, 3]
        self.assertGreater((alpha > 0).sum(), 0)
        self.assertGreater((alpha == 0).sum(), 0)
        self.assertLess(superficie["celdas_cubiertas"], superficie["celdas_totales"])

    def test_escalas_son_fijas_y_fluidez_no_tiene_verde(self):
        actual = mapa_geo.CONFIG_INDICADORES["currentSpeed"]
        libre = mapa_geo.CONFIG_INDICADORES["freeFlowSpeed"]
        self.assertEqual(actual["paradas"], libre["paradas"])
        self.assertEqual((actual["vmin"], actual["vmax"]), (10, 75))
        ratio = mapa_geo.CONFIG_INDICADORES["velocidad_ratio"]
        self.assertEqual(ratio["ticks"], ["0", "0,60", "0,75", "0,90", "1"])
        for _, color in ratio["paradas"]:
            rojo, verde, azul = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            self.assertGreater(rojo, verde)
            self.assertGreaterEqual(verde, azul)


if __name__ == "__main__":
    unittest.main()
