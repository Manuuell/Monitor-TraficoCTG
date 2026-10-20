"""Regresiones para controles que protegen secretos y archivos sensibles."""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
import google_upload  # noqa: E402
import rotacion_llaves  # noqa: E402
from security_utils import clave_valida, huella_clave, sanitizar_error  # noqa: E402


class ClaveAdministrativaTest(unittest.TestCase):
    def test_acepta_solo_la_clave_exacta_aunque_tenga_ene(self):
        self.assertTrue(clave_valida("contraseña-ñ", "contraseña-ñ"))
        self.assertFalse(clave_valida("contrasena-n", "contraseña-ñ"))
        self.assertFalse(clave_valida("", "contraseña-ñ"))

    def test_sin_clave_configurada_el_panel_queda_cerrado(self):
        self.assertFalse(clave_valida("", ""))
        self.assertFalse(clave_valida("cualquiera", ""))

    def test_la_huella_no_contiene_la_clave(self):
        huella = huella_clave("secreto-admin")
        self.assertNotIn("secreto-admin", huella)
        self.assertEqual(huella, huella_clave("secreto-admin"))


class ErroresSinSecretosTest(unittest.TestCase):
    def test_elimina_llave_explicita_y_parametros_de_url(self):
        secreto = "tomtom-super-secreto"
        error = (
            "HTTPSConnection failed for "
            f"https://api.tomtom.com/flow?point=1,2&key={secreto}&api_key=otra"
        )

        limpio = sanitizar_error(error, secreto)

        self.assertNotIn(secreto, limpio)
        self.assertNotIn("api_key=otra", limpio)
        self.assertIn("key=[REDACTED]", limpio)
        self.assertIn("api_key=[REDACTED]", limpio)


class ArchivosSensiblesTest(unittest.TestCase):
    def test_token_oauth_se_escribe_con_modo_0600(self):
        with tempfile.TemporaryDirectory() as temporal:
            token = Path(temporal) / "privado" / "token.json"
            with mock.patch.object(config, "OAUTH_TOKEN_FILE", token):
                google_upload.guardar_token_seguro('{"refresh_token":"secreto"}')

            self.assertEqual(stat.S_IMODE(token.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(token.parent.stat().st_mode), 0o700)

    def test_estado_de_llaves_usa_huellas_y_modo_0600(self):
        secreto = "llave-que-no-debe-persistirse"
        with tempfile.TemporaryDirectory() as temporal:
            estado_file = Path(temporal) / "estado_llaves.json"
            with (
                mock.patch.object(rotacion_llaves, "ESTADO_FILE", estado_file),
                mock.patch.object(config, "API_KEYS", [secreto]),
                mock.patch.object(config, "API_KEYS_RESERVA", []),
                mock.patch.object(config, "VPS_ID", "1"),
            ):
                elegida = rotacion_llaves.siguiente_llave()

            contenido = estado_file.read_text(encoding="utf-8")
            estado = json.loads(contenido)
            self.assertEqual(elegida, secreto)
            self.assertNotIn(secreto, contenido)
            self.assertIn(rotacion_llaves._id_llave(secreto), estado["llaves"])
            self.assertEqual(stat.S_IMODE(estado_file.stat().st_mode), 0o600)

    def test_migra_estado_antiguo_que_contenia_la_llave(self):
        secreto = "llave-legada"
        with tempfile.TemporaryDirectory() as temporal:
            estado_file = Path(temporal) / "estado_llaves.json"
            estado_file.write_text(
                json.dumps({
                    "mes": rotacion_llaves._mes_actual(),
                    "cursor": 0,
                    "llaves": {secreto: {"consumo": 9, "agotada": False}},
                }),
                encoding="utf-8",
            )
            with (
                mock.patch.object(rotacion_llaves, "ESTADO_FILE", estado_file),
                mock.patch.object(config, "API_KEYS", [secreto]),
                mock.patch.object(config, "API_KEYS_RESERVA", []),
            ):
                estado = rotacion_llaves.cargar_estado()
                rotacion_llaves.guardar_estado(estado)

            contenido = estado_file.read_text(encoding="utf-8")
            self.assertNotIn(secreto, contenido)
            self.assertEqual(
                estado["llaves"][rotacion_llaves._id_llave(secreto)]["consumo"],
                9,
            )


if __name__ == "__main__":
    unittest.main()
