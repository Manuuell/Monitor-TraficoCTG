"""
Repara las filas de un libro del Google Sheet escritas antes de que su
encabezado ganara una columna en medio, y que por eso se leen corridas.

Caso que lo motivo: el libro TomTom_Cartagena_Datos_Parte2 se creo el
08/09/2026 con 29 columnas. El 19/09 la rotacion de llaves agrego llave_id
entre vps_id y error_msg, y el encabezado se reemplazo por el de 30 columnas
sin mover las filas ya escritas. Desde error_msg hacia la derecha, esas filas
(2 a 64.863) se leen una columna corrida: la fecha cae en velocidad_ratio.
PostgreSQL no se afecto (el ETL inserta por nombre de columna).

La reparacion inserta una celda vacia en la columna nueva SOLO en las filas
viejas, corriendo sus celdas un lugar a la derecha (InsertRange de la API de
Sheets: una operacion, no reescribe ni convierte ningun valor). Detecta las
filas viejas porque su ultima columna (dia_semana) esta vacia, y exige que
formen un bloque contiguo desde la fila 2; si no, no toca nada.

Por defecto solo diagnostica. Con --aplicar, primero copia el libro como
respaldo en Drive y despues repara.

Uso:
    python3 reparar_columnas_sheet.py                      # diagnostico
    python3 reparar_columnas_sheet.py --aplicar            # respaldo + reparacion
    python3 reparar_columnas_sheet.py --libro NOMBRE --columna llave_id
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import config
import google_upload
from googleapiclient.discovery import build

# Filas por lectura: columnas enteras de cientos de miles de filas repetidas
# comprimen tanto que httplib2 las rechaza por seguridad
BLOQUE = 20_000
MASCARA_LLAVE = re.compile(r"[A-Za-z0-9]{8}")


def _letra(i: int) -> str:
    """Indice de columna (0 = A) a letra de A1."""
    letras = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        letras = chr(ord("A") + r) + letras
    return letras


def _columna(svc, sheet_id: str, i: int, filas: int) -> list:
    valores = []
    for desde in range(2, filas + 1, BLOQUE):
        hasta = min(desde + BLOQUE - 1, filas)
        rango = f"{config.SHEET_TAB}!{_letra(i)}{desde}:{_letra(i)}{hasta}"
        r = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range=rango).execute()
        bloque = [x[0] if x else "" for x in r.get("values", [])]
        valores += bloque + [""] * (hasta - desde + 1 - len(bloque))
    return valores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--libro", default=f"{config.SHEET_NOMBRE_BASE}_Parte2")
    parser.add_argument("--columna", default="llave_id",
                        help="columna que se agrego en medio del encabezado")
    parser.add_argument("--aplicar", action="store_true",
                        help="respalda el libro y repara (sin esto solo diagnostica)")
    args = parser.parse_args()

    creds = google_upload.cargar_credenciales()
    if creds is None:
        print("ERROR: sin credenciales de Google.")
        return 1
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    nombre = args.libro.replace("'", "\\'")
    archivos = drive.files().list(
        q=f"name = '{nombre}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
        fields="files(id,name)",
    ).execute().get("files", [])
    if len(archivos) != 1:
        print(f"ERROR: se esperaba 1 libro llamado {args.libro}, hay {len(archivos)}.")
        return 1
    sheet_id = archivos[0]["id"]

    meta = svc.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets(properties(sheetId,title,gridProperties))",
    ).execute()
    pestana = next(s["properties"] for s in meta["sheets"]
                   if s["properties"]["title"] == config.SHEET_TAB)
    filas_grid = pestana["gridProperties"]["rowCount"]

    encabezado = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{config.SHEET_TAB}!1:1",
    ).execute()["values"][0]
    if args.columna not in encabezado:
        print(f"ERROR: {args.columna} no esta en el encabezado; nada que reparar.")
        return 1
    i_col, i_ultima = encabezado.index(args.columna), len(encabezado) - 1
    print(f"Libro: {args.libro} | encabezado de {len(encabezado)} columnas | "
          f"{args.columna} en la columna {_letra(i_col)}")

    print("Leyendo la ultima columna y la columna agregada...")
    ultima = _columna(svc, sheet_id, i_ultima, filas_grid)
    agregada = _columna(svc, sheet_id, i_col, filas_grid)
    i_tiempo = encabezado.index("consultation_time")
    tiempo = _columna(svc, sheet_id, i_tiempo, filas_grid)
    n = max((k for k, v in enumerate(tiempo) if v), default=-1) + 1
    viejas = [k for k in range(n) if ultima[k] == ""]

    print(f"Filas con datos: {n:,} | con el formato anterior (ultima columna vacia): {len(viejas):,}")
    if not viejas:
        print("Nada que reparar.")
        return 0
    if viejas != list(range(len(viejas))):
        print("ERROR: las filas viejas no forman un bloque contiguo desde la fila 2; "
              "se aborta sin tocar nada.")
        return 1
    con_mascara = [k for k in viejas if MASCARA_LLAVE.fullmatch(agregada[k] or "")]
    if con_mascara:
        print(f"ERROR: {len(con_mascara)} filas viejas ya tienen algo con forma de llave "
              f"en {args.columna} (ej. fila {con_mascara[0] + 2}); se aborta.")
        return 1

    fin = len(viejas) + 1   # ultima fila vieja (numeracion de la hoja)
    print(f"A reparar: filas 2 a {fin:,} ({tiempo[0]} -> {tiempo[len(viejas) - 1]})")
    print(f"Hoy en {args.columna} tienen, por ejemplo: {agregada[0][:70]!r}")

    if not args.aplicar:
        print("\nDiagnostico solamente. Para reparar: python3 reparar_columnas_sheet.py --aplicar")
        return 0

    respaldo = f"{args.libro}_respaldo_{datetime.now().strftime('%Y%m%d_%H%M')}"
    print(f"Respaldando como '{respaldo}'...")
    copia = drive.files().copy(fileId=sheet_id, body={"name": respaldo}, fields="id").execute()
    print(f"  Respaldo creado: {copia['id']}")

    print("Insertando la celda vacia en las filas viejas...")
    svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": [{
        "insertRange": {
            "range": {
                "sheetId": pestana["sheetId"],
                "startRowIndex": 1, "endRowIndex": fin,          # filas 2..fin
                "startColumnIndex": i_col, "endColumnIndex": i_col + 1,
            },
            "shiftDimension": "COLUMNS",
        }
    }]}).execute()

    # Verificacion: las filas reparadas ya tienen dia_semana en su lugar
    ultima_rep = _columna(svc, sheet_id, i_ultima, fin)
    pendientes = sum(1 for v in ultima_rep[:len(viejas)] if v == "")
    if pendientes:
        print(f"AVISO: {pendientes} filas siguen con la ultima columna vacia; revisar el respaldo.")
        return 1
    print(f"Listo: {len(viejas):,} filas reparadas. Respaldo: {respaldo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
