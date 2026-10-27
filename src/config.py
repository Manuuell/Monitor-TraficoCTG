"""
Configuracion centralizada del proyecto TomTom Cartagena.
Las claves API se leen desde variables de entorno por seguridad.
"""
import os
from pathlib import Path

# ============================================================
# RUTAS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
NODOS_PATH = BASE_DIR / "nodos.xlsx"
RESULTADOS_DIR = BASE_DIR / "data" / "resultados"
LOG_FILE = BASE_DIR / "logs" / "ejecuciones.jsonl"
CRON_LOG = BASE_DIR / "logs" / "cron.log"

# Credenciales Google. En produccion conviene apuntar CREDENCIALES_DIR a una
# ruta fuera del repositorio y de carpetas sincronizadas (Drive/iCloud).
_credenciales_dir = os.environ.get("CREDENCIALES_DIR", "").strip()
CREDENCIALES_DIR = (
    Path(_credenciales_dir).expanduser()
    if _credenciales_dir else BASE_DIR / "credenciales"
)
OAUTH_CLIENT_FILE = CREDENCIALES_DIR / "oauth_client.json"
OAUTH_TOKEN_FILE = CREDENCIALES_DIR / "token.json"

# ============================================================
# API TOMTOM
# ============================================================
# La clave se lee desde variable de entorno TOMTOM_API_KEY
API_KEY = os.environ.get("TOMTOM_API_KEY", "")

# Rotacion automatica de llaves: lista separada por comas de todas las llaves
# disponibles. Cada llave pertenece a una cuenta con su propia cuota mensual.
# El ETL reparte las llamadas entre ellas (round-robin) y, cuando una devuelve
# 403 InsufficientFunds, salta a la siguiente sin perder la corrida.
# Si TOMTOM_API_KEYS esta vacio, se usa TOMTOM_API_KEY como unica llave.
API_KEYS = [
    k.strip() for k in os.environ.get("TOMTOM_API_KEYS", "").split(",") if k.strip()
]
if not API_KEYS and API_KEY:
    API_KEYS = [API_KEY]

# Llaves de reserva: solo se usan cuando todas las de API_KEYS estan agotadas.
API_KEYS_RESERVA = [
    k.strip() for k in os.environ.get("TOMTOM_API_KEYS_RESERVA", "").split(",")
    if k.strip() and k.strip() not in API_KEYS
]

# Llaves para capturar_red.py (rutas entre nodos vecinos, una sola vez). Mejor
# de una cuenta aparte para no gastar el saldo del ETL; si se deja vacio, el
# script usa las de TOMTOM_API_KEYS.
API_KEYS_RED = [
    k.strip() for k in os.environ.get("TOMTOM_API_KEYS_RED", "").split(",") if k.strip()
]

# Horas tras las que una llave marcada como agotada se vuelve a probar, por si
# su cuenta recibio creditos. Permite volver a las principales sin esperar al
# cambio de mes.
REPROBAR_AGOTADA_HORAS = float(os.environ.get("REPROBAR_AGOTADA_HORAS", "6"))

# Cuota gratuita mensual por cuenta (llave). Se usa para el indicador de
# consumo acumulado y para saltar una llave antes de agotarla.
CUOTA_MENSUAL_LLAVE = int(os.environ.get("CUOTA_MENSUAL_LLAVE", "20000"))

# Identificador del VPS (1 o 2) - para distinguir en los logs
VPS_ID = os.environ.get("VPS_ID", "local")

URL_FLOWBASE = "https://api.tomtom.com/traffic/services/4/flowSegmentData"
ZOOM = 10
STYLE = "relative"
UNIT = "KMPH"
TIMEOUT_SEG = 30

# ============================================================
# LIMITES Y HORARIOS
# ============================================================
LIMITE_API_DIARIO = 2500
TZ = "America/Bogota"

# Horarios programados (formato HH:MM) - para mostrar en dashboard
HORARIOS = {
    "Turno 1": ["04:00", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30"],
    "Turno 2": ["08:00", "09:00", "10:00", "11:00", "12:00", "12:30", "13:00"],
    "Turno 3": ["13:30", "14:00", "15:00", "16:00", "17:00", "17:30", "18:00"],
    "Turno 4": ["18:30", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00"],
}
# El dashboard ordena y filtra las horas segun estas corridas (ver horario.py)

VPS_TURNOS = {
    "1": ["Turno 1", "Turno 2"],
    "2": ["Turno 3", "Turno 4"],
}

# ============================================================
# GOOGLE DRIVE / SHEETS
# ============================================================
DRIVE_FOLDER_ID = os.environ.get(
    "DRIVE_FOLDER_ID",
    "1zGbiM_tpJQSmEDjhXJsDOYw4yFhFqjhd",
)
SHEET_ID = os.environ.get(
    "SHEET_ID",
    "1Y8rXAeXVx3LPQ-I783OwbAmeNdKak3fJ5jKmfZb_LNU",
)
SHEET_TAB = os.environ.get("SHEET_TAB", "datos")

# Nombre base de los libros. Google limita cada hoja de calculo a 10 millones
# de celdas; al alcanzarlo el ETL crea "<base>_Parte2", "_Parte3"... en la
# misma carpeta de Drive y sigue escribiendo alli (ver google_upload.rotar_sheet).
SHEET_NOMBRE_BASE = os.environ.get("SHEET_NOMBRE_BASE", "TomTom_Cartagena_Datos")

# Carpeta exclusiva en Drive para los backups de PostgreSQL (off-site)
DRIVE_BACKUP_FOLDER_ID = os.environ.get("DRIVE_BACKUP_FOLDER_ID", "")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Activar/desactivar subida a Google (util para pruebas locales)
SUBIR_A_GOOGLE = os.environ.get("SUBIR_A_GOOGLE", "true").lower() == "true"

# ============================================================
# FIREBASE (app TransCaribe — snapshot de trafico para motor de ETAs)
# ============================================================
FIREBASE_CRED_FILE = CREDENCIALES_DIR / "firebase_transcaribe.json"
SUBIR_A_FIRESTORE = os.environ.get("SUBIR_A_FIRESTORE", "true").lower() == "true"

# ============================================================
# POSTGRESQL (migracion desde Google Sheets)
# ============================================================
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = os.environ.get("DB_PORT", "5432")
DB_NAME     = os.environ.get("DB_NAME", "trafico")
DB_USER     = os.environ.get("DB_USER", "trafico_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

# Escritura dual: si true, ademas de Sheets tambien inserta en PostgreSQL
GUARDAR_EN_DB = os.environ.get("GUARDAR_EN_DB", "false").lower() == "true"

# Fuente de lectura del dashboard: "sheets" (actual) o "db" (PostgreSQL)
FUENTE_DASHBOARD = os.environ.get("FUENTE_DASHBOARD", "sheets").lower()

# ============================================================
# GOOGLE STREET VIEW (foto del nodo en la ventana emergente del mapa)
# ============================================================
# Llave de la Street View Static API. Viaja en el HTML del dashboard, asi que
# en Google Cloud debe quedar restringida a esa API y al dominio del
# dashboard (HTTP referrer), con un tope diario de cuota. Sin llave, el popup
# del mapa sale sin foto.
GOOGLE_STREETVIEW_KEY = os.environ.get("GOOGLE_STREETVIEW_KEY", "")
