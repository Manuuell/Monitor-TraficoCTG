"""Utilidades pequeñas para evitar que secretos lleguen a logs o interfaces."""
from __future__ import annotations

import hashlib
import hmac
import re


def sanitizar_error(error, *secretos: str, limite: int = 500) -> str:
    """Elimina credenciales de un error antes de imprimirlo o persistirlo."""
    texto = str(error or "")
    for secreto in secretos:
        if secreto:
            texto = texto.replace(str(secreto), "[REDACTED]")
    texto = re.sub(
        r"([?&](?:key|api[_-]?key|apikey)=)[^&\s\"']+",
        r"\1[REDACTED]",
        texto,
        flags=re.IGNORECASE,
    )
    return texto[:limite]


def huella_clave(clave: str) -> str:
    """Huella con la que la sesion recuerda el acceso sin guardar la clave."""
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def clave_valida(intento: str, esperada: str) -> bool:
    """Compara en tiempo constante; una clave vacia nunca abre el panel.

    Se comparan bytes: hmac.compare_digest con str rechaza (TypeError) los
    caracteres no ASCII, como la ñ de "contraseña".
    """
    if not esperada:
        return False
    return hmac.compare_digest(
        (intento or "").encode("utf-8"), esperada.encode("utf-8")
    )
