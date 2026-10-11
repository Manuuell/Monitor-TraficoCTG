"""
Rotacion automatica entre llaves API de TomTom.

Cada llave pertenece a una cuenta con su propia cuota mensual
(config.CUOTA_MENSUAL_LLAVE). El ETL reparte las llamadas entre las llaves de
config.API_KEYS en round-robin y, cuando una devuelve 403 InsufficientFunds,
la marca como agotada y salta a la siguiente sin perder la corrida. Lo mismo
ocurre si TomTom la rechaza por otro motivo (llave revocada o bloqueada, o
limite de llamadas): ver motivo_descarte().

Las llaves de config.API_KEYS_RESERVA solo entran cuando todas las principales
estan agotadas. Una llave agotada se vuelve a probar pasadas
config.REPROBAR_AGOTADA_HORAS, asi el ETL regresa a las principales en cuanto
alguna recibe creditos y la reserva queda en reposo.

El estado (consumo por llave y llaves agotadas) se guarda en
data/estado_llaves.json. Es local a cada VPS: TomTom igualmente rechaza con
403 cuando una llave se agota, asi que el peor caso es una llamada fallida de
mas antes de detectarlo.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta

import config

ESTADO_FILE = config.BASE_DIR / "data" / "estado_llaves.json"

_LOCK = threading.Lock()


def _mes_actual() -> str:
    return datetime.now().strftime("%Y-%m")


def mask(llave: str) -> str:
    """Huella corta y estable que no revela ningun prefijo de la llave."""
    return f"sha256:{_id_llave(llave)[:12]}" if llave else "?"


def _id_llave(llave: str) -> str:
    """Identificador persistente no reversible para una llave de alta entropia."""
    return hashlib.sha256(llave.encode("utf-8")).hexdigest()


def _offset_inicial() -> int:
    """
    Desfase del round-robin por VPS. Reparte las llaves entre servidores para
    que no arranquen siempre por la misma: VPS 1 empieza en la primera llave,
    VPS 2 en la segunda, etc.
    """
    try:
        vps = int(config.VPS_ID)
    except (ValueError, TypeError):
        vps = 1
    return max(vps - 1, 0)


def _estado_vacio() -> dict:
    return {"mes": _mes_actual(), "cursor": _offset_inicial(), "llaves": {}}


def _todas() -> list:
    return config.API_KEYS + config.API_KEYS_RESERVA


def _registro(llaves: dict, llave: str) -> dict:
    identificador = _id_llave(llave)
    # Migracion transparente desde el formato antiguo, que usaba la llave
    # completa como clave del JSON. Al guardar de nuevo ya no queda el secreto.
    legado = llaves.pop(llave, None)
    if legado is not None and identificador not in llaves:
        llaves[identificador] = legado
    return llaves.setdefault(
        identificador,
        {"consumo": 0, "agotada": False, "ultimo_error": None, "ultima_vez": None},
    )


def cargar_estado() -> dict:
    """Lee el estado; lo reinicia si cambio el mes (nueva cuota)."""
    try:
        with open(ESTADO_FILE, encoding="utf-8") as f:
            estado = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        estado = {}

    if estado.get("mes") != _mes_actual():
        estado = _estado_vacio()

    estado.setdefault("mes", _mes_actual())
    estado.setdefault("cursor", _offset_inicial())
    estado.setdefault("llaves", {})

    # Añade llaves nuevas al pool (consumo 0) para que aparezcan al rotar.
    for llave in _todas():
        _registro(estado["llaves"], llave)

    return estado


# Motivos por los que una llave sale de la rotacion (ver motivo_descarte).
SIN_CREDITOS = "sin_creditos"
BLOQUEADA = "bloqueada"
LIMITE = "limite"

# Un 429 es un limite de llamadas por segundo/dia: se levanta pronto, no hace
# falta esperar lo mismo que para una recarga de creditos.
HORAS_REPROBAR_LIMITE = 1


def _disponible(reg: dict) -> bool:
    """No agotada, o descartada hace mas de las horas que toca a su motivo."""
    if not reg.get("agotada"):
        return True
    horas = (
        HORAS_REPROBAR_LIMITE if reg.get("motivo") == LIMITE
        else config.REPROBAR_AGOTADA_HORAS
    )
    desde = reg.get("agotada_desde") or reg.get("ultima_vez")
    try:
        marca = datetime.strptime(desde, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    return datetime.now() - marca >= timedelta(hours=horas)


def guardar_estado(estado: dict) -> None:
    try:
        ESTADO_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(ESTADO_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = -1
                json.dump(estado, f, indent=2, ensure_ascii=False)
        finally:
            if fd >= 0:
                os.close(fd)
    except OSError as e:
        print(f"  [Llaves] No se pudo guardar {ESTADO_FILE.name}: {e}")


def siguiente_llave() -> str:
    """
    Devuelve la proxima llave (round-robin), saltando las agotadas.
    Prioridad: principales disponibles, luego reserva disponible. Si todas
    estan agotadas, reintenta la menos usada: la cuota pudo haberse renovado.
    """
    with _LOCK:
        estado = cargar_estado()
        llaves = estado["llaves"]

        candidatas = [
            k for k in config.API_KEYS if _disponible(_registro(llaves, k))
        ] or [
            k for k in config.API_KEYS_RESERVA if _disponible(_registro(llaves, k))
        ]
        if not candidatas:
            candidatas = sorted(
                _todas(),
                key=lambda k: _registro(llaves, k).get("consumo", 0),
            )

        n = len(candidatas)
        cursor = estado.get("cursor", 0) % n
        elegida = candidatas[cursor]
        estado["cursor"] = (cursor + 1) % n
        guardar_estado(estado)
        return elegida


def marcar_agotada(llave: str, error: str, motivo: str = SIN_CREDITOS) -> None:
    with _LOCK:
        estado = cargar_estado()
        reg = _registro(estado["llaves"], llave)
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reg["agotada"] = True
        reg["agotada_desde"] = ahora
        reg["motivo"] = motivo
        reg["ultimo_error"] = (error or "")[:300]
        reg["ultima_vez"] = ahora
        guardar_estado(estado)


def registrar_consumo(consumo_por_llave: dict, ultimo_exito: dict = None) -> None:
    """
    Suma las llamadas exitosas de esta corrida a cada llave.

    ultimo_exito: {llave: "YYYY-mm-dd HH:MM:SS"} de su ultima respuesta buena.
    Una llave agotada vuelve a contar como disponible solo si respondio bien
    DESPUES de su descarte: si en la misma corrida acerto y luego se agoto,
    sigue agotada (antes el consumo la rehabilitaba sin mirar el orden).
    """
    if not consumo_por_llave:
        return
    with _LOCK:
        estado = cargar_estado()
        for llave, n in consumo_por_llave.items():
            reg = _registro(estado["llaves"], llave)
            reg["consumo"] = reg.get("consumo", 0) + int(n)
            exito = (ultimo_exito or {}).get(llave)
            descarte = reg.get("agotada_desde")
            if reg.get("agotada") and exito and (not descarte or exito > descarte):
                reg["agotada"] = False
            reg["ultima_vez"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        guardar_estado(estado)


def motivo_descarte(resp: dict):
    """
    Motivo por el que la llave debe salir de la rotacion, o None si el fallo
    no es culpa de la llave (red, 5xx de TomTom, punto sin datos):
      - SIN_CREDITOS: 403 InsufficientFunds.
      - BLOQUEADA: 401, o 403 por otra razon (llave revocada, cuenta
        suspendida, dominio/IP no permitido).
      - LIMITE: 429, demasiadas llamadas.
    """
    if resp.get("ok"):
        return None
    status = resp.get("status")
    if status == 403:
        texto = (resp.get("error") or "").lower()
        if "insufficientfunds" in texto or "credits" in texto:
            return SIN_CREDITOS
        return BLOQUEADA
    if status == 401:
        return BLOQUEADA
    if status == 429:
        return LIMITE
    return None


def disponible(llave: str) -> bool:
    """True si la llave no esta agotada o ya toca volver a probarla."""
    with _LOCK:
        return _disponible(_registro(cargar_estado()["llaves"], llave))


def resumen() -> list:
    """Estado actual por llave, para logs y el dashboard."""
    estado = cargar_estado()
    out = []
    for i, llave in enumerate(_todas()):
        reg = _registro(estado["llaves"], llave)
        out.append({
            "llave_id": mask(llave),
            "cuenta": i + 1,
            "tipo": "reserva" if llave in config.API_KEYS_RESERVA else "principal",
            "consumo": reg.get("consumo", 0),
            "agotada": reg.get("agotada", False),
            "motivo": reg.get("motivo") if reg.get("agotada") else None,
            "ultimo_error": reg.get("ultimo_error"),
            "ultima_vez": reg.get("ultima_vez"),
            "agotada_desde": reg.get("agotada_desde"),
            "cuota": config.CUOTA_MENSUAL_LLAVE,
        })
    return out
