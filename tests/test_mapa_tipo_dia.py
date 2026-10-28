"""Filtros de tipo de dia compartidos por los dos mapas."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import db  # noqa: E402
import mapa_nodos  # noqa: E402


class MapaTipoDiaTest(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "consultation_time": pd.to_datetime([
                "2026-10-05 08:00:00",  # lunes
                "2026-10-09 08:00:00",  # viernes
                "2026-10-10 08:00:00",  # sabado
                "2026-10-11 08:00:00",  # domingo
            ]),
            "id_nodo": ["A"] * 4,
            "ok": [True] * 4,
            "currentSpeed": [10.0, 20.0, 30.0, 40.0],
            "freeFlowSpeed": [50.0] * 4,
            "velocidad_ratio": [0.2, 0.4, 0.6, 0.8],
        })

    def test_selector_incluye_laborables_y_fin_de_semana(self):
        self.assertEqual(
            mapa_nodos.TIPOS_DIA[:4],
            ["Todos", "Días laborables (L–V)", "Fin de semana", "Quincena"],
        )

    def test_respaldo_pandas_filtra_laborables(self):
        salida = mapa_nodos.promedios_por_nodo_df(self.df, laborables=True)
        self.assertEqual(int(salida.iloc[0]["n"]), 2)
        self.assertAlmostEqual(float(salida.iloc[0]["vel_actual"]), 15.0)

    def test_respaldo_pandas_filtra_fin_de_semana(self):
        salida = mapa_nodos.promedios_por_nodo_df(self.df, fin_semana=True)
        self.assertEqual(int(salida.iloc[0]["n"]), 2)
        self.assertAlmostEqual(float(salida.iloc[0]["vel_actual"]), 35.0)

    @patch("db.get_engine", return_value=object())
    @patch("db.pd.read_sql", return_value=pd.DataFrame())
    def test_postgresql_usa_isodow_para_ambos_grupos(self, read_sql, _engine):
        db.promedios_por_nodo(laborables=True)
        consulta_laborables = str(read_sql.call_args.args[0])
        self.assertIn("EXTRACT(ISODOW", consulta_laborables)
        self.assertIn("BETWEEN 1 AND 5", consulta_laborables)

        db.promedios_por_nodo(fin_semana=True)
        consulta_fin_semana = str(read_sql.call_args.args[0])
        self.assertIn("IN (6, 7)", consulta_fin_semana)


if __name__ == "__main__":
    unittest.main()
