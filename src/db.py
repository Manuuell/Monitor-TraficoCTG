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
        conn.execute(text(
            f'CREATE INDEX IF NOT EXISTS idx_{TABLA}_nodo_ct '
            f'ON {TABLA} ("id_nodo", "consultation_time");'
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


def leer_nodo_rango(id_nodo: str, fecha_ini: date, fecha_fin: date) -> pd.DataFrame:
    """Lee solo las columnas analiticas de un nodo dentro del rango pedido.

    Un resultado vacio es valido y no significa que PostgreSQL haya fallado;
    por eso los errores se propagan al dashboard, que decide si usa el
    respaldo de Sheets/CSV. La consulta aprovecha el indice compuesto por
    nodo y fecha y evita transferir todo el historico para dibujar la vista.
    """
    query = text(
        f'SELECT "id_nodo", "nombre_nodo", ok, "currentSpeed", '
        f'"freeFlowSpeed", "delay_abs_seg", "velocidad_ratio", '
        f'"consultation_time" FROM {TABLA} '
        f'WHERE "id_nodo" = :id_nodo '
        f'AND "consultation_time" >= :ini AND "consultation_time" < :fin '
        f'ORDER BY "consultation_time";'
    )
    df = pd.read_sql(
        query,
        get_engine(),
        params={
            "id_nodo": str(id_nodo),
            "ini": fecha_ini,
            "fin": fecha_fin + timedelta(days=1),
        },
    )
    return _postprocesar_lectura(df)


def leer_resumen_ejecuciones(n_dias: int = 7) -> pd.DataFrame:
    """Resume las corridas en PostgreSQL sin transferir cada medicion.

    Devuelve una fila por ``consultation_time`` y VPS. Una corrida es parcial
    cuando respondio al menos un nodo pero tambien hubo fallos, y fallida
    cuando no respondio ninguno. Los valores nulos de ``ok`` cuentan como
    fallo. A diferencia de ``leer_datos``, los errores se propagan para que el
    panel pueda elegir de forma explicita un respaldo local.
    """
    query = text(
        f'SELECT "consultation_time" AS timestamp, '
        f'COALESCE(NULLIF("vps_id", \'\'), \'?\') AS vps_id, '
        f'COUNT(*) AS total_nodos, '
        f'COUNT(*) FILTER (WHERE COALESCE(ok, FALSE)) AS consultas_ok, '
        f'COUNT(*) - COUNT(*) FILTER (WHERE COALESCE(ok, FALSE)) AS consultas_error, '
        f'CASE '
        f'  WHEN COUNT(*) FILTER (WHERE COALESCE(ok, FALSE)) = 0 THEN \'ERROR\' '
        f'  WHEN COUNT(*) - COUNT(*) FILTER (WHERE COALESCE(ok, FALSE)) > 0 THEN \'PARCIAL\' '
        f'  ELSE \'OK\' END AS estado, '
        f'MIN(NULLIF("error_msg", \'\')) AS error '
        f'FROM {TABLA} '
        f'WHERE "consultation_time" >= NOW() - (:dias || \' days\')::interval '
        f'GROUP BY "consultation_time", "vps_id" '
        f'ORDER BY "consultation_time";'
    )
    df = pd.read_sql(query, get_engine(), params={"dias": int(n_dias)})
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def promedios_por_nodo(
    fecha_ini: date = None, fecha_fin: date = None,
    hora_ini: int = 0, hora_fin: int = 23, mes: int = None,
    dia_semana: int = None, quincena: bool = False, ids: list = None,
) -> pd.DataFrame:
    """
    Promedio por nodo de las lecturas validas que cumplen los filtros del
    mapa. Agrega en PostgreSQL y devuelve una fila por nodo (113), en vez de
    traer cientos de miles de mediciones al dashboard.

        fecha_ini, fecha_fin  dias inclusive, o None para no acotar
        hora_ini, hora_fin  rango de horas inclusive (05 incluye 05:30)
        mes                 1-12, o None para todos
        dia_semana          1=Lunes ... 7=Domingo (ISODOW), o None
        quincena            solo el dia 15 y el ultimo dia de cada mes
        ids                 lista de id_nodo, o None para todos

    Columnas: id_nodo, vel_actual, vel_libre, ratio, n.

    A diferencia de leer_rango, un error de conexion se propaga: un resultado
    vacio es normal (un mes sin datos) y el dashboard solo debe caer a Sheets
    cuando la BD no responde.
    """
    ts = '"consultation_time"'
    condiciones = [
        "ok", f"{ts} IS NOT NULL",
        f"EXTRACT(HOUR FROM {ts}) BETWEEN :h0 AND :h1",
    ]
    params = {"h0": hora_ini, "h1": hora_fin}
    # Comparar el timestamp directo (no su fecha) usa idx_mediciones_ct
    if fecha_ini is not None:
        condiciones.append(f"{ts} >= :ini")
        params["ini"] = fecha_ini
    if fecha_fin is not None:
        condiciones.append(f"{ts} < :fin")
        params["fin"] = fecha_fin + timedelta(days=1)
    if mes is not None:
        condiciones.append(f"EXTRACT(MONTH FROM {ts}) = :mes")
        params["mes"] = mes
    if dia_semana is not None:
        condiciones.append(f"EXTRACT(ISODOW FROM {ts}) = :dow")
        params["dow"] = dia_semana
    if quincena:
        condiciones.append(
            f"(EXTRACT(DAY FROM {ts}) = 15 OR {ts}::date = "
            f"(date_trunc('month', {ts}) + interval '1 month - 1 day')::date)"
        )
    if ids:
        condiciones.append("id_nodo = ANY(:ids)")
        params["ids"] = list(ids)

    query = text(
        f'SELECT id_nodo, AVG("currentSpeed") AS vel_actual, '
        f'AVG("freeFlowSpeed") AS vel_libre, AVG(velocidad_ratio) AS ratio, '
        f'COUNT(*) AS n FROM {TABLA} '
        f'WHERE {" AND ".join(condiciones)} GROUP BY id_nodo;'
    )
    return pd.read_sql(query, get_engine(), params=params)


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


# ============================================================
# ESTADO DE LAS LLAVES TOMTOM DE CADA VPS
# ============================================================
# Cada VPS solo conoce las llaves de su propio .env y su estado_llaves.json.
# Para que el panel administrativo muestre las de todos, cada ETL publica aqui
# su resumen al final de la corrida. Solo IDs enmascarados (rotacion_llaves.
# mask), nunca la llave completa.
TABLA_LLAVES = "estado_llaves"


def guardar_estado_llaves(vps_id: str, llaves: list) -> int:
    """
    Reemplaza las filas de vps_id con su resumen actual de llaves
    (rotacion_llaves.resumen()). Crea la tabla si no existe.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {TABLA_LLAVES} ("
            "vps_id TEXT NOT NULL, llave_id TEXT NOT NULL, orden INTEGER, tipo TEXT, "
            "consumo INTEGER, cuota INTEGER, agotada BOOLEAN, motivo TEXT, "
            "ultima_vez TEXT, agotada_desde TEXT, actualizado TIMESTAMP DEFAULT now(), "
            "PRIMARY KEY (vps_id, llave_id));"
        ))
        conn.execute(text(f"DELETE FROM {TABLA_LLAVES} WHERE vps_id = :vps;"), {"vps": str(vps_id)})
        for orden, llave in enumerate(llaves, start=1):
            conn.execute(text(
                f"INSERT INTO {TABLA_LLAVES} (vps_id, llave_id, orden, tipo, consumo, cuota, "
                "agotada, motivo, ultima_vez, agotada_desde) VALUES (:vps, :llave, :orden, "
                ":tipo, :consumo, :cuota, :agotada, :motivo, :ultima, :desde);"
            ), {
                "vps": str(vps_id), "llave": llave["llave_id"], "orden": orden,
                "tipo": llave.get("tipo"), "consumo": int(llave.get("consumo") or 0),
                "cuota": int(llave.get("cuota") or 0), "agotada": bool(llave.get("agotada")),
                "motivo": llave.get("motivo"), "ultima": llave.get("ultima_vez"),
                "desde": llave.get("agotada_desde"),
            })
    return len(llaves)


def leer_estado_llaves() -> pd.DataFrame:
    """Estado publicado por cada VPS (ver guardar_estado_llaves), vacio si no hay tabla."""
    with get_engine().connect() as conn:
        existe = conn.execute(text("SELECT to_regclass(:t);"), {"t": TABLA_LLAVES}).scalar()
        if existe is None:
            return pd.DataFrame()
        return pd.read_sql(text(f"SELECT * FROM {TABLA_LLAVES} ORDER BY vps_id, orden;"), conn)
