"""Lecturas y diagnósticos de solo lectura para el panel administrativo."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config  # noqa: E402
import google_upload  # noqa: E402
import rotacion_llaves  # noqa: E402


COLUMNAS_EJECUCION = [
    "timestamp", "vps_id", "total_nodos", "consultas_ok",
    "consultas_error", "estado", "error",
]


def ejecuciones_vacias() -> pd.DataFrame:
    """Crea el esquema vacio conservando tipos aptos para calculos."""
    return pd.DataFrame({
        "timestamp": pd.Series(dtype="datetime64[ns]"),
        "vps_id": pd.Series(dtype="string"),
        "total_nodos": pd.Series(dtype="int64"),
        "consultas_ok": pd.Series(dtype="int64"),
        "consultas_error": pd.Series(dtype="int64"),
        "estado": pd.Series(dtype="string"),
        "error": pd.Series(dtype="object"),
    })


@st.cache_data(ttl=60, show_spinner=False)
def cargar_logs() -> pd.DataFrame:
    """Carga el registro local del VPS 1 y descarta líneas incompletas."""
    if not config.LOG_FILE.exists():
        return pd.DataFrame()
    entradas = []
    with config.LOG_FILE.open(encoding="utf-8") as archivo:
        for linea in archivo:
            try:
                entradas.append(json.loads(linea))
            except (json.JSONDecodeError, TypeError):
                continue
    if not entradas:
        return pd.DataFrame()
    df = pd.DataFrame(entradas)
    df["timestamp"] = pd.to_datetime(df.get("timestamp"), errors="coerce")
    return df.dropna(subset=["timestamp"]).sort_values("timestamp")


@st.cache_data(ttl=300, show_spinner=False)
def cargar_mediciones_recientes(n_dias: int = 1) -> tuple[pd.DataFrame, str]:
    """Lee PostgreSQL o solo la cola reciente del Sheet activo como respaldo."""
    if getattr(config, "FUENTE_DASHBOARD", "sheets") == "db":
        try:
            import db

            df = db.leer_datos(n_dias=n_dias)
            if not df.empty:
                return df, "PostgreSQL"
        except Exception:
            pass

    try:
        estado = capacidad_sheets()
        if not estado.get("ok"):
            return pd.DataFrame(), "Google Sheets no disponible"
        activo = capacidad_sheet(estado)
        credenciales = google_upload.cargar_credenciales()
        if credenciales is None:
            return pd.DataFrame(), "Google Sheets sin credenciales"

        from googleapiclient.discovery import build

        # Tres días de margen cubren cambios de horario sin descargar todo el
        # histórico (el libro original ronda los diez millones de celdas).
        ventana = max((n_dias + 2) * 113 * 28, 10_000)
        fila_final = max(int(activo.get("filas", 0)), 2)
        fila_inicial = max(2, fila_final - ventana + 1)
        servicio = build("sheets", "v4", credentials=credenciales, cache_discovery=False)
        respuesta = servicio.spreadsheets().values().batchGet(
            spreadsheetId=activo["sheet_id"],
            ranges=[
                f"{config.SHEET_TAB}!1:1",
                f"{config.SHEET_TAB}!A{fila_inicial}:AZ{fila_final}",
            ],
        ).execute()
        rangos = respuesta.get("valueRanges", [])
        encabezados = (rangos[0].get("values") or [[]])[0] if rangos else []
        filas = rangos[1].get("values", []) if len(rangos) > 1 else []
        if not encabezados or not filas:
            return pd.DataFrame(), f"Google Sheets · Parte {activo['parte']}"
        ancho = len(encabezados)
        normalizadas = [(fila + [""] * ancho)[:ancho] for fila in filas]
        df = pd.DataFrame(normalizadas, columns=encabezados)
        if "consultation_time" in df.columns:
            df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
            desde = pd.Timestamp.now().normalize() - pd.Timedelta(days=max(n_dias - 1, 0))
            df = df[df["consultation_time"] >= desde]
        return df, f"Google Sheets · Parte {activo['parte']}"
    except Exception:
        return pd.DataFrame(), "Google Sheets no disponible"


def mascara_ok(df: pd.DataFrame) -> pd.Series:
    if df.empty or "ok" not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    return df["ok"].astype(str).str.strip().str.lower().isin(["true", "1"])


def ejecuciones_desde_mediciones(df: pd.DataFrame) -> pd.DataFrame:
    """Reconstruye ejecuciones de todos los VPS a partir de mediciones."""
    if df.empty or not {"consultation_time", "vps_id"}.issubset(df.columns):
        return ejecuciones_vacias()
    datos = df.copy()
    datos["consultation_time"] = pd.to_datetime(
        datos["consultation_time"], errors="coerce"
    )
    datos = datos.dropna(subset=["consultation_time"])
    if datos.empty:
        return ejecuciones_vacias()
    datos["vps_id"] = datos["vps_id"].astype(str)
    datos["ok_bool"] = mascara_ok(datos)
    ejecuciones = datos.groupby(["consultation_time", "vps_id"]).agg(
        total_nodos=("ok_bool", "count"),
        consultas_ok=("ok_bool", "sum"),
    ).reset_index()
    ejecuciones["consultas_error"] = (
        ejecuciones["total_nodos"] - ejecuciones["consultas_ok"]
    )
    ejecuciones["estado"] = "OK"
    parcial = (ejecuciones["consultas_ok"] > 0) & (ejecuciones["consultas_error"] > 0)
    fallida = ejecuciones["consultas_ok"] <= 0
    ejecuciones.loc[parcial, "estado"] = "PARCIAL"
    ejecuciones.loc[fallida, "estado"] = "ERROR"
    if "error_msg" in datos.columns:
        errores = (
            datos.assign(error_msg=datos["error_msg"].fillna("").astype(str).str.strip())
            .query("error_msg != ''")
            .groupby(["consultation_time", "vps_id"])["error_msg"]
            .first()
        )
        ejecuciones["error"] = [
            errores.get((fila.consultation_time, fila.vps_id))
            for fila in ejecuciones.itertuples()
        ]
    else:
        ejecuciones["error"] = None
    ejecuciones = ejecuciones.rename(columns={"consultation_time": "timestamp"})
    return ejecuciones[COLUMNAS_EJECUCION]


def logs_vps2_desde_mediciones(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibilidad: devuelve solo las ejecuciones reconstruidas del VPS 2."""
    ejecuciones = ejecuciones_desde_mediciones(df)
    return ejecuciones[ejecuciones["vps_id"].astype(str) == "2"].copy()


