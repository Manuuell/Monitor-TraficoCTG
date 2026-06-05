"""
Migracion UNICA: Google Sheets -> PostgreSQL.

Lee TODO el historico del Sheet (sin recorte de fechas), lo inserta en
PostgreSQL y VERIFICA que los conteos y rangos de fecha coincidan.

NO borra nada del Sheet. Es seguro correrlo: si la tabla ya tiene datos,
preguntara antes de duplicar.

Uso (en VPS 1, con el venv activo y las variables DB_* en el .env):
    cd /home/ubuntu/proyect_r
    source venv/bin/activate
    set -a; source .env; set +a
    python3 migrar_a_postgres.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd
from googleapiclient.discovery import build

import config
import google_upload
import db


def leer_sheet_completo() -> pd.DataFrame:
    """Lee el Sheet ENTERO sin filtrar por fecha (a diferencia de leer_sheet)."""
    creds = google_upload.cargar_credenciales()
    if creds is None:
        print("ERROR: no hay credenciales Google. Corre autorizar_google.py primero.")
        return pd.DataFrame()

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    result = service.spreadsheets().values().get(
        spreadsheetId=config.SHEET_ID, range=config.SHEET_TAB,
    ).execute()
    values = result.get("values", [])
    if len(values) < 2:
        return pd.DataFrame()

    headers = list(values[0])
    data_rows = values[1:]

    # Rellenar filas cortas / extender encabezado si hace falta
    max_cols = max((len(r) for r in data_rows), default=0)
    if max_cols > len(headers):
        headers += [f"col_{i}" for i in range(len(headers), max_cols)]
    n = len(headers)
    rows = [(r + [""] * (n - len(r)))[:n] for r in data_rows]
    return pd.DataFrame(rows, columns=headers)


def main() -> int:
    print("=" * 60)
    print("MIGRACION Google Sheets -> PostgreSQL")
    print("=" * 60)

    # 1. Leer el Sheet completo
    print("\n[1/5] Leyendo Google Sheet completo...")
    df_sheet = leer_sheet_completo()
    if df_sheet.empty:
        print("  No hay datos en el Sheet. Nada que migrar.")
        return 1
    filas_sheet = len(df_sheet)
    print(f"  Filas en el Sheet: {filas_sheet:,}")

    # 2. Crear esquema en PostgreSQL
    print("\n[2/5] Creando esquema en PostgreSQL (idempotente)...")
    try:
        db.crear_esquema()
        print("  Tabla e indices listos.")
    except Exception as e:
        print(f"  ERROR creando esquema: {e}")
        print("  Revisa que PostgreSQL este corriendo y las variables DB_* en .env.")
        return 1

    # 3. Verificar si ya hay datos (evitar duplicar)
    existentes = db.contar_filas()
    if existentes > 0:
        print(f"\n  ATENCION: la tabla ya tiene {existentes:,} filas.")
        resp = input("  ¿Insertar de todas formas? Puede duplicar. (escribe 'si'): ").strip().lower()
        if resp != "si":
            print("  Cancelado por el usuario.")
            return 0

    # 4. Insertar
    print("\n[3/5] Insertando filas en PostgreSQL...")
    try:
        insertadas = db.insertar_dataframe(df_sheet)
        print(f"  Filas insertadas: {insertadas:,}")
    except Exception as e:
        print(f"  ERROR insertando: {e}")
        return 1

    # 5. Verificacion
    print("\n[4/5] Verificando conteos...")
    total_db = db.contar_filas()
    print(f"  Sheet:      {filas_sheet:,} filas")
    print(f"  PostgreSQL: {total_db:,} filas")

    print("\n[5/5] Verificando rango de fechas...")
    ct_sheet = pd.to_datetime(df_sheet["consultation_time"], errors="coerce")
    min_sheet, max_sheet = ct_sheet.min(), ct_sheet.max()
    min_db, max_db = db.rango_fechas()
    print(f"  Sheet      min/max: {min_sheet}  ->  {max_sheet}")
    print(f"  PostgreSQL min/max: {min_db}  ->  {max_db}")

    # Resultado
    print("\n" + "=" * 60)
    ok_conteo = (total_db - existentes) == filas_sheet
    if ok_conteo:
        print("✓ MIGRACION VERIFICADA: los conteos coinciden.")
        print("  El Sheet sigue intacto como respaldo. No se borro nada.")
    else:
        print("⚠ ADVERTENCIA: los conteos NO coinciden exactamente.")
        print(f"  Esperado +{filas_sheet:,}, real +{total_db - existentes:,}.")
        print("  Revisa antes de cambiar el dashboard a PostgreSQL.")
    print("=" * 60)
    return 0 if ok_conteo else 1


if __name__ == "__main__":
    sys.exit(main())
