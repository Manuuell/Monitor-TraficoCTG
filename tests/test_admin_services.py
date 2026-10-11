"""Pruebas de los calculos del monitor administrativo."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))

import admin_services as servicios  # noqa: E402


class AdminServicesTests(unittest.TestCase):
    def setUp(self) -> None:
        ahora = pd.Timestamp.now().floor("s")
        self.ahora = ahora
        self.ejecuciones = pd.DataFrame([
            {
                "timestamp": ahora - pd.Timedelta(hours=1),
                "vps_id": "1",
                "total_nodos": 113,
                "consultas_ok": 113,
                "consultas_error": 0,
                "estado": "OK",
                "error": None,
            },
            {
                "timestamp": ahora - pd.Timedelta(hours=2),
                "vps_id": "1",
                "total_nodos": 113,
                "consultas_ok": 110,
                "consultas_error": 3,
                "estado": "PARCIAL",
                "error": "3 nodos sin respuesta",
            },
            {
                "timestamp": ahora - pd.Timedelta(hours=3),
                "vps_id": "2",
                "total_nodos": 113,
                "consultas_ok": 0,
                "consultas_error": 113,
                "estado": "ERROR",
                "error": "TomTom no disponible",
            },
        ])

    def test_reconstruye_ejecuciones_de_ambos_vps(self) -> None:
        instante_1 = self.ahora - pd.Timedelta(minutes=10)
        instante_2 = self.ahora - pd.Timedelta(minutes=5)
        mediciones = pd.DataFrame([
            {"consultation_time": instante_1, "vps_id": "1", "ok": True},
            {"consultation_time": instante_1, "vps_id": "1", "ok": False,
             "error_msg": "timeout"},
            {"consultation_time": instante_2, "vps_id": "2", "ok": False,
             "error_msg": "sin cuota"},
            {"consultation_time": instante_2, "vps_id": "2", "ok": False,
             "error_msg": "sin cuota"},
        ])

        resultado = servicios.ejecuciones_desde_mediciones(mediciones)

        self.assertEqual(set(resultado["vps_id"]), {"1", "2"})
        por_vps = resultado.set_index("vps_id")
        self.assertEqual(por_vps.loc["1", "estado"], "PARCIAL")
        self.assertEqual(por_vps.loc["1", "consultas_error"], 1)
        self.assertEqual(por_vps.loc["2", "estado"], "ERROR")
        self.assertEqual(por_vps.loc["2", "consultas_ok"], 0)

    def test_error_explicito_del_proceso_no_se_oculta(self) -> None:
        entrada = pd.DataFrame([{
            "timestamp": self.ahora,
            "vps_id": "1",
            "total_nodos": 113,
            "consultas_ok": 113,
            "consultas_error": 0,
            "estado": "ERROR",
            "error": "fallo al guardar",
        }])

        resultado = servicios.normalizar_ejecuciones(entrada)

        self.assertEqual(resultado.loc[0, "estado"], "ERROR")
        self.assertEqual(len(servicios.errores_recientes(resultado)), 1)

    def test_combinar_prefiere_detalle_del_log_local(self) -> None:
        instante = self.ahora - pd.Timedelta(minutes=20)
        mediciones = pd.DataFrame([
            {"consultation_time": instante, "vps_id": "1", "ok": True},
        ])
        logs = pd.DataFrame([{
            "timestamp": instante,
            "vps_id": "1",
            "total_nodos": 1,
            "consultas_ok": 1,
            "consultas_error": 0,
            "estado": "ERROR",
            "error": "fallo de subida",
        }])

        resultado = servicios.combinar_ejecuciones(logs, mediciones)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado.iloc[0]["estado"], "ERROR")
        self.assertEqual(resultado.iloc[0]["error"], "fallo de subida")

    def test_ultimas_ejecuciones_limita_por_vps_y_ordena(self) -> None:
        filas = []
        for indice in range(25):
            filas.append({
                "timestamp": self.ahora - pd.Timedelta(minutes=indice),
                "vps_id": "1",
                "total_nodos": 1,
                "consultas_ok": 1,
                "consultas_error": 0,
                "estado": "OK",
                "error": None,
            })
        filas.append({**filas[0], "vps_id": "2"})

        resultado = servicios.ultimas_ejecuciones(pd.DataFrame(filas), "1", 20)

        self.assertEqual(len(resultado), 20)
        self.assertTrue((resultado["vps_id"] == "1").all())
        self.assertTrue(resultado["timestamp"].is_monotonic_decreasing)

    def test_ejecuciones_por_hora_cuenta_corridas_no_nodos(self) -> None:
        resultado = servicios.ejecuciones_por_hora(self.ejecuciones, 7)

        self.assertEqual(int(resultado["total"].sum()), 3)
        self.assertEqual(int(resultado["completas"].sum()), 1)
        self.assertEqual(int(resultado["parciales"].sum()), 1)
        self.assertEqual(int(resultado["fallidas"].sum()), 1)
        self.assertTrue(resultado["hora"].str.match(r"^\d{2}:00$").all())

    def test_errores_recientes_incluye_parciales_y_fallidas(self) -> None:
        antigua = self.ejecuciones.iloc[[2]].copy()
        antigua["timestamp"] = self.ahora - pd.Timedelta(days=8)
        datos = pd.concat([self.ejecuciones, antigua], ignore_index=True)

        resultado = servicios.errores_recientes(datos, 7)

        self.assertEqual(set(resultado["estado"]), {"PARCIAL", "ERROR"})
        self.assertEqual(len(resultado), 2)
        self.assertTrue((resultado["consultas_error"] > 0).all())

    def test_resumen_vacio_conserva_fechas_validas(self) -> None:
        vacio = servicios.ejecuciones_vacias()

        resumen = servicios.resumen_operativo_ejecuciones(vacio)

        self.assertEqual(resumen["ejecuciones"], 0)
        self.assertEqual(resumen["vps1"]["llamadas"], 0)
        self.assertTrue(pd.isna(resumen["ultima"]))
        self.assertTrue(servicios.ejecuciones_por_hora(vacio).empty)
        self.assertTrue(servicios.errores_recientes(vacio).empty)

    def test_estado_google_persistente_se_lee_sin_consulta_externa(self) -> None:
        google = {"ok": True, "estado": "Activo", "detalle": "Disponible"}
        sheets = {"ok": True, "partes": [{"parte": 1}], "errores": []}
        instante = pd.Timestamp("2026-10-11 06:15:00").to_pydatetime()

        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "estado_google.json"
            servicios.guardar_estado_google(google, sheets, ruta, instante)
            resultado = servicios.cargar_estado_google(ruta)

            self.assertEqual(resultado["actualizado"], "2026-10-11T06:15:00")
            self.assertEqual(resultado["google"]["estado"], "Activo")
            self.assertEqual(resultado["sheets"]["partes"][0]["parte"], 1)
            self.assertEqual(ruta.stat().st_mode & 0o777, 0o600)

    def test_estado_google_invalido_vuelve_a_pendiente(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "estado_google.json"
            ruta.write_text("{incompleto", encoding="utf-8")

            resultado = servicios.cargar_estado_google(ruta)

            self.assertIsNone(resultado["google"]["ok"])
            self.assertEqual(resultado["google"]["estado"], "Pendiente")


if __name__ == "__main__":
    unittest.main()
