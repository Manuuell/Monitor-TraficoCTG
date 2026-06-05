"""
Elimina del Google Sheet las filas donde ok=False y http_status=403
(filas del run fallido por InsufficientFunds de TomTom).
"""
import sys
sys.path.insert(0, "/home/ubuntu/proyect_r/src")
import config, google_upload
from googleapiclient.discovery import build

creds = google_upload.cargar_credenciales()
service = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Leer hoja completa
result = service.spreadsheets().values().get(
    spreadsheetId=config.SHEET_ID,
    range=config.SHEET_TAB,
).execute()
values = result.get("values", [])
headers = values[0]
rows = values[1:]

print("Total filas antes:", len(rows))

# Encontrar indices de columnas
col_ok     = headers.index("ok")
col_status = headers.index("http_status")

# Identificar filas malas: ok=False y http_status=403
# El indice en la hoja es i+2 (fila 1=header, datos desde fila 2), pero
# para la API de Sheets usamos indice 0-based: header=0, datos desde 1
bad_indices = []  # indices 0-based en la hoja (0=header, 1=primera fila de datos)
for i, row in enumerate(rows):
    ok_val     = row[col_ok]     if col_ok     < len(row) else ""
    status_val = row[col_status] if col_status < len(row) else ""
    if ok_val == "False" and status_val == "403":
        bad_indices.append(i + 1)  # +1 porque el header ocupa el indice 0

print("Filas a eliminar:", len(bad_indices))

if not bad_indices:
    print("Nada que eliminar.")
    sys.exit(0)

# Eliminar de abajo hacia arriba para no desplazar indices
# Construir requests de deleteRows en orden inverso
requests = []
for sheet_row_idx in sorted(bad_indices, reverse=True):
    requests.append({
        "deleteDimension": {
            "range": {
                "sheetId": 0,          # primera hoja
                "dimension": "ROWS",
                "startIndex": sheet_row_idx,
                "endIndex": sheet_row_idx + 1,
            }
        }
    })

# Ejecutar en lotes de 100 para no superar limites de la API
BATCH = 100
for i in range(0, len(requests), BATCH):
    lote = requests[i:i+BATCH]
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.SHEET_ID,
        body={"requests": lote},
    ).execute()
    print("  Lote eliminado:", len(lote), "filas")

print("Listo. Filas eliminadas:", len(bad_indices))

# Verificar resultado
result2 = service.spreadsheets().values().get(
    spreadsheetId=config.SHEET_ID,
    range=config.SHEET_TAB,
).execute()
print("Total filas despues:", len(result2.get("values", [])) - 1)
