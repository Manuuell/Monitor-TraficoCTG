#!/bin/bash
# Comprueba Google Drive/Sheets y publica un estado local para el panel admin.

set -e
umask 077

PROJECT_DIR="/home/ubuntu/proyect_r"
cd "$PROJECT_DIR"

if [ -f "$PROJECT_DIR/.env" ]; then
    chmod 600 "$PROJECT_DIR/.env"
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

source "$PROJECT_DIR/venv/bin/activate"
python3 src/verificar_google_programado.py
