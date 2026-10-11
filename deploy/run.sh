#!/bin/bash
# Wrapper que ejecuta el script Python con el entorno correcto.
# Llamado por cron en cada horario programado.

set -e
umask 077

PROJECT_DIR="/home/ubuntu/proyect_r"
cd "$PROJECT_DIR"

# Cargar variables de entorno
if [ -f "$PROJECT_DIR/.env" ]; then
    chmod 600 "$PROJECT_DIR/.env"
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

if [ -n "${CREDENCIALES_DIR:-}" ] && [ -d "$CREDENCIALES_DIR" ]; then
    chmod 700 "$CREDENCIALES_DIR"
    find "$CREDENCIALES_DIR" -type f -exec chmod 600 {} +
fi

# Activar venv
source "$PROJECT_DIR/venv/bin/activate"

# Ejecutar y registrar salida
python3 src/descargar_trafico.py >> logs/cron.log 2>&1
