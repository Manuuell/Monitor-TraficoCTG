"""
Modulo para subir archivos a Google Drive y agregar filas a Google Sheets
usando OAuth (no Service Account).

Requiere haber corrido primero `python src/autorizar_google.py` para generar
el token.json en la carpeta credenciales/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config


def cargar_credenciales() -> Credentials | None:
    """Carga el token guardado y lo refresca si esta vencido."""
    if not config.OAUTH_TOKEN_FILE.exists():
        return None

    creds = Credentials.from_authorized_user_file(
        str(config.OAUTH_TOKEN_FILE), config.GOOGLE_SCOPES
    )

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Guardar token actualizado
            with open(config.OAUTH_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"  [Google] No se pudo refrescar token: {e}")
            return None

    return creds


def subir_csv_a_drive(creds: Credentials, csv_path: Path) -> str | None:
    """Sube un CSV a la carpeta Drive configurada. Devuelve el ID del archivo."""
    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        file_metadata = {
            "name": csv_path.name,
            "parents": [config.DRIVE_FOLDER_ID],
        }
        media = MediaFileUpload(str(csv_path), mimetype="text/csv", resumable=False)

        archivo = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        ).execute()

        return archivo.get("id")
    except HttpError as e:
        print(f"  [Drive] Error subiendo: {e}")
        return None
    except Exception as e:
        print(f"  [Drive] Error inesperado: {e}")
        return None


def subir_archivo_a_drive(
    creds: Credentials, path: Path, folder_id: str,
    mimetype: str = "application/octet-stream",
) -> str | None:
    """Sube cualquier archivo a una carpeta Drive especifica. Devuelve el ID."""
    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        file_metadata = {"name": Path(path).name, "parents": [folder_id]}
        media = MediaFileUpload(str(path), mimetype=mimetype, resumable=False)
        archivo = service.files().create(
            body=file_metadata, media_body=media, fields="id",
        ).execute()
        return archivo.get("id")
    except HttpError as e:
        print(f"  [Drive] Error subiendo {Path(path).name}: {e}")
        return None
    except Exception as e:
        print(f"  [Drive] Error inesperado subiendo {Path(path).name}: {e}")
        return None


# ============================================================
# ROTACION DE LIBROS (limite duro de Google: 10.000.000 celdas por hoja de calculo)
# ============================================================
# El limite es POR LIBRO, no por pestana: agregar una pestana nueva no libera
# nada. Al llenarse, el ETL crea "<SHEET_NOMBRE_BASE>_ParteN" en la misma
# carpeta de Drive y sigue escribiendo alli. El libro anterior queda intacto
# como archivo historico.
#
# Los dos VPS no comparten disco, asi que la carpeta de Drive es la fuente de
# verdad: el primero que rota crea la parte, el segundo la encuentra y la
# adopta. El JSON local es solo cache para no listar Drive en cada ejecucion.

MIME_SHEET = "application/vnd.google-apps.spreadsheet"
ESTADO_SHEET_FILE = config.BASE_DIR / "data" / "sheet_activo.json"


def _leer_estado_sheet() -> dict:
    """Puntero local al libro en uso. Vacio mientras no haya habido rotacion."""
    try:
        with open(ESTADO_SHEET_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _guardar_estado_sheet(sheet_id: str, nombre: str, parte: int) -> None:
    try:
        ESTADO_SHEET_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ESTADO_SHEET_FILE, "w") as f:
            json.dump({"sheet_id": sheet_id, "nombre": nombre, "parte": parte}, f, indent=2)
    except OSError as e:
        # Sin cache se vuelve a resolver contra Drive en la proxima rotacion.
        print(f"  [Sheets] No se pudo guardar {ESTADO_SHEET_FILE.name}: {e}")


def sheet_activo() -> str:
    """ID del libro en el que se escribe ahora (el original si no hubo rotacion)."""
    return _leer_estado_sheet().get("sheet_id") or config.SHEET_ID


def parte_activa() -> int:
    """Numero de parte en uso. 1 = libro original."""
    return _leer_estado_sheet().get("parte", 1)


def _es_error_limite(err: Exception) -> bool:
    """True si el error de la API es el rechazo por superar las 10M celdas."""
    texto = str(err)
    return "10000000" in texto or "10,000,000" in texto


def _partes_en_drive(creds: Credentials) -> list:
    """Devuelve [(parte, id, nombre)] de los libros '<base>_ParteN' de la carpeta, ordenado."""
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    consulta = (
        f"'{config.DRIVE_FOLDER_ID}' in parents and trashed = false "
        f"and mimeType = '{MIME_SHEET}' "
        f"and name contains '{config.SHEET_NOMBRE_BASE}_Parte'"
    )
    partes = []
    token = None
    while True:
        resp = service.files().list(
            q=consulta,
            fields="nextPageToken, files(id, name)",
            pageSize=100,
            pageToken=token,
        ).execute()
        for archivo in resp.get("files", []):
            sufijo = archivo["name"].rsplit("_Parte", 1)[-1]
            if sufijo.isdigit():
                partes.append((int(sufijo), archivo["id"], archivo["name"]))
        token = resp.get("nextPageToken")
        if not token:
            break
    return sorted(partes)


def _crear_parte(creds: Credentials, parte: int, columnas: list) -> tuple:
    """Crea el libro de la parte indicada con la pestana y los encabezados listos."""
    nombre = f"{config.SHEET_NOMBRE_BASE}_Parte{parte}"

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    archivo = drive.files().create(
        body={
            "name": nombre,
            "mimeType": MIME_SHEET,
            "parents": [config.DRIVE_FOLDER_ID],
        },
        fields="id",
    ).execute()
    sheet_id = archivo["id"]

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    meta = sheets.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets(properties(sheetId))",
    ).execute()
    gid = meta["sheets"][0]["properties"]["sheetId"]

    # El libro nace como "Hoja 1" de 1000x26; la tabla tiene 29 columnas.
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "updateSheetProperties": {
                "properties": {
                    "sheetId": gid,
                    "title": config.SHEET_TAB,
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": max(len(columnas), 26),
                    },
                },
                "fields": "title,gridProperties(rowCount,columnCount)",
            }
        }]},
    ).execute()

    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{config.SHEET_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [columnas]},
    ).execute()

    return sheet_id, nombre


def rotar_sheet(creds: Credentials, columnas: list) -> str | None:
    """
    Pasa al siguiente libro. Si el otro VPS ya creo la parte siguiente la
    adopta en vez de duplicarla. Devuelve el nuevo SHEET_ID, o None si fallo.
    """
    actual = parte_activa()
    try:
        existentes = _partes_en_drive(creds)
    except Exception as e:
        print(f"  [Sheets] No se pudieron listar las partes en Drive: {e}")
        existentes = []

    posteriores = [p for p in existentes if p[0] > actual]
    if posteriores:
        parte, sheet_id, nombre = posteriores[-1]
        _guardar_estado_sheet(sheet_id, nombre, parte)
        print(f"  [Sheets] Rotacion: se adopta {nombre} (ya creado por el otro VPS)")
        return sheet_id

    siguiente = max([actual] + [p[0] for p in existentes]) + 1
    try:
        sheet_id, nombre = _crear_parte(creds, siguiente, columnas)
    except Exception as e:
        print(f"  [Sheets] No se pudo crear la parte {siguiente}: {e}")
        return None

    _guardar_estado_sheet(sheet_id, nombre, siguiente)
    print(f"  [Sheets] Rotacion: libro lleno, se continua en {nombre} ({sheet_id})")
    return sheet_id


def asegurar_encabezados(
    creds: Credentials, columnas: list, sheet_id: str | None = None,
) -> bool:
    """Verifica que la primera fila tenga los encabezados correctos; los crea o actualiza si hay columnas nuevas."""
    sheet_id = sheet_id or sheet_activo()
    try:
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{config.SHEET_TAB}!1:1",
        ).execute()

        valores = result.get("values", [])
        encabezado_actual = valores[0] if valores and valores[0] else []

        if not encabezado_actual:
            # Sheet vacio: crear encabezados
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{config.SHEET_TAB}!A1",
                valueInputOption="RAW",
                body={"values": [columnas]},
            ).execute()
            print(f"  [Sheets] Encabezados creados ({len(columnas)} columnas)")
        elif len(encabezado_actual) < len(columnas):
            # Hay columnas nuevas: actualizar el encabezado completo
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{config.SHEET_TAB}!A1",
                valueInputOption="RAW",
                body={"values": [columnas]},
            ).execute()
            print(f"  [Sheets] Encabezados actualizados: {len(encabezado_actual)} → {len(columnas)} columnas")
        return True
    except HttpError as e:
        print(f"  [Sheets] Error en encabezados: {e}")
        return False


def agregar_filas_a_sheet(creds: Credentials, df: pd.DataFrame) -> int:
    """
    Agrega las filas del DataFrame al final del libro activo. Si el libro
    alcanzo las 10M celdas, rota al siguiente y reintenta una vez.
    Devuelve cantidad agregada.
    """
    columnas = df.columns.tolist()

    # Convertir a lista de listas, reemplazando NaN por string vacio
    # y normalizando booleanos a TRUE/FALSE para consistencia en Sheets
    df_clean = df.fillna("").astype(str)
    df_clean = df_clean.replace({"True": "TRUE", "False": "FALSE"})
    valores = df_clean.values.tolist()

    sheet_id = sheet_activo()

    for intento in (1, 2):
        try:
            service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            asegurar_encabezados(creds, columnas, sheet_id)

            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"{config.SHEET_TAB}!A1",
                valueInputOption="RAW",   # RAW evita que Sheets convierta fechas a serial
                insertDataOption="INSERT_ROWS",
                body={"values": valores},
            ).execute()

            return len(valores)
        except HttpError as e:
            if intento == 1 and _es_error_limite(e):
                print("  [Sheets] Libro lleno (10M celdas); rotando al siguiente...")
                nuevo = rotar_sheet(creds, columnas)
                if nuevo and nuevo != sheet_id:
                    sheet_id = nuevo
                    continue
            print(f"  [Sheets] Error agregando filas: {e}")
            return 0
        except Exception as e:
            print(f"  [Sheets] Error inesperado: {e}")
            return 0

    return 0


def _leer_un_libro(service, sheet_id: str) -> pd.DataFrame:
    """Lee la pestana de datos de UN libro, sin filtrar ni convertir tipos."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=config.SHEET_TAB,
    ).execute()
    values = result.get("values", [])
    if len(values) < 2:
        return pd.DataFrame()

    headers = list(values[0])
    data_rows = values[1:]

    # Si las filas de datos tienen mas columnas que el encabezado,
    # extender el encabezado con nombres provisionales
    max_data_cols = max((len(r) for r in data_rows), default=0)
    if max_data_cols > len(headers):
        headers += [f"col_{i}" for i in range(len(headers), max_data_cols)]

    n_cols = len(headers)
    rows = [(r + [""] * (n_cols - len(r)))[:n_cols] for r in data_rows]
    return pd.DataFrame(rows, columns=headers)


