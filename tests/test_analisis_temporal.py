"""Pruebas de las agregaciones que alimentan el analisis temporal."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import analisis_temporal as temporal  # noqa: E402


class AnalisisTemporalTest(unittest.TestCase):
    def test_filtra_estado_fecha_hora_dia_y_nodo(self):
        df = pd.DataFrame({
            "consultation_time": [
                "2026-10-05 08:00:00",  # lunes, valida
                "2026-10-05 18:00:00",  # fuera de hora
                "2026-10-06 08:00:00",  # martes
                "2026-10-05 08:00:00",  # otro nodo
                "2026-10-05 08:00:00",  # fallo
            ],
            "id_nodo": ["A", "A", "A", "B", "A"],
            "ok": [True, True, True, True, False],
            "currentSpeed": [20, 30, 40, 50, 999],
        })

        salida = temporal.filtrar_mediciones(
            df,
            "currentSpeed",
            fecha_ini=date(2026, 10, 5),
            fecha_fin=date(2026, 10, 5),
            desde="07:00",
            hasta="09:00",
            tipo_dia="Días laborables (L–V)",
            ids=("A",),
        )

        self.assertEqual(salida["currentSpeed"].tolist(), [20])

    def test_ejecuciones_tienen_igual_peso_y_duplicados_no_sesgan(self):
        df = pd.DataFrame({
            "consultation_time": pd.to_datetime([
                "2026-10-05 08:00:00",
                "2026-10-05 08:00:00",
                "2026-10-05 08:00:00",
                "2026-10-06 08:00:00",
                "2026-10-06 08:00:00",
            ]),
            "id_nodo": ["A", "A", "B", "A", "B"],
            "currentSpeed": [10, 30, 40, 50, 70],
        })

        serie = temporal.serie_por_ejecucion(df, "currentSpeed")
        corrida = temporal.resumen_por_corrida(serie).iloc[0]

        # Ejecucion 1: promedio de A=(10+30)/2 y B=40 -> 30.
        # Ejecucion 2: promedio de A=50 y B=70 -> 60. Corrida de las 08:00 -> 45.
        self.assertEqual(serie["valor"].tolist(), [30.0, 60.0])
        self.assertEqual(corrida["corrida"], "08:00")
        self.assertAlmostEqual(corrida["promedio"], 45.0)
        self.assertEqual(corrida["ejecuciones"], 2)

    def test_corridas_de_media_hora_aparte_y_en_orden_de_dia_operativo(self):
        serie = pd.DataFrame({
            "consultation_time": pd.to_datetime([
                "2026-10-06 00:00:03", "2026-10-05 05:30:02", "2026-10-05 05:00:01",
            ]),
            "valor": [30.0, 20.0, 40.0],
            "n_nodos": [113, 113, 113],
        })

        resumen = temporal.resumen_por_corrida(serie)

        self.assertEqual(resumen["corrida"].tolist(), ["05:00", "05:30", "00:00"])
        self.assertEqual(resumen["promedio"].tolist(), [40.0, 20.0, 30.0])

    def test_tendencia_mensual_da_el_mismo_peso_a_cada_dia(self):
        serie = pd.DataFrame({
            "consultation_time": pd.to_datetime([
                "2026-01-01 08:00:00",
                "2026-01-01 09:00:00",
                "2026-01-02 08:00:00",
            ]),
            "valor": [10.0, 20.0, 90.0],
            "n_nodos": [100, 100, 100],
        })

        mes = temporal.tendencia_mensual(serie).iloc[0]

        # Dia 1 = 15; dia 2 = 90; promedio mensual diario = 52.5.
        self.assertAlmostEqual(mes["promedio"], 52.5)
        self.assertEqual(mes["dias"], 2)
        self.assertEqual(mes["ejecuciones"], 3)

    def test_mapa_calor_conserva_celdas_sin_datos(self):
        serie = pd.DataFrame({
            "consultation_time": pd.to_datetime(["2026-10-05 08:00:00"]),
            "valor": [0.75],
            "n_nodos": [113],
        })

        valores, conteos = temporal.mapa_calor(serie)

        self.assertAlmostEqual(valores.loc[0, "08:00"], 0.75)
        self.assertEqual(conteos.loc[0, "08:00"], 1)
        self.assertTrue(pd.isna(valores.loc[1, "08:00"]))
        # Columnas = corridas del cron, de 04:00 a 00:00
        self.assertEqual(list(valores.columns)[0], "04:00")
        self.assertEqual(list(valores.columns)[-1], "00:00")

    def test_solo_quedan_las_tres_metricas_pedidas(self):
        self.assertEqual(
            list(temporal.METRICAS),
            ["Velocidad de circulación (km/h)", "Velocidad de flujo libre (km/h)", "Índice de fluidez (0–1)"],
        )

    def test_escalas_visuales_avanzan_de_oscuro_a_claro(self):
        self.assertEqual(temporal.ESCALA_VELOCIDAD, "Blues_r")
        posiciones = [posicion for posicion, _ in temporal.ESCALA_FLUIDEZ]
        self.assertEqual(posiciones, sorted(posiciones))
        self.assertEqual(posiciones[0], 0)
        self.assertEqual(posiciones[-1], 1)
        self.assertTrue({0.60, 0.75, 0.90}.issubset(posiciones))
        self.assertEqual(temporal.ESCALA_FLUIDEZ[0][1], "#7F1D1D")
        self.assertEqual(temporal.ESCALA_FLUIDEZ[-1][1], "#FBBF24")
        luminosidades = []
        for _, hexadecimal in temporal.ESCALA_FLUIDEZ:
            rojo, verde, azul = (
                int(hexadecimal[inicio:inicio + 2], 16) for inicio in (1, 3, 5)
            )
            self.assertGreater(rojo, verde)
            self.assertGreaterEqual(verde, azul)
            luminosidades.append(0.2126 * rojo + 0.7152 * verde + 0.0722 * azul)
        self.assertTrue(all(
            anterior < siguiente
            for anterior, siguiente in zip(luminosidades, luminosidades[1:])
        ))


if __name__ == "__main__":
    unittest.main()
