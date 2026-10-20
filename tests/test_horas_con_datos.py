"""Horas que el dashboard muestra en ejes y en la barra de horas."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import config  # noqa: E402
import mapa_nodos  # noqa: E402


class HorasConDatosTest(unittest.TestCase):
    def test_salen_del_horario_del_cron_sin_la_franja_vacia(self):
        self.assertEqual(config.HORAS_CON_DATOS, [0] + list(range(4, 24)))

    def test_cada_franja_cae_en_horas_que_ofrece_la_barra(self):
        # La barra (select_slider) falla si la franja fija un valor fuera de sus opciones
        for nombre, rango in mapa_nodos.FRANJAS.items():
            if rango is None:
                continue
            with self.subTest(franja=nombre):
                self.assertIn(rango[0], config.HORAS_CON_DATOS)
                self.assertIn(rango[1], config.HORAS_CON_DATOS)

    def test_escala_marca_una_posicion_por_hora_con_datos(self):
        escala = mapa_nodos._escala_horas()
        self.assertEqual(escala.count('class="marca'), len(config.HORAS_CON_DATOS))
        self.assertNotIn(">2<", escala)


if __name__ == "__main__":
    unittest.main()
