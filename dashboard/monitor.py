"""
Dashboard Streamlit - Monitor de Trafico TomTom Cartagena
Diseno con identidad visual UTB (navy + cyan).
"""
import json
import sys
import time
import glob
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
import config        # noqa: E402
import google_upload  # noqa: E402

# ============================================================
# CONFIGURACION DE PAGINA
# ============================================================
st.set_page_config(
    page_title="UTB - Monitor de Trafico Cartagena",
    layout="wide",
    page_icon="🚦",
    initial_sidebar_state="expanded",
)

# ============================================================
# COLORES UTB — Tema azul completo
# ============================================================
UTB_NAVY       = "#003087"           # Azul UTB principal
UTB_NAVY_DARK  = "#001f5c"           # Azul UTB oscuro (fondo)
UTB_NAVY_LIGHT = "#0a3272"           # Superficies / tarjetas
UTB_BLUE_LIGHT = "#1e73be"           # Azul intermedio (hover, detalles)
UTB_CYAN       = "#5eead4"           # Acento teal
UTB_CYAN_DARK  = "#14b8a6"           # Acento teal oscuro
UTB_BG         = "#001a4d"           # Fondo de pagina (azul mas oscuro)
UTB_BORDER     = "rgba(255,255,255,0.12)"   # Bordes sutiles
UTB_WHITE      = "#ffffff"           # Texto principal
UTB_GRAY       = "rgba(255,255,255,0.6)"    # Texto secundario

COLOR_FLUIDO        = "#22c55e"   # verde   — ratio > 0.90
COLOR_MODERADO      = "#a3e635"   # lima    — 0.75 a 0.90
COLOR_LENTO         = "#f59e0b"   # naranja — 0.60 a 0.75
COLOR_CONGESTIONADO = "#ef4444"   # rojo    — ratio < 0.60

# Umbrales de clasificacion de congestion (revisados tras feedback del asesor:
# el esquema anterior 0.75/0.50 subestimaba nodos como Bazurto con ratio ~0.6)
UMBRAL_FLUIDO   = 0.90
UMBRAL_MODERADO = 0.75
UMBRAL_LENTO    = 0.60


def clasificar_ratio(r):
    """Devuelve (color_hex, etiqueta) segun el ratio de velocidad."""
    if r is None or (isinstance(r, float) and pd.isna(r)):
        return UTB_GRAY, "Sin dato"
    if r > UMBRAL_FLUIDO:
        return COLOR_FLUIDO, "Fluido"
    if r > UMBRAL_MODERADO:
        return COLOR_MODERADO, "Moderado"
    if r > UMBRAL_LENTO:
        return COLOR_LENTO, "Lento"
    return COLOR_CONGESTIONADO, "Congestionado"

NUMERIC_COLS = [
    "lat", "lon", "currentSpeed", "freeFlowSpeed", "currentTravelTime",
    "freeFlowTravelTime", "confidence", "delay_abs_seg", "delay_rel_pct",
    "velocidad_ratio", "http_status",
]

LOGO_PATH = Path(__file__).parent / "assets" / "utb-logo.svg"


def cargar_logo_utb() -> str:
    if not LOGO_PATH.exists():
        return ""
    svg_text = LOGO_PATH.read_text(encoding="utf-8")
    svg_text = svg_text.replace('width="183"', 'width="100%"').replace('height="46"', 'height="auto"')
    return svg_text


LOGO_UTB_SVG = cargar_logo_utb()

