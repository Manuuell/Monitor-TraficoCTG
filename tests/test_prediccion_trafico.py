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
        corridas = [
            dia + pd.Timedelta(hours=hora)
            for dia in pd.date_range("2026-09-20", periods=60, freq="D")
            for hora in (4, 7, 17, 23)
        ]
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
        esperadas = pd.Series([38.0, 43.0, 48.0])
        self.assertLess((prediccion["vel_actual"].reset_index(drop=True) - esperadas).abs().mean(), 3)

    def test_random_forest_usa_los_hiperparametros_configurados(self):
        modelo = prediccion_trafico.entrenar_random_forest(
            self.historico, self.catalogo)
        bosque = modelo["pipeline"].named_steps["modelo"]
        self.assertEqual(bosque.n_estimators, 160)
        self.assertEqual(bosque.max_depth, 16)
        self.assertEqual(bosque.min_samples_split, 2)
        self.assertEqual(bosque.min_samples_leaf, 20)
        self.assertEqual(bosque.max_features, 0.6)
        self.assertTrue(bosque.bootstrap)
        self.assertEqual(bosque.random_state, 42)
        self.assertEqual(bosque.n_jobs, -1)

    def test_mezcla_75_random_forest_y_25_promedio(self):
        prediccion = prediccion_trafico.combinar_predicciones([40.0], [60.0])
        self.assertAlmostEqual(float(prediccion[0]), 45.0)
        self.assertEqual(prediccion_trafico.PESO_RANDOM_FOREST, 0.75)
        self.assertEqual(prediccion_trafico.PESO_PROMEDIO_HISTORICO, 0.25)

    def test_entrenamiento_no_recorta_las_mediciones_de_tres_meses(self):
        repeticiones = 201
        historico_amplio = pd.concat(
            [self.historico] * repeticiones, ignore_index=True)
        X, y, _ = prediccion_trafico.preparar_entrenamiento(
            historico_amplio, self.catalogo)
        self.assertEqual(len(X), len(historico_amplio))
        self.assertEqual(len(y), len(historico_amplio))
        self.assertGreater(len(X), 60_000)

    def test_ventana_no_usa_datos_posteriores_a_la_prediccion(self):
        fechas = pd.date_range("2026-01-01", "2026-07-01", freq="12h")
        historico = pd.DataFrame({
            "consultation_time": fechas,
            "marca": range(len(fechas)),
        })
        ventana, periodo = prediccion_trafico.seleccionar_ventana_entrenamiento(
            historico, date(2026, 4, 15), "12:00")
        objetivo = pd.Timestamp("2026-04-15 12:00")
        self.assertTrue((ventana["consultation_time"] < objetivo).all())
        self.assertGreaterEqual(
            ventana["consultation_time"].min(), objetivo - pd.DateOffset(months=3))
        self.assertFalse(periodo["usa_ultimos_disponibles"])

    def test_fecha_futura_usa_los_tres_meses_reales_mas_recientes(self):
        fechas = pd.date_range("2026-01-01", "2026-07-01", freq="12h")
        historico = pd.DataFrame({"consultation_time": fechas})
        ventana, periodo = prediccion_trafico.seleccionar_ventana_entrenamiento(
            historico, date(2027, 1, 1), "17:00")
        ultima = fechas.max()
        self.assertEqual(ventana["consultation_time"].max(), ultima)
        self.assertGreaterEqual(
            ventana["consultation_time"].min(), ultima - pd.DateOffset(months=3))
        self.assertTrue(periodo["usa_ultimos_disponibles"])


if __name__ == "__main__":
    unittest.main()