def normalizar_ejecuciones(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos y deriva OK/PARCIAL/ERROR de los conteos reales."""
    if df.empty:
        return ejecuciones_vacias()
    datos = df.copy()
    for columna in COLUMNAS_EJECUCION:
        if columna not in datos.columns:
            datos[columna] = None
    datos["timestamp"] = pd.to_datetime(datos["timestamp"], errors="coerce")
    datos["vps_id"] = datos["vps_id"].fillna("?").astype(str)
    estado_original = datos["estado"].fillna("").astype(str).str.upper()
    for columna in ["total_nodos", "consultas_ok", "consultas_error"]:
        datos[columna] = pd.to_numeric(datos[columna], errors="coerce").fillna(0).astype(int)
    # Algunos logs antiguos no guardaban consultas_error.
    sin_conteo = (datos["consultas_error"] == 0) & (
        datos["total_nodos"] > datos["consultas_ok"]
    )
    datos.loc[sin_conteo, "consultas_error"] = (
        datos.loc[sin_conteo, "total_nodos"] - datos.loc[sin_conteo, "consultas_ok"]
    )
    datos["estado"] = "OK"
    error_explicito = estado_original.eq("ERROR")
    parcial = (
        (datos["consultas_ok"] > 0)
        & (datos["consultas_error"] > 0)
        & ~error_explicito
    )
    fallida = error_explicito | (
        (datos["consultas_ok"] <= 0) & (datos["total_nodos"] > 0)
    )
    datos.loc[parcial, "estado"] = "PARCIAL"
    datos.loc[fallida, "estado"] = "ERROR"
    return (
        datos.dropna(subset=["timestamp"])[COLUMNAS_EJECUCION]
        .sort_values("timestamp", kind="stable")
        .reset_index(drop=True)
    )


def combinar_ejecuciones(logs: pd.DataFrame, mediciones: pd.DataFrame) -> pd.DataFrame:
    reconstruidas = ejecuciones_desde_mediciones(mediciones)
    partes = [parte for parte in (reconstruidas, logs) if not parte.empty]
    if not partes:
        return ejecuciones_vacias()
    combinado = pd.concat(partes, ignore_index=True, sort=False)
    combinado = normalizar_ejecuciones(combinado)
    # El log local se concatena al final y conserva su detalle cuando coincide
    # con el resumen reconstruido desde PostgreSQL/CSV.
    return combinado.drop_duplicates(["timestamp", "vps_id"], keep="last")


def _ejecuciones_desde_csv_local(n_dias: int) -> pd.DataFrame:
    """Reconstruye las corridas guardadas localmente sin consultar Internet."""
    desde = pd.Timestamp.now().normalize() - pd.Timedelta(days=max(n_dias - 1, 0))
    partes = []
    for path in sorted(config.RESULTADOS_DIR.glob("*.csv")):
        try:
            fecha_archivo = datetime.strptime(
                "_".join(path.stem.rsplit("_", 2)[-2:]), "%Y%m%d_%H%M%S"
            )
            if fecha_archivo < desde.to_pydatetime():
                continue
        except ValueError:
            pass
        try:
            partes.append(pd.read_csv(path))
        except (OSError, ValueError, pd.errors.ParserError):
            continue
    if not partes:
        return ejecuciones_vacias()
    mediciones = pd.concat(partes, ignore_index=True)
    return ejecuciones_desde_mediciones(mediciones)


@st.cache_data(ttl=60, show_spinner=False)
def cargar_ejecuciones_recientes(n_dias: int = 7) -> tuple[pd.DataFrame, str]:
    """Carga un resumen ligero de corridas sin bloquearse con Google.

    PostgreSQL agrupa en el servidor y devuelve unas pocas filas. Si no esta
    configurado o no responde, se usan el log y los CSV locales. Las consultas
    a Drive/Sheets quedan para el diagnostico solicitado por el usuario.
    """
    logs = cargar_logs()
    desde = pd.Timestamp.now() - pd.Timedelta(days=n_dias)
    if not logs.empty:
        logs = normalizar_ejecuciones(logs)
        logs = logs[logs["timestamp"] >= desde]

    resumen_db = ejecuciones_vacias()
    fuente = "log local"
    intentar_db = bool(
        getattr(config, "DB_PASSWORD", "")
        or getattr(config, "GUARDAR_EN_DB", False)
        or getattr(config, "FUENTE_DASHBOARD", "") == "db"
    )
    if intentar_db:
        try:
            import db

            resumen_db = db.leer_resumen_ejecuciones(n_dias=n_dias)
            fuente = "PostgreSQL + log local"
        except Exception as error:
            print(f"  [Admin] PostgreSQL no disponible: {error}")

    partes = [parte for parte in (resumen_db, logs) if not parte.empty]
    if not resumen_db.empty:
        combinado = normalizar_ejecuciones(pd.concat(partes, ignore_index=True, sort=False))
        return combinado.drop_duplicates(["timestamp", "vps_id"], keep="last"), fuente

    locales = _ejecuciones_desde_csv_local(n_dias)
    partes = [parte for parte in (locales, logs) if not parte.empty]
    if not partes:
        return ejecuciones_vacias(), "sin fuente disponible"
    combinado = normalizar_ejecuciones(pd.concat(partes, ignore_index=True, sort=False))
    return (
        combinado.drop_duplicates(["timestamp", "vps_id"], keep="last"),
        "CSV + log local" if not locales.empty else "log local",
    )


def resumen_operativo_ejecuciones(ejecuciones: pd.DataFrame) -> dict:
    """Indicadores diarios y ultima corrida calculados desde el resumen."""
    datos = normalizar_ejecuciones(ejecuciones)
    hoy = datetime.now().date()
    salida = {}
    for vps_id in ("1", "2"):
        vps = datos[datos["vps_id"] == vps_id]
        vps_hoy = vps[vps["timestamp"].dt.date == hoy]
        salida[f"vps{vps_id}"] = {
            "llamadas": int(vps_hoy["total_nodos"].sum()),
            "ok": int(vps_hoy["consultas_ok"].sum()),
            "fallidas": int(vps_hoy["consultas_error"].sum()),
            "ejecuciones": len(vps_hoy),
            "ultima": vps["timestamp"].max() if not vps.empty else pd.NaT,
        }
    candidatos = [
        salida["vps1"]["ultima"], salida["vps2"]["ultima"],
    ]
    candidatos = [fecha for fecha in candidatos if pd.notna(fecha)]
    salida["ejecuciones"] = (
        salida["vps1"]["ejecuciones"] + salida["vps2"]["ejecuciones"]
    )
    salida["ultima"] = max(candidatos) if candidatos else pd.NaT
    return salida


def resumen_operativo(logs: pd.DataFrame, mediciones: pd.DataFrame) -> dict:
    """Compatibilidad con el calculo anterior basado en logs + mediciones."""
    return resumen_operativo_ejecuciones(combinar_ejecuciones(logs, mediciones))


def ultimas_ejecuciones(ejecuciones: pd.DataFrame, vps_id: str, limite: int = 20) -> pd.DataFrame:
    datos = normalizar_ejecuciones(ejecuciones)
    return (
        datos[datos["vps_id"] == str(vps_id)]
        .sort_values("timestamp", ascending=False)
        .head(limite)
        .reset_index(drop=True)
    )


def ejecuciones_por_hora(ejecuciones: pd.DataFrame, n_dias: int = 7) -> pd.DataFrame:
    """Cuenta corridas completas, parciales y fallidas por hora del dia."""
    datos = normalizar_ejecuciones(ejecuciones)
    desde = pd.Timestamp.now() - pd.Timedelta(days=n_dias)
    datos = datos[datos["timestamp"] >= desde].copy()
    columnas = ["hora", "completas", "parciales", "fallidas", "total"]
    if datos.empty:
        return pd.DataFrame(columns=columnas)
    datos["hora"] = datos["timestamp"].dt.strftime("%H:00")
    tabla = (
        datos.groupby(["hora", "estado"]).size().unstack(fill_value=0)
        .rename(columns={"OK": "completas", "PARCIAL": "parciales", "ERROR": "fallidas"})
    )
    for columna in ["completas", "parciales", "fallidas"]:
        if columna not in tabla.columns:
            tabla[columna] = 0
    tabla = tabla.reset_index()
    tabla["total"] = tabla[["completas", "parciales", "fallidas"]].sum(axis=1)
    return tabla[columnas].sort_values("hora").reset_index(drop=True)


def errores_recientes(ejecuciones: pd.DataFrame, n_dias: int = 7) -> pd.DataFrame:
    """Incluye fallos totales y parciales con al menos un nodo fallido."""
    datos = normalizar_ejecuciones(ejecuciones)
    desde = pd.Timestamp.now() - pd.Timedelta(days=n_dias)
    tiene_detalle = datos["error"].fillna("").astype(str).str.strip().ne("")
    mascara = (datos["timestamp"] >= desde) & (
        (datos["consultas_error"] > 0)
        | (datos["estado"] != "OK")
        | tiene_detalle
    )
    return datos[mascara].sort_values("timestamp", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def verificar_google() -> dict:
    try:
        credenciales = google_upload.cargar_credenciales()
        if credenciales is None:
            return {
                "ok": False,
                "estado": "No conectado",
                "detalle": "No se encontró un token OAuth válido.",
            }
        if credenciales.valid:
            return {
                "ok": True,
                "estado": "Activo",
                "detalle": "Drive y Sheets están disponibles.",
            }
        return {
            "ok": False,
            "estado": "Expirado",
            "detalle": "La autorización requiere renovación.",
        }
    except Exception as error:
        return {"ok": False, "estado": "Error", "detalle": str(error)[:160]}


@st.cache_data(ttl=3600, show_spinner=False)
def capacidad_sheets() -> dict:
    """Consulta la capacidad del libro original y de todas sus partes en Drive."""
    limite = 10_000_000
    try:
        credenciales = google_upload.cargar_credenciales()
        if credenciales is None:
            return {"ok": False, "detalle": "Sin credenciales Google"}

        from googleapiclient.discovery import build

        servicio = build("sheets", "v4", credentials=credenciales, cache_discovery=False)
        libros = [(1, config.SHEET_ID, config.SHEET_NOMBRE_BASE)]
        for parte, sheet_id, nombre in google_upload._partes_en_drive(credenciales):
            if sheet_id not in {libro[1] for libro in libros}:
                libros.append((parte, sheet_id, nombre))

        resultados = []
        errores = []
        parte_activa = max((parte for parte, _, _ in libros), default=1)
        for parte, sheet_id, nombre_drive in sorted(libros):
            try:
                meta = servicio.spreadsheets().get(
                    spreadsheetId=sheet_id,
                    fields="properties(title),sheets(properties(title,gridProperties))",
                ).execute()
                celdas = 0
                columnas_datos = 0
                filas_datos = 0
                for hoja in meta.get("sheets", []):
                    propiedades = hoja.get("properties", {})
                    grilla = propiedades.get("gridProperties", {})
                    filas = int(grilla.get("rowCount", 0))
                    columnas = int(grilla.get("columnCount", 0))
                    celdas += filas * columnas
                    if propiedades.get("title") == config.SHEET_TAB:
                        columnas_datos = columnas
                        filas_datos = filas
                columnas_datos = columnas_datos or 29
                consumo_diario = 113 * 28 * columnas_datos
                restantes = max(limite - celdas, 0)
                dias = int(restantes / consumo_diario) if consumo_diario else None
                fecha_llena = (
                    (datetime.now() + timedelta(days=dias)).strftime("%d/%m/%Y")
                    if dias is not None else None
                )
                resultados.append({
                    "ok": True,
                    "celdas": celdas,
                    "limite": limite,
                    "pct": celdas / limite * 100,
                    "dias": dias,
                    "fecha_llena": fecha_llena,
                    "parte": parte,
                    "nombre": meta.get("properties", {}).get("title", nombre_drive),
                    "sheet_id": sheet_id,
                    "filas": filas_datos,
                    "columnas": columnas_datos,
                    "activa": parte == parte_activa,
                })
            except Exception as error:
                errores.append(f"Parte {parte}: {str(error)[:120]}")

        if not resultados:
            return {"ok": False, "detalle": "; ".join(errores) or "Sin libros accesibles"}
        return {"ok": True, "partes": resultados, "errores": errores}
    except Exception as error:
        return {"ok": False, "detalle": str(error)[:160]}


def capacidad_sheet(estado: dict | None = None) -> dict:
    """Compatibilidad: devuelve la parte activa (la más reciente en Drive)."""
    estado = estado or capacidad_sheets()
    if not estado.get("ok"):
        return estado
    partes = estado.get("partes", [])
    return next((parte for parte in partes if parte.get("activa")), partes[-1])


def _tarjeta_llave(fila: dict) -> dict:
    """Datos de una llave para su tarjeta: consumo del mes frente a su limite."""
    consumo = int(fila.get("consumo") or 0)
    cuota = int(fila.get("cuota") or 0)
    agotada = bool(fila.get("agotada"))
    if agotada:
        estado = "AGOTADA"
    else:
        estado = "EN USO" if fila.get("tipo") == "principal" else "RESERVA"
    return {
        "identificador": fila["llave_id"],
        "tipo": fila.get("tipo") or "principal",
        "consumo": consumo,
        "cuota": cuota,
        "pct": consumo / cuota * 100 if cuota else None,
        "estado": estado,
        "motivo": fila.get("motivo") if agotada else None,
        "ultima_vez": fila.get("ultima_vez") or "Sin uso registrado",
    }


@st.cache_data(ttl=60, show_spinner=False)
def estado_api_keys() -> dict:
    """
    Llaves TomTom de cada VPS, en uso y de reserva, con su consumo del mes y
    su limite. Cada VPS solo conoce las de su .env, asi que cada ETL publica
    su estado en PostgreSQL al final de la corrida (db.guardar_estado_llaves)
    y aqui se leen las de todos. Si este VPS aun no publico, se usa su estado
    local. Nunca devuelve el valor completo de una llave.
    """
    publicado, error = pd.DataFrame(), None
    consultar_db = bool(
        getattr(config, "DB_PASSWORD", "")
        or getattr(config, "GUARDAR_EN_DB", False)
        or getattr(config, "FUENTE_DASHBOARD", "") == "db"
    )
    if consultar_db:
        try:
            import db

            publicado = db.leer_estado_llaves()
        except Exception as e:
            error = str(e)[:160]

    por_vps: dict[str, dict] = {}
    for fila in publicado.to_dict("records"):
        vps = por_vps.setdefault(str(fila["vps_id"]), {
            "vps_id": str(fila["vps_id"]), "actualizado": fila.get("actualizado"),
            "principal": [], "reserva": [],
        })
        tarjeta = _tarjeta_llave(fila)
        vps["reserva" if tarjeta["tipo"] == "reserva" else "principal"].append(tarjeta)

    local = str(config.VPS_ID)
    if local not in por_vps and (config.API_KEYS or config.API_KEYS_RESERVA):
        vps = por_vps[local] = {"vps_id": local, "actualizado": None, "principal": [], "reserva": []}
        for fila in rotacion_llaves.resumen():
            tarjeta = _tarjeta_llave(fila)
            vps["reserva" if tarjeta["tipo"] == "reserva" else "principal"].append(tarjeta)

    for vps_id, vps in por_vps.items():
        vps["turnos"] = list(config.VPS_TURNOS.get(vps_id, []))
        actualizado = vps.get("actualizado")
        vps["actualizado"] = (
            pd.Timestamp(actualizado).strftime("%d/%m %H:%M")
            if actualizado is not None and pd.notna(actualizado) else "estado local"
        )
    return {
        "mes": datetime.now().strftime("%Y-%m"),
        "vps": [por_vps[k] for k in sorted(por_vps)],
        "error": error,
    }


def proxima_ejecucion() -> datetime | None:
    ahora = datetime.now()
    candidatos = []
    for horas in config.HORARIOS.values():
        for hora in horas:
            horas_num, minutos_num = map(int, hora.split(":"))
            ejecucion = ahora.replace(
                hour=horas_num, minute=minutos_num, second=0, microsecond=0
            )
            if hora == "00:00" and ahora.hour > 12:
                ejecucion += timedelta(days=1)
            if ejecucion > ahora:
                candidatos.append(ejecucion)
    return min(candidatos) if candidatos else None


def archivos_recientes(limite: int = 8) -> pd.DataFrame:
    archivos = sorted(config.RESULTADOS_DIR.glob("*.csv"), reverse=True)[:limite]
    filas = []
    for archivo in archivos:
        stat = archivo.stat()
        filas.append({
            "Archivo": archivo.name,
            "Tamaño": f"{stat.st_size / 1024:.1f} KB",
            "Modificado": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
        })
    return pd.DataFrame(filas)


def diagnostico_configuracion() -> dict:
    """Estado visible sin revelar claves, tokens ni contraseñas."""
    return {
        "Fuente del dashboard": getattr(config, "FUENTE_DASHBOARD", "sheets"),
        "Subida a Google": bool(config.SUBIR_A_GOOGLE),
        "Escritura PostgreSQL": bool(config.GUARDAR_EN_DB),
        "Subida a Firestore": bool(config.SUBIR_A_FIRESTORE),
        "Llaves TomTom activas": len(config.API_KEYS),
        "Llaves TomTom de reserva": len(config.API_KEYS_RESERVA),
        "Token Google presente": config.OAUTH_TOKEN_FILE.exists(),
        "Archivo de nodos presente": config.NODOS_PATH.exists(),
        "Directorio de resultados": config.RESULTADOS_DIR.exists(),
        "Log de ejecuciones": config.LOG_FILE.exists(),
        "VPS configurado": str(config.VPS_ID),
        "Protección del panel": bool(os.environ.get("ADMIN_PASSWORD", "")),
    }


def probar_postgresql() -> dict:
    try:
        import db

        filas = db.contar_filas()
        minimo, maximo = db.rango_fechas()
        return {
            "ok": True,
            "detalle": f"Conexión activa · {filas:,} filas",
            "desde": minimo,
            "hasta": maximo,
        }
    except Exception as error:
        return {"ok": False, "detalle": str(error)[:200]}
