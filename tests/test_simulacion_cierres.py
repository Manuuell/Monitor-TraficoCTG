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
        puntos = {
            "A": [10.0000, -75.0000], "B": [10.0000, -74.9990],
            "C": [10.0010, -75.0000], "D": [10.0010, -74.9990],
        }

        def conexion(a, b, ida, vuelta=None):
            path = [puntos[a], puntos[b]]
            return {
                "a": a, "b": b, "d_ab_m": ida,
                "d_ba_m": ida if vuelta is None else vuelta,
                "path": path, "path_ba": path[::-1],
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

    def test_devuelve_hasta_tres_rutas_unicas_ordenadas_por_tiempo(self):
        puntos = {"E": [10.0020, -75.0000], "F": [10.0020, -74.9990]}

        def conexion(a, b, distancia):
            base = {
                "A": [10.0000, -75.0000], "B": [10.0000, -74.9990],
                "C": [10.0010, -75.0000], "D": [10.0010, -74.9990],
                **puntos,
            }
            return {
                "a": a, "b": b, "d_ab_m": distancia, "d_ba_m": distancia,
                "path": [base[a], base[b]], "path_ba": [base[b], base[a]],
            }

        red = {
            "conexiones": [
                conexion("A", "B", 100), conexion("B", "D", 100),
                conexion("A", "C", 140), conexion("C", "D", 140),
                conexion("A", "E", 180), conexion("E", "F", 90),
                conexion("F", "D", 90),
            ],
            "restricciones_giro": [],
        }
        promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 40.0, "ratio": 0.9}
            for nodo in "ABCDEF"
        }
        rutas = red_nodos.rutas_mas_rapidas("A", "D", red, promedios, cantidad=3)
        self.assertEqual([r["nodos"] for r in rutas], [
            ["A", "B", "D"], ["A", "C", "D"], ["A", "E", "F", "D"],
        ])
        self.assertEqual([r["dist_m"] for r in rutas], [200, 280, 360])
        self.assertEqual(len({tuple(r["nodos"]) for r in rutas}), 3)
        self.assertEqual([r["tiempo_s"] for r in rutas],
                         sorted(r["tiempo_s"] for r in rutas))

    def test_informa_solo_las_rutas_disponibles(self):
        rutas = red_nodos.rutas_mas_rapidas(
            "A", "D", self.red, self.promedios, cantidad=3)
        self.assertEqual(len(rutas), 2)
        self.assertEqual([r["nodos"] for r in rutas],
                         [["A", "B", "D"], ["A", "C", "D"]])

    def test_todas_las_alternativas_respetan_los_giros_restringidos(self):
        red = copy.deepcopy(self.red)
        red["restricciones_giro"] = [["A", "B", "D"]]
        rutas = red_nodos.rutas_mas_rapidas(
            "A", "D", red, self.promedios, cantidad=3)
        self.assertEqual([r["nodos"] for r in rutas], [["A", "C", "D"]])
        self.assertNotIn(["A", "B", "D"], [r["nodos"] for r in rutas])

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

    def test_respeta_un_sentido_vial_explicito(self):
        red = copy.deepcopy(self.red)
        red["conexiones"][0]["permitir_ab"] = False
        self.assertEqual(self.ruta(red=red)["nodos"], ["A", "C", "D"])

    def test_un_retardo_de_infraestructura_cambia_la_ruta_optima(self):
        red = copy.deepcopy(self.red)
        red["conexiones"][0]["retardo_ab_s"] = 30
        ruta = self.ruta(red=red)
        self.assertEqual(ruta["nodos"], ["A", "C", "D"])
        self.assertEqual(ruta["retardo_s"], 0)

    def test_una_penalizacion_de_giro_cambia_la_ruta_optima(self):
        red = copy.deepcopy(self.red)
        red["penalizaciones_giro"] = [{
            "anterior": "A", "intermedio": "B", "siguiente": "D", "retardo_s": 30,
        }]
        self.assertEqual(self.ruta(red=red)["nodos"], ["A", "C", "D"])

    def test_bloquea_otra_arista_que_reutiliza_la_geometria_roja(self):
        red = copy.deepcopy(self.red)
        # A->C comparte primero mas de 24 m con el trazado cerrado A->B y
        # luego se desvia al norte. No puede usarse como subruta alternativa.
        red["conexiones"][2]["path"] = [
            [10.0000, -75.0000], [10.0000, -74.9996], [10.0010, -75.0000],
        ]
        cierre = [{"inicio": "A", "fin": "B", "sentido": "ida"}]
        self.assertIsNone(self.ruta(cierre, red=red))

    def test_llegar_al_nodo_del_cierre_no_cuenta_como_reutilizarlo(self):
        red = copy.deepcopy(self.red)
        # E->A llega a A en la misma direccion del cierre A->B, con vertices
        # cada ~3 m en los ultimos 13 m: solo toca el cierre al final.
        e = [10.0000, -75.0010]
        cerca_de_a = [[10.0000, -75.0000 - 0.00003 * k] for k in (4, 3, 2, 1)]
        path = [e, *cerca_de_a, [10.0000, -75.0000]]
        red["conexiones"].append({
            "a": "E", "b": "A", "d_ab_m": 110, "d_ba_m": 110,
            "path": path, "path_ba": path[::-1],
        })
        promedios = {**self.promedios, "E": self.promedios["A"]}
        cierre = [{"inicio": "A", "fin": "B", "sentido": "ida"}]
        ruta = red_nodos.ruta_mas_rapida("E", "D", red, promedios, cierres=cierre)
        self.assertEqual(ruta["nodos"], ["E", "A", "C", "D"])


