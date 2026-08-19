"""
Modulo de acceso a PostgreSQL para el Monitor de Trafico.

Mantiene los MISMOS nombres de columnas que el Google Sheet / CSV para que
el dashboard y el resto del codigo no necesiten cambios de logica.

Variables de entorno (ver config.py):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

Uso tipico:
    import db
    db.crear_esquema()                 # idempotente, crea tabla + indices
    db.insertar_dataframe(df)          # agrega filas de una ejecucion
    df = db.leer_datos(n_dias=30)      # lee historico (mismo formato que Sheet)
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.types import (
    BigInteger, Boolean, Float, Integer, Text, TIMESTAMP, Date,
)

import config

TABLA = "mediciones"

# Tipos explicitos por columna (evita que pandas adivine mal).
# Se usan los MISMOS nombres que el DataFrame original.
_DTYPES = {
    "id_nodo": Text(), "nombre_nodo": Text(), "categoria": Text(),
    "prioridad": Text(), "zona": Text(), "barrios_que_colinda": Text(),
    "notas": Text(),
    "lat": Float(), "lon": Float(),
    "activo_final": Boolean(),
    "ok": Boolean(), "http_status": Integer(),
    "currentSpeed": Float(), "freeFlowSpeed": Float(),
    "currentTravelTime": Float(), "freeFlowTravelTime": Float(),
    "confidence": Float(), "roadClosure": Boolean(), "frc": Text(),
    "consultation_time": TIMESTAMP(), "vps_id": Text(), "error_msg": Text(),
    "delay_abs_seg": Float(), "delay_rel_pct": Float(), "velocidad_ratio": Float(),
    "fecha": Date(), "hora": Text(), "turno": Text(), "dia_semana": Text(),
}

# Columnas que deben ser numericas al leer (igual que en el dashboard)
_NUMERIC_COLS = [
    "lat", "lon", "currentSpeed", "freeFlowSpeed", "currentTravelTime",
    "freeFlowTravelTime", "confidence", "delay_abs_seg", "delay_rel_pct",
    "velocidad_ratio", "http_status",
]

_engine = None


def get_engine():
    """Devuelve un engine SQLAlchemy reutilizable (con pool)."""
    global _engine
    if _engine is None:
        url = (
            f"postgresql+psycopg2://{config.DB_USER}:{config.DB_PASSWORD}"
            f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        )
        # connect_timeout corto: si la BD no responde, el dashboard cae a
        # Sheets en segundos en vez de colgarse.
        _engine = create_engine(
            url, pool_pre_ping=True, pool_recycle=1800,
            connect_args={"connect_timeout": 5},
        )
    return _engine


def _coaccionar_tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos del DataFrame antes de insertar."""
    df = df.copy()

    # Booleanos: acepta TRUE/True/1
    for col in ["ok", "activo_final", "roadClosure"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.strip().str.upper()
                .map({"TRUE": True, "1": True, "FALSE": False, "0": False})
            )

    # Numericos
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fechas
    if "consultation_time" in df.columns:
        df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date

    return df


def crear_esquema() -> None:
    """Crea la tabla (si no existe) y los indices. Idempotente."""
    engine = get_engine()
    # Crear tabla vacia con tipos correctos usando un DataFrame plantilla
    plantilla = pd.DataFrame({c: pd.Series(dtype="object") for c in _DTYPES})
    plantilla.to_sql(
        TABLA, engine, if_exists="append", index=False, dtype=_DTYPES,
    )
    # Indices para acelerar consultas del dashboard
    with engine.begin() as conn:
        conn.execute(text(
            f'CREATE INDEX IF NOT EXISTS idx_{TABLA}_ct '
            f'ON {TABLA} ("consultation_time");'
        ))
        conn.execute(text(
            f'CREATE INDEX IF NOT EXISTS idx_{TABLA}_vps_ct '
            f'ON {TABLA} ("vps_id", "consultation_time");'
        ))
        conn.execute(text(
            f'CREATE INDEX IF NOT EXISTS idx_{TABLA}_nodo '
            f'ON {TABLA} ("id_nodo");'
        ))


def insertar_dataframe(df: pd.DataFrame) -> int:
    """Agrega las filas del DataFrame a la tabla. Devuelve cantidad insertada."""
    if df is None or df.empty:
        return 0
    engine = get_engine()
    # Solo columnas conocidas, en el orden del esquema
    cols = [c for c in _DTYPES if c in df.columns]
    df_ins = _coaccionar_tipos(df[cols])
    df_ins.to_sql(TABLA, engine, if_exists="append", index=False, dtype=_DTYPES)
    return len(df_ins)


def _postprocesar_lectura(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos tras leer de la BD (mismo formato que google_upload.leer_sheet)."""
    if "consultation_time" in df.columns:
        df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def leer_datos(n_dias: int = 30) -> pd.DataFrame:
    """Lee el historico de los ultimos n_dias. Mismo formato que google_upload.leer_sheet."""
    engine = get_engine()
    query = text(
        f'SELECT * FROM {TABLA} '
        f'WHERE "consultation_time" >= NOW() - (:dias || \' days\')::interval '
        f'ORDER BY "consultation_time";'
    )
    try:
        df = pd.read_sql(query, engine, params={"dias": n_dias})
    except Exception as e:
        print(f"  [DB] Error leyendo: {e}")
        return pd.DataFrame()

    return _postprocesar_lectura(df)


def leer_rango(fecha_ini: date, fecha_fin: date) -> pd.DataFrame:
    """
    Lee las mediciones con consultation_time entre fecha_ini y fecha_fin
    (ambos dias inclusive). Trae solo el periodo pedido — usa el indice
    idx_mediciones_ct, no recorre la tabla completa.
    """
    engine = get_engine()
    query = text(
        f'SELECT * FROM {TABLA} '
        f'WHERE "consultation_time" >= :ini AND "consultation_time" < :fin '
        f'ORDER BY "consultation_time";'
    )
    try:
        df = pd.read_sql(
            query, engine,
            params={"ini": fecha_ini, "fin": fecha_fin + timedelta(days=1)},
        )
    except Exception as e:
        print(f"  [DB] Error leyendo rango: {e}")
        return pd.DataFrame()

    return _postprocesar_lectura(df)


def contar_filas() -> int:
    """Cuenta el total de filas en la tabla (para verificacion de migracion)."""
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {TABLA};")).scalar()


def rango_fechas() -> tuple:
    """Devuelve (min, max) de consultation_time. Para verificacion."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            f'SELECT MIN("consultation_time"), MAX("consultation_time") FROM {TABLA};'
        )).fetchone()
    return row[0], row[1]
