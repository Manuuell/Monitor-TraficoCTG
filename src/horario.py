"""
Horario operativo del dashboard, derivado de los horarios del cron.

El dia de mediciones empieza con la primera corrida del Turno 1 (04:00) y
termina con la de medianoche (00:00), asi que los ejes y la barra de horas van
de 4:00 a 0:00 y no muestran la franja vacia de 01 a 03.

Cada medicion se asigna a su corrida de media hora (05:31 -> 05:30): las
corridas extra de 05:30, 06:30... se ven aparte de las de la hora en punto.
"""
from __future__ import annotations

import pandas as pd

import config


def _minutos(hhmm: str) -> int:
    horas, minutos = (int(parte) for parte in hhmm.split(":"))
    return horas * 60 + minutos


# Minuto del dia en que empieza el dia operativo (04:00 -> 240)
INICIO = _minutos(config.HORARIOS["Turno 1"][0])


def minuto_operativo(hhmm: str) -> int:
    """Minutos desde el inicio del dia operativo (04:00 -> 0, 00:00 -> 1200)."""
    return (_minutos(hhmm) - INICIO) % 1440


# Las 28 corridas del cron en orden de dia operativo: 04:00, 05:00, 05:30 ... 00:00
CORRIDAS = sorted(
    {hora for horas in config.HORARIOS.values() for hora in horas},
    key=minuto_operativo,
)
# Horas con corridas, en el mismo orden: 4, 5 ... 23, 0
HORAS = list(dict.fromkeys(int(corrida[:2]) for corrida in CORRIDAS))
DIA_COMPLETO = (CORRIDAS[0], CORRIDAS[-1])


def etiqueta(corrida: str) -> str:
    """'05:30' -> '5:30', igual que las horas de la barra."""
    return f"{int(corrida[:2])}:{corrida[3:]}"


def orden_hora(hora: int) -> int:
    """Clave para ordenar horas sueltas como el dia operativo (4 ... 23, 0)."""
    return (hora * 60 - INICIO) % 1440


def corrida_de(ts: pd.Series) -> pd.Series:
    """Etiqueta HH:MM de la corrida de media hora de cada medicion."""
    media_hora = (ts.dt.minute // 30 * 30).map("{:02d}".format)
    return ts.dt.strftime("%H:") + media_hora


def en_horario(ts: pd.Series, desde: str | None, hasta: str | None) -> pd.Series:
    """True si la medicion cae entre las corridas desde y hasta (ambas incluidas).

    Sin rango devuelve True para todo. Una medicion de 01 a 03 (fuera del cron)
    solo entra si no se pide rango.
    """
    if desde is None or hasta is None:
        return pd.Series(True, index=ts.index)
    minuto = (ts.dt.hour * 60 + ts.dt.minute // 30 * 30 - INICIO) % 1440
    return minuto.between(minuto_operativo(desde), minuto_operativo(hasta))


def condicion_sql(columna: str) -> str:
    """Mismo filtro que en_horario para PostgreSQL; usa los parametros :m0 y :m1."""
    minuto = (
        f"CAST(EXTRACT(HOUR FROM {columna}) * 60 "
        f"+ FLOOR(EXTRACT(MINUTE FROM {columna}) / 30) * 30 AS integer)"
    )
    return f"MOD({minuto} - {INICIO} + 1440, 1440) BETWEEN :m0 AND :m1"


def parametros_sql(desde: str, hasta: str) -> dict:
    return {"m0": minuto_operativo(desde), "m1": minuto_operativo(hasta)}
