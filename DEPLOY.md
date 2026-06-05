# Guia de Despliegue — TomTom Cartagena

Sistema de descarga automatica de datos de trafico desde TomTom Traffic Flow API
para 113 nodos en Cartagena, distribuido en 2 VPS Oracle Cloud.

## Arquitectura

```
VPS 1 (158.101.105.13)           VPS 2 (IP nueva)
  Key 1 - Turnos 1 y 2             Key 2 - Turnos 3 y 4
  14 ejec/dia x 113 = 1,582        14 ejec/dia x 113 = 1,582
       |                                 |
       └─────────> data/resultados/*.csv <─────────┘
                          |
                  Dashboard Streamlit (puerto 8501)
```

## Estructura del proyecto

```
proyect_r/
├── nodos.xlsx                   # Tabla de nodos (lat, lon, etc)
├── requirements.txt             # Dependencias Python
├── .env.example                 # Plantilla de configuracion
├── src/
│   ├── config.py                # Configuracion centralizada
│   └── descargar_trafico.py     # Script principal
├── dashboard/
│   └── monitor.py               # Dashboard Streamlit
├── deploy/
│   ├── setup_vps.sh             # Setup automatico del VPS
│   ├── run.sh                   # Wrapper que llama cron
│   ├── crontab_vps1.txt         # Cron jobs VPS 1
│   ├── crontab_vps2.txt         # Cron jobs VPS 2
│   └── dashboard.service        # systemd para Streamlit
├── data/resultados/             # CSVs con timestamp
└── logs/
    ├── ejecuciones.jsonl        # Log estructurado por ejecucion
    └── cron.log                 # Salida cruda de cron
```

## Despliegue paso a paso

### Pre-requisitos

- 2 instancias Oracle Cloud Ubuntu en ejecucion
- 2 API Keys de TomTom (una por VPS)
- Llave SSH para conectarse a ambas

### Paso 1 — Conectarse al VPS 1

Desde PowerShell:

```powershell
ssh -i C:\ruta\a\tu\llave.pem ubuntu@158.101.105.13
```

### Paso 2 — Clonar o subir el proyecto

**Opcion A: Subir desde PC con SCP** (recomendado si no usan Git)

Desde otra PowerShell en tu PC:

```powershell
scp -i C:\ruta\a\tu\llave.pem -r C:\Users\MANUEL\Desktop\proyect_r ubuntu@158.101.105.13:/home/ubuntu/
```

**Opcion B: Clonar desde Git** (si lo subiste a un repositorio):

```bash
git clone https://github.com/usuario/proyect_r.git /home/ubuntu/proyect_r
```

### Paso 3 — Configurar variables

```bash
cd /home/ubuntu/proyect_r
cp .env.example .env
nano .env
```

Editar:
```
TOMTOM_API_KEY=tu_clave_api_1
VPS_ID=1
```

Guardar con `Ctrl+O`, Enter, `Ctrl+X`.

### Paso 4 — Ejecutar setup automatico

```bash
chmod +x deploy/setup_vps.sh
./deploy/setup_vps.sh
```

Esto:
- Actualiza Ubuntu
- Instala Python 3, pip, venv, cron
- Configura zona horaria Bogota
- Crea entorno virtual e instala paquetes
- Crea carpetas data/ y logs/

### Paso 5 — Prueba manual

```bash
./deploy/run.sh
```

Verifica que se creo un CSV:

```bash
ls data/resultados/
cat logs/ejecuciones.jsonl
```

### Paso 6 — Instalar cron jobs

**En VPS 1:**
```bash
crontab deploy/crontab_vps1.txt
crontab -l   # Verificar
```

**En VPS 2 (repetir pasos 1-5 alli):**
```bash
crontab deploy/crontab_vps2.txt
```

### Paso 7 — Dashboard (en cualquier VPS o ambos)

Opcion rapida (manual):
```bash
source venv/bin/activate
streamlit run dashboard/monitor.py
```

Opcion automatica (servicio systemd, se reinicia solo):
```bash
sudo cp deploy/dashboard.service /etc/systemd/system/
sudo systemctl enable dashboard
sudo systemctl start dashboard
sudo systemctl status dashboard
```

Abrir el puerto 8501 en Oracle Cloud:
1. Networking → VCN → Security Lists → Default Security List
2. Add Ingress Rule:
   - Source CIDR: `0.0.0.0/0`
   - Protocol: TCP
   - Destination Port Range: `8501`

Acceder al dashboard:
```
http://158.101.105.13:8501
```

## Verificacion y troubleshooting

**Ver logs en vivo:**
```bash
tail -f logs/cron.log
tail -f logs/ejecuciones.jsonl
```

**Verificar cron esta corriendo:**
```bash
sudo systemctl status cron
```

**Probar ejecucion manual:**
```bash
./deploy/run.sh
```

**Ver proxima ejecucion programada:**
```bash
crontab -l
```

**Si el dashboard no carga:**
- Verificar que el puerto 8501 esta abierto (Security List + ufw)
- Verificar firewall: `sudo ufw allow 8501/tcp`

## Mantenimiento

**Limpiar CSVs antiguos (>30 dias):**
```bash
find data/resultados -name "*.csv" -mtime +30 -delete
```

**Agregar a crontab para limpieza automatica semanal:**
```
0 3 * * 0 find /home/ubuntu/proyect_r/data/resultados -name "*.csv" -mtime +30 -delete
```

## Distribucion de carga

| VPS | API Key | Turnos | Horarios | Llamadas/dia |
|-----|---------|--------|----------|--------------|
| 1 | Key 1 | 1 y 2 | 4am - 1pm | 1,582 |
| 2 | Key 2 | 3 y 4 | 1:30pm - 12am | 1,582 |
| **Total** | | | **28 ejecuciones** | **3,164** |

Ambos VPS dentro del limite gratuito de 2,500 llamadas/dia por clave.