def libros_para_lectura(creds: Credentials) -> list:
    """
    IDs de todos los libros del historico: el original mas las partes creadas
    por rotacion. Si Drive no responde, al menos devuelve el original y el activo.
    """
    ids = [config.SHEET_ID]
    try:
        for _, sheet_id, _ in _partes_en_drive(creds):
            if sheet_id not in ids:
                ids.append(sheet_id)
    except Exception as e:
        print(f"  [Sheets] No se pudieron listar las partes: {e}")
        activo = sheet_activo()
        if activo not in ids:
            ids.append(activo)
    return ids


def leer_sheet(n_dias: int = 30) -> pd.DataFrame:
    """Lee los datos de todos los libros del historico y filtra a los ultimos n_dias dias."""
    creds = cargar_credenciales()
    if creds is None:
        return pd.DataFrame()
    try:
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        partes = []
        for sheet_id in libros_para_lectura(creds):
            try:
                df_parte = _leer_un_libro(service, sheet_id)
            except Exception as e:
                print(f"  [Sheets] Error leyendo libro {sheet_id}: {e}")
                continue
            if not df_parte.empty:
                partes.append(df_parte)

        if not partes:
            return pd.DataFrame()

        df = partes[0] if len(partes) == 1 else pd.concat(partes, ignore_index=True)

        if "consultation_time" in df.columns:
            # Sheets convierte fechas a serial numerico (dias desde 1899-12-30).
            # Este parser maneja tanto el string original como el serial.
            def _parsear(val):
                if not val or val == "":
                    return pd.NaT
                ts = pd.to_datetime(val, errors="coerce")
                if pd.notna(ts):
                    return ts
                try:
                    f = float(val)
                    if 40000 < f < 80000:          # rango plausible 2009–2119
                        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=f)
                except (ValueError, TypeError):
                    pass
                return pd.NaT

            df["consultation_time"] = df["consultation_time"].apply(_parsear)
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=n_dias)
            df = df[df["consultation_time"] >= cutoff]

        return df.reset_index(drop=True)
    except Exception as e:
        print(f"  [Sheets] Error leyendo: {e}")
        return pd.DataFrame()


def subir_resultados(csv_path: Path, df: pd.DataFrame) -> dict:
    """
    Punto de entrada principal: sube CSV a Drive Y agrega filas al Sheet.
    Devuelve dict con resultados.
    """
    resultado = {
        "drive_ok": False,
        "drive_id": None,
        "sheets_ok": False,
        "filas_agregadas": 0,
        "error": None,
    }

    if not config.SUBIR_A_GOOGLE:
        resultado["error"] = "SUBIR_A_GOOGLE=false (deshabilitado)"
        return resultado

    creds = cargar_credenciales()
    if creds is None:
        resultado["error"] = "No hay credenciales Google. Corre: python src/autorizar_google.py"
        return resultado

    # Subir CSV a Drive
    drive_id = subir_csv_a_drive(creds, csv_path)
    if drive_id:
        resultado["drive_ok"] = True
        resultado["drive_id"] = drive_id
        print(f"  [Drive] CSV subido: {csv_path.name} (id: {drive_id})")

    # Agregar filas al Sheet
    filas = agregar_filas_a_sheet(creds, df)
    if filas > 0:
        resultado["sheets_ok"] = True
        resultado["filas_agregadas"] = filas
        print(f"  [Sheets] {filas} filas agregadas al Sheet")

    return resultado
