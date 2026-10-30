"""Filtros del mapa que siguen la ultima corrida y carga del rango en la BD."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit import __version__ as st_version
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import db  # noqa: E402


def _pagina_mapa():
    import pandas as pd
    import streamlit as st

    import mapa_nodos

    ultima = pd.Timestamp(st.session_state.get("prueba_ultima", "2026-10-27 07:02:00"))
    fechas = (pd.Timestamp("2026-10-01").date(), pd.Timestamp("2026-10-27").date())
    st.session_state["prueba_filtros"] = mapa_nodos.panel_filtros(
        "mapa", {"A": "Nodo A"}, fechas, ultima
    )


def _pagina_selector_horas():
    import streamlit as st

    import mapa_nodos

    st.session_state.setdefault("prueba_horas", ("05:30", "00:00"))
    mapa_nodos.selector_horas(
        "prueba_horas", lambda: None, ["05:30", "07:00", "00:00"]
    )


class UltimaCorridaTest(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_function(_pagina_mapa)
        self.app.run()

    def test_arranca_en_vivo_con_la_ultima_corrida(self):
        self.assertEqual(self.app.session_state["mapa_franja"], "Última ejecución (7:00)")
        self.assertEqual(tuple(self.app.session_state["mapa_horas"]), ("07:00", "07:00"))
        self.assertTrue(self.app.session_state["prueba_filtros"]["en_vivo"])
        self.assertEqual(
            self.app.selectbox(key="mapa_horas_inicio").label, "Hora inicial"
        )
        self.assertEqual(
            self.app.selectbox(key="mapa_horas_fin").label, "Hora final"
        )

    def test_corrida_nueva_con_la_pagina_abierta_sigue_en_vivo(self):
        self.app.session_state["prueba_ultima"] = "2026-10-27 07:31:00"
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state["mapa_franja"], "Última ejecución (7:30)")
        self.assertEqual(tuple(self.app.session_state["mapa_horas"]), ("07:30", "07:30"))
        self.assertTrue(self.app.session_state["prueba_filtros"]["en_vivo"])

    # Antes de 1.54 cambiar las opciones de un selectbox lo reinicia aunque
    # la opcion elegida siga en la lista; produccion usa 1.58.
    @unittest.skipIf(
        tuple(int(p) for p in st_version.split(".")[:2]) < (1, 54),
        "requiere streamlit >= 1.54 (requirements.txt)",
    )
    def test_corrida_nueva_respeta_otra_franja_elegida(self):
        self.app.selectbox(key="mapa_franja").select("Hora pico AM (5:30–7:30)").run()
        self.app.session_state["prueba_ultima"] = "2026-10-27 07:31:00"
        self.app.run()
        self.assertEqual(self.app.session_state["mapa_franja"], "Hora pico AM (5:30–7:30)")
        self.assertEqual(tuple(self.app.session_state["mapa_horas"]), ("05:30", "07:30"))


class LeerRangoTest(unittest.TestCase):
    @patch("db.get_engine", return_value=object())
    @patch("db.pd.read_sql", side_effect=RuntimeError("sin conexion"))
    def test_error_de_conexion_se_propaga(self, _read_sql, _engine):
        # El dashboard distingue asi una BD caida de un periodo sin datos
        with self.assertRaises(RuntimeError):
            db.leer_rango(date(2026, 10, 27), date(2026, 10, 27))

    @patch("db.get_engine", return_value=object())
    @patch("db.pd.read_sql", return_value=pd.DataFrame({
        "corrida": ["00:00", "05:30", "04:00"],
    }))
    def test_corridas_sql_quedan_en_orden_operativo(self, read_sql, _engine):
        corridas = db.leer_corridas_disponibles(
            date(2026, 10, 27), date(2026, 10, 27)
        )
        self.assertEqual(corridas, ["04:00", "05:30", "00:00"])
        self.assertIn("SELECT DISTINCT", str(read_sql.call_args.args[0]))


class SelectorHorasTest(unittest.TestCase):
    def test_hora_final_no_ofrece_horas_anteriores(self):
        app = AppTest.from_function(_pagina_selector_horas)
        app.run()
        self.assertEqual(
            app.selectbox(key="prueba_horas_inicio").options,
            ["05:30", "07:00", "00:00"],
        )
        app.selectbox(key="prueba_horas_inicio").select("07:00").run()
        self.assertEqual(
            app.selectbox(key="prueba_horas_fin").options,
            ["07:00", "00:00"],
        )
        self.assertEqual(
            tuple(app.session_state["prueba_horas"]), ("07:00", "00:00")
        )


if __name__ == "__main__":
    unittest.main()
