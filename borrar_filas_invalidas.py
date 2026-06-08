"""
Elimina del Google Sheet las filas con columnas desplazadas, detectables
porque su columna 'vps_id' NO contiene '1' ni '2' (corresponden a
ejecuciones que fallaron por completo y se subieron mal formadas).

No toca PostgreSQL ni los CSV. Es seguro: muestra cuantas borraria y
solo elimina las que cumplen la condicion exacta.

Uso (en VPS 1, con el venv activo):
    cd /home/ubuntu/proyect_r
    source venv/bin/activate
    set -a; source .env; set +a
    python3 borrar_filas_invalidas.py
"""
import sys
sys.path.insert(0, "/home/ubuntu/proyect_r/src")

import config
import google_upload
from googleapiclient.discovery import build

VALIDOS = {"1", "2"}

creds = google_upload.cargar_credenciales()
service = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Leer la hoja completa
result = service.spreadsheets().values().get(
    spreadsheetId=config.SHEET_ID, range=config.SHEET_TAB,
).execute()
values = result.get("values", [])
headers = values[0]
rows = values[1:]
print("Total filas antes:", len(rows))

col_vps = headers.index("vps_id")

# Identificar filas malas: vps_id no es '1' ni '2'
bad_indices = []   # indices 0-based en la hoja (0 = header)
for i, row in enumerate(rows):
    vps_val = row[col_vps].strip() if col_vps < len(row) else ""
    if vps_val not in VALIDOS:
        bad_indices.append(i + 1)   # +1 porque el header ocupa el indice 0

print("Filas a eliminar (vps_id invalido):", len(bad_indices))
if not bad_indices:
    print("Nada que eliminar. El Sheet ya esta limpio.")
    sys.exit(0)

# Eliminar de abajo hacia arriba para no desplazar indices
requests = []
for sheet_row_idx in sorted(bad_indices, reverse=True):
    requests.append({
        "deleteDimension": {
            "range": {
                "sheetId": 0,
                "dimension": "ROWS",
                "startIndex": sheet_row_idx,
                "endIndex": sheet_row_idx + 1,
            }
        }
    })

# Ejecutar en lotes de 100
BATCH = 100
for i in range(0, len(requests), BATCH):
    lote = requests[i:i + BATCH]
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.SHEET_ID, body={"requests": lote},
    ).execute()
    print("  Lote eliminado:", len(lote), "filas")

# Verificar
result2 = service.spreadsheets().values().get(
    spreadsheetId=config.SHEET_ID, range=config.SHEET_TAB,
).execute()
print("Total filas despues:", len(result2.get("values", [])) - 1)
print("Listo. Filas eliminadas:", len(bad_indices))