# ============================================================
# CSS PERSONALIZADO — Tema azul UTB completo + DM Sans
# ============================================================
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    .stApp label, .stApp a, .stApp td, .stApp th,
    .stApp [data-testid="stMarkdown"],
    .stApp [data-testid="stMetricLabel"],
    .stApp [data-testid="stMetricValue"],
    .stApp [data-testid="stMetricDelta"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label {{
        font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }}

    /* ── Fondo general ── */
    .stApp {{
        background: linear-gradient(160deg, {UTB_NAVY_DARK} 0%, {UTB_BG} 100%);
    }}
    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }}

    /* ── Header ── */
    .utb-header {{
        background: linear-gradient(135deg, {UTB_NAVY} 0%, {UTB_NAVY_DARK} 100%);
        padding: 20px 28px;
        border-radius: 10px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        border: 1px solid {UTB_BORDER};
        position: relative;
        overflow: hidden;
    }}
    .utb-header::before {{
        content: "";
        position: absolute;
        top: -60px; right: -60px;
        width: 220px; height: 220px;
        background: radial-gradient(circle, rgba(94,234,212,0.15) 0%, transparent 70%);
        border-radius: 50%;
    }}
    .utb-brand {{
        color: #ffffff;
        font-size: 26px;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }}
    .utb-brand-accent {{ color: {UTB_CYAN}; font-weight: 700; }}
    .utb-subtitle {{
        color: {UTB_GRAY};
        font-size: 14px;
        margin: 4px 0 0 0;
        font-weight: 400;
    }}
    .utb-clock {{
        color: {UTB_NAVY_DARK};
        font-size: 14px;
        font-weight: 600;
        background: rgba(255,255,255,0.92);
        padding: 8px 16px;
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.3);
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }}

    /* ── Métricas ── */
    [data-testid="stMetric"] {{
        background: {UTB_NAVY_LIGHT};
        padding: 20px 24px;
        border-radius: 12px;
        border: 1px solid {UTB_BORDER};
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        transition: all 0.2s;
    }}
    [data-testid="stMetric"]:hover {{
        border-color: {UTB_CYAN};
        box-shadow: 0 4px 16px rgba(94,234,212,0.15);
        transform: translateY(-2px);
    }}
    [data-testid="stMetricLabel"] {{
        color: {UTB_GRAY} !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }}
    [data-testid="stMetricValue"] {{
        color: {UTB_WHITE} !important;
        font-size: 32px !important;
        font-weight: 700 !important;
    }}
    [data-testid="stMetricDelta"] {{ color: {UTB_CYAN} !important; font-weight: 600 !important; }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {{
        background: {UTB_NAVY} !important;
        border-right: 1px solid {UTB_BORDER};
    }}
    [data-testid="stSidebar"] * {{ color: rgba(255,255,255,0.85) !important; }}
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {{ color: {UTB_CYAN} !important; }}
    [data-testid="stSidebar"] [data-testid="stExpander"] {{
        background: rgba(255,255,255,0.06);
        border: 1px solid {UTB_BORDER};
        border-radius: 8px;
    }}
    [data-testid="stSidebar"] select,
    [data-testid="stSidebar"] input {{
        background: rgba(255,255,255,0.08) !important;
        border-color: {UTB_BORDER} !important;
        color: white !important;
    }}

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        background: transparent;
        border-bottom: 1px solid {UTB_BORDER};
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent;
        border-radius: 8px 8px 0 0;
        padding: 12px 24px;
        color: {UTB_GRAY};
        font-weight: 600;
        font-size: 14px;
    }}
    .stTabs [aria-selected="true"] {{
        background: {UTB_NAVY_LIGHT} !important;
        color: {UTB_CYAN} !important;
        border-bottom: 2px solid {UTB_CYAN};
    }}

    /* ── Botones ── */
    .stButton button {{
        background: {UTB_CYAN};
        color: {UTB_NAVY_DARK};
        border: none;
        border-radius: 8px;
        font-weight: 700;
        padding: 8px 20px;
        transition: all 0.2s;
    }}
    .stButton button:hover {{
        background: {UTB_CYAN_DARK};
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(94,234,212,0.3);
    }}

    /* ── Labels / inputs ── */
    .stSelectbox label, .stTextInput label, .stDateInput label {{
        color: {UTB_GRAY} !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    [data-testid="stDataFrame"] {{
        background: {UTB_NAVY_LIGHT};
        border-radius: 8px;
        border: 1px solid {UTB_BORDER};
    }}

    /* ── Misc ── */
    hr {{ border-color: {UTB_BORDER} !important; }}
    .utb-footer {{
        background: {UTB_NAVY_LIGHT};
        padding: 16px;
        border-radius: 8px;
        margin-top: 24px;
        text-align: center;
        color: {UTB_GRAY};
        font-size: 12px;
        border-top: 2px solid {UTB_CYAN};
    }}
    h2 {{ color: {UTB_WHITE}; font-weight: 700; margin-top: 0; }}
    h3 {{
        color: {UTB_CYAN};
        font-size: 16px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 12px;
    }}
    .badge-ok {{
        background: rgba(52,211,153,0.15); color: {COLOR_FLUIDO};
        padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600;
    }}
    .badge-error {{
        background: rgba(248,113,113,0.15); color: {COLOR_CONGESTIONADO};
        padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600;
    }}
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    [data-testid="stHeader"] {{ background: transparent; height: 0; }}
    [data-testid="collapsedControl"] {{
        background: {UTB_CYAN} !important;
        border-radius: 50%;
        padding: 8px;
        top: 14px; left: 14px;
        z-index: 999;
        box-shadow: 0 4px 12px rgba(94,234,212,0.4);
        transition: all 0.2s;
    }}
    [data-testid="collapsedControl"]:hover {{
        background: {UTB_CYAN_DARK} !important;
        transform: scale(1.1);
    }}
    [data-testid="collapsedControl"] svg {{
        color: {UTB_NAVY_DARK} !important;
        fill: {UTB_NAVY_DARK} !important;
    }}
    [data-testid="stSidebarCollapseButton"] button {{ color: {UTB_CYAN} !important; }}
</style>
""", unsafe_allow_html=True)


# ============================================================
# UTILIDADES
# ============================================================
def plotly_base(fig, height: int = 340):
    fig.update_layout(
        paper_bgcolor=UTB_NAVY_LIGHT,
        plot_bgcolor=UTB_NAVY_DARK,
        font_color=UTB_WHITE,
        font_family="DM Sans",
        height=height,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.08)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.08)"),
    )
    return fig


@st.cache_data(ttl=60)
def cargar_logs() -> pd.DataFrame:
    if not config.LOG_FILE.exists():
        return pd.DataFrame()
    entries = []
    with open(config.LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not entries:
        return pd.DataFrame()
    df = pd.DataFrame(entries)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp")


@st.cache_data(ttl=60)
def listar_archivos() -> list:
    files = sorted(glob.glob(str(config.RESULTADOS_DIR / "*.csv")))
    return [Path(f) for f in files]


@st.cache_data(ttl=60)
def cargar_csv(path_str: str) -> pd.DataFrame:
    df = pd.read_csv(path_str)
    if "consultation_time" in df.columns:
        df["consultation_time"] = pd.to_datetime(df["consultation_time"])
    return df


@st.cache_data(ttl=300)
def cargar_desde_sheets(n_dias: int = 30) -> pd.DataFrame:
    """
    Carga el historico. Fuente segun config.FUENTE_DASHBOARD:
      - "db"     → PostgreSQL (rapido). Si falla, cae a Sheets.
      - "sheets" → Google Sheets (default).
    El nombre se mantiene por compatibilidad con el resto del dashboard.
    """
    fuente = getattr(config, "FUENTE_DASHBOARD", "sheets")

    if fuente == "db":
        try:
            import db  # import diferido
            df = db.leer_datos(n_dias=n_dias)
            if not df.empty:
                return df
            # BD vacia → intentar Sheets como respaldo
        except Exception as e:
            print(f"  [Dashboard] PostgreSQL no disponible, usando Sheets: {e}")

    # Fuente Sheets (default o fallback)
    try:
        df = google_upload.leer_sheet(n_dias=n_dias)
        if df.empty:
            return pd.DataFrame()
        if "consultation_time" in df.columns:
            df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
        for col in NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def rango_fechas_historico() -> tuple:
    """
    (fecha_min, fecha_max, fuente) del historico disponible, sin descargar
    los datos. Con FUENTE_DASHBOARD=db lo responde PostgreSQL al instante;
    si no, se obtiene del Sheet completo (comportamiento anterior).
    """
    if getattr(config, "FUENTE_DASHBOARD", "sheets") == "db":
        try:
            import db  # import diferido
            mn, mx = db.rango_fechas()
            if mn is not None and mx is not None:
                return mn.date(), mx.date(), "PostgreSQL"
        except Exception as e:
            print(f"  [Dashboard] PostgreSQL no disponible para rango: {e}")

    df = cargar_desde_sheets(n_dias=3650)
    if df.empty or "consultation_time" not in df.columns:
        return None, None, None
    fechas = df["consultation_time"].dropna()
    if fechas.empty:
        return None, None, None
    return fechas.dt.date.min(), fechas.dt.date.max(), "Google Sheets"


@st.cache_data(ttl=300)
def cargar_historico(fecha_ini, fecha_fin) -> tuple:
    """
    Datos del periodo [fecha_ini, fecha_fin] y la fuente usada.
    PostgreSQL consulta solo el rango pedido (rapido); Sheets descarga el
    historico completo y recorta (respaldo si la BD no esta disponible).
    """
    if getattr(config, "FUENTE_DASHBOARD", "sheets") == "db":
        try:
            import db  # import diferido
            df = db.leer_rango(fecha_ini, fecha_fin)
            if not df.empty:
                return df, "PostgreSQL"
        except Exception as e:
            print(f"  [Dashboard] PostgreSQL no disponible, usando Sheets: {e}")

    df = cargar_desde_sheets(n_dias=3650)
    if df.empty or "consultation_time" not in df.columns:
        return pd.DataFrame(), None
    mask = (
        (df["consultation_time"].dt.date >= fecha_ini) &
        (df["consultation_time"].dt.date <= fecha_fin)
    )
    return df[mask].copy(), "Google Sheets"


def leyenda_ratio(modo: str = "ratio"):
    """
    Renderiza una leyenda de colores debajo de las graficas.
    modo='ratio'  → explica el velocity ratio (0-1)
    modo='velocidad' → explica velocidades en km/h
    modo='proceso'   → explica OK/Error en ejecuciones
    """
    if modo == "ratio":
        st.markdown(f"""
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;
                    background:rgba(255,255,255,0.05);border-radius:8px;
                    padding:10px 16px;margin-top:4px;border:1px solid rgba(255,255,255,0.1);">
            <span style="color:rgba(255,255,255,0.5);font-size:11px;font-weight:700;
                         letter-spacing:1px;text-transform:uppercase;">Interpretación:</span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:12px;border-radius:50%;
                             background:{COLOR_FLUIDO};display:inline-block;flex-shrink:0;"></span>
                <b style="color:{COLOR_FLUIDO};">Fluido</b>&nbsp;&gt; 0.90
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:12px;border-radius:50%;
                             background:{COLOR_MODERADO};display:inline-block;flex-shrink:0;"></span>
                <b style="color:{COLOR_MODERADO};">Moderado</b>&nbsp;0.75 – 0.90
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:12px;border-radius:50%;
                             background:{COLOR_LENTO};display:inline-block;flex-shrink:0;"></span>
                <b style="color:{COLOR_LENTO};">Lento</b>&nbsp;0.60 – 0.75
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:12px;border-radius:50%;
                             background:{COLOR_CONGESTIONADO};display:inline-block;flex-shrink:0;"></span>
                <b style="color:{COLOR_CONGESTIONADO};">Congestionado</b>&nbsp;&lt; 0.60
            </span>
            <span style="color:rgba(255,255,255,0.4);font-size:11px;margin-left:auto;">
                Ratio = velocidad actual ÷ velocidad libre · 1.0 = sin tráfico · 0.0 = detenido
            </span>
        </div>
        """, unsafe_allow_html=True)

    elif modo == "velocidad":
        st.markdown(f"""
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;
                    background:rgba(255,255,255,0.05);border-radius:8px;
                    padding:10px 16px;margin-top:4px;border:1px solid rgba(255,255,255,0.1);">
            <span style="color:rgba(255,255,255,0.5);font-size:11px;font-weight:700;
                         letter-spacing:1px;text-transform:uppercase;">Interpretación:</span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:3px;background:{UTB_CYAN};display:inline-block;"></span>
                <b style="color:{UTB_CYAN};">Velocidad actual</b>&nbsp;— km/h medidos en tiempo real con tráfico
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:3px;background:rgba(255,255,255,0.4);
                             display:inline-block;border-top:2px dashed rgba(255,255,255,0.4);"></span>
                <b style="color:rgba(255,255,255,0.6);">Velocidad libre</b>&nbsp;— km/h que tendría la vía sin tráfico
            </span>
            <span style="color:rgba(255,255,255,0.4);font-size:11px;margin-left:auto;">
                La brecha entre ambas líneas representa el tiempo perdido por congestión
            </span>
        </div>
        """, unsafe_allow_html=True)

    elif modo == "proceso":
        st.markdown(f"""
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;
                    background:rgba(255,255,255,0.05);border-radius:8px;
                    padding:10px 16px;margin-top:4px;border:1px solid rgba(255,255,255,0.1);">
            <span style="color:rgba(255,255,255,0.5);font-size:11px;font-weight:700;
                         letter-spacing:1px;text-transform:uppercase;">Interpretación:</span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:12px;border-radius:3px;
                             background:{COLOR_FLUIDO};display:inline-block;"></span>
                <b style="color:{COLOR_FLUIDO};">Consultas OK</b>&nbsp;— nodos respondidos correctamente por TomTom
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,0.85);">
                <span style="width:12px;height:12px;border-radius:3px;
                             background:{COLOR_CONGESTIONADO};display:inline-block;"></span>
                <b style="color:{COLOR_CONGESTIONADO};">Errores</b>&nbsp;— nodos con fallo (red, cuota, API)
            </span>
            <span style="color:rgba(255,255,255,0.4);font-size:11px;margin-left:auto;">
                Cada barra = una ejecución del cron · 113 nodos por ejecución
            </span>
        </div>
        """, unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def cargar_geometria() -> dict:
    """Carga la geometria de las calles (capturada con capturar_geometria.py)."""
    path = BASE_DIR / "data" / "nodos_geometria.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def color_por_ratio(ratio):
    if pd.isna(ratio):
        return [107, 114, 128, 160]   # gris — sin dato
    if ratio > UMBRAL_FLUIDO:
        return [34, 197, 94, 220]     # verde — Fluido
    if ratio > UMBRAL_MODERADO:
        return [163, 230, 53, 220]    # lima — Moderado
    if ratio > UMBRAL_LENTO:
        return [245, 158, 11, 220]    # naranja — Lento
    return [239, 68, 68, 235]         # rojo — Congestionado


@st.cache_data(ttl=3600)
def verificar_token_google() -> dict:
    """Verifica el estado del token OAuth de Google. Cachea 1 hora."""
    try:
        creds = google_upload.cargar_credenciales()
        if creds is None:
            return {"ok": False, "estado": "No encontrado", "detalle": "token.json no existe o esta corrupto"}
        if creds.valid:
            return {"ok": True, "estado": "Activo", "detalle": "Conexion con Google OK"}
        elif creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            return {"ok": True, "estado": "Renovado", "detalle": "Token renovado automaticamente"}
        else:
            return {"ok": False, "estado": "Expirado", "detalle": "Requiere re-autorizacion manual en tu PC"}
    except Exception as e:
        return {"ok": False, "estado": "Error", "detalle": str(e)[:120]}


@st.cache_data(ttl=3600)
def capacidad_sheet() -> dict:
    """
    Ocupacion del Google Sheet frente al limite duro de Google (10 millones
    de celdas por hoja de calculo). Al alcanzarlo el ETL rota solo a un libro
    nuevo ("<base>_ParteN") y sigue escribiendo alli, asi que este indicador
    mide el libro ACTIVO y avisa cuando toca la proxima rotacion.

    Cachea 1 hora: el tamano crece despacio y es una llamada extra a la API.
    """
    LIMITE = 10_000_000
    try:
        creds = google_upload.cargar_credenciales()
        if creds is None:
            return {"ok": False, "detalle": "Sin credenciales Google"}

        from googleapiclient.discovery import build
        svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        # Se mide el libro ACTIVO: tras una rotacion el original queda lleno
        # y congelado, y lo que importa es cuanto le queda al que se escribe.
        sheet_id = google_upload.sheet_activo()
        parte = google_upload.parte_activa()
        meta = svc.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="properties(title),sheets(properties(title,gridProperties))",
        ).execute()

        celdas = 0
        cols_datos = 0
        for s in meta.get("sheets", []):
            p = s["properties"]
            g = p.get("gridProperties", {})
            filas = g.get("rowCount", 0)
            cols = g.get("columnCount", 0)
            celdas += filas * cols
            if p.get("title") == config.SHEET_TAB:
                cols_datos = cols

        if cols_datos == 0:
            cols_datos = 29  # ancho tipico de la tabla de mediciones

        # Consumo diario: 113 nodos x 28 ejecuciones programadas
        celdas_dia = 113 * 28 * cols_datos
        restantes = max(LIMITE - celdas, 0)
        dias = int(restantes / celdas_dia) if celdas_dia > 0 else None
        fecha_llena = (datetime.now() + timedelta(days=dias)).strftime("%d/%m/%Y") if dias is not None else None

        return {
            "ok": True,
            "celdas": celdas,
            "limite": LIMITE,
            "pct": celdas / LIMITE * 100,
            "dias": dias,
            "fecha_llena": fecha_llena,
            "parte": parte,
            "nombre": meta.get("properties", {}).get("title", ""),
            "detalle": None,
        }
    except Exception as e:
        return {"ok": False, "detalle": str(e)[:120]}


def calcular_proxima_ejecucion():
    ahora = datetime.now()
    horarios_hoy = []
    for turno_horarios in config.HORARIOS.values():
        for h in turno_horarios:
            hh, mm = map(int, h.split(":"))
            t = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if h == "00:00" and ahora.hour > 12:
                t = t + timedelta(days=1)
            if t > ahora:
                horarios_hoy.append(t)
    return min(horarios_hoy) if horarios_hoy else None


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    if LOGO_UTB_SVG:
        st.markdown(f"""
        <div style="text-align:center;padding:24px 16px;border-bottom:1px solid rgba(255,255,255,0.15);margin-bottom:20px;">
            {LOGO_UTB_SVG}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="text-align:center;padding:16px 0;border-bottom:1px solid rgba(255,255,255,0.15);margin-bottom:20px;">
            <div style="color:{UTB_CYAN};font-size:11px;font-weight:700;letter-spacing:2px;">UNIVERSIDAD</div>
            <div style="color:#ffffff;font-size:22px;font-weight:800;margin:4px 0;">TECNOLÓGICA</div>
            <div style="color:#ffffff;font-size:14px;font-weight:600;">DE BOLÍVAR</div>
        </div>
        """, unsafe_allow_html=True)

    # --- Estado del token Google ---
    token_st = verificar_token_google()
    if token_st["ok"]:
        st.markdown(f"""
        <div style="background:rgba(16,185,129,0.1);border-left:3px solid {COLOR_FLUIDO};
             padding:10px 12px;border-radius:6px;margin-bottom:16px;">
            <div style="color:{COLOR_FLUIDO};font-size:11px;font-weight:700;">
                ● GOOGLE · {token_st['estado'].upper()}</div>
            <div style="color:{UTB_GRAY};font-size:11px;">{token_st['detalle']}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:rgba(239,68,68,0.15);border-left:3px solid {COLOR_CONGESTIONADO};
             padding:10px 12px;border-radius:6px;margin-bottom:16px;animation:pulse 2s infinite;">
            <div style="color:{COLOR_CONGESTIONADO};font-size:11px;font-weight:700;">
                ⚠ GOOGLE · {token_st['estado'].upper()}</div>
            <div style="color:{UTB_GRAY};font-size:11px;">{token_st['detalle']}</div>
        </div>""", unsafe_allow_html=True)

    # --- Capacidad del Google Sheet (limite 10M celdas) ---
    cap = capacidad_sheet()
    if cap["ok"]:
        _pct = cap["pct"]
        if _pct >= 90:
            _color, _icono, _estado = COLOR_CONGESTIONADO, "⚠", "CRITICO"
        elif _pct >= 75:
            _color, _icono, _estado = COLOR_LENTO, "⚠", "ALTO"
        elif _pct >= 50:
            _color, _icono, _estado = COLOR_MODERADO, "●", "MODERADO"
        else:
            _color, _icono, _estado = COLOR_FLUIDO, "●", "OK"

        _aviso = (
            f"Se llena ~{cap['fecha_llena']} ({cap['dias']} dias)"
            if cap["dias"] is not None else "Sin proyeccion"
        )
        # Al llenarse se rota automaticamente: el aviso deja de ser una alarma.
        _parte_txt = f" · PARTE {cap['parte']}" if cap.get("parte", 1) > 1 else ""
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.06);border-left:3px solid {_color};
             padding:10px 12px;border-radius:6px;margin-bottom:16px;">
            <div style="color:{_color};font-size:11px;font-weight:700;">
                {_icono} HOJA DE CALCULO · {_estado}{_parte_txt}</div>
            <div style="background:rgba(0,0,0,0.25);border-radius:4px;height:6px;
                 overflow:hidden;margin:6px 0;">
                <div style="background:{_color};width:{min(_pct, 100):.1f}%;
                     height:100%;border-radius:4px;"></div>
            </div>
            <div style="color:{UTB_GRAY};font-size:11px;">
                {cap['celdas']:,} / {cap['limite']:,} celdas · {_pct:.1f}%</div>
            <div style="color:{UTB_GRAY};font-size:11px;">{_aviso}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.06);border-left:3px solid {UTB_GRAY};
             padding:10px 12px;border-radius:6px;margin-bottom:16px;">
            <div style="color:{UTB_GRAY};font-size:11px;font-weight:700;">
                ● HOJA DE CALCULO · SIN DATO</div>
            <div style="color:{UTB_GRAY};font-size:11px;">{cap.get('detalle') or 'No disponible'}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("### Archivo a visualizar")
    archivos = listar_archivos()
    if archivos:
        opciones = ["Ultimo disponible"] + [f.name for f in reversed(archivos[-50:])]
        seleccion = st.selectbox("", opciones, label_visibility="collapsed")
        archivo_actual = archivos[-1] if seleccion == "Ultimo disponible" else next(
            (f for f in archivos if f.name == seleccion), archivos[-1]
        )
    else:
        archivo_actual = None
        st.warning("Sin archivos aun")

    if st.button("Recargar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # --- Links directos Google ---
    drive_url  = f"https://drive.google.com/drive/folders/{config.DRIVE_FOLDER_ID}"
    sheets_url = f"https://docs.google.com/spreadsheets/d/{config.SHEET_ID}"

    st.markdown(f"""
    <div style="margin-bottom:16px;">
        <div style="color:{UTB_CYAN};font-size:11px;font-weight:700;letter-spacing:1.5px;margin-bottom:10px;">
            ACCESO RÁPIDO
        </div>
        <a href="{drive_url}" target="_blank" style="
            display:flex; align-items:center; gap:10px;
            background:rgba(255,255,255,0.07);
            border:1px solid rgba(255,255,255,0.12);
            border-radius:8px; padding:10px 14px;
            color:#ffffff; text-decoration:none;
            font-size:13px; font-weight:600;
            margin-bottom:8px;
            transition:all 0.2s;">
            <span style="font-size:18px;">📁</span>
            <div>
                <div style="color:#ffffff;font-size:13px;font-weight:600;">Google Drive</div>
                <div style="color:rgba(255,255,255,0.5);font-size:11px;">Carpeta de CSVs</div>
            </div>
            <span style="margin-left:auto;color:rgba(255,255,255,0.4);font-size:16px;">↗</span>
        </a>
        <a href="{sheets_url}" target="_blank" style="
            display:flex; align-items:center; gap:10px;
            background:rgba(255,255,255,0.07);
            border:1px solid rgba(255,255,255,0.12);
            border-radius:8px; padding:10px 14px;
            color:#ffffff; text-decoration:none;
            font-size:13px; font-weight:600;
            transition:all 0.2s;">
            <span style="font-size:18px;">📊</span>
            <div>
                <div style="color:#ffffff;font-size:13px;font-weight:600;">Google Sheets</div>
                <div style="color:rgba(255,255,255,0.5);font-size:11px;">Base de datos principal</div>
            </div>
            <span style="margin-left:auto;color:rgba(255,255,255,0.4);font-size:16px;">↗</span>
        </a>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown("### Horarios programados")
    for turno, horas in config.HORARIOS.items():
        with st.expander(turno, expanded=False):
            for h in horas:
                st.markdown(
                    f"<div style='padding:4px 0;color:{UTB_GRAY};font-size:13px;'>• {h}</div>",
                    unsafe_allow_html=True,
                )


# ============================================================
# HEADER
# ============================================================
ahora = datetime.now()
proxima = calcular_proxima_ejecucion()
proxima_str = proxima.strftime("%H:%M") if proxima else "—"

st.markdown(f"""
<div class="utb-header">
    <div>
        <h1 class="utb-brand">Monitor <span class="utb-brand-accent">Trafico</span></h1>
        <p class="utb-subtitle">Cartagena · 113 nodos de monitoreo · Datos TomTom Traffic Flow</p>
    </div>
    <div style="text-align:right;">
        <div class="utb-clock">{ahora.strftime("%H:%M")} · {ahora.strftime("%d/%m/%Y")}</div>
        <div style="color:{UTB_GRAY};font-size:11px;margin-top:6px;">
            Proxima ejecucion: <span style="color:{UTB_CYAN};font-weight:600;">{proxima_str}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Banner de alerta si el token esta expirado
token_st = verificar_token_google()
if not token_st["ok"]:
    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.12);border:1px solid {COLOR_CONGESTIONADO};
         padding:16px 20px;border-radius:8px;margin-bottom:20px;">
        <div style="color:{COLOR_CONGESTIONADO};font-size:16px;font-weight:700;margin-bottom:8px;">
            ⚠ Token Google expirado — los datos no se estan subiendo a Drive ni Sheets
        </div>
        <div style="color:{UTB_WHITE};font-size:13px;line-height:1.6;">
            <b>Pasos para renovarlo:</b><br>
            1. En tu PC: <code style="background:{UTB_BG};border:1px solid {UTB_BORDER};color:{UTB_NAVY};padding:2px 8px;border-radius:4px;">python src/autorizar_google.py</code><br>
            2. Sube el nuevo token:
            <code style="background:{UTB_BG};border:1px solid {UTB_BORDER};color:{UTB_NAVY};padding:2px 8px;border-radius:4px;">
            scp credenciales/token.json ubuntu@158.101.105.13:/home/ubuntu/proyect_r/credenciales/</code><br>
            3. Recarga esta pagina.
        </div>
    </div>""", unsafe_allow_html=True)

def _mascara_ok(df: pd.DataFrame) -> pd.Series:
    """
    Filas cuya consulta a TomTom fue exitosa. La columna 'ok' llega como bool
    desde PostgreSQL y como texto ("TRUE") desde Sheets y los CSV, asi que se
    normaliza en ambos casos.
    """
    if df.empty or "ok" not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    return df["ok"].astype(str).str.lower().isin(["true", "1"])


# ============================================================
# CARGAR DATOS BASE
# ============================================================
logs = cargar_logs()
df_actual = cargar_csv(str(archivo_actual)) if archivo_actual else pd.DataFrame()

# ── Snapshot: elige la ejecucion mas reciente entre VPS 1 (local) y VPS 2 (Sheets) ──
_df_sheets_1d = cargar_desde_sheets(n_dias=1)

_local_time = (
    df_actual["consultation_time"].max()
    if not df_actual.empty and "consultation_time" in df_actual.columns
    else pd.NaT
)
_sheets_time = (
    _df_sheets_1d["consultation_time"].max()
    if not _df_sheets_1d.empty and "consultation_time" in _df_sheets_1d.columns
    else pd.NaT
)

if pd.notna(_sheets_time) and (pd.isna(_local_time) or _sheets_time > _local_time):
    df_snapshot = _df_sheets_1d[_df_sheets_1d["consultation_time"] == _sheets_time].copy()
    _vps = str(df_snapshot["vps_id"].iloc[0]) if "vps_id" in df_snapshot.columns and len(df_snapshot) else "?"
    snapshot_label = f"VPS {_vps} · Sheets · {_sheets_time.strftime('%d/%m/%Y %H:%M')}"
else:
    df_snapshot = df_actual.copy()
    snapshot_label = archivo_actual.name if archivo_actual else "Sin datos"

# ── Respaldo cuando la ultima corrida no dejo ni un nodo valido ──
# Pasa cuando la API rechaza las 113 consultas (p.ej. 403 InsufficientFunds).
# Sin esto el mapa filtra por ok=true, se queda sin filas y pydeck dibuja un
# lienzo vacio sin explicar nada. Se guarda el diagnostico y se retrocede al
# ultimo snapshot con datos reales, rotulado como desactualizado.
snapshot_degradado = None

if not df_snapshot.empty and not _mascara_ok(df_snapshot).any():
    _motivo = ""
    if "error_msg" in df_snapshot.columns:
        _msgs = df_snapshot["error_msg"].dropna().astype(str)
        _msgs = _msgs[_msgs.str.strip() != ""]
        if not _msgs.empty:
            _motivo = _msgs.value_counts().index[0]

    _http = ""
    if "http_status" in df_snapshot.columns:
        _hs = pd.to_numeric(df_snapshot["http_status"], errors="coerce").dropna()
        if not _hs.empty:
            _http = str(int(_hs.mode().iloc[0]))

    snapshot_degradado = {
        "label_fallido": snapshot_label,
        "nodos": len(df_snapshot),
        "http": _http,
        "motivo": _motivo,
        "label_valido": None,
        "hora_valida": None,
    }

    _pool = _df_sheets_1d if not _df_sheets_1d.empty else df_actual
    if not _pool.empty and "consultation_time" in _pool.columns:
        _ok_pool = _pool[_mascara_ok(_pool)]
        if not _ok_pool.empty:
            _t_ok = _ok_pool["consultation_time"].max()
            df_snapshot = _ok_pool[_ok_pool["consultation_time"] == _t_ok].copy()
            _vps_ok = (
                str(df_snapshot["vps_id"].iloc[0])
                if "vps_id" in df_snapshot.columns and len(df_snapshot) else "?"
            )
            snapshot_degradado["label_valido"] = (
                f"VPS {_vps_ok} · {_t_ok.strftime('%d/%m/%Y %H:%M')}"
            )
            snapshot_degradado["hora_valida"] = _t_ok
            snapshot_label = f"{snapshot_degradado['label_valido']} · DESACTUALIZADO"

# ============================================================
# METRICAS PRINCIPALES
# ============================================================
col1, col2, col3, col4 = st.columns(4)

hoy = datetime.now().date()

# VPS 1: desde log local
logs_hoy = logs[logs["timestamp"].dt.date == hoy] if not logs.empty else pd.DataFrame()
llamadas_vps1 = int(logs_hoy["total_nodos"].sum()) if not logs_hoy.empty else 0
# Consultas que de verdad devolvieron datos. El total intentado no sirve para
# saber si el sistema esta sano: con la API caida sigue marcando 1.582.
exitosas_vps1 = int(logs_hoy["consultas_ok"].sum()) if not logs_hoy.empty and "consultas_ok" in logs_hoy.columns else 0
fallidas_vps1 = max(llamadas_vps1 - exitosas_vps1, 0)
ejec_vps1     = len(logs_hoy)
ultima_vps1   = logs.iloc[-1]["timestamp"] if not logs.empty else None
estado_vps1   = logs.iloc[-1]["estado"]    if not logs.empty else "—"

# VPS 2: desde Google Sheets (el log de VPS 2 esta en otro servidor)
df_sheets_hoy = pd.DataFrame()
if not _df_sheets_1d.empty and "consultation_time" in _df_sheets_1d.columns:
    df_sheets_hoy = _df_sheets_1d[
        (_df_sheets_1d["consultation_time"].dt.date == hoy) &
        (_df_sheets_1d["vps_id"].astype(str) == "2")
    ]
llamadas_vps2 = len(df_sheets_hoy)
exitosas_vps2 = int(_mascara_ok(df_sheets_hoy).sum())
fallidas_vps2 = max(llamadas_vps2 - exitosas_vps2, 0)
ejec_vps2     = df_sheets_hoy["consultation_time"].nunique() if not df_sheets_hoy.empty else 0
ultima_vps2   = df_sheets_hoy["consultation_time"].max()    if not df_sheets_hoy.empty else None

# Ultima ejecucion global (el mas reciente entre ambos VPS)
if ultima_vps1 and ultima_vps2 and pd.notna(ultima_vps2):
    if ultima_vps2 > ultima_vps1:
        ultima_str, estado_str = ultima_vps2.strftime("%H:%M"), "VPS2 OK"
    else:
        ultima_str, estado_str = ultima_vps1.strftime("%H:%M"), estado_vps1
elif ultima_vps2 and pd.notna(ultima_vps2):
    ultima_str, estado_str = ultima_vps2.strftime("%H:%M"), "VPS2 OK"
elif ultima_vps1:
    ultima_str, estado_str = ultima_vps1.strftime("%H:%M"), estado_vps1
else:
    ultima_str, estado_str = "—", "Sin datos"

ejec_total = ejec_vps1 + ejec_vps2

def _delta_consultas(llamadas: int, fallidas: int) -> tuple:
    """Delta de la tarjeta: en rojo si hubo consultas fallidas hoy."""
    if fallidas > 0:
        return f"-{fallidas:,} fallidas", "normal"
    return f"{llamadas/config.LIMITE_API_DIARIO*100:.1f}% de 2,500", "off"


with col1:
    _d, _dc = _delta_consultas(llamadas_vps1, fallidas_vps1)
    st.metric("VPS 1 · Nodos OK", f"{exitosas_vps1:,}", _d, delta_color=_dc)
with col2:
    _d, _dc = _delta_consultas(llamadas_vps2, fallidas_vps2)
    st.metric("VPS 2 · Nodos OK", f"{exitosas_vps2:,}", _d, delta_color=_dc)
with col3:
    st.metric("Ejecuciones hoy", ejec_total, "de 28 programadas", delta_color="off")
with col4:
    st.metric("Ultima ejecucion", ultima_str, estado_str, delta_color="off")

if logs.empty and df_sheets_hoy.empty:
    st.info("Aun no hay ejecuciones registradas.")

# ============================================================
# CUOTA DIARIA API TOMTOM
# ============================================================
LIMITE = config.LIMITE_API_DIARIO  # 2500

def _semaforo_cuota(usado: int, limite: int) -> tuple:
    """Devuelve (color_hex, emoji, texto_estado) segun el porcentaje de cuota usada."""
    pct = usado / limite if limite > 0 else 0
    if pct >= 0.95:
        return "#FF4B4B", "🔴", "CRITICO"
    elif pct >= 0.80:
        return "#FFA500", "🟠", "ALTO"
    elif pct >= 0.60:
        return "#FFD700", "🟡", "MODERADO"
    else:
        return "#00C48C", "🟢", "OK"

st.markdown(
    f"<h4 style='color:{UTB_CYAN};margin-top:24px;margin-bottom:4px;letter-spacing:1px;'>"
    f"CUOTA DIARIA API TOMTOM</h4>",
    unsafe_allow_html=True,
)

qa, qb = st.columns(2)

for col_q, vps_label, usado in [(qa, "VPS 1", llamadas_vps1), (qb, "VPS 2", llamadas_vps2)]:
    pct       = min(usado / LIMITE, 1.0)
    color, emoji, estado = _semaforo_cuota(usado, LIMITE)
    restantes = max(LIMITE - usado, 0)
    with col_q:
        st.markdown(
            f"<div style='background:{UTB_NAVY_LIGHT};border-radius:10px;padding:14px 18px;border-left:4px solid {color};box-shadow:0 1px 3px rgba(0,48,135,0.06);border:1px solid {UTB_BORDER};border-left:4px solid {color};'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
            f"  <span style='color:#FFFFFF;font-weight:700;font-size:15px;'>{emoji} {vps_label}</span>"
            f"  <span style='color:{color};font-weight:700;font-size:13px;'>{estado}</span>"
            f"</div>"
            f"<div style='background:rgba(0,0,0,0.25);border-radius:6px;height:12px;overflow:hidden;margin-bottom:8px;'>"
            f"  <div style='background:{color};width:{pct*100:.1f}%;height:100%;border-radius:6px;transition:width 0.4s;'></div>"
            f"</div>"
            f"<div style='display:flex;justify-content:space-between;'>"
            f"  <span style='color:{UTB_GRAY};font-size:12px;'>{usado:,} / {LIMITE:,} llamadas</span>"
            f"  <span style='color:{UTB_GRAY};font-size:12px;'>{restantes:,} restantes · {pct*100:.1f}%</span>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# Advertencia si alguno supera el 80%
for vps_label, usado in [("VPS 1", llamadas_vps1), ("VPS 2", llamadas_vps2)]:
    pct = usado / LIMITE if LIMITE > 0 else 0
    if pct >= 0.95:
        st.error(f"⛔ {vps_label} ha alcanzado el {pct*100:.1f}% de la cuota — riesgo de error 403 InsufficientFunds.")
    elif pct >= 0.80:
        st.warning(f"⚠️ {vps_label} lleva el {pct*100:.1f}% de la cuota diaria. Evita ejecutar pruebas manuales hoy.")

st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

# ============================================================
# AVISO DE CAPTURA DETENIDA
# ============================================================
# Un mapa vacio no explica nada. Si la ultima corrida no trajo un solo nodo
# valido, se dice por que y desde cuando, con el error crudo de la API.
if snapshot_degradado:
    _sd = snapshot_degradado
    _motivo_txt = (_sd["motivo"] or "sin detalle en error_msg")
    _motivo_txt = _motivo_txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(_motivo_txt) > 300:
        _motivo_txt = _motivo_txt[:300] + "..."
    _http_txt = f"HTTP {_sd['http']} · " if _sd["http"] else ""

    if _sd["label_valido"]:
        _horas = (datetime.now() - _sd["hora_valida"]).total_seconds() / 3600
        _respaldo = (
            f"El mapa y el analisis muestran el ultimo dato bueno: "
            f"<b style='color:{UTB_WHITE};'>{_sd['label_valido']}</b> "
            f"({_horas:.1f} h de antiguedad). No es la situacion actual del trafico."
        )
    else:
        _respaldo = "No hay ninguna corrida reciente con datos validos para mostrar."

    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.12);border-left:4px solid {COLOR_CONGESTIONADO};
         padding:14px 18px;border-radius:8px;margin-bottom:16px;">
        <div style="color:{COLOR_CONGESTIONADO};font-size:13px;font-weight:800;
             letter-spacing:1px;margin-bottom:6px;">
            &#9888; CAPTURA DE DATOS DETENIDA</div>
        <div style="color:{UTB_GRAY};font-size:13px;line-height:1.6;">
            La corrida <b style="color:{UTB_WHITE};">{_sd['label_fallido']}</b> devolvio
            <b style="color:{COLOR_CONGESTIONADO};">0 de {_sd['nodos']} nodos validos</b>.<br/>
            {_http_txt}Respuesta de la API:
            <code style="background:{UTB_NAVY_LIGHT};color:{COLOR_LENTO};padding:2px 6px;
             border-radius:4px;font-size:12px;">{_motivo_txt}</code><br/>
            {_respaldo}
        </div>
    </div>""", unsafe_allow_html=True)

# ============================================================
# TABS
# ============================================================
tab_mapa, tab_datos, tab_proceso, tab_historia = st.tabs(
    ["Mapa de Trafico", "Analisis de Nodos", "Monitor del Proceso", "Historico"]
)

# ----------------------------------------------------------------
# TAB MAPA
# ----------------------------------------------------------------
with tab_mapa:
    if df_snapshot.empty:
        st.info("No hay datos para mostrar.")
    else:
        st.markdown(
            f"<div style='color:{UTB_GRAY};font-size:13px;margin-bottom:16px;'>"
            f"Fuente: <code style='background:{UTB_NAVY_LIGHT};color:{UTB_CYAN};padding:4px 8px;border-radius:4px;'>"
            f"{snapshot_label}</code> · {len(df_snapshot)} nodos</div>",
            unsafe_allow_html=True,
        )
        df_ok = df_snapshot[_mascara_ok(df_snapshot)].dropna(subset=["lat", "lon"]).copy()

        if df_ok.empty:
            st.warning(
                "Ningun nodo de esta corrida tiene lectura valida, "
                "asi que el mapa no puede dibujar puntos."
            )

        if "velocidad_ratio" in df_ok.columns:
            df_ok["color"] = df_ok["velocidad_ratio"].apply(color_por_ratio)
            geo = cargar_geometria()

            # Selector de visualizacion: calles (si hay geometria) o puntos
            opciones_vista = (["Calles", "Puntos"] if geo else ["Puntos"])
            vista = st.radio(
                "Visualizacion del mapa", opciones_vista,
                horizontal=True, label_visibility="collapsed",
            )
            if not geo:
                st.caption("Para ver las calles trazadas, ejecuta capturar_geometria.py una vez.")

            try:
                import pydeck as pdk

                tooltip = {
                    "html": "<b style='color:#5eead4;'>{nombre_nodo}</b><br/>"
                            "<span style='color:rgba(255,255,255,0.6);'>Ratio:</span> <b>{ratio_txt}</b><br/>"
                            "<span style='color:rgba(255,255,255,0.6);'>Actual:</span> <b>{currentSpeed}</b> km/h",
                    "style": {
                        "backgroundColor": UTB_NAVY_LIGHT, "color": UTB_WHITE,
                        "padding": "10px", "borderRadius": "8px",
                        "border": f"1px solid {UTB_BORDER}",
                    },
                }

                if vista == "Calles":
                    # Unir geometria (estatica) con el ratio actual de cada nodo
                    ratio_nodo = dict(zip(df_ok["id_nodo"].astype(str), df_ok["velocidad_ratio"]))
                    spd_nodo   = dict(zip(df_ok["id_nodo"].astype(str),
                                          df_ok["currentSpeed"] if "currentSpeed" in df_ok.columns else []))
                    path_rows = []
                    for id_nodo, info in geo.items():
                        r = ratio_nodo.get(str(id_nodo))
                        path_rows.append({
                            "path": info["path"],
                            "color": color_por_ratio(r if r is not None else float("nan")),
                            "nombre_nodo": info.get("nombre", ""),
                            "ratio_txt": f"{r:.2f}" if r is not None and not pd.isna(r) else "—",
                            "currentSpeed": spd_nodo.get(str(id_nodo), "—"),
                        })
                    capa = pdk.Layer(
                        "PathLayer", data=path_rows,
                        get_path="path", get_color="color",
                        get_width=6, width_min_pixels=4,
                        width_scale=1, cap_rounded=True, joint_rounded=True,
                        pickable=True,
                    )
                else:
                    df_ok["ratio_txt"] = df_ok["velocidad_ratio"].apply(
                        lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    capa = pdk.Layer(
                        "ScatterplotLayer", data=df_ok,
                        get_position="[lon, lat]", get_fill_color="color",
                        get_radius=100, pickable=True, opacity=0.8, stroked=True,
                        get_line_color=[255, 255, 255, 80], line_width_min_pixels=1,
                    )

                st.pydeck_chart(pdk.Deck(
                    layers=[capa],
                    initial_view_state=pdk.ViewState(
                        latitude=df_ok["lat"].mean(),
                        longitude=df_ok["lon"].mean(),
                        zoom=12.3, pitch=30,
                    ),
                    tooltip=tooltip,
                    map_style="dark",
                ), height=540)
                leyenda_ratio("ratio")
            except ImportError:
                st.map(df_ok, latitude="lat", longitude="lon")

            st.markdown("### Distribucion del trafico")
            ca, cb, cc, cd = st.columns(4)
            r_ok = df_ok["velocidad_ratio"]
            n_fluido   = (r_ok > UMBRAL_FLUIDO).sum()
            n_moderado = ((r_ok > UMBRAL_MODERADO) & (r_ok <= UMBRAL_FLUIDO)).sum()
            n_lento    = ((r_ok > UMBRAL_LENTO) & (r_ok <= UMBRAL_MODERADO)).sum()
            n_cong     = (r_ok <= UMBRAL_LENTO).sum()
            for col_ui, n, color, label, desc in [
                (ca, n_fluido,   COLOR_FLUIDO,        "FLUIDO",        "Ratio > 0.90"),
                (cb, n_moderado, COLOR_MODERADO,      "MODERADO",      "0.75 – 0.90"),
                (cc, n_lento,    COLOR_LENTO,         "LENTO",         "0.60 – 0.75"),
                (cd, n_cong,     COLOR_CONGESTIONADO, "CONGESTIONADO", "Ratio < 0.60"),
            ]:
                with col_ui:
                    st.markdown(f"""
                    <div style="background:{UTB_NAVY_LIGHT};padding:20px;border-radius:12px;border-left:4px solid {color};border:1px solid {UTB_BORDER};box-shadow:0 2px 8px rgba(0,0,0,0.2);">
                        <div style="color:{color};font-size:12px;font-weight:700;letter-spacing:1px;">● {label}</div>
                        <div style="color:{UTB_WHITE};font-size:36px;font-weight:800;margin:8px 0;">{n}</div>
                        <div style="color:{UTB_GRAY};font-size:12px;">{desc}</div>
                    </div>""", unsafe_allow_html=True)
        else:
            st.map(df_ok, latitude="lat", longitude="lon")

# ----------------------------------------------------------------
# TAB ANALISIS DE NODOS
# ----------------------------------------------------------------
with tab_datos:
    if df_snapshot.empty:
        st.info("No hay datos.")
    else:
        st.caption(f"Fuente: {snapshot_label}")
        if "velocidad_ratio" in df_snapshot.columns:
            st.markdown("### Top 10 nodos mas congestionados")
            # Ranking: el mas congestionado (menor ratio) arriba.
            # En barras horizontales la primera fila va abajo, por eso
            # ordenamos ascendente=False para que el menor ratio quede al tope.
            top10 = (
                df_snapshot[df_snapshot["ok"].astype(str).str.lower().isin(["true", "1"])]
                .nsmallest(10, "velocidad_ratio")
                .sort_values("velocidad_ratio", ascending=False)
            )
            top10["color"] = top10["velocidad_ratio"].apply(lambda r: clasificar_ratio(r)[0])
            fig_top = px.bar(
                top10,
                x="velocidad_ratio",
                y="nombre_nodo",
                orientation="h",
                color="color",
                color_discrete_map="identity",
                labels={"velocidad_ratio": "Ratio velocidad (0=congestionado · 1=fluido)", "nombre_nodo": ""},
                text=top10["velocidad_ratio"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else ""),
            )
            fig_top.update_traces(textposition="outside")
            fig_top = plotly_base(fig_top, height=380)
            fig_top.update_layout(
                xaxis=dict(range=[0, 1.15]),
                showlegend=False,
            )
            st.plotly_chart(fig_top, use_container_width=True)
            leyenda_ratio("ratio")

        st.markdown("### Tabla completa")
        cf1, cf2 = st.columns(2)
        with cf1:
            cats = ["Todas"] + sorted(df_snapshot["categoria"].dropna().unique().tolist())
            cat_sel = st.selectbox("Categoria", cats)
        with cf2:
            zonas = ["Todas"] + sorted(df_snapshot["zona"].dropna().unique().tolist()) if "zona" in df_snapshot.columns else ["Todas"]
            zona_sel = st.selectbox("Zona", zonas)

        df_filt = df_snapshot.copy()
        if cat_sel != "Todas":
            df_filt = df_filt[df_filt["categoria"] == cat_sel]
        if zona_sel != "Todas" and "zona" in df_filt.columns:
            df_filt = df_filt[df_filt["zona"] == zona_sel]

        st.dataframe(df_filt, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar CSV filtrado",
            df_filt.to_csv(index=False).encode("utf-8"),
            file_name=f"trafico_filtrado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

# ----------------------------------------------------------------
# TAB MONITOR DEL PROCESO
# ----------------------------------------------------------------
with tab_proceso:
    # Reconstruir ejecuciones de VPS 2 desde Sheets (su log esta en otro servidor)
    logs_vps2 = pd.DataFrame()
    if not _df_sheets_1d.empty and "consultation_time" in _df_sheets_1d.columns:
        df_v2 = _df_sheets_1d[_df_sheets_1d["vps_id"].astype(str) == "2"].copy()
        if not df_v2.empty:
            df_v2["ok_bool"] = df_v2["ok"].astype(str).str.upper() == "TRUE"
            grp = df_v2.groupby("consultation_time").agg(
                total_nodos=("ok_bool", "count"),
                consultas_ok=("ok_bool", "sum"),
            ).reset_index()
            grp["consultas_error"] = grp["total_nodos"] - grp["consultas_ok"]
            grp["vps_id"] = "2"
            grp["estado"] = grp["consultas_error"].apply(lambda x: "ERROR" if x > 0 else "OK")
            grp["error"] = None
            grp = grp.rename(columns={"consultation_time": "timestamp"})
            logs_vps2 = grp[["timestamp", "vps_id", "total_nodos", "consultas_ok", "consultas_error", "estado", "error"]]

    # Combinar VPS 1 (log local) + VPS 2 (reconstruido desde Sheets)
    if not logs_vps2.empty:
        logs_combined = pd.concat([logs, logs_vps2], ignore_index=True).sort_values("timestamp")
    else:
        logs_combined = logs.copy()

    if logs_combined.empty:
        st.info("No hay registros de ejecuciones aun.")
    else:
        st.markdown("### Ultimas 20 ejecuciones (VPS 1 + VPS 2)")
        st.caption("VPS 1 desde log local · VPS 2 reconstruido desde Google Sheets")
        st.dataframe(
            logs_combined.tail(20).sort_values("timestamp", ascending=False),
            use_container_width=True, hide_index=True,
        )

        st.markdown("### Ejecuciones por hora (hoy)")
        hoy_p = datetime.now().date()
        logs_hoy2 = logs_combined[logs_combined["timestamp"].dt.date == hoy_p].copy()
        if not logs_hoy2.empty:
            logs_hoy2["hora"] = logs_hoy2["timestamp"].dt.strftime("%H:%M")
            por_hora = logs_hoy2.groupby("hora").agg(
                consultas_ok=("consultas_ok", "sum"),
                consultas_error=("consultas_error", "sum"),
                vps=("vps_id", lambda x: "+".join(sorted(x.unique()))),
            ).reset_index()

            fig_proc = go.Figure()
            fig_proc.add_trace(go.Bar(
                x=por_hora["hora"], y=por_hora["consultas_ok"],
                name="OK", marker_color=UTB_CYAN,
                text=por_hora["vps"].apply(lambda v: f"VPS{v}"),
                textposition="inside",
            ))
            fig_proc.add_trace(go.Bar(
                x=por_hora["hora"], y=por_hora["consultas_error"],
                name="Error", marker_color=COLOR_CONGESTIONADO,
            ))
            fig_proc.update_layout(barmode="stack", xaxis_title="Hora", yaxis_title="Consultas")
            fig_proc = plotly_base(fig_proc, height=300)
            st.plotly_chart(fig_proc, use_container_width=True)
            leyenda_ratio("proceso")
        else:
            st.info("Aun no hay ejecuciones hoy.")

        st.markdown("### Errores en los ultimos 7 dias")
        hace_7d = datetime.now() - timedelta(days=7)
        errores = logs_combined[
            (logs_combined["timestamp"] >= hace_7d) &
            (logs_combined["estado"] == "ERROR")
        ]
        if errores.empty:
            st.markdown(
                f"<div style='background:rgba(16,185,129,0.1);border-left:4px solid {COLOR_FLUIDO};"
                f"padding:16px;border-radius:8px;color:{COLOR_FLUIDO};font-weight:600;'>"
                f"✓ Sin errores en los ultimos 7 dias</div>",
                unsafe_allow_html=True,
            )
        else:
            st.dataframe(errores, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------
# TAB HISTORICO
# ----------------------------------------------------------------
with tab_historia:
    st.markdown("### Datos historicos")
    st.caption("Incluye datos de VPS 1 (Turnos 1-2) y VPS 2 (Turnos 3-4)")

    # Rango de fechas disponible (consulta ligera; los datos del periodo se
    # cargan despues, solo para el rango que el usuario elija).
    with st.spinner("Consultando datos disponibles..."):
        min_fecha, max_fecha, fuente_rango = rango_fechas_historico()

    if min_fecha is None:
        st.warning("No hay datos historicos o no hay conexion con la fuente.")
    else:
        # Valor por defecto: ultimos 7 dias, recortado al rango disponible
        ini_default = max(min_fecha, max_fecha - timedelta(days=7))

        hf1, hf2, hf3, hf4 = st.columns([2, 2, 2, 1])
        with hf1:
            fecha_ini = st.date_input(
                "Desde", value=ini_default,
                min_value=min_fecha, max_value=max_fecha,
            )
        with hf2:
            fecha_fin = st.date_input(
                "Hasta", value=max_fecha,
                min_value=min_fecha, max_value=max_fecha,
            )
        with hf3:
            tipo_dia = st.selectbox(
                "Tipo de dia",
                ["Todos", "Solo laborables (L-V)", "Solo fin de semana",
                 "Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"],
            )
        with hf4:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if st.button("Recargar datos", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        st.caption(
            f"Datos disponibles: {min_fecha.strftime('%d/%m/%Y')} → "
            f"{max_fecha.strftime('%d/%m/%Y')} · Fuente: {fuente_rango}"
        )

        if fecha_fin < fecha_ini:
            st.error("La fecha 'Hasta' debe ser mayor o igual a 'Desde'.")
            df_periodo = pd.DataFrame()
        else:
            with st.spinner("Cargando periodo seleccionado..."):
                df_periodo, fuente_datos = cargar_historico(fecha_ini, fecha_fin)

            if fuente_datos is None:
                st.warning("No se pudo cargar el periodo desde ninguna fuente.")
            elif fuente_datos != fuente_rango:
                st.caption(f"Fuente del periodo: {fuente_datos}")

            # Filtro por tipo de dia (cambio 7)
            if not df_periodo.empty and tipo_dia != "Todos":
                wd = df_periodo["consultation_time"].dt.weekday  # 0=Lunes
                dias_idx = {"Lunes": 0, "Martes": 1, "Miercoles": 2, "Jueves": 3,
                            "Viernes": 4, "Sabado": 5, "Domingo": 6}
                if tipo_dia == "Solo laborables (L-V)":
                    df_periodo = df_periodo[wd < 5]
                elif tipo_dia == "Solo fin de semana":
                    df_periodo = df_periodo[wd >= 5]
                else:
                    df_periodo = df_periodo[wd == dias_idx[tipo_dia]]

            if df_periodo.empty:
                st.info(
                    f"Sin datos entre {fecha_ini.strftime('%d/%m/%Y')} y "
                    f"{fecha_fin.strftime('%d/%m/%Y')}"
                    + (f" para '{tipo_dia}'." if tipo_dia != "Todos" else ".")
                )
            else:
                # Metricas del periodo
                n_ejec    = df_periodo["consultation_time"].nunique()
                vel_prom  = df_periodo["currentSpeed"].mean()
                ratio_prom = df_periodo["velocidad_ratio"].mean()
                n_reg     = len(df_periodo)

                mc1, mc2, mc3, mc4 = st.columns(4)
                with mc1: st.metric("Ejecuciones", n_ejec)
                with mc2: st.metric("Vel. promedio", f"{vel_prom:.1f} km/h" if pd.notna(vel_prom) else "—")
                with mc3: st.metric("Ratio promedio", f"{ratio_prom:.2f}" if pd.notna(ratio_prom) else "—")
                with mc4: st.metric("Registros totales", f"{n_reg:,}")

                # --- Grafica 1: Evolucion velocidad promedio ---
                st.markdown("### Evolucion de velocidad promedio")
                evo = (
                    df_periodo.groupby("consultation_time")
                    .agg(vel_actual=("currentSpeed", "mean"), vel_libre=("freeFlowSpeed", "mean"))
                    .reset_index()
                    .sort_values("consultation_time")
                )
                # Insertar cortes (NaN) cuando hay un hueco > 90 min entre ejecuciones
                # consecutivas, para que la noche/dias sin datos se vean como
                # interrupciones reales y no como lineas diagonales engañosas (cambio 6).
                evo = evo.set_index("consultation_time")
                gaps = evo.index.to_series().diff() > pd.Timedelta(minutes=90)
                if gaps.any():
                    filas_gap = []
                    for ts in evo.index[gaps]:
                        filas_gap.append(pd.Series({"vel_actual": None, "vel_libre": None},
                                                   name=ts - pd.Timedelta(minutes=1)))
                    evo = pd.concat([evo, pd.DataFrame(filas_gap)]).sort_index()
                evo = evo.reset_index().rename(columns={"index": "consultation_time"})

                fig_line = go.Figure()
                fig_line.add_trace(go.Scatter(
                    x=evo["consultation_time"], y=evo["vel_libre"],
                    name="Velocidad libre", line=dict(color=UTB_GRAY, dash="dash", width=1.5),
                    connectgaps=False,
                ))
                fig_line.add_trace(go.Scatter(
                    x=evo["consultation_time"], y=evo["vel_actual"],
                    name="Velocidad actual", line=dict(color=UTB_CYAN, width=2),
                    fill="tonexty", fillcolor="rgba(94,234,212,0.12)",
                    connectgaps=False,
                ))
                fig_line.update_layout(xaxis_title="Fecha/Hora", yaxis_title="km/h")
                fig_line = plotly_base(fig_line, height=320)
                st.plotly_chart(fig_line, use_container_width=True)
                leyenda_ratio("velocidad")

                # --- Grafica 2: Top nodos mas congestionados en el periodo ---
                st.markdown("### Nodos mas congestionados en el periodo")
                por_nodo = (
                    df_periodo[df_periodo["ok"].astype(str).str.lower() == "true"]
                    .groupby("nombre_nodo")
                    .agg(ratio_prom=("velocidad_ratio", "mean"), vel_prom=("currentSpeed", "mean"))
                    .reset_index()
                    .nsmallest(15, "ratio_prom")            # 15 mas congestionados
                    .sort_values("ratio_prom", ascending=False)  # mas congestionado arriba
                )
                por_nodo["color"] = por_nodo["ratio_prom"].apply(lambda r: clasificar_ratio(r)[0])
                fig_nodos = px.bar(
                    por_nodo,
                    x="ratio_prom",
                    y="nombre_nodo",
                    orientation="h",
                    color="color",
                    color_discrete_map="identity",
                    labels={"ratio_prom": "Ratio promedio", "nombre_nodo": ""},
                    text=por_nodo["ratio_prom"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else ""),
                )
                fig_nodos.update_traces(textposition="outside")
                fig_nodos = plotly_base(fig_nodos, height=430)
                fig_nodos.update_layout(xaxis=dict(range=[0, 1.15]), showlegend=False)
                st.plotly_chart(fig_nodos, use_container_width=True)
                leyenda_ratio("ratio")

                # --- Grafica 3: Heatmap hora x dia de semana ---
                st.markdown("### Heatmap de congestion por hora y dia")
                dias_disponibles = df_periodo["consultation_time"].dt.date.nunique()
                if dias_disponibles < 2:
                    st.info("Se necesitan al menos 2 dias de datos para mostrar el heatmap.")
                else:
                    df_heat = df_periodo.copy()
                    df_heat["hora"]    = df_heat["consultation_time"].dt.hour
                    df_heat["dia_num"] = df_heat["consultation_time"].dt.weekday  # 0=Lunes

                    pivot = (
                        df_heat.groupby(["dia_num", "hora"])["velocidad_ratio"]
                        .mean()
                        .unstack(fill_value=None)
                    )
                    dias_es = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
                    y_labels = [dias_es[i] for i in pivot.index if i < 7]
                    x_labels = [f"{h:02d}:00" for h in pivot.columns]

                    fig_heat = go.Figure(go.Heatmap(
                        z=pivot.values,
                        x=x_labels,
                        y=y_labels,
                        colorscale=[[0, COLOR_CONGESTIONADO], [0.5, COLOR_LENTO], [1, COLOR_FLUIDO]],
                        zmin=0, zmax=1,
                        colorbar=dict(title="Ratio", tickfont=dict(color=UTB_WHITE)),
                        hovertemplate="Hora: %{x}<br>Dia: %{y}<br>Ratio: %{z:.2f}<extra></extra>",
                    ))
                    fig_heat.update_layout(
                        paper_bgcolor=UTB_NAVY_LIGHT,
                        plot_bgcolor=UTB_NAVY_DARK,
                        font_color=UTB_WHITE,
                        font_family="DM Sans",
                        height=320,
                        margin=dict(l=0, r=0, t=10, b=0),
                        xaxis=dict(title="Hora del dia", gridcolor="rgba(255,255,255,0.08)"),
                        yaxis=dict(title="", gridcolor="rgba(255,255,255,0.08)"),
                    )
                    st.plotly_chart(fig_heat, use_container_width=True)

                # ------------------------------------------------
                # Grafica 4: Hora pico vs hora valle
                # ------------------------------------------------
                st.markdown("### Hora pico vs hora valle")
                st.caption("Velocidad promedio por franja horaria — identifica cuando fluye mejor la ciudad")

                FRANJAS = {
                    "Madrugada (00–05)": (0, 5),
                    "Mañana temprano (06–07)": (6, 7),
                    "Hora pico AM (08–09)": (8, 9),
                    "Media mañana (10–11)": (10, 11),
                    "Hora pico medio (12–13)": (12, 13),
                    "Tarde (14–15)": (14, 15),
                    "Pre-pico PM (16)": (16, 16),
                    "Hora pico PM (17–18)": (17, 18),
                    "Noche (19–23)": (19, 23),
                }

                df_franjas = df_periodo.copy()
                df_franjas["hora_num"] = df_franjas["consultation_time"].dt.hour

                filas_f = []
                for label, (h_ini, h_fin) in FRANJAS.items():
                    sub = df_franjas[
                        (df_franjas["hora_num"] >= h_ini) & (df_franjas["hora_num"] <= h_fin)
                    ]
                    if sub.empty:
                        continue
                    filas_f.append({
                        "franja": label,
                        "vel_actual": sub["currentSpeed"].mean(),
                        "vel_libre":  sub["freeFlowSpeed"].mean(),
                        "ratio":      sub["velocidad_ratio"].mean(),
                        "n_muestras": len(sub),
                    })

                if filas_f:
                    df_f = pd.DataFrame(filas_f)
                    fig_franjas = go.Figure()
                    fig_franjas.add_trace(go.Bar(
                        name="Velocidad libre",
                        x=df_f["franja"],
                        y=df_f["vel_libre"],
                        marker_color=UTB_GRAY,
                        opacity=0.55,
                    ))
                    fig_franjas.add_trace(go.Bar(
                        name="Velocidad actual",
                        x=df_f["franja"],
                        y=df_f["vel_actual"],
                        marker_color=[
                            COLOR_FLUIDO if r > 0.75 else (COLOR_LENTO if r > 0.5 else COLOR_CONGESTIONADO)
                            for r in df_f["ratio"].fillna(0)
                        ],
                    ))
                    # Linea de ratio superpuesta (eje Y secundario)
                    fig_franjas.add_trace(go.Scatter(
                        name="Ratio (eje →)",
                        x=df_f["franja"],
                        y=df_f["ratio"],
                        mode="lines+markers",
                        yaxis="y2",
                        line=dict(color=UTB_CYAN, width=2),
                        marker=dict(size=8, color=UTB_CYAN),
                    ))
                    fig_franjas.update_layout(
                        barmode="group",
                        xaxis_title="",
                        yaxis=dict(title="km/h", gridcolor="rgba(138,154,184,0.15)"),
                        yaxis2=dict(
                            title=dict(text="Ratio (0–1)", font=dict(color=UTB_CYAN)),
                            overlaying="y",
                            side="right",
                            range=[0, 1.2],
                            showgrid=False,
                            tickfont=dict(color=UTB_CYAN),
                        ),
                    )
                    fig_franjas = plotly_base(fig_franjas, height=370)
                    st.plotly_chart(fig_franjas, use_container_width=True)
                    leyenda_ratio("velocidad")

                    # Mini tabla resumen
                    df_f_disp = df_f.copy()
                    df_f_disp["vel_actual"]  = df_f_disp["vel_actual"].apply(lambda x: f"{x:.1f} km/h" if pd.notna(x) else "—")
                    df_f_disp["vel_libre"]   = df_f_disp["vel_libre"].apply(lambda x: f"{x:.1f} km/h" if pd.notna(x) else "—")
                    df_f_disp["ratio"]       = df_f_disp["ratio"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    df_f_disp = df_f_disp.rename(columns={
                        "franja": "Franja", "vel_actual": "Vel. actual",
                        "vel_libre": "Vel. libre", "ratio": "Ratio", "n_muestras": "Muestras",
                    })
                    st.dataframe(df_f_disp, use_container_width=True, hide_index=True)
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.05);border-left:3px solid {UTB_CYAN};"
                        f"border-radius:6px;padding:10px 14px;margin-top:6px;font-size:12px;"
                        f"color:rgba(255,255,255,0.75);'>"
                        f"<b style='color:{UTB_CYAN};'>¿Por qué varían las muestras?</b> "
                        f"Cada franja agrupa distinta cantidad de horas y de ejecuciones: las franjas "
                        f"con más horas o más días dentro del rango seleccionado acumulan más mediciones "
                        f"(113 nodos por ejecución). Franjas con pocas muestras son menos representativas "
                        f"y deben interpretarse con cautela.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("No hay suficientes datos para calcular franjas horarias en este periodo.")

                st.divider()

                # ------------------------------------------------
                # Grafica 5: Vista de un solo nodo
                # ------------------------------------------------
                st.markdown("### Vista de un solo nodo")
                st.caption("Selecciona un punto de monitoreo para ver su evolucion historica completa")

                nodos_disponibles = sorted(
                    df_periodo["nombre_nodo"].dropna().unique().tolist()
                ) if "nombre_nodo" in df_periodo.columns else []

                if not nodos_disponibles:
                    st.info("No hay datos de nodos en el periodo seleccionado.")
                else:
                    nodo_sel = st.selectbox(
                        "Nodo",
                        nodos_disponibles,
                        key="nodo_historico_sel",
                    )
                    df_nodo = df_periodo[df_periodo["nombre_nodo"] == nodo_sel].copy()
                    df_nodo = df_nodo.sort_values("consultation_time")

                    if df_nodo.empty:
                        st.info(f"Sin datos para {nodo_sel} en el periodo.")
                    else:
                        # Metricas del nodo
                        vel_n     = df_nodo["currentSpeed"].mean()
                        ratio_n   = df_nodo["velocidad_ratio"].mean()
                        delay_n   = df_nodo["delay_abs_seg"].mean()
                        n_obs     = len(df_nodo)

                        nc1, nc2, nc3, nc4 = st.columns(4)
                        with nc1: st.metric("Vel. promedio", f"{vel_n:.1f} km/h" if pd.notna(vel_n) else "—")
                        with nc2: st.metric("Ratio promedio", f"{ratio_n:.2f}" if pd.notna(ratio_n) else "—")
                        with nc3: st.metric("Demora prom.", f"{delay_n:.0f} s" if pd.notna(delay_n) else "—")
                        with nc4: st.metric("Observaciones", n_obs)

                        # Grafica de velocidad en el tiempo
                        fig_nodo = go.Figure()
                        fig_nodo.add_trace(go.Scatter(
                            x=df_nodo["consultation_time"],
                            y=df_nodo["freeFlowSpeed"],
                            name="Velocidad libre",
                            line=dict(color=UTB_GRAY, dash="dash", width=1.5),
                        ))
                        fig_nodo.add_trace(go.Scatter(
                            x=df_nodo["consultation_time"],
                            y=df_nodo["currentSpeed"],
                            name="Velocidad actual",
                            line=dict(color=UTB_CYAN, width=2),
                            fill="tonexty",
                            fillcolor="rgba(94,234,212,0.12)",
                        ))
                        fig_nodo.update_layout(
                            xaxis_title="Fecha/Hora",
                            yaxis_title="km/h",
                            title=dict(text=nodo_sel, font=dict(color=UTB_WHITE, size=13)),
                        )
                        fig_nodo = plotly_base(fig_nodo, height=300)
                        st.plotly_chart(fig_nodo, use_container_width=True)
                        leyenda_ratio("velocidad")

                        # Ratio promedio por hora del dia (barras)
                        df_nodo["hora_num"] = df_nodo["consultation_time"].dt.hour
                        por_hora_n = (
                            df_nodo.groupby("hora_num")
                            .agg(ratio_h=("velocidad_ratio", "mean"), vel_h=("currentSpeed", "mean"))
                            .reset_index()
                        )

                        fig_hora_n = go.Figure()
                        fig_hora_n.add_trace(go.Bar(
                            x=[f"{h:02d}:00" for h in por_hora_n["hora_num"]],
                            y=por_hora_n["ratio_h"],
                            marker_color=[
                                COLOR_FLUIDO if r > 0.75 else (COLOR_LENTO if r > 0.5 else COLOR_CONGESTIONADO)
                                for r in por_hora_n["ratio_h"].fillna(0)
                            ],
                            name="Ratio por hora",
                            text=por_hora_n["ratio_h"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else ""),
                            textposition="outside",
                        ))
                        fig_hora_n.update_layout(
                            xaxis_title="Hora del dia",
                            yaxis_title="Ratio (0=congestion · 1=fluido)",
                            yaxis=dict(range=[0, 1.2]),
                        )
                        fig_hora_n = plotly_base(fig_hora_n, height=280)
                        st.plotly_chart(fig_hora_n, use_container_width=True)
                        leyenda_ratio("ratio")

                        # Peor hora / Mejor hora
                        if not por_hora_n.empty:
                            peor = por_hora_n.loc[por_hora_n["ratio_h"].idxmin()]
                            mejor = por_hora_n.loc[por_hora_n["ratio_h"].idxmax()]
                            ph1, ph2 = st.columns(2)
                            with ph1:
                                st.markdown(
                                    f"<div style='background:rgba(239,68,68,0.1);border-left:3px solid {COLOR_CONGESTIONADO};"
                                    f"padding:12px 16px;border-radius:6px;'>"
                                    f"<div style='color:{COLOR_CONGESTIONADO};font-size:11px;font-weight:700;'>⚠ PEOR HORA</div>"
                                    f"<div style='color:{UTB_WHITE};font-size:22px;font-weight:700;'>{int(peor['hora_num']):02d}:00</div>"
                                    f"<div style='color:{UTB_GRAY};font-size:12px;'>Ratio {peor['ratio_h']:.2f} · "
                                    f"Vel. {peor['vel_h']:.1f} km/h</div></div>",
                                    unsafe_allow_html=True,
                                )
                            with ph2:
                                st.markdown(
                                    f"<div style='background:rgba(16,185,129,0.1);border-left:3px solid {COLOR_FLUIDO};"
                                    f"padding:12px 16px;border-radius:6px;'>"
                                    f"<div style='color:{COLOR_FLUIDO};font-size:11px;font-weight:700;'>✓ MEJOR HORA</div>"
                                    f"<div style='color:{UTB_WHITE};font-size:22px;font-weight:700;'>{int(mejor['hora_num']):02d}:00</div>"
                                    f"<div style='color:{UTB_GRAY};font-size:12px;'>Ratio {mejor['ratio_h']:.2f} · "
                                    f"Vel. {mejor['vel_h']:.1f} km/h</div></div>",
                                    unsafe_allow_html=True,
                                )

                st.divider()

                # ------------------------------------------------
                # Exportar reporte HTML
                # ------------------------------------------------
                st.markdown("### Exportar reporte")
                st.caption("Descarga un reporte HTML con todos los graficos — abre en tu navegador y usa Ctrl+P para exportar a PDF")

                if st.button("📥 Generar reporte HTML", use_container_width=False):
                    with st.spinner("Generando reporte..."):
                        # Construir HTML con plotly embebido
                        periodo_label = f"{fecha_ini.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')}"
                        ts_gen = datetime.now().strftime("%d/%m/%Y %H:%M")

                        # Volver a generar las figuras (sin cache de streamlit)
                        evo2 = (
                            df_periodo.groupby("consultation_time")
                            .agg(vel_actual=("currentSpeed", "mean"), vel_libre=("freeFlowSpeed", "mean"))
                            .reset_index().sort_values("consultation_time")
                        )
                        fig_r1 = go.Figure()
                        fig_r1.add_trace(go.Scatter(x=evo2["consultation_time"], y=evo2["vel_libre"],
                            name="Velocidad libre", line=dict(color="#8A9AB8", dash="dash", width=1.5)))
                        fig_r1.add_trace(go.Scatter(x=evo2["consultation_time"], y=evo2["vel_actual"],
                            name="Velocidad actual", line=dict(color="#00D4D4", width=2),
                            fill="tonexty", fillcolor="rgba(94,234,212,0.12)"))
                        fig_r1.update_layout(title="Evolucion de velocidad promedio",
                            xaxis_title="Fecha/Hora", yaxis_title="km/h",
                            paper_bgcolor="#0A1F44", plot_bgcolor="#15294D",
                            font_color="#FFFFFF", height=350)

                        por_nodo2 = (
                            df_periodo[df_periodo["ok"].astype(str).str.lower() == "true"]
                            .groupby("nombre_nodo")
                            .agg(ratio_prom=("velocidad_ratio", "mean"), vel_prom=("currentSpeed", "mean"))
                            .reset_index().sort_values("ratio_prom").head(15)
                        )
                        fig_r2 = px.bar(por_nodo2, x="ratio_prom", y="nombre_nodo", orientation="h",
                            color="ratio_prom",
                            color_continuous_scale=[[0,"#EF4444"],[0.5,"#F59E0B"],[1,"#10B981"]],
                            labels={"ratio_prom": "Ratio promedio", "nombre_nodo": ""},
                            title="Nodos mas congestionados")
                        fig_r2.update_coloraxes(showscale=False)
                        fig_r2.update_layout(paper_bgcolor="#0A1F44", plot_bgcolor="#15294D",
                            font_color="#FFFFFF", height=420, xaxis=dict(range=[0,1.15]))

                        html_parts = [f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Reporte Trafico Cartagena · {periodo_label}</title>
<style>
  body {{ background:#0A1F44; color:#FFFFFF; font-family:sans-serif; margin:0; padding:24px; }}
  h1 {{ color:#00D4D4; border-bottom:2px solid #00D4D4; padding-bottom:8px; }}
  h2 {{ color:#00D4D4; font-size:16px; text-transform:uppercase; letter-spacing:1px; margin-top:32px; }}
  .meta {{ color:#8A9AB8; font-size:13px; margin-bottom:24px; }}
  .metric-box {{ display:inline-block; background:#15294D; border-left:3px solid #00D4D4;
    padding:12px 20px; border-radius:6px; margin:8px 8px 8px 0; }}
  .metric-label {{ color:#8A9AB8; font-size:11px; font-weight:700; text-transform:uppercase; }}
  .metric-value {{ color:#FFFFFF; font-size:24px; font-weight:700; }}
  .chart-wrap {{ margin:16px 0; }}
  @media print {{ body {{ background:#fff; color:#000; }} h1,h2 {{ color:#003366; }} }}
</style>
</head>
<body>
<h1>Monitor de Trafico · Cartagena</h1>
<p class="meta">Periodo: <b>{periodo_label}</b> &nbsp;|&nbsp; Generado: {ts_gen} &nbsp;|&nbsp;
Fuente: TomTom Traffic Flow · VPS 1 + VPS 2</p>

<div>
  <div class="metric-box"><div class="metric-label">Ejecuciones</div>
    <div class="metric-value">{n_ejec}</div></div>
  <div class="metric-box"><div class="metric-label">Vel. promedio</div>
    <div class="metric-value">{f"{vel_prom:.1f} km/h" if pd.notna(vel_prom) else "—"}</div></div>
  <div class="metric-box"><div class="metric-label">Ratio promedio</div>
    <div class="metric-value">{f"{ratio_prom:.2f}" if pd.notna(ratio_prom) else "—"}</div></div>
  <div class="metric-box"><div class="metric-label">Registros</div>
    <div class="metric-value">{n_reg:,}</div></div>
</div>

<h2>Evolucion de velocidad promedio</h2>
<div class="chart-wrap">
{fig_r1.to_html(full_html=False, include_plotlyjs="cdn")}
</div>

<h2>Nodos mas congestionados</h2>
<div class="chart-wrap">
{fig_r2.to_html(full_html=False, include_plotlyjs=False)}
</div>
"""]
                        # Agregar tabla de franjas si existe
                        if filas_f:
                            tabla_rows = "".join(
                                f"<tr><td>{r['franja']}</td><td>{r['vel_actual']:.1f} km/h</td>"
                                f"<td>{r['vel_libre']:.1f} km/h</td><td>{r['ratio']:.2f}</td>"
                                f"<td>{r['n_muestras']}</td></tr>"
                                for r in filas_f if pd.notna(r.get("vel_actual"))
                            )
                            html_parts.append(f"""
<h2>Franjas horarias</h2>
<table style="width:100%;border-collapse:collapse;color:#FFF;">
  <thead><tr style="border-bottom:1px solid #00D4D4;color:#8A9AB8;font-size:12px;">
    <th style="text-align:left;padding:8px;">Franja</th>
    <th>Vel. actual</th><th>Vel. libre</th><th>Ratio</th><th>Muestras</th>
  </tr></thead>
  <tbody>{tabla_rows}</tbody>
</table>""")

                        html_parts.append(f"""
<p style="color:#8A9AB8;font-size:11px;margin-top:40px;border-top:1px solid #15294D;padding-top:12px;">
  Universidad Tecnológica de Bolívar · Monitor de Trafico Cartagena ·
  Generado el {ts_gen}
</p>
</body></html>""")

                        html_final = "\n".join(html_parts)

                    st.download_button(
                        label="⬇ Descargar reporte HTML",
                        data=html_final.encode("utf-8"),
                        file_name=f"reporte_trafico_{fecha_ini.strftime('%Y%m%d')}_{fecha_fin.strftime('%Y%m%d')}.html",
                        mime="text/html",
                        use_container_width=False,
                    )
                    st.success("Reporte generado. Haz clic en el boton de descarga.")

# ============================================================
# FOOTER
# ============================================================
st.markdown(f"""
<div class="utb-footer">
    <strong style="color:{UTB_CYAN};">Universidad Tecnológica de Bolívar</strong> ·
    Monitor de Trafico Cartagena ·
    Fuente: <span style="color:{UTB_WHITE};">TomTom Traffic Flow API</span>
</div>
""", unsafe_allow_html=True)

# ============================================================
# NOTA DE ACTUALIZACION MANUAL
# ============================================================
# El auto-refresco fue desactivado: recargaba la pagina completa y
# perdia los filtros seleccionados (feedback del asesor). Ahora la
# actualizacion es manual con el boton "Recargar datos" del menu lateral.
st.markdown(
    f"<div style='text-align:center;color:{UTB_GRAY};font-size:11px;"
    f"margin-top:6px;padding:4px;'>"
    f"Los datos no se actualizan solos · usa <b style='color:{UTB_CYAN};'>Recargar datos</b> "
    f"en el menu lateral para traer la informacion mas reciente</div>",
    unsafe_allow_html=True,
)
