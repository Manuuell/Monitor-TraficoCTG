#!/usr/bin/env bash
# Segundo servidor local con la paleta del dashboard R (puerto 8503), para
# compararlo con el diseno actual (dashboard/monitor.py en el 8502).
# Mismas fuentes que el 8502: PostgreSQL local en solo lectura.
cd "$(dirname "$0")/../.." || exit 1
set -a
[ -f .env ] && . ./.env
set +a
export FUENTE_DASHBOARD=db DB_HOST=localhost DB_USER="$USER"
export PGOPTIONS="-c default_transaction_read_only=on"

# El tema base de .streamlit/config.toml es oscuro: aqui se fuerza el claro
# con los colores del R (menta como color primario, tinta azul).
exec venv/bin/streamlit run dashboard/diseno_r/monitor.py \
    --server.port 8503 --server.headless true \
    --theme.base light \
    --theme.primaryColor "#14b8a6" \
    --theme.backgroundColor "#f3f7fe" \
    --theme.secondaryBackgroundColor "#eef3fd" \
    --theme.textColor "#12307a" \
    --theme.font "sans serif"
