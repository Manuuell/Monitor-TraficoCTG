"""Carga del rango de fechas en la BD."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import db  # noqa: E402


class LeerRangoTest(unittest.TestCase):
    @patch("db.get_engine", return_value=object())
    @patch("db.pd.read_sql", side_effect=RuntimeError("sin conexion"))
    def test_error_de_conexion_se_propaga(self, _read_sql, _engine):
        # El dashboard distingue asi una BD caida de un periodo sin datos
        with self.assertRaises(RuntimeError):
            db.leer_rango(date(2026, 10, 27), date(2026, 10, 27))


if __name__ == "__main__":
    unittest.main()
