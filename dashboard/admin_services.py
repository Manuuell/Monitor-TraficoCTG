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


def logs_vps2_desde_mediciones(df: pd.DataFrame) -> pd.DataFrame:
    """Reconstruye ejecuciones del VPS 2 a partir de sus mediciones."""
    columnas = [
        "timestamp", "vps_id", "total_nodos", "consultas_ok",
        "consultas_error", "estado", "error",
    ]
    if df.empty or not {"consultation_time", "vps_id"}.issubset(df.columns):
        return pd.DataFrame(columns=columnas)
    vps2 = df[df["vps_id"].astype(str) == "2"].copy()
    if vps2.empty:
        return pd.DataFrame(columns=columnas)
    vps2["ok_bool"] = mascara_ok(vps2)
    ejecuciones = vps2.groupby("consultation_time").agg(
        total_nodos=("ok_bool", "count"),
        consultas_ok=("ok_bool", "sum"),
    ).reset_index()
    ejecuciones["consultas_error"] = (
        ejecuciones["total_nodos"] - ejecuciones["consultas_ok"]
    )
    ejecuciones["vps_id"] = "2"
    ejecuciones["estado"] = ejecuciones["consultas_error"].map(
        lambda cantidad: "ERROR" if cantidad else "OK"
    )
    ejecuciones["error"] = None
    ejecuciones = ejecuciones.rename(columns={"consultation_time": "timestamp"})
    return ejecuciones[columnas]


def combinar_ejecuciones(logs: pd.DataFrame, mediciones: pd.DataFrame) -> pd.DataFrame:
    vps2 = logs_vps2_desde_mediciones(mediciones)
    partes = [parte for parte in (logs, vps2) if not parte.empty]
    if not partes:
        return pd.DataFrame()
    combinado = pd.concat(partes, ignore_index=True, sort=False)
    combinado["timestamp"] = pd.to_datetime(combinado["timestamp"], errors="coerce")
    return combinado.dropna(subset=["timestamp"]).sort_values("timestamp")


def resumen_operativo(logs: pd.DataFrame, mediciones: pd.DataFrame) -> dict:
    """Calcula consumo, resultados y última ejecución de cada VPS."""
    def sumar(df: pd.DataFrame, columna: str) -> int:
        if df.empty or columna not in df.columns:
            return 0
        return int(pd.to_numeric(df[columna], errors="coerce").fillna(0).sum())

    hoy = datetime.now().date()
    logs_hoy = (
        logs[logs["timestamp"].dt.date == hoy].copy()
        if not logs.empty else pd.DataFrame()
    )
    llamadas_1 = sumar(logs_hoy, "total_nodos")
    ok_1 = sumar(logs_hoy, "consultas_ok")
    ultima_1 = logs["timestamp"].max() if not logs.empty else pd.NaT

    mediciones_hoy = pd.DataFrame()
    if not mediciones.empty and {"consultation_time", "vps_id"}.issubset(mediciones.columns):
        mediciones_hoy = mediciones[
            (mediciones["consultation_time"].dt.date == hoy)
            & (mediciones["vps_id"].astype(str) == "2")
        ].copy()
    llamadas_2 = len(mediciones_hoy)
    ok_2 = int(mascara_ok(mediciones_hoy).sum())
    ultima_2 = (
        mediciones_hoy["consultation_time"].max()
        if not mediciones_hoy.empty else pd.NaT
    )

    ejec_1 = len(logs_hoy)
    ejec_2 = (
        mediciones_hoy["consultation_time"].nunique()
        if not mediciones_hoy.empty else 0
    )
    candidatos = [fecha for fecha in (ultima_1, ultima_2) if pd.notna(fecha)]
    ultima = max(candidatos) if candidatos else pd.NaT

    return {
        "vps1": {
            "llamadas": llamadas_1,
            "ok": ok_1,
            "fallidas": max(llamadas_1 - ok_1, 0),
            "ejecuciones": ejec_1,
            "ultima": ultima_1,
        },
        "vps2": {
            "llamadas": llamadas_2,
            "ok": ok_2,
            "fallidas": max(llamadas_2 - ok_2, 0),
            "ejecuciones": ejec_2,
            "ultima": ultima_2,
        },
        "ejecuciones": ejec_1 + ejec_2,
        "ultima": ultima,
    }


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


