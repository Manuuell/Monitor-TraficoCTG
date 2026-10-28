"""Corredores de la hoja CORREDORES: lectura."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import descargar_trafico as dt  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
