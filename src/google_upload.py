"""
Modulo para subir archivos a Google Drive y agregar filas a Google Sheets
usando OAuth (no Service Account).

Requiere haber corrido primero `python src/autorizar_google.py` para generar
el token.json en la carpeta credenciales/.
"""
from __future__ import annotations

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


def asegurar_encabezados(creds: Credentials, columnas: list) -> bool:
    """Verifica que la primera fila tenga los encabezados correctos; los crea o actualiza si hay columnas nuevas."""
    try:
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        result = service.spreadsheets().values().get(
            spreadsheetId=config.SHEET_ID,
            range=f"{config.SHEET_TAB}!1:1",
        ).execute()

        valores = result.get("values", [])
        encabezado_actual = valores[0] if valores and valores[0] else []

        if not encabezado_actual:
            # Sheet vacio: crear encabezados
            service.spreadsheets().values().update(
                spreadsheetId=config.SHEET_ID,
                range=f"{config.SHEET_TAB}!A1",
                valueInputOption="RAW",
                body={"values": [columnas]},
            ).execute()
            print(f"  [Sheets] Encabezados creados ({len(columnas)} columnas)")
        elif len(encabezado_actual) < len(columnas):
            # Hay columnas nuevas: actualizar el encabezado completo
            service.spreadsheets().values().update(
                spreadsheetId=config.SHEET_ID,
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
    """Agrega las filas del DataFrame al final del Sheet. Devuelve cantidad agregada."""
    try:
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        columnas = df.columns.tolist()
        asegurar_encabezados(creds, columnas)

        # Convertir a lista de listas, reemplazando NaN por string vacio
        # y normalizando booleanos a TRUE/FALSE para consistencia en Sheets
        df_clean = df.fillna("").astype(str)
        df_clean = df_clean.replace({"True": "TRUE", "False": "FALSE"})
        valores = df_clean.values.tolist()

        service.spreadsheets().values().append(
            spreadsheetId=config.SHEET_ID,
            range=f"{config.SHEET_TAB}!A1",
            valueInputOption="RAW",   # RAW evita que Sheets convierta fechas a serial
            insertDataOption="INSERT_ROWS",
            body={"values": valores},
        ).execute()

        return len(valores)
    except HttpError as e:
        print(f"  [Sheets] Error agregando filas: {e}")
        return 0
    except Exception as e:
        print(f"  [Sheets] Error inesperado: {e}")
        return 0


def leer_sheet(n_dias: int = 30) -> pd.DataFrame:
    """Lee los datos del Sheet y filtra a los ultimos n_dias dias."""
    creds = cargar_credenciales()
    if creds is None:
        return pd.DataFrame()
    try:
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        result = service.spreadsheets().values().get(
            spreadsheetId=config.SHEET_ID,
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
        df = pd.DataFrame(rows, columns=headers)

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
