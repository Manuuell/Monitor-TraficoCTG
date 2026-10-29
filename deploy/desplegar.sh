#!/bin/bash
# =====================================================================
#  Recibe por stdin un paquete .tgz con los archivos de la app (lo manda
#  GitHub Actions desde .github/workflows/desplegar.yml) y lo instala en
#  el proyecto: respalda, instala dependencias si cambio requirements.txt,
#  reemplaza solo los archivos que cambiaron y reinicia el dashboard. Si
#  el dashboard no responde, vuelve a los archivos anteriores.
#
#  Solo instala RUTAS: nunca toca .env, data/estado_llaves.json,
#  data/sheet_activo.json, credenciales/ ni el crontab.
#
#  Se instala una vez a mano FUERA del proyecto, para que un despliegue no
#  pueda reemplazarlo a medias:
#    mkdir -p ~/desplegar && install -m 700 deploy/desplegar.sh ~/desplegar/
#  y la llave de GitHub va en ~/.ssh/authorized_keys forzada a este script:
#    command="/home/ubuntu/desplegar/desplegar.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... github-actions-desplegar
#
#  Prueba sin instalar nada (recibe, revisa y compila):
#    tar czf - .commit src dashboard ... | ssh -i <llave> ubuntu@<vps> prueba
# =====================================================================
set -euo pipefail
umask 077

PROJECT_DIR="/home/ubuntu/proyect_r"
PY="$PROJECT_DIR/venv/bin/python"
RUTAS=(src dashboard .streamlit requirements.txt nodos.xlsx
       data/red_nodos.json data/red_nodos_revision.csv)
MODO="${SSH_ORIGINAL_COMMAND:-${1:-}}"
SELLO=$(date +%Y%m%d_%H%M%S)
RESPALDO="$PROJECT_DIR/.respaldos/despliegue_$SELLO"
LOG="$PROJECT_DIR/logs/despliegues.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# Un despliegue a la vez
exec 9>"$PROJECT_DIR/.desplegando.lock"
flock -w 900 9 || { log "ERROR: otro despliegue sigue en curso"; exit 1; }

# Carpeta temporal en el mismo disco: mv reemplaza cada archivo de una vez
# y una sesion abierta del dashboard nunca lee uno a medias
NUEVO=$(mktemp -d "$PROJECT_DIR/.desplegando.XXXXXX")
trap 'rm -rf "$NUEVO"' EXIT

# 1. Recibir y revisar el paquete
tar xzf - -C "$NUEVO"
for r in src dashboard requirements.txt; do
    [ -e "$NUEVO/$r" ] || { log "ERROR: el paquete no trae $r"; exit 1; }
done
COMMIT=$(cat "$NUEVO/.commit" 2>/dev/null || echo "?")
log "Recibido $COMMIT"

find "$NUEVO/src" "$NUEVO/dashboard" -name '*.py' -print0 \
    | xargs -0 "$PY" -c 'import sys; [compile(open(f, "rb").read(), f, "exec") for f in sys.argv[1:]]'

if [ "$MODO" = "prueba" ]; then
    log "Prueba OK: $COMMIT compila; no se instalo nada"
    exit 0
fi

# 2. Esperar a que no corra el ETL (hasta 15 min): reemplazar src/ en medio
# de una corrida mezclaria versiones. El cron arranca a :00 y :30.
# pgrep y no ps | grep -q: con pipefail, el SIGPIPE de ps daria un falso "no corre"
etl_corriendo() { pgrep -f "src/descargar_trafico.py" >/dev/null; }
for _ in $(seq 90); do
    if ! etl_corriendo && [[ ! $(date +%M) =~ ^(29|30|59|00)$ ]]; then
        break
    fi
    sleep 10
done
if etl_corriendo; then
    log "ERROR: el ETL sigue corriendo despues de 15 min; no se desplego"
    exit 1
fi

# 3. Respaldo de lo que hay
PRESENTES=()
for r in "${RUTAS[@]}"; do
    [ -e "$PROJECT_DIR/$r" ] && PRESENTES+=("$r")
done
mkdir -p "$RESPALDO"
tar czf "$RESPALDO/antes.tgz" -C "$PROJECT_DIR" --exclude=__pycache__ "${PRESENTES[@]}"

restaurar() {
    log "Restaurando $RESPALDO/antes.tgz"
    tar xzf "$RESPALDO/antes.tgz" -C "$PROJECT_DIR"
    sudo -n systemctl restart dashboard
}

# 4. Dependencias antes que el codigo
if ! cmp -s "$NUEVO/requirements.txt" "$PROJECT_DIR/requirements.txt"; then
    log "requirements.txt cambio: instalando dependencias"
    "$PROJECT_DIR/venv/bin/pip" install -q -r "$NUEVO/requirements.txt"
fi

# 5. Reemplazar solo los archivos que cambiaron
trap 'restaurar' ERR
EN_PAQUETE=()
for r in "${RUTAS[@]}"; do
    [ -e "$NUEVO/$r" ] && EN_PAQUETE+=("$r")
done
CAMBIADOS=0
while IFS= read -r -d '' f; do
    if ! cmp -s "$NUEVO/$f" "$PROJECT_DIR/$f"; then
        mkdir -p "$PROJECT_DIR/$(dirname "$f")"
        mv -f "$NUEVO/$f" "$PROJECT_DIR/$f"
        CAMBIADOS=$((CAMBIADOS + 1))
    fi
done < <(cd "$NUEVO" && find "${EN_PAQUETE[@]}" -type f -not -path '*/__pycache__/*' -print0)

if [ "$CAMBIADOS" -eq 0 ]; then
    trap - ERR
    rm -rf "$RESPALDO"
    log "Sin cambios: $COMMIT ya estaba instalado"
    echo "$COMMIT $(date '+%F %T')" > "$PROJECT_DIR/.desplegado"
    exit 0
fi
log "$CAMBIADOS archivo(s) reemplazados; reiniciando el dashboard"

# 6. Reiniciar y revisar que responda (hasta 2 min)
sudo -n systemctl restart dashboard
for _ in $(seq 40); do
    if curl -fsS -m 5 http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
        trap - ERR
        echo "$COMMIT $(date '+%F %T')" > "$PROJECT_DIR/.desplegado"
        log "Desplegado $COMMIT (respaldo en $RESPALDO)"
        exit 0
    fi
    sleep 3
done

trap - ERR
log "ERROR: el dashboard no respondio tras el reinicio"
restaurar
exit 1
