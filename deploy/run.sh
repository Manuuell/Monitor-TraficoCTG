#!/bin/bash
# Wrapper que ejecuta el script Python con el entorno correcto.
# Llamado por cron en cada horario programado.

set -e

PROJECT_DIR="/home/ubuntu/proyect_r"
cd "$PROJECT_DIR"

# Cargar variables de entorno
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Activar venv
source "$PROJECT_DIR/venv/bin/activate"

# Ejecutar y registrar salida
python3 src/descargar_trafico.py >> logs/cron.log 2>&1
