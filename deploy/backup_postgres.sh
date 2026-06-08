#!/bin/bash
# =====================================================================
#  Backup comprimido de PostgreSQL con rotacion automatica.
#  Genera un volcado completo de la base 'trafico', lo comprime y
#  conserva solo los ultimos 30 dias.
#
#  Uso manual:
#    bash /home/ubuntu/proyect_r/deploy/backup_postgres.sh
#
#  Automatizado: ver la entrada de cron en este mismo archivo (abajo).
# =====================================================================
set -e

PROJECT_DIR="/home/ubuntu/proyect_r"
BACKUP_DIR="$PROJECT_DIR/backups"
mkdir -p "$BACKUP_DIR"

# Cargar credenciales de la base de datos desde el .env
set -a
source "$PROJECT_DIR/.env"
set +a

STAMP=$(date +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/trafico_$STAMP.sql.gz"

# Volcado comprimido de toda la base de datos
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" | gzip > "$OUT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup creado: $OUT ($(du -h "$OUT" | cut -f1))"

# Copia off-site a Google Drive (carpeta exclusiva de backups)
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
    python3 "$PROJECT_DIR/subir_backup_drive.py" "$OUT" || echo "Aviso: no se pudo subir el backup a Drive"
fi

# Rotacion: eliminar backups locales de mas de 30 dias
find "$BACKUP_DIR" -name 'trafico_*.sql.gz' -mtime +30 -delete

# Listar los backups actuales
echo "Backups disponibles:"
ls -lh "$BACKUP_DIR" | grep trafico_ | awk '{print "  " $9 "  " $5}'
