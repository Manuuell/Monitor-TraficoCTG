"""Pruebas de los calculos que alimentan el analisis por nodo."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

import analisis_nodo as nodo  # noqa: E402


class AnalisisNodoTest(unittest.TestCase):
    def test_consolida_duplicados_y_recalcula_el_ratio(self):
        df = pd.DataFrame({
            "consultation_time": [
                "2026-10-05 08:00:00",
                "2026-10-05 08:00:00",
                "2026-10-05 09:00:00",
                "2026-10-05 10:00:00",
            ],
            "id_nodo": ["A", "A", "B", "A"],
            "ok": [True, True, True, False],
            "currentSpeed": [30, 50, 999, 999],
            "freeFlowSpeed": [60, 100, 100, 100],
            "velocidad_ratio": [0.99, 0.99, 9.99, 9.99],
            "delay_abs_seg": [10, 20, 0, 0],
        })

        salida = nodo.preparar_mediciones(df, "A")

        self.assertEqual(len(salida), 1)
        self.assertAlmostEqual(salida.iloc[0]["currentSpeed"], 40.0)
        self.assertAlmostEqual(salida.iloc[0]["freeFlowSpeed"], 80.0)
        self.assertAlmostEqual(salida.iloc[0]["velocidad_ratio"], 0.5)
        self.assertAlmostEqual(salida.iloc[0]["delay_abs_seg"], 15.0)

    def test_filtra_fecha_tipo_de_dia_y_valores_invalidos(self):
        df = pd.DataFrame({
            "consultation_time": [
                "2026-10-05 08:00:00",  # lunes valido
                "2026-10-10 08:00:00",  # sabado
                "2026-10-05 09:00:00",  # flujo libre invalido
                "2026-10-06 08:00:00",  # fuera del rango
            ],
            "id_nodo": ["A"] * 4,
            "ok": [True] * 4,
            "currentSpeed": [30, 40, 20, 50],
            "freeFlowSpeed": [60, 80, 0, 100],
        })

        salida = nodo.preparar_mediciones(
            df,
            "A",
            fecha_ini=date(2026, 10, 5),
            fecha_fin=date(2026, 10, 5),
            tipo_dia="Días laborables (L–V)",
        )

        self.assertEqual(salida["currentSpeed"].tolist(), [30])

    def test_series_respetan_el_peso_de_cada_ejecucion(self):
        ejecuciones = pd.DataFrame({
            "consultation_time": pd.to_datetime([
                "2026-10-05 08:00:00",
                "2026-10-05 08:30:00",
                "2026-10-06 09:00:00",
            ]),
            "currentSpeed": [30.0, 50.0, 90.0],
            "freeFlowSpeed": [60.0, 100.0, 100.0],
            "velocidad_ratio": [0.5, 0.5, 0.9],
            "delay_abs_seg": [10.0, 20.0, 5.0],
        })

        diaria = nodo.serie_diaria(ejecuciones)
        hora = nodo.resumen_por_hora(ejecuciones)

        self.assertEqual(diaria["ejecuciones"].tolist(), [2, 1])
        self.assertAlmostEqual(diaria.iloc[0]["ratio_promedio"], 0.5)
        self.assertEqual(hora["hora"].tolist(), [8, 9])
        self.assertEqual(hora["ejecuciones"].tolist(), [2, 1])

    def test_distribucion_usa_los_umbrales_exactos_del_dashboard(self):
        ratios = [0.9001, 0.90, 0.7501, 0.75, 0.6001, 0.60]
        ejecuciones = pd.DataFrame({"velocidad_ratio": ratios})

        salida = nodo.distribucion_congestion(ejecuciones)

        self.assertEqual(salida["categoria"].tolist(), nodo.CATEGORIAS)
        self.assertEqual(salida["mediciones"].tolist(), [1, 2, 2, 1])
        self.assertAlmostEqual(salida["porcentaje"].sum(), 100.0)


if __name__ == "__main__":
    unittest.main()