class CalzadasParalelasTest(unittest.TestCase):
    def setUp(self):
        self.promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 45.0, "ratio": 0.8}
            for nodo in "OABD"
        }

    @staticmethod
    def conexion(a, b, path, distancia=1400, **extra):
        return {
            "a": a, "b": b, "d_ab_m": distancia, "d_ba_m": distancia,
            "path": path, "path_ba": list(reversed(path)), **extra,
        }

    def test_origen_elige_la_calzada_paralela_que_avanza_al_destino(self):
        path = [
            [10.0000, -75.0000], [10.0000, -75.0010],
            [10.0001, -75.0010], [10.0001, -75.0000],
            [10.0001, -74.9900],
        ]
        red = {
            "conexiones": [self.conexion("O", "D", path)],
            "puntos": {"O": [10.0000, -75.0000], "D": [10.0000, -74.9900]},
            "restricciones_giro": [],
        }
        ruta = red_nodos.ruta_mas_rapida("O", "D", red, self.promedios)
        self.assertTrue(ruta["calzada_origen_ajustada"])
        self.assertGreater(ruta["recorte_m"], 150)
        self.assertLess(ruta["dist_m"], 1300)
        self.assertEqual(ruta["punto_origen"], red["puntos"]["O"])
        self.assertEqual(ruta["trazos"][0][0], ruta["punto_origen"])
        self.assertIn([10.0001, -75.0000], ruta["trazos"][0])

    def test_destino_termina_en_la_calzada_correcta_sin_vuelta_final(self):
        path = [
            [10.0000, -75.0000], [10.0000, -74.9900],
            [10.0000, -74.9890], [10.0001, -74.9890],
            [10.0001, -74.9900],
        ]
        red = {
            "conexiones": [self.conexion("O", "D", path)],
            "puntos": {"O": [10.0000, -75.0000], "D": [10.0000, -74.9900]},
            "restricciones_giro": [],
        }
        ruta = red_nodos.ruta_mas_rapida("O", "D", red, self.promedios)
        self.assertTrue(ruta["calzada_destino_ajustada"])
        self.assertGreater(ruta["recorte_m"], 150)
        self.assertLess(ruta["dist_m"], 1300)
        self.assertEqual(ruta["punto_destino"], red["puntos"]["D"])
        self.assertEqual(ruta["trazos"][0][-1], ruta["punto_destino"])

    def test_compara_calzadas_antes_de_elegir_la_ruta_mas_rapida(self):
        puntos = {
            "O": [10.0000, -75.0000], "A": [10.0010, -74.9950],
            "D": [10.0000, -74.9900],
        }
        path_con_retorno = [
            [10.0000, -75.0000], [10.0000, -75.0010],
            [10.0001, -75.0010], [10.0001, -75.0000],
            [10.0001, -74.9900],
        ]
        conexiones = [
            self.conexion("O", "D", path_con_retorno, 1400),
            self.conexion("O", "A", [puntos["O"], puntos["A"]], 650),
            self.conexion("A", "D", [puntos["A"], puntos["D"]], 650),
        ]
        red_sin_ajuste = {"conexiones": conexiones, "restricciones_giro": []}
        red_ajustada = {**red_sin_ajuste, "puntos": puntos}
        anterior = red_nodos.ruta_mas_rapida(
            "O", "D", red_sin_ajuste, self.promedios)
        corregida = red_nodos.ruta_mas_rapida(
            "O", "D", red_ajustada, self.promedios)
        self.assertEqual(anterior["nodos"], ["O", "A", "D"])
        self.assertEqual(corregida["nodos"], ["O", "D"])
        self.assertLess(corregida["tiempo_s"], anterior["tiempo_s"])

    def test_misma_via_y_sentido_no_se_recorta(self):
        path = [[10.0000, -75.0000], [10.0000, -74.9950], [10.0000, -74.9900]]
        red = {
            "conexiones": [self.conexion("O", "D", path, distancia=1100)],
            "puntos": {"O": path[0], "D": path[-1]},
            "restricciones_giro": [],
        }
        ruta = red_nodos.ruta_mas_rapida("O", "D", red, self.promedios)
        self.assertFalse(ruta["calzada_origen_ajustada"])
        self.assertFalse(ruta["calzada_destino_ajustada"])
        self.assertAlmostEqual(ruta["dist_m"], 1100)

    def test_sentido_opuesto_usa_su_geometria_dirigida(self):
        ida = [[10.0001, -75.0000], [10.0001, -74.9900]]
        vuelta = [[10.0000, -74.9900], [10.0000, -75.0000]]
        conexion = self.conexion("O", "D", ida, distancia=1100)
        conexion["path_ba"] = vuelta
        red = {
            "conexiones": [conexion],
            "puntos": {"O": [10.0000, -75.0000], "D": [10.0000, -74.9900]},
            "restricciones_giro": [],
        }
        ruta = red_nodos.ruta_mas_rapida("D", "O", red, self.promedios)
        self.assertEqual(ruta["trazos"][0], vuelta)
        self.assertEqual(ruta["nodos"], ["D", "O"])

    def test_via_de_un_solo_sentido_no_inventa_la_vuelta(self):
        path = [[10.0000, -75.0000], [10.0000, -74.9900]]
        red = {
            "conexiones": [self.conexion(
                "O", "D", path, permitir_ab=True, permitir_ba=False)],
            "puntos": {"O": path[0], "D": path[-1]},
            "restricciones_giro": [],
        }
        self.assertIsNone(red_nodos.ruta_mas_rapida("D", "O", red, self.promedios))

    def test_retorno_necesario_en_la_misma_calzada_se_conserva(self):
        path = [
            [10.0000, -75.0000], [10.0000, -74.9950],
            [10.0000, -75.0000], [10.0000, -75.0050],
        ]
        red = {
            "conexiones": [self.conexion("O", "D", path, distancia=1700)],
            "puntos": {"O": path[0], "D": path[-1]},
            "restricciones_giro": [],
        }
        ruta = red_nodos.ruta_mas_rapida("O", "D", red, self.promedios)
        self.assertFalse(ruta["calzada_origen_ajustada"])
        self.assertAlmostEqual(ruta["dist_m"], 1700)

    def test_un_cierre_obliga_a_usar_la_otra_conexion(self):
        puntos = {
            "O": [10.0000, -75.0000], "A": [10.0000, -74.9950],
            "B": [10.0010, -74.9950], "D": [10.0000, -74.9900],
        }
        conexiones = [
            self.conexion("O", "A", [puntos["O"], puntos["A"]], 500),
            self.conexion("A", "D", [puntos["A"], puntos["D"]], 500),
            self.conexion("O", "B", [
                puntos["O"], [10.0010, -75.0000], puntos["B"]], 700),
            self.conexion("B", "D", [puntos["B"], puntos["D"]], 700),
        ]
        red = {"conexiones": conexiones, "puntos": puntos, "restricciones_giro": []}
        cierre = [{"inicio": "O", "fin": "A", "sentido": "ida"}]
        ruta = red_nodos.ruta_mas_rapida(
            "O", "D", red, self.promedios, cierres=cierre)
        self.assertEqual(ruta["nodos"], ["O", "B", "D"])

    def test_origen_intermedio_no_obliga_a_tocar_un_nodo_lateral(self):
        puntos = {
            "O": [10.0001, -74.9950], "A": [10.0000, -75.0000],
            "B": [10.0000, -74.9900], "D": [10.0000, -74.9800],
        }
        conexiones = [
            self.conexion("O", "A", [
                puntos["O"], [10.0030, -74.9970], puntos["A"]], 1100),
            self.conexion("A", "B", [puntos["A"], puntos["B"]], 1100),
            self.conexion("B", "D", [puntos["B"], puntos["D"]], 1100),
        ]
        promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 45.0, "ratio": 0.8}
            for nodo in puntos
        }
        red_anterior = {"conexiones": conexiones, "restricciones_giro": []}
        red_nueva = {**red_anterior, "puntos": puntos}
        anterior = red_nodos.ruta_mas_rapida("O", "D", red_anterior, promedios)
        corregida = red_nodos.ruta_mas_rapida("O", "D", red_nueva, promedios)
        self.assertEqual(anterior["nodos"], ["O", "A", "B", "D"])
        self.assertEqual(corregida["nodos"], ["O", "B", "D"])
        self.assertNotIn("A", corregida["nodos"])
        self.assertLess(corregida["tiempo_s"], anterior["tiempo_s"])

    def test_destino_intermedio_no_se_sobrepasa_para_tocar_otro_nodo(self):
        puntos = {
            "O": [10.0000, -75.0000], "B": [10.0000, -74.9900],
            "C": [10.0000, -74.9800], "D": [10.0001, -74.9850],
        }
        conexiones = [
            self.conexion("O", "B", [puntos["O"], puntos["B"]], 1100),
            self.conexion("B", "C", [puntos["B"], puntos["C"]], 1100),
            self.conexion("C", "D", [
                puntos["C"], [10.0030, -74.9830], puntos["D"]], 1000),
        ]
        promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 45.0, "ratio": 0.8}
            for nodo in puntos
        }
        red_anterior = {"conexiones": conexiones, "restricciones_giro": []}
        red_nueva = {**red_anterior, "puntos": puntos}
        anterior = red_nodos.ruta_mas_rapida("O", "D", red_anterior, promedios)
        corregida = red_nodos.ruta_mas_rapida("O", "D", red_nueva, promedios)
        self.assertEqual(anterior["nodos"], ["O", "B", "C", "D"])
        self.assertEqual(corregida["nodos"], ["O", "B", "D"])
        self.assertNotIn("C", corregida["nodos"])
        self.assertLess(corregida["tiempo_s"], anterior["tiempo_s"])

    def test_destino_no_se_confunde_con_una_via_lejana_no_incidente(self):
        puntos = {
            "O": [10.0000, -75.0000], "A": [10.0000, -74.9900],
            "X": [10.0000, -74.9800], "D": [10.0033, -74.9850],
        }
        conexiones = [
            self.conexion("O", "A", [puntos["O"], puntos["A"]], 1100),
            self.conexion("A", "X", [puntos["A"], puntos["X"]], 1100),
            self.conexion("X", "D", [puntos["X"], puntos["D"]], 900),
        ]
        promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 45.0, "ratio": 0.8}
            for nodo in puntos
        }
        red = {"conexiones": conexiones, "puntos": puntos,
               "restricciones_giro": []}
        ruta = red_nodos.ruta_mas_rapida("O", "D", red, promedios)
        ultima_conexion = ruta["tramos"][-1][0]
        self.assertIn("D", (ultima_conexion["a"], ultima_conexion["b"]))
        self.assertEqual(ruta["punto_origen"], puntos["O"])
        self.assertEqual(ruta["punto_destino"], puntos["D"])
        self.assertEqual(ruta["trazos"][0][0], puntos["O"])
        self.assertEqual(ruta["trazos"][-1][-1], puntos["D"])

    def test_sentido_contrario_busca_la_calzada_paralela_legal(self):
        puntos = {
            "O": [10.0001, -74.9950], "A": [10.0000, -75.0000],
            "B": [10.0000, -74.9900], "C": [10.0002, -74.9900],
            "D": [10.0002, -75.0000], "T": [10.0002, -75.0050],
        }
        este = self.conexion("A", "B", [puntos["A"], puntos["B"]], 1100,
                              permitir_ab=True, permitir_ba=False)
        oeste = self.conexion("C", "D", [puntos["C"], puntos["D"]], 1100,
                               permitir_ab=True, permitir_ba=False)
        conexiones = [
            este, oeste,
            self.conexion("D", "T", [puntos["D"], puntos["T"]], 550),
            self.conexion("O", "A", [puntos["O"], puntos["A"]], 600),
        ]
        promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 45.0, "ratio": 0.8}
            for nodo in puntos
        }
        red = {"conexiones": conexiones, "puntos": puntos,
               "restricciones_giro": []}
        ruta = red_nodos.ruta_mas_rapida("O", "T", red, promedios)
        self.assertEqual(ruta["nodos"], ["O", "D", "T"])
        self.assertNotIn("B", ruta["nodos"])
        self.assertEqual(ruta["tramos"][0][0]["a"], "C")

    def test_la_ruta_resultante_no_repite_nodos_ni_conexiones(self):
        red = copy.deepcopy(self.red_de_ciclo())
        promedios = {
            nodo: {"vel_actual": 36.0, "vel_libre": 45.0, "ratio": 0.8}
            for nodo in "OABCD"
        }
        ruta = red_nodos.ruta_mas_rapida("O", "D", red, promedios)
        ids_aristas = [paso["id_arista"] for paso in ruta["_pasos"]]
        self.assertEqual(len(ruta["nodos"]), len(set(ruta["nodos"])))
        self.assertEqual(len(ids_aristas), len(set(ids_aristas)))

    @classmethod
    def red_de_ciclo(cls):
        puntos = {
            "O": [10.0000, -75.0000], "A": [10.0000, -74.9990],
            "B": [10.0010, -74.9990], "C": [10.0010, -75.0000],
            "D": [10.0020, -74.9990],
        }
        return {
            "conexiones": [
                cls.conexion("O", "A", [puntos["O"], puntos["A"]], 100),
                cls.conexion("A", "B", [puntos["A"], puntos["B"]], 100),
                cls.conexion("B", "C", [puntos["B"], puntos["C"]], 100),
                cls.conexion("C", "A", [puntos["C"], puntos["A"]], 100),
                cls.conexion("B", "D", [puntos["B"], puntos["D"]], 100),
            ],
            "restricciones_giro": [],
        }


if __name__ == "__main__":
    unittest.main()
