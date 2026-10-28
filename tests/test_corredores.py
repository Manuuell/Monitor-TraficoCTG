"""Corredores de la hoja CORREDORES: lectura, tramos sobre la red y resumen."""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import config  # noqa: E402
import capturar_red  # noqa: E402
import descargar_trafico as dt  # noqa: E402
import red_nodos  # noqa: E402


class RutaTomTomTest(unittest.TestCase):
    def test_modo_pedestrian_y_ruta_mas_corta(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.return_value = {"routes": [{
            "summary": {"lengthInMeters": 321},
            "legs": [{"points": [
                {"latitude": 10.0, "longitude": -75.0},
                {"latitude": 10.001, "longitude": -75.001},
            ]}],
        }]}
        nodos = pd.DataFrame([
            {"lat": 10.0, "lon": -75.0},
            {"lat": 10.001, "lon": -75.001},
        ])
        with mock.patch("capturar_red.requests.get", return_value=respuesta) as pedir:
            distancia, trazado = capturar_red.ruta_tomtom(
                nodos, 0, 1, capturar_red.Llaves(["llave-prueba"]),
                con_trazado=True, tipo="shortest", modo="pedestrian",
            )
        params = pedir.call_args.kwargs["params"]
        self.assertEqual(distancia, 321)
        self.assertEqual(trazado, [[10.0, -75.0], [10.001, -75.001]])
        self.assertEqual(params["travelMode"], "pedestrian")
        self.assertEqual(params["routeType"], "shortest")
        self.assertEqual(params["traffic"], "false")


class LeerCorredoresTest(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.excel = Path(carpeta.name) / "nodos.xlsx"
        filas = [
            ("AV. UNO", 2, "JA_FRANCISCO"),     # el catalogo lo escribe con espacio
            ("AV. UNO", 1, "PUE_CANA"),
            ("AV. UNO", 3, "NO_EXISTE"),
            ("AV. UNO", 4, "TUN_CRE"),
            ("AV. DOS", 1, "TUN_CRE"),
            ("AV. DOS", 2, "TUN_CRE"),          # repetido seguido: se deja uno
            ("AV. DOS", 3, "dis naval 2"),
        ]
        with pd.ExcelWriter(self.excel) as escritor:
            pd.DataFrame(filas, columns=["Corredor", "Orden", "id_nodo"]).to_excel(
                escritor, sheet_name="CORREDORES", index=False)
        self.catalogo = ["PUE_CANA", "JA _FRANCISCO", "TUN_CRE", "DIS_NAVAL 2"]

    def test_orden_de_la_hoja_e_ids_del_catalogo(self):
        corredores, faltantes = dt.leer_corredores(self.excel, self.catalogo)
        self.assertEqual(list(corredores), ["AV. UNO", "AV. DOS"])
        self.assertEqual(corredores["AV. UNO"], ["PUE_CANA", "JA _FRANCISCO", "TUN_CRE"])
        self.assertEqual(corredores["AV. DOS"], ["TUN_CRE", "DIS_NAVAL 2"])
        self.assertEqual(faltantes, ["NO_EXISTE"])

    def test_pares_seguidos_sin_sentido(self):
        corredores, _ = dt.leer_corredores(self.excel, self.catalogo)
        self.assertEqual(dt.pares_corredores(corredores), [
            ("DIS_NAVAL 2", "TUN_CRE"), ("JA _FRANCISCO", "PUE_CANA"), ("JA _FRANCISCO", "TUN_CRE"),
        ])

    def test_excel_sin_la_hoja(self):
        otro = self.excel.with_name("sin_hoja.xlsx")
        pd.DataFrame({"x": [1]}).to_excel(otro, sheet_name="NODOS", index=False)
        self.assertEqual(dt.leer_corredores(otro, self.catalogo), ({}, []))


class ArmarCorredoresTest(unittest.TestCase):
    def setUp(self):
        self.red = {"conexiones": [
            {"a": "A", "b": "B", "d_ab_m": 1000, "d_ba_m": 1200, "path": [[0, 0], [0, 1]],
             "path_ba": [[0, 1], [0, 0]]},
            {"a": "C", "b": "B", "d_ab_m": 500, "d_ba_m": 600, "path": [[1, 1], [0, 1]],
             "path_ba": [[0, 1], [1, 1]]},
        ]}

    def test_cada_tramo_en_su_sentido_mas_corto_y_color_fijo(self):
        uno, dos = red_nodos.armar_corredores({"UNO": ["A", "B", "C"], "DOS": ["C", "D"]}, self.red)
        # A->B: la ida (1000) es mas corta; B->C: C->B (500) es mas corta que B->C (600)
        self.assertEqual([s for _, s in uno["tramos"]], [1, 1])
        self.assertEqual(uno["sin_conexion"], 0)
        self.assertEqual(dos["sin_conexion"], 1)                       # C-D no es conexion
        self.assertEqual((uno["color"], dos["color"]), tuple(red_nodos.PALETA_CORREDORES[:2]))

    def test_el_orden_del_corredor_no_cambia_el_trazado(self):
        ida = red_nodos.armar_corredores({"UNO": ["A", "B", "C"]}, self.red)[0]
        vuelta = red_nodos.armar_corredores({"UNO": ["C", "B", "A"]}, self.red)[0]
        self.assertEqual({(c["a"], c["b"], s) for c, s in ida["tramos"]},
                         {(c["a"], c["b"], s) for c, s in vuelta["tramos"]})

    def test_resumen_con_la_distancia_mas_corta_de_cada_tramo(self):
        uno = red_nodos.armar_corredores({"UNO": ["A", "B", "C"]}, self.red)[0]
        prom = {n: {"vel_actual": 36.0, "vel_libre": 72.0, "ratio": r}
                for n, r in (("A", 0.5), ("B", 0.5), ("C", 0.8))}
        r = red_nodos.resumen_corredor(uno, prom)
        self.assertEqual(r["dist_m"], 1000 + 500)
        self.assertAlmostEqual(r["tiempo_s"], 1500 / 10)               # 36 km/h = 10 m/s
        self.assertAlmostEqual(r["tiempo_libre_s"], 1500 / 20)
        self.assertAlmostEqual(r["ratio"], 0.6)

    def test_resumen_sin_datos_o_sin_conexion_queda_vacio(self):
        uno, dos = red_nodos.armar_corredores({"UNO": ["A", "B"], "DOS": ["C", "D"]}, self.red)
        self.assertTrue(math.isnan(red_nodos.resumen_corredor(uno, {})["tiempo_s"]))
        prom = {n: {"vel_actual": 36.0, "vel_libre": 72.0, "ratio": 0.9} for n in "CD"}
        self.assertTrue(math.isnan(red_nodos.resumen_corredor(dos, prom)["dist_m"]))

    def test_trazado_sin_sentido_se_usa_solo_en_corredores(self):
        conexion = dict(self.red["conexiones"][0],
                        path_corredor=[[0, 0], [0.5, 0.5], [0, 1]])
        puntos = {"A": {"lat": 0, "lon": 0}, "B": {"lat": 0, "lon": 1}}
        self.assertEqual(red_nodos._trazo(conexion, puntos, True), conexion["path"])
        self.assertEqual(red_nodos._trazo_corredor(conexion, puntos, True),
                         conexion["path_corredor"])
        self.assertEqual(red_nodos._trazo_corredor(conexion, puntos, True, -1),
                         conexion["path_corredor"][::-1])

    def test_distancia_visual_no_cambia_la_ruta_origen_destino(self):
        conexion = dict(self.red["conexiones"][0], d_corredor_m=300)
        red = {"conexiones": [conexion]}
        prom = {n: {"vel_actual": 36.0, "vel_libre": 72.0, "ratio": 0.9} for n in "AB"}
        corredor = red_nodos.armar_corredores({"UNO": ["A", "B"]}, red)[0]
        resumen = red_nodos.resumen_corredor(corredor, prom)
        ruta = red_nodos.ruta_mas_rapida("A", "B", red, prom)
        self.assertEqual(resumen["dist_m"], 300)
        self.assertEqual(resumen["tiempo_s"], 30)
        self.assertEqual(ruta["dist_m"], 1000)


class CorredoresDelProyectoTest(unittest.TestCase):
    """La hoja real y data/red_nodos.json: cada corredor se dibuja por la via."""

    def test_todos_los_pares_de_corredores_son_conexiones(self):
        nodos = dt.cargar_nodos(config.NODOS_PATH)
        corredores, faltantes = dt.leer_corredores(config.NODOS_PATH, nodos["id_nodo"].astype(str))
        self.assertTrue(corredores)
        self.assertEqual(faltantes, [])
        red = json.loads((ROOT / "data" / "red_nodos.json").read_text(encoding="utf-8"))
        armados = red_nodos.armar_corredores(corredores, red)
        self.assertEqual({c["nombre"]: c["sin_conexion"] for c in armados if c["sin_conexion"]}, {})

    def test_tramos_especiales_tienen_geometria_tomtom_sin_sentido(self):
        esperados = {
            frozenset(("DES_LAGO", "MAN_ADU")),
            frozenset(("RET_TRAV57&54", "ROS_ACC")),
            frozenset(("TIE_ARAPOZO", "ENT_TERMINAL")),
            frozenset(("BAY_CTG", "RAM_CTG")),
        }
        red = json.loads((ROOT / "data" / "red_nodos.json").read_text(encoding="utf-8"))
        encontrados = {}
        for conexion in red["conexiones"]:
            par = frozenset((conexion["a"], conexion["b"]))
            if par in esperados:
                encontrados[par] = conexion
        self.assertEqual(set(encontrados), esperados)
        for conexion in encontrados.values():
            self.assertGreater(conexion.get("d_corredor_m", 0), 0)
            self.assertGreaterEqual(len(conexion.get("path_corredor", [])), 2)
            self.assertEqual(conexion.get("modo_path_corredor"),
                             "TomTom pedestrian shortest")


if __name__ == "__main__":
    unittest.main()
