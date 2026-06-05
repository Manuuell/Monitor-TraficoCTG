#!/bin/bash
# Setup automatico para VPS Ubuntu.
# Ejecutar UNA sola vez al provisionar la instancia.
#
# Uso:
#   chmod +x deploy/setup_vps.sh
#   ./deploy/setup_vps.sh

set -e

PROJECT_DIR="/home/ubuntu/proyect_r"

echo "============================================"
echo "  SETUP VPS - TomTom Cartagena"
echo "============================================"

# 1. Actualizar sistema
echo ">>> Actualizando paquetes del sistema..."
sudo apt update
sudo apt upgrade -y

# 2. Instalar dependencias
echo ">>> Instalando Python y herramientas..."
sudo apt install -y python3 python3-pip python3-venv git cron

# 3. Configurar zona horaria
echo ">>> Configurando zona horaria America/Bogota..."
sudo timedatectl set-timezone America/Bogota

# 4. Crear venv e instalar paquetes
echo ">>> Creando entorno virtual..."
cd "$PROJECT_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Crear carpetas si no existen
mkdir -p data/resultados logs

# 6. Verificar que .env existe
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo ""
    echo "⚠️  IMPORTANTE: No existe el archivo .env"
    echo "    Copia .env.example a .env y completa con tu API_KEY:"
    echo "    cp .env.example .env"
    echo "    nano .env"
    echo ""
fi

# 7. Dar permisos al script de ejecucion
chmod +x deploy/run.sh

echo ""
echo "============================================"
echo "  ✅ Setup completado"
echo "============================================"
echo ""
echo "Proximos pasos:"
echo "  1. Editar .env con la API_KEY y VPS_ID correctos"
echo "  2. Subir el archivo nodos.xlsx a $PROJECT_DIR/"
echo "  3. Probar manualmente: ./deploy/run.sh"
echo "  4. Instalar cron jobs:"
echo "       - Si eres VPS 1: crontab deploy/crontab_vps1.txt"
echo "       - Si eres VPS 2: crontab deploy/crontab_vps2.txt"
echo "  5. Verificar: crontab -l"
echo ""
