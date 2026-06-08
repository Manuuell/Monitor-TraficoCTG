"""
Backfill de Google Sheets + Drive a partir de los CSV locales.

Reconstruye en Sheets/Drive las ejecuciones que NO se subieron durante una
caida del token de Google. No duplica: compara contra las marcas de tiempo
(consultation_time) que ya existen en el Sheet y solo sube las que faltan.

Se ejecuta EN CADA VPS (cada uno tiene sus propios CSV de sus turnos):
    cd /home/ubuntu/proyect_r
    source venv/bin/activate
    set -a; source .env; set +a
    python3 rellenar_backfill.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd

import config
import google_upload


def main() -> int:
    print("=" * 60)
    print("BACKFILL Sheets + Drive desde CSV locales")
    print("=" * 60)

    creds = google_upload.cargar_credenciales()
    if creds is None:
        print("ERROR: no hay credenciales Google. Renueva el token primero.")
        return 1

    # 1. Marcas de tiempo que YA estan en el Sheet (para no duplicar)
    print("\n[1/3] Leyendo ejecuciones existentes en el Sheet...")
    df_sheet = google_upload.leer_sheet(n_dias=60)
    existentes = set()
    if not df_sheet.empty and "consultation_time" in df_sheet.columns:
        existentes = set(
            pd.to_datetime(df_sheet["consultation_time"], errors="coerce")
            .dropna().dt.strftime("%Y-%m-%d %H:%M:%S")
        )
    print(f"  Ejecuciones ya presentes en Sheets: {len(existentes)}")

    # 2. Recorrer CSV locales
    print("\n[2/3] Revisando CSV locales...")
    csvs = sorted(config.RESULTADOS_DIR.glob("TomTom_TrafficFlow_*.csv"))
    print(f"  CSV encontrados: {len(csvs)}")

    subidos_sheet = 0
    subidos_drive = 0
    saltados = 0

    for csv_path in csvs:
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            print(f"  [!] No se pudo leer {csv_path.name}: {e}")
            continue

        if df.empty or "consultation_time" not in df.columns:
            continue

        # La marca de tiempo de la ejecucion (igual en todas las filas del CSV)
        ct_raw = str(df["consultation_time"].iloc[0])
        ct_norm = pd.to_datetime(ct_raw, errors="coerce")
        if pd.isna(ct_norm):
            continue
        ct_key = ct_norm.strftime("%Y-%m-%d %H:%M:%S")

        # Si ya esta en Sheets, saltar
        if ct_key in existentes:
            saltados += 1
            continue

        # 3. Subir a Sheets y a Drive
        print(f"  -> Faltante: {csv_path.name} ({ct_key})")
        n = google_upload.agregar_filas_a_sheet(creds, df)
        if n > 0:
            subidos_sheet += n
            existentes.add(ct_key)   # evitar reprocesar en esta corrida
        drive_id = google_upload.subir_csv_a_drive(creds, csv_path)
        if drive_id:
            subidos_drive += 1

    # Resumen
    print("\n[3/3] Resumen")
    print(f"  Ejecuciones ya presentes (saltadas): {saltados}")
    print(f"  Filas agregadas a Sheets:            {subidos_sheet}")
    print(f"  CSV subidos a Drive:                 {subidos_drive}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
