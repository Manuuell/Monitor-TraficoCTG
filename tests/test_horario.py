"""Horario operativo: corridas del cron, franjas, filtro por rango y escala."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import horario  # noqa: E402
import mapa_nodos  # noqa: E402


class HorarioTest(unittest.TestCase):
    def test_corridas_van_de_las_4_a_medianoche_sin_la_franja_vacia(self):
        self.assertEqual(len(horario.CORRIDAS), 28)
        self.assertEqual(horario.DIA_COMPLETO, ("04:00", "00:00"))
        self.assertIn("05:30", horario.CORRIDAS)
        self.assertLess(horario.CORRIDAS.index("05:00"), horario.CORRIDAS.index("05:30"))
        self.assertEqual(horario.HORAS, list(range(4, 24)) + [0])

    def test_franjas_cubren_cada_corrida_una_sola_vez(self):
        cubiertas = []
        for nombre, rango in mapa_nodos.FRANJAS.items():
            if nombre in (mapa_nodos.TODO_EL_DIA, mapa_nodos.PERSONALIZADO):
                continue
            # La barra (select_slider) falla si la franja fija un valor fuera de sus opciones
            self.assertIn(rango[0], horario.CORRIDAS, nombre)
            self.assertIn(rango[1], horario.CORRIDAS, nombre)
            ini, fin = (horario.CORRIDAS.index(c) for c in rango)
            cubiertas += horario.CORRIDAS[ini:fin + 1]
        self.assertEqual(cubiertas, horario.CORRIDAS)

    def test_horas_pico_son_las_de_las_corridas_de_media_hora(self):
        self.assertEqual(mapa_nodos.FRANJAS["Hora pico AM (5:30–7:30)"], ("05:30", "07:30"))
        self.assertEqual(mapa_nodos.FRANJAS["Medio día (12:00–13:30)"], ("12:00", "13:30"))

    def test_rango_cruza_la_medianoche_y_deja_fuera_la_madrugada_vacia(self):
        ts = pd.to_datetime(pd.Series([
            "2026-10-05 18:30:02",  # antes de la Noche
            "2026-10-05 19:00:01",
            "2026-10-05 23:00:02",
            "2026-10-06 00:00:03",  # ultima corrida del dia
            "2026-10-06 02:00:00",  # corrida manual fuera del cron
            "2026-10-06 04:00:01",
        ]))
        noche = horario.en_horario(ts, "19:00", "00:00")
        self.assertEqual(noche.tolist(), [False, True, True, True, False, False])
        completo = horario.en_horario(ts, *horario.DIA_COMPLETO)
        self.assertEqual(completo.tolist(), [True, True, True, True, False, True])
        self.assertTrue(horario.en_horario(ts, None, None).all())

    def test_cada_medicion_cae_en_su_corrida_de_media_hora(self):
        ts = pd.to_datetime(pd.Series(["2026-10-05 05:30:02", "2026-10-05 05:31:10",
                                        "2026-10-05 06:00:01", "2026-10-06 00:00:03"]))
        self.assertEqual(horario.corrida_de(ts).tolist(), ["05:30", "05:30", "06:00", "00:00"])
        # 05:00 y 05:30 son corridas distintas
        self.assertFalse(horario.en_horario(ts, "05:00", "05:00").iloc[0])

    def test_escala_marca_cada_corrida_y_numera_cada_4_horas(self):
        escala = mapa_nodos._escala_horas()
        self.assertEqual(escala.count('class="marca'), len(horario.CORRIDAS))
        numeros = [n.split("<")[0].split(">")[-1] for n in escala.split('class="num')[1:]]
        self.assertEqual(numeros, ["4", "8", "12", "16", "20", "0"])
        # Los extremos se alinean hacia dentro para no salirse de la tarjeta
        self.assertIn('class="num inicio"', escala)
        self.assertIn('class="num fin"', escala)


if __name__ == "__main__":
    unittest.main()