def estado_api_keys(mediciones: pd.DataFrame | None = None) -> dict:
    """Inventario seguro de claves: nunca devuelve el valor completo."""
    resumen_rotacion = rotacion_llaves.resumen()
    estado_por_id = {fila["llave_id"]: fila for fila in resumen_rotacion}
    telemetria_mensual = rotacion_llaves.ESTADO_FILE.exists()
    uso_hoy: dict[str, int] = {}
    if mediciones is not None and not mediciones.empty and "llave_id" in mediciones.columns:
        uso_hoy = {
            str(llave).strip(): int(cantidad)
            for llave, cantidad in mediciones["llave_id"].dropna().value_counts().items()
            if str(llave).strip()
        }
    inventario: dict[str, dict] = {}

    def registrar(llave: str, servicio: str, proposito: str) -> None:
        if not llave:
            return
        identificador = rotacion_llaves.mask(llave)
        fila = inventario.setdefault(identificador, {
            "identificador": identificador,
            "servicio": servicio,
            "propositos": [],
        })
        if proposito not in fila["propositos"]:
            fila["propositos"].append(proposito)

    for llave in config.API_KEYS:
        registrar(llave, "TomTom Traffic Flow", "Rotación principal")
    for llave in config.API_KEYS_RESERVA:
        registrar(llave, "TomTom Traffic Flow", "Reserva")
    if config.API_KEY and config.API_KEY not in config.API_KEYS:
        registrar(config.API_KEY, "TomTom Traffic Flow", "Compatibilidad local")
    for llave in config.API_KEYS_RED:
        registrar(llave, "TomTom Routing", "Captura de red")
    if config.GOOGLE_STREETVIEW_KEY:
        registrar(config.GOOGLE_STREETVIEW_KEY, "Google Street View", "Fotos de nodos")

    filas = []
    for numero, (identificador, base) in enumerate(inventario.items(), start=1):
        rotacion = estado_por_id.get(identificador)
        consumo_hoy = uso_hoy.get(identificador)
        if rotacion and telemetria_mensual:
            consumo = int(rotacion.get("consumo", 0))
            cuota = int(rotacion.get("cuota", 0))
            pct = consumo / cuota * 100 if cuota else 0
            estado = "AGOTADA" if rotacion.get("agotada") else "ACTIVA"
            detalle = rotacion.get("motivo") or "Disponible para rotación"
            ultima = rotacion.get("ultima_vez") or "Sin uso registrado"
        else:
            consumo = None
            cuota = None
            pct = None
            estado = "ACTIVA HOY" if consumo_hoy else "CONFIGURADA"
            detalle = (
                "Uso diario reconstruido desde Google Sheets"
                if consumo_hoy else "Uso no registrado por el ETL"
            )
            ultima = "Sin telemetría local"
        filas.append({
            "numero": numero,
            **base,
            "proposito": " · ".join(base["propositos"]),
            "consumo": consumo,
            "cuota": cuota,
            "pct": pct,
            "estado": estado,
            "detalle": detalle,
            "ultima_vez": ultima,
            "consumo_hoy": consumo_hoy,
        })
    identificadas = sum(
        cantidad for llave_id, cantidad in uso_hoy.items()
        if llave_id in inventario
    )
    total_hoy = len(mediciones) if mediciones is not None else 0
    return {
        "mes": datetime.now().strftime("%Y-%m"),
        "telemetria_mensual": telemetria_mensual,
        "total_hoy": total_hoy,
        "sin_identificar": max(total_hoy - identificadas, 0),
        "claves": filas,
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
