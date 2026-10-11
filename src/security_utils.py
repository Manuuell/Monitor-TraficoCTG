"""Utilidades pequeñas para evitar que secretos lleguen a logs o interfaces."""
from __future__ import annotations

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
