"""Cierres temporales y rutas alternativas de la simulacion vial."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))

import red_nodos  # noqa: E402


class SimulacionCierresTest(unittest.TestCase):
    def setUp(self):
        def conexion(a, b, ida, vuelta=None):
            return {
                "a": a, "b": b, "d_ab_m": ida,
                "d_ba_m": ida if vuelta is None else vuelta,
                "path": [[0, 0], [1, 1]], "path_ba": [[1, 1], [0, 0]],
            }

        self.red = {
            "conexiones": [
                conexion("A", "B", 100),
                conexion("B", "D", 100),
                conexion("A", "C", 180),
                conexion("C", "D", 180),
            ],
            "restricciones_giro": [],
        }
        self.promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 40.0, "ratio": 0.9}
            for nodo in "ABCD"
        }

    def ruta(self, cierres=None, red=None):
        return red_nodos.ruta_mas_rapida(
            "A", "D", red or self.red, self.promedios, cierres=cierres
        )

    def test_sin_cierres_elige_el_menor_tiempo(self):
        ruta = self.ruta()
        self.assertEqual(ruta["nodos"], ["A", "B", "D"])
        self.assertEqual(ruta["dist_m"], 200)

    def test_cierre_de_un_sentido_conserva_el_contrario(self):
        cierre = [{"inicio": "A", "fin": "B", "sentido": "ida"}]
        self.assertEqual(self.ruta(cierre)["nodos"], ["A", "C", "D"])
        vuelta = red_nodos.ruta_mas_rapida("B", "A", self.red, self.promedios,
                                           cierres=cierre)
        self.assertEqual(vuelta["nodos"], ["B", "A"])

    def test_cierre_en_ambos_sentidos_bloquea_ida_y_vuelta(self):
        cierre = [{"inicio": "A", "fin": "B", "sentido": "ambos"}]
        self.assertEqual(
            red_nodos.aristas_cerradas(cierre), {("A", "B"), ("B", "A")}
        )
        self.assertEqual(self.ruta(cierre)["nodos"], ["A", "C", "D"])

    def test_varios_cierres_pueden_dejar_el_destino_sin_ruta(self):
        cierres = [
            {"inicio": "A", "fin": "B", "sentido": "ida"},
            {"inicio": "A", "fin": "C", "sentido": "ida"},
        ]
        self.assertIsNone(self.ruta(cierres))

    def test_los_cierres_no_modifican_la_red_original(self):
        original = copy.deepcopy(self.red)
        self.ruta([{"inicio": "A", "fin": "B", "sentido": "ambos"}])
        self.assertEqual(self.red, original)

    def test_el_nodo_final_solo_ofrece_conexiones_directas(self):
        self.assertEqual(red_nodos.nodos_conectados(self.red, "A"), ["B", "C"])
        self.assertIsNone(red_nodos.buscar_conexion(self.red, "A", "D"))

    def test_respeta_una_restriccion_de_giro_explicita(self):
        red = copy.deepcopy(self.red)
        red["restricciones_giro"] = [["A", "B", "D"]]
        self.assertEqual(self.ruta(red=red)["nodos"], ["A", "C", "D"])


if __name__ == "__main__":
    unittest.main()
