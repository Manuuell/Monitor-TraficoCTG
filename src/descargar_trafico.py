"""
Descarga datos de TomTom Traffic Flow para los nodos de Cartagena.
Equivalente Python del PROYECT_1.R original.

Uso:
    TOMTOM_API_KEY=xxx VPS_ID=1 python3 descargar_trafico.py
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

import config
import google_upload


def determinar_turno(dt: datetime) -> str:
    hhmm = dt.hour * 100 + dt.minute
    if hhmm == 0 or hhmm >= 1830:
        return "Turno 4"
    elif hhmm >= 1330:
        return "Turno 3"
    elif hhmm >= 800:
        return "Turno 2"
    else:
        return "Turno 1"


def cargar_nodos(path: Path) -> pd.DataFrame:
    """Lee el Excel de nodos, normaliza columnas y filtra activos con coordenadas validas."""
    df = pd.read_excel(path)

    # Normalizar nombres de columnas (igual que el R original)
    df.columns = [
        str(c).strip().lower().replace(" ", "_") for c in df.columns
    ]
    df.columns = ["".join(ch for ch in c if ch.isalnum() or ch == "_") for c in df.columns]

    requeridas = {"id_nodo", "nombre_nodo", "categoria", "lat", "lon"}
    faltantes = requeridas - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas requeridas en Excel: {faltantes}")

    # Crear columnas opcionales si no existen
    for col in ["prioridad", "activo", "zona", "barrios_que_colinda", "notas", "columna1"]:
        if col not in df.columns:
            df[col] = None

    # Tipos numericos
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")

    # Logica de "activo": acepta varios formatos
    def es_activo(val):
        if pd.isna(val):
            return None
        s = str(val).strip().upper()
        if s in {"TRUE", "T", "SI", "SÍ", "YES", "Y", "1"}:
            return True
        if s in {"FALSE", "F", "NO", "N", "0"}:
            return False
        return None

    activo_txt = df["activo"].apply(es_activo)
    activo_col1 = pd.to_numeric(df["columna1"], errors="coerce").map(
        {1.0: True, 0.0: False}
    )
    df["activo_final"] = activo_txt.fillna(activo_col1).fillna(True)

    # Filtrar
    df = df[df["lat"].notna() & df["lon"].notna()]
    df = df[df["activo_final"] == True]

    if df.empty:
        raise ValueError("No hay nodos activos con coordenadas validas para consultar.")

    return df.reset_index(drop=True)


def consultar_flow(lat: float, lon: float, api_key: str) -> dict:
    """Consulta el endpoint Traffic Flow de TomTom para un punto."""
    url = f"{config.URL_FLOWBASE}/{config.STYLE}/{config.ZOOM}/json"
    params = {
        "key": api_key,
        "point": f"{lat:.6f},{lon:.6f}",
        "unit": config.UNIT,
    }

    try:
        r = requests.get(url, params=params, timeout=config.TIMEOUT_SEG)
    except requests.RequestException as e:
        return {"ok": False, "status": None, "data": None, "error": f"Conexion: {e}"}

    if r.status_code >= 300:
        return {"ok": False, "status": r.status_code, "data": None, "error": r.text[:500]}

    try:
        return {"ok": True, "status": r.status_code, "data": r.json(), "error": None}
    except ValueError:
        return {"ok": False, "status": r.status_code, "data": None, "error": "JSON invalido"}



def extraer_metricas(resp: dict) -> dict:
    """Extrae los campos relevantes de la respuesta TomTom."""
    if not resp["ok"] or not resp["data"]:
        return {}
    fsd = resp["data"].get("flowSegmentData", {}) or {}
    return {
        "currentSpeed": fsd.get("currentSpeed"),
        "freeFlowSpeed": fsd.get("freeFlowSpeed"),
        "currentTravelTime": fsd.get("currentTravelTime"),
        "freeFlowTravelTime": fsd.get("freeFlowTravelTime"),
        "confidence": fsd.get("confidence"),
        "roadClosure": fsd.get("roadClosure"),
        "frc": fsd.get("frc"),
    }


def registrar_log(inicio: datetime, total: int, ok: int, error: str = None) -> None:
    """Agrega una entrada al log JSONL de ejecuciones."""
    entry = {
        "timestamp": inicio.strftime("%Y-%m-%d %H:%M:%S"),
        "vps_id": config.VPS_ID,
        "total_nodos": total,
        "consultas_ok": ok,
        "consultas_error": max(total - ok, 0),
        "estado": "OK" if error is None else "ERROR",
        "error": error,
    }
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    inicio = datetime.now()
    print(f"\n{'='*60}")
    print(f"INICIO DESCARGA TOMTOM - VPS {config.VPS_ID}")
    print(f"Hora: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if not config.API_KEY:
        msg = "TOMTOM_API_KEY no esta configurada"
        print(f"ERROR: {msg}")
        registrar_log(inicio, 0, 0, msg)
        return 1

    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        nodos = cargar_nodos(config.NODOS_PATH)
    except Exception as e:
        print(f"ERROR cargando nodos: {e}")
        registrar_log(inicio, 0, 0, str(e))
        return 1

    total = len(nodos)
    print(f"Nodos activos a consultar: {total}")

    resultados = []
    ok_count = 0

    for idx, nodo in nodos.iterrows():
        resp = consultar_flow(nodo["lat"], nodo["lon"], config.API_KEY)
        metricas = extraer_metricas(resp)

        fila = {
            "id_nodo": nodo.get("id_nodo"),
            "nombre_nodo": nodo.get("nombre_nodo"),
            "categoria": nodo.get("categoria"),
            "prioridad": nodo.get("prioridad"),
            "zona": nodo.get("zona"),
            "barrios_que_colinda": nodo.get("barrios_que_colinda"),
            "notas": nodo.get("notas"),
            "lat": nodo["lat"],
            "lon": nodo["lon"],
            "activo_final": nodo["activo_final"],
            "ok": resp["ok"],
            "http_status": resp["status"],
            # Inicializar metricas en None para mantener orden de columnas estable
            # aunque la API falle y metricas sea {}
            "currentSpeed": None,
            "freeFlowSpeed": None,
            "currentTravelTime": None,
            "freeFlowTravelTime": None,
            "confidence": None,
            "roadClosure": None,
            "frc": None,
            **metricas,
            "consultation_time": inicio.strftime("%Y-%m-%d %H:%M:%S"),
            "vps_id": config.VPS_ID,
            "error_msg": resp["error"],
        }

        # Calculos derivados
        ct = metricas.get("currentTravelTime")
        ft = metricas.get("freeFlowTravelTime")
        cs = metricas.get("currentSpeed")
        fs = metricas.get("freeFlowSpeed")

        if ct is not None and ft is not None:
            fila["delay_abs_seg"] = ct - ft
            fila["delay_rel_pct"] = (100 * (ct - ft) / ft) if ft > 0 else None
        else:
            fila["delay_abs_seg"] = None
            fila["delay_rel_pct"] = None

        if cs is not None and fs is not None and fs > 0:
            fila["velocidad_ratio"] = cs / fs
        else:
            fila["velocidad_ratio"] = None

        # Columnas de tiempo al final para no desplazar las existentes
        fila["fecha"]     = inicio.strftime("%Y-%m-%d")
        fila["hora"]      = inicio.strftime("%H:%M")
        fila["turno"]     = determinar_turno(inicio)
        fila["dia_semana"] = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"][inicio.weekday()]

        resultados.append(fila)
        if resp["ok"]:
            ok_count += 1

        # Pequeno respiro entre llamadas para no saturar
        time.sleep(0.05)

        if (idx + 1) % 20 == 0:
            print(f"  Progreso: {idx + 1}/{total} ({ok_count} OK)")

    # Guardar resultados localmente
    stamp = inicio.strftime("%Y%m%d_%H%M%S")
    out_csv = config.RESULTADOS_DIR / f"TomTom_TrafficFlow_{stamp}.csv"
    df_resultados = pd.DataFrame(resultados)
    df_resultados.to_csv(out_csv, index=False, encoding="utf-8")

    fin = datetime.now()
    duracion = (fin - inicio).total_seconds()

    print(f"\n{'='*60}")
    print(f"FINALIZADO")
    print(f"Archivo local: {out_csv}")
    print(f"Consultas OK: {ok_count}/{total}")
    print(f"Errores: {total - ok_count}")
    print(f"Duracion: {duracion:.1f}s")

    # Subir a Google Drive + Sheets
    if config.SUBIR_A_GOOGLE:
        print(f"\nSubiendo a Google...")
        upload_result = google_upload.subir_resultados(out_csv, df_resultados)
        if upload_result["error"]:
            print(f"  Aviso: {upload_result['error']}")

    # Escritura dual: insertar tambien en PostgreSQL (red de seguridad)
    # No interrumpe el flujo si falla — Sheets sigue siendo el respaldo.
    if config.GUARDAR_EN_DB:
        print(f"\nInsertando en PostgreSQL...")
        try:
            import db  # import diferido: solo si GUARDAR_EN_DB=true
            n_db = db.insertar_dataframe(df_resultados)
            print(f"  [DB] {n_db} filas insertadas en PostgreSQL")
        except Exception as e:
            print(f"  [DB] Aviso: no se pudo insertar en PostgreSQL: {e}")

    print(f"{'='*60}\n")

    registrar_log(inicio, total, ok_count, None if ok_count > 0 else "Todas las consultas fallaron")
    return 0


if __name__ == "__main__":
    sys.exit(main())
