import sys
sys.path.insert(0, "/home/ubuntu/proyect_r/src")
import config, google_upload
from googleapiclient.discovery import build

creds = google_upload.cargar_credenciales()
service = build("sheets", "v4", credentials=creds, cache_discovery=False)
result = service.spreadsheets().values().get(
    spreadsheetId=config.SHEET_ID, range=config.SHEET_TAB,
).execute()
values = result.get("values", [])
headers = values[0]
rows = values[1:]

print("Total filas:", len(rows))
print()
for row in rows[-5:]:
    r = dict(zip(headers, row + [""] * (len(headers) - len(row))))
    ok = r.get("ok", "")
    ht = r.get("http_status", "")
    ct = r.get("consultation_time", "")
    vp = r.get("vps_id", "")
    em = r.get("error_msg", "")[:80]
    print("ok=" + ok + " | status=" + ht + " | time=" + ct + " | vps=" + vp + " | err=" + em)
