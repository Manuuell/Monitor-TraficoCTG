"""
Sube un backup de PostgreSQL a la carpeta exclusiva de Drive (off-site).

Lo invoca backup_postgres.sh tras generar el volcado. Tambien se puede
correr a mano pasando la ruta del backup:
    python3 subir_backup_drive.py backups/trafico_20260608_020000.sql.gz

Si no se pasa ruta, sube el backup mas reciente de la carpeta backups/.
Requiere DRIVE_BACKUP_FOLDER_ID configurado en el .env.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import config
import google_upload


def main() -> int:
    if not config.DRIVE_BACKUP_FOLDER_ID:
        print("  [Backup Drive] DRIVE_BACKUP_FOLDER_ID no configurado; se omite la subida.")
        return 0

    # Determinar el archivo a subir
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        backups = sorted((config.BASE_DIR / "backups").glob("trafico_*.sql.gz"))
        if not backups:
            print("  [Backup Drive] No hay backups locales para subir.")
            return 1
        path = backups[-1]

    if not path.exists():
        print(f"  [Backup Drive] No existe el archivo: {path}")
        return 1

    creds = google_upload.cargar_credenciales()
    if creds is None:
        print("  [Backup Drive] Sin credenciales Google.")
        return 1

    file_id = google_upload.subir_archivo_a_drive(
        creds, path, config.DRIVE_BACKUP_FOLDER_ID, mimetype="application/gzip",
    )
    if file_id:
        print(f"  [Backup Drive] Subido off-site: {path.name} (id: {file_id})")
        return 0
    print("  [Backup Drive] Fallo la subida a Drive.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
