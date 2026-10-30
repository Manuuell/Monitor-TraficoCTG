"""Random Forest y seleccion exacta de corridas para Simulaciones."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

import prediccion_trafico  # noqa: E402


class PrediccionTraficoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogo = pd.DataFrame([
            {"id_nodo": "A", "lat": 10.40, "lon": -75.50},
            {"id_nodo": "B", "lat": 10.41, "lon": -75.49},
            {"id_nodo": "C", "lat": 10.42, "lon": -75.48},
        ])
        filas = []
        corridas = pd.date_range("2026-09-20 04:00", periods=280, freq="90min")
        for instante in corridas:
            for indice, nodo in enumerate("ABC"):
                libre = 50 + indice * 5
                reduccion = 12 if instante.hour in (6, 7, 17, 18) else 3
                filas.append({
                    "id_nodo": nodo,
                    "consultation_time": instante,
                    "currentSpeed": libre - reduccion,
                    "freeFlowSpeed": libre,
                    "lat": 10.40 + indice * 0.01,
                    "lon": -75.50 + indice * 0.01,
                    "ok": True,
                })
        cls.historico = pd.DataFrame(filas)

    def test_corrida_real_usa_un_dia_y_hora_exactos(self):
        fecha = self.historico.iloc[0]["consultation_time"].date()
        resumen = prediccion_trafico.resumir_corrida_real(
            self.historico, fecha, "04:00")
        self.assertEqual(set(resumen["id_nodo"]), {"A", "B", "C"})
        self.assertFalse(resumen["predicho"].any())
        self.assertTrue((resumen["ratio"] > 0).all())
        vacio = prediccion_trafico.resumir_corrida_real(
            self.historico, date(2030, 1, 1), "04:00")
        self.assertTrue(vacio.empty)

    def test_random_forest_predice_todos_los_nodos(self):
        modelo = prediccion_trafico.entrenar_random_forest(
            self.historico, self.catalogo)
        prediccion = prediccion_trafico.predecir_velocidades(
            modelo, self.catalogo, date(2027, 1, 15), "17:00")
        self.assertEqual(list(prediccion["id_nodo"]), ["A", "B", "C"])
        self.assertTrue(prediccion["predicho"].all())
        self.assertTrue((prediccion["vel_actual"] > 0).all())
        self.assertTrue((prediccion["ratio"] > 0).all())
        self.assertGreaterEqual(modelo["filas"], 500)


if __name__ == "__main__":
    unittest.main()
