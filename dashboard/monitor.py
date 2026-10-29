"""
Dashboard Streamlit - Smart City Cartagena.
Diseño claro con tarjetas, tipografía Inter y componentes de movilidad urbana.
"""
import html
import json
import sys
import time
import glob
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
import config        # noqa: E402
import google_upload  # noqa: E402
import horario       # noqa: E402
import analisis_nodo  # noqa: E402
import analisis_temporal  # noqa: E402
import mapa_nodos     # noqa: E402
import red_nodos      # noqa: E402
from security_utils import sanitizar_error  # noqa: E402

# ============================================================
# CONFIGURACION DE PAGINA
# ============================================================
st.set_page_config(
    page_title="Smart City Cartagena",
    layout="wide",
    page_icon="🚦",
    initial_sidebar_state="expanded",
)

# Streamlit toma el idioma del calendario de ``navigator.language`` y no
# permite fijarlo desde ``st.date_input``. Este observador traduce los textos
# del calendario y de su lista de meses, incluidos los elementos que BaseWeb
# crea en portales fuera del widget, y los textos fijos en ingles de Streamlit
# que ve el usuario: barra de las tablas, sus avisos y el indicador de carga.
components.html(
    """
    <script>
    (() => {
      try {
        const parentWindow = window.parent;
        const doc = parentWindow.document;
        if (parentWindow.__calendarioEspanolObserver) {
          parentWindow.__calendarioEspanolObserver.disconnect();
        }

        const traducciones = {
          January: "Enero", February: "Febrero", March: "Marzo",
          April: "Abril", May: "Mayo", June: "Junio", July: "Julio",
          August: "Agosto", September: "Septiembre", October: "Octubre",
          November: "Noviembre", December: "Diciembre",
          Mo: "Lu", Tu: "Ma", We: "Mi", Th: "Ju",
          Fr: "Vi", Sa: "Sá", Su: "Do"
        };
        const etiquetas = {
          "Previous month": "Mes anterior",
          "Next month": "Mes siguiente",
          "Select a month": "Seleccionar mes",
          "Select a year": "Seleccionar año"
        };
        const textosStreamlit = {
          "Download as CSV": "Descargar como CSV",
          "Search": "Buscar",
          "Fullscreen": "Pantalla completa",
          "Close fullscreen": "Salir de pantalla completa",
          "Show/hide columns": "Mostrar u ocultar columnas",
          "Running...": "Cargando...",
          "Running…": "Cargando…",
          "Stop": "Detener",
          "No results": "Sin resultados",
          "Clear all": "Borrar todo"
        };
        const zonasStreamlit = '[role="tooltip"], [data-baseweb="tooltip"], ' +
          '[data-testid="stStatusWidget"], [data-testid="stElementToolbar"], [role="listbox"]';

        const traducirTexto = (raiz, diccionario = traducciones) => {
          const walker = doc.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
          const nodos = [];
          while (walker.nextNode()) nodos.push(walker.currentNode);
          nodos.forEach((nodo) => {
            const limpio = nodo.nodeValue.trim();
            if (diccionario[limpio]) {
              nodo.nodeValue = nodo.nodeValue.replace(limpio, diccionario[limpio]);
            }
          });
        };

        const traducirCalendarios = () => {
          doc.querySelectorAll('[data-baseweb="calendar"], [role="listbox"]').forEach((raiz) => traducirTexto(raiz));
          doc.querySelectorAll('[data-baseweb="calendar"] [aria-label]').forEach((elemento) => {
            const etiqueta = elemento.getAttribute('aria-label');
            if (etiquetas[etiqueta]) elemento.setAttribute('aria-label', etiquetas[etiqueta]);
          });
          doc.querySelectorAll(zonasStreamlit).forEach((raiz) => {
            traducirTexto(raiz, textosStreamlit);
            raiz.querySelectorAll('[aria-label], [title]').forEach((elemento) => {
              ['aria-label', 'title'].forEach((atributo) => {
                const valor = elemento.getAttribute(atributo);
                if (textosStreamlit[valor]) elemento.setAttribute(atributo, textosStreamlit[valor]);
              });
            });
          });
        };

        const observer = new MutationObserver(traducirCalendarios);
        observer.observe(doc.body, {childList: true, subtree: true, characterData: true});
        parentWindow.__calendarioEspanolObserver = observer;
        traducirCalendarios();
      } catch (_) {
        // El calendario sigue siendo util si un navegador restringe el iframe.
      }
    })();
    </script>
    """,
    height=0,
)

# ============================================================
# PALETA DEL DASHBOARD R (app_prueba.R) — tema claro azul + menta
# ============================================================
R_AZUL_OSC    = "#12307a"   # --blue-d / --ink: tinta y titulos
R_AZUL        = "#1f48b8"   # --blue: barra lateral, acentos de texto
R_AZUL_MED    = "#2f66e0"   # --blue-m
R_MENTA       = "#2dd4bf"   # --mint: bordes y detalles
R_MENTA_OSC   = "#14b8a6"   # --mint-d
R_MENTA_CLARA = "#5eead4"   # acento sobre los fondos azules (encabezado, barra lateral)
R_LINEA       = "#ececf0"   # --line: divisores y bordes de controles
R_TENUE       = "#58585d"   # --muted: texto secundario
R_SOMBRA      = "0 1px 2px rgba(17,17,19,.06), 0 12px 28px -12px rgba(17,17,19,.14)"

# Mismos nombres que el original para no reescribir cada uso. Cambia el
# papel de algunos: UTB_WHITE pasa a ser la tinta (texto principal),
# UTB_NAVY_LIGHT la superficie blanca de las tarjetas y UTB_CYAN el acento
# de texto (la menta no se lee sobre blanco; queda para bordes y barras).
UTB_NAVY       = R_AZUL
UTB_NAVY_DARK  = R_AZUL_OSC
UTB_NAVY_LIGHT = "#ffffff"
UTB_BLUE_LIGHT = R_AZUL_MED
UTB_CYAN       = R_AZUL
UTB_CYAN_DARK  = R_MENTA_OSC
UTB_BG         = "#fcfcfd"
UTB_BORDER     = R_LINEA
UTB_WHITE      = "#111113"
UTB_GRAY       = R_TENUE
SUPERFICIE_SUAVE = "#f6f6f8"   # avisos y leyendas sobre el fondo claro
SERIE_ACTUAL   = "#3b82f6"     # COL$azul: serie principal de las graficas
SERIE_LIBRE    = "#94a3b8"     # COL$gris: velocidad de flujo libre

# Colores de nivel del R por nombre (Fluido verde, Moderado ambar,
# Congestionado rojo). "Lento" no existe en el R: toma su naranja (bg-orange).
# Los umbrales siguen siendo los del asesor (0.90 / 0.75 / 0.60).
COLOR_FLUIDO        = "#10b981"   # verde esmeralda — ratio > 0.90
COLOR_MODERADO      = "#f59e0b"   # ambar           — 0.75 a 0.90
COLOR_LENTO         = "#f97316"   # naranja         — 0.60 a 0.75
COLOR_CONGESTIONADO = "#ef4444"   # rojo            — ratio < 0.60

# Variantes de alto contraste para texto sobre superficies claras. Los tonos
# anteriores se conservan en barras, puntos, bordes y mapas.
TEXTO_FLUIDO        = "#047857"
TEXTO_MODERADO      = "#92400e"
TEXTO_LENTO         = "#c2410c"
TEXTO_CONGESTIONADO = "#b91c1c"
TEXTO_MENTA         = "#0f766e"

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

def _rgba(hex_color: str, alfa: float) -> str:
    """'#rrggbb' -> 'rgba(r,g,b,alfa)' para fondos translucidos."""
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alfa})"


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
# CSS PERSONALIZADO — Paleta del dashboard R + Inter
# ============================================================
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    .stApp label, .stApp a, .stApp td, .stApp th, .stApp button, .stApp input,
    .stApp [data-testid="stMarkdown"],
    .stApp [data-testid="stMetricLabel"],
    .stApp [data-testid="stMetricValue"],
    .stApp [data-testid="stMetricDelta"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label {{
        font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif !important;
    }}

    /* ── Fondo general (.content-wrapper del R) ── */
    .stApp {{
        background: #fcfcfd;
        color: #111113;
        color-scheme: light;
    }}
    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1480px;
    }}

    /* ── Encabezado grande (.hero del R) ── */
    .utb-header {{
        background: linear-gradient(120deg, #1b3fa6 0%, #2a5bd0 55%, #3f7cf0 100%);
        padding: 28px 34px;
        border-radius: 36px;
        margin-bottom: 28px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 28px;
        flex-wrap: wrap;
        box-shadow: 0 1px 2px rgba(17,17,19,.06), 0 18px 36px -18px rgba(31,72,184,.38);
        position: relative;
        overflow: hidden;
        isolation: isolate;
    }}
    .utb-header::before {{
        content: "";
        position: absolute;
        z-index: -1;
        width: 360px;
        height: 360px;
        right: -110px;
        top: -205px;
        border: 1px solid rgba(255,255,255,.18);
        border-radius: 50%;
        box-shadow: 0 0 0 46px rgba(255,255,255,.035), 0 0 0 92px rgba(255,255,255,.025);
    }}
    .utb-header::after {{
        content: "";
        position: absolute;
        z-index: -1;
        inset: 0;
        opacity: .13;
        background-image: radial-gradient(rgba(255,255,255,.8) .8px, transparent .8px);
        background-size: 18px 18px;
        mask-image: linear-gradient(90deg, transparent 28%, #000 68%, transparent 100%);
    }}
    .utb-header-content {{
        position: relative;
        z-index: 2;
        min-width: 410px;
    }}
    .utb-eyebrow {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 9px;
        color: #dbe7ff;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: .13em;
        text-transform: uppercase;
    }}
    .utb-live-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: {R_MENTA_CLARA};
        box-shadow: 0 0 0 5px rgba(94,234,212,.16);
    }}
    .utb-brand {{
        color: #ffffff !important;
        font-size: 44px !important;
        font-weight: 800 !important;
        margin: 0 0 14px !important;
        padding: 0 !important;
        letter-spacing: -1.6px;
        line-height: 1.1 !important;
    }}
    .utb-brand-accent {{ color: {R_MENTA_CLARA}; font-weight: 800; }}
    .utb-header-chips {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }}
    .utb-header-chip {{
        display: inline-flex;
        align-items: center;
        min-height: 28px;
        padding: 5px 11px;
        border: 1px solid rgba(255,255,255,.20);
        border-radius: 999px;
        background: rgba(255,255,255,.10);
        color: #eef4ff;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: .02em;
        backdrop-filter: blur(6px);
    }}
    .utb-route {{
        position: absolute;
        z-index: 1;
        top: 50%;
        right: 245px;
        width: 215px;
        height: 84px;
        transform: translateY(-50%);
        opacity: .78;
        pointer-events: none;
    }}
    .utb-status {{
        position: relative;
        z-index: 2;
        min-width: 210px;
        text-align: right;
    }}
    .utb-status-label {{
        margin-bottom: 7px;
        color: rgba(255,255,255,.68);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
    }}
    .utb-clock {{
        color: {R_AZUL_OSC};
        font-size: 14px;
        font-weight: 600;
        background: #ffffff;
        padding: 9px 22px;
        border-radius: 999px;
        display: inline-block;
    }}
    .utb-next-run {{
        margin-top: 9px;
        color: #dbe7ff;
        font-size: 12px;
    }}
    .utb-next-run span {{ color: {R_MENTA_CLARA}; font-weight: 700; }}

    /* ── Tarjetas de indicadores (.small-box del R) ── */
    [data-testid="stMetric"] {{
        background: #ffffff;
        padding: 22px 24px 20px;
        border-radius: 28px;
        border: 0;
        box-shadow: {R_SOMBRA};
        transition: all 0.2s;
        position: relative;
        overflow: hidden;
    }}
    [data-testid="stMetric"]::before {{
        content: "";
        display: block;
        width: 34px;
        height: 5px;
        margin-bottom: 15px;
        border-radius: 999px;
        background: linear-gradient(90deg, {R_AZUL_MED}, {R_MENTA});
    }}
    [data-testid="stMetric"]:hover {{
        box-shadow: 0 2px 4px rgba(17,17,19,.07), 0 20px 34px -14px rgba(17,17,19,.2);
        transform: translateY(-2px);
    }}
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{
        color: {R_TENUE} !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        text-transform: none;
        letter-spacing: .02em;
    }}
    [data-testid="stMetricValue"] {{
        color: {R_AZUL_OSC} !important;
        font-size: 34px !important;
        font-weight: 700 !important;
        letter-spacing: -1px;
    }}

    /* ── Etiquetas y campos (controles del R) ── */
    .stSelectbox label, .stTextInput label, .stDateInput label,
    .stSelectbox label p, .stTextInput label p, .stDateInput label p {{
        color: {R_TENUE} !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.7px;
    }}
    .stApp [data-baseweb="select"] > div,
    .stApp [data-baseweb="input"] {{
        background: #f7faff !important;
        border-color: #cbd9f3 !important;
        border-radius: 10px !important;
    }}
    .stApp [data-baseweb="input"] > div, .stApp input {{ background: transparent !important; }}
    [data-testid="stDataFrame"] {{
        background: #ffffff;
        border-radius: 24px;
        border: 0;
        box-shadow: {R_SOMBRA};
        overflow: hidden;
    }}

    /* ── Graficas y mapas en caja blanca (.box del R) ── */
    [data-testid="stPlotlyChart"] {{
        background: #ffffff;
        border: 0;
        border-radius: 28px;
        box-shadow: {R_SOMBRA};
        /* Sin relleno: Plotly toma el ancho y el alto completos del
           recuadro, y con relleno se salia por la derecha (las 00:00, el
           titulo del eje derecho) y por abajo ("Hora del dia"). El aire lo
           dan los margenes de plotly_base. */
        padding: 0;
    }}
    /* Boton propio: Plotly no recibe el control nativo de pantalla completa
       en esta version de Streamlit. */
    [class*="st-key-expandir_grafica_"] button {{
        width: 38px !important;
        min-width: 38px !important;
        height: 38px !important;
        min-height: 38px !important;
        padding: 0 !important;
        border: 0 !important;
        border-radius: 12px !important;
        background: {R_AZUL} !important;
        color: #ffffff !important;
        font-size: 18px !important;
        font-weight: 700 !important;
        box-shadow: 0 6px 14px -8px rgba(18,48,122,.65) !important;
    }}
    [class*="st-key-expandir_grafica_"] button:hover {{
        background: {R_AZUL_OSC} !important;
        color: #ffffff !important;
    }}
    [data-testid="stDialog"] [role="dialog"] {{
        width: min(96vw, 1800px) !important;
        max-width: 96vw !important;
    }}
    iframe[title="streamlit_folium.st_folium"] {{
        border: 0 !important;
        border-radius: 28px;
        box-shadow: {R_SOMBRA};
    }}

    /* ── Leyenda editorial del índice de fluidez ── */
    .flow-legend {{
        position: relative;
        overflow: hidden;
        margin-top: 10px;
        padding: 18px;
        background: #ffffff;
        border: 1px solid #e7eaf0;
        border-radius: 22px;
        box-shadow: 0 14px 34px -28px rgba(18,48,122,.55);
    }}
    .flow-legend::after {{
        content: "";
        position: absolute;
        width: 180px;
        height: 180px;
        right: -105px;
        top: -120px;
        border-radius: 50%;
        border: 1px solid rgba(47,102,224,.12);
        pointer-events: none;
    }}
    .flow-legend-head {{
        position: relative;
        z-index: 1;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        margin-bottom: 14px;
    }}
    .flow-title-group {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
    .flow-title-icon {{
        width: 34px;
        height: 34px;
        display: grid;
        place-items: center;
        flex: 0 0 34px;
        color: {R_AZUL};
        background: #edf3ff;
        border-radius: 11px;
        font-size: 17px;
        font-weight: 800;
    }}
    .flow-title {{
        color: {R_AZUL};
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 1.35px;
        text-transform: uppercase;
    }}
    .flow-subtitle {{ color: {R_TENUE}; font-size: 11px; margin-top: 2px; }}
    .flow-formula {{
        max-width: 560px;
        padding: 8px 12px;
        color: {R_TENUE};
        background: #f6f8fc;
        border: 1px solid #e4e9f3;
        border-radius: 999px;
        font-size: 11px;
        line-height: 1.35;
        text-align: right;
    }}
    .flow-formula b {{ color: {R_AZUL_OSC}; }}
    .flow-scale {{ display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; }}
    .flow-level {{
        position: relative;
        min-width: 0;
        min-height: 112px;
        padding: 14px 15px 13px;
        background: linear-gradient(145deg,#ffffff 0%,var(--flow-soft) 100%);
        border: 1px solid color-mix(in srgb,var(--flow-color) 28%,#ffffff);
        border-top: 4px solid var(--flow-color);
        border-radius: 16px;
        box-shadow: 0 12px 24px -24px var(--flow-color);
        transition: transform .16s ease, box-shadow .16s ease;
    }}
    .flow-level:hover {{ transform: translateY(-2px); box-shadow: 0 16px 28px -22px var(--flow-color); }}
    .flow-level-head {{ display: flex; align-items: center; gap: 8px; }}
    .flow-dot {{
        width: 10px;
        height: 10px;
        flex: 0 0 10px;
        border-radius: 50%;
        background: var(--flow-color);
        box-shadow: 0 0 0 4px var(--flow-soft);
    }}
    .flow-level-name {{ color: {UTB_WHITE}; font-size: 14px; font-weight: 800; }}
    .flow-range {{ color: {R_AZUL_OSC}; font-size: 20px; font-weight: 800; letter-spacing: -.3px; margin-top: 13px; }}
    .flow-note {{ color: {R_TENUE}; font-size: 11px; line-height: 1.35; margin-top: 3px; }}
    @media (max-width: 980px) {{
        .flow-legend-head {{ align-items: flex-start; flex-direction: column; }}
        .flow-formula {{ max-width: none; text-align: left; border-radius: 12px; }}
        .flow-scale {{ grid-template-columns: repeat(2,minmax(0,1fr)); }}
    }}
    @media (max-width: 560px) {{
        .flow-legend {{ padding: 14px; border-radius: 18px; }}
        .flow-scale {{ grid-template-columns: 1fr; }}
    }}

    /* ── Barra lateral (degradado azul del R) ── */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #1f48b8 0%, #2a5bd0 60%, #3b73e6 100%) !important;
        border-right: 0;
    }}
    [data-testid="stSidebar"] > div {{ background: transparent !important; }}
    [data-testid="stSidebarHeader"] {{
        min-height: 44px !important;
        height: 44px !important;
        padding: 4px 10px 0 !important;
    }}
    [data-testid="stSidebarUserContent"] {{ padding-top: 0 !important; }}
    .utb-sidebar-logo {{
        text-align: center;
        padding: 8px 16px 18px;
        border-bottom: 1px solid rgba(255,255,255,0.15);
        margin-bottom: 20px;
    }}
    [data-testid="stSidebar"] * {{ color: #dbe7ff !important; }}
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {{ color: #ffffff !important; }}
    [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.2) !important; }}
    [data-testid="stSidebar"] [data-testid="stExpander"] {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 10px;
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] details,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {{
        background: transparent !important;
        border: 0 !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div {{
        background: rgba(255,255,255,0.12) !important;
        border: 1px solid rgba(255,255,255,0.28) !important;
        border-radius: 10px !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] svg {{ fill: #ffffff !important; }}
    /* Los botones tipo pildora mantienen contraste sobre la barra lateral */
    [data-testid="stSidebar"] .stButton button,
    [data-testid="stSidebar"] .stButton button * {{ color: #ffffff !important; }}

    /* ── Pestañas (.nav-tabs-custom del R) ── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 6px;
        background: #ffffff;
        border: 0;
        border-radius: 999px;
        padding: 6px;
        box-shadow: {R_SOMBRA};
        overflow-x: auto;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent;
        border-radius: 999px;
        padding: 10px 20px;
        color: {R_TENUE};
        font-weight: 600;
        font-size: 14px;
    }}
    .stTabs [data-baseweb="tab"] p {{ color: inherit; font-weight: 600; }}
    /* La regla de color de arriba anula el hover de Streamlit: se repone */
    .stTabs [data-baseweb="tab"] {{ transition: background .2s ease, color .2s ease; }}
    .stTabs [aria-selected="false"]:hover {{
        background: rgba(31,72,184,0.08);
        color: {R_AZUL};
    }}
    .stTabs [aria-selected="true"] {{
        background: {R_AZUL} !important;
        color: #ffffff !important;
        box-shadow: none;
    }}
    .stTabs [aria-selected="true"]:hover {{ background: {R_AZUL_OSC} !important; }}
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{
        display: none;
    }}

    /* ── Botones (.btn-success del R) ── */
    .stButton button, .stDownloadButton button {{
        background: #111113;
        color: #ffffff;
        border: 1px solid #111113;
        border-radius: 999px;
        font-weight: 600;
        padding: 8px 20px;
        transition: all 0.2s;
    }}
    .stButton button p, .stDownloadButton button p {{ color: inherit; font-weight: 600; }}
    .stButton button:hover, .stDownloadButton button:hover {{
        background: {R_AZUL};
        border-color: {R_AZUL};
        color: #ffffff;
        transform: translateY(-1px);
    }}

    /* ── Titulos de seccion (.sec-head del R): tinta, mayusculas, filete menta ── */
    hr {{ border-color: {R_LINEA} !important; }}
    h2 {{ color: #111113; font-weight: 700; letter-spacing: -.02em; margin-top: 0; }}
    h3 {{
        color: #111113 !important;
        font-size: 20px !important;
        font-weight: 700 !important;
        text-transform: none;
        letter-spacing: -.02em;
        border-left: 0;
        padding: 0 !important;
        margin: 16px 0 14px !important;
    }}
    .badge-ok {{
        background: rgba(16,185,129,0.12); color: {TEXTO_FLUIDO};
        padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
    }}
    .badge-error {{
        background: rgba(239,68,68,0.12); color: {TEXTO_CONGESTIONADO};
        padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
    }}
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    /* La barra superior de Streamlit mide 60 px (min-height fijo) y va encima
       del contenido: transparente y sin capturar clics, salvo sus botones.
       No se le quita el alto porque ahi vive el boton que reabre la barra
       lateral: con height 0 ese boton quedaba en 0x0 y no se podia volver
       a abrir. Antes se tragaba los clics de esa franja al hacer scroll. */
    [data-testid="stHeader"] {{ background: transparent !important; }}
    /* !important: Streamlit le pone pointer-events:auto a la barra de
       herramientas, que ocupa todo el ancho */
    [data-testid="stHeader"], [data-testid="stHeader"] * {{ pointer-events: none !important; }}
    [data-testid="stHeader"] button, [data-testid="stHeader"] a {{ pointer-events: auto !important; }}
    /* De la barra de herramientas solo se ocultan Deploy y el menu: ahi
       mismo vive el boton que reabre la barra lateral, y al ocultar toda la
       barra (stToolbar) no habia forma de volver a abrirla sin recargar. */
    [data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stDecoration"],
    [data-testid="stSidebarNav"] {{ display: none !important; }}
    h2, h3 {{ scroll-margin-top: 1rem; }}
    [data-testid="stExpandSidebarButton"] {{
        background: {R_MENTA} !important;
        border-radius: 50%;
        box-shadow: 0 4px 12px rgba(45,212,191,0.4);
    }}
    [data-testid="stExpandSidebarButton"] svg {{
        color: {R_AZUL_OSC} !important;
        fill: {R_AZUL_OSC} !important;
    }}
    [data-testid="stSidebarCollapseButton"] button {{ color: #ffffff !important; }}

    /* ── Footer editorial inspirado en la composicion de Innvita ── */
    /* Azul de la pagina (misma familia que la barra lateral y el encabezado),
       un poco mas oscuro a la derecha para que el texto pequeno se lea. */
    [data-testid="stLayoutWrapper"]:has(> .st-key-dashboard_footer) {{
        order: 2147483647;
    }}
    .dashboard-footer {{
        margin: 44px 0 4px;
        padding: 42px 44px 24px;
        border-radius: 40px;
        background: linear-gradient(120deg, #172f86 0%, #1f48b8 55%, #2a5bd0 100%);
        box-shadow: 0 10px 30px rgba(31,72,184,.25);
        color: #ffffff;
        overflow: hidden;
    }}
    .dashboard-footer * {{ font-family: 'Inter', system-ui, sans-serif !important; }}
    .footer-brand {{
        margin: 0 0 8px;
        color: #ffffff;
        font-size: 28px;
        line-height: 1.1;
        font-weight: 700;
        letter-spacing: -.04em;
    }}
    .footer-brand span {{ color: {R_MENTA_CLARA}; }}
    .footer-lead {{
        max-width: 650px;
        margin: 0 0 34px;
        color: #dbe7ff !important;
        font-size: 19px;
        line-height: 1.45;
        letter-spacing: -.01em;
    }}
    .footer-lead strong {{ color: #ffffff; font-weight: 700; }}
    .footer-grid {{
        display: grid;
        grid-template-columns: 1.1fr 1.25fr 1.1fr;
        gap: 34px;
        padding: 30px 0;
        border-top: 1px solid rgba(255,255,255,.18);
        border-bottom: 1px solid rgba(255,255,255,.18);
    }}
    .footer-kicker {{
        margin-bottom: 12px;
        color: #ffffff;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: .02em;
    }}
    .footer-copy {{
        margin: 0;
        color: #d6e2fb !important;
        font-size: 13px;
        line-height: 1.7;
    }}
    .footer-bottom {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        padding-top: 20px;
        color: #c9d8f7;
        font-size: 11px;
        letter-spacing: .02em;
    }}
    .footer-admin-link {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        flex-shrink: 0;
        min-height: 42px;
        padding: 9px 16px 9px 18px;
        border-radius: 999px;
        background: #ffffff;
        color: #111113 !important;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: .01em;
        text-decoration: none !important;
        transition: transform .2s ease, background .2s ease;
    }}
    .footer-admin-link:hover {{
        background: {R_MENTA_CLARA};
        color: #111113 !important;
        transform: translateY(-1px);
    }}
    .footer-admin-arrow {{
        display: grid;
        place-items: center;
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: {R_AZUL_OSC};
        color: #ffffff !important;
        font-size: 14px;
        line-height: 1;
    }}
    /* El mismo boton en la barra lateral ocupa todo el ancho */
    .sidebar-admin-link {{
        display: flex;
        justify-content: space-between;
        width: 100%;
        box-sizing: border-box;
    }}
    @media (max-width: 800px) {{
        .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
        .utb-header {{ border-radius: 28px; padding: 26px 24px; }}
        .utb-header-content {{ min-width: 0; width: 100%; }}
        .utb-brand {{ font-size: 36px !important; }}
        .utb-route {{ display: none; }}
        .utb-status {{ min-width: 0; text-align: left; }}
        .dashboard-footer {{ margin-left: -1rem; margin-right: -1rem; padding: 34px 24px 22px; border-radius: 32px 32px 0 0; }}
        .footer-grid {{ grid-template-columns: 1fr; gap: 24px; }}
        .footer-bottom {{ flex-direction: column; align-items: flex-start; }}
    }}
    @media (min-width: 801px) and (max-width: 1120px) {{
        .utb-route {{ display: none; }}
    }}
</style>
""", unsafe_allow_html=True)


# ============================================================
# UTILIDADES
# ============================================================
# tema_plotly del R: fondo transparente (la caja blanca la pone el CSS),
# tinta azul, rejilla celeste y etiqueta flotante azul oscuro
REJILLA = "#e3eaf7"
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


@st.dialog("Gráfica ampliada", width="large")
def grafica_ampliada(fig, clave: str):
    """Abre una copia grande de la grafica sin alterar sus filtros."""
    fig_grande = go.Figure(fig)
    fig_grande.update_layout(height=720)
    st.plotly_chart(
        fig_grande,
        theme=None,
        config=PLOTLY_CONFIG,
        key=f"{clave}_ampliada",
    )
    st.caption("Pulsa × o la tecla Esc para volver al tablero.")


@st.fragment
def mostrar_grafica(fig, clave: str) -> None:
    """Renderiza una grafica con un control de ampliacion siempre visible."""
    espacio, accion = st.columns([12, 1])
    with accion:
        ampliar = st.button(
            "⛶",
            key=f"expandir_grafica_{clave}",
            help="Abrir esta gráfica en una vista grande",
            width="content",
        )
    if ampliar:
        grafica_ampliada(fig, clave)
    st.plotly_chart(
        fig,
        theme=None,
        config=PLOTLY_CONFIG,
        key=f"grafica_{clave}",
    )


def plotly_base(fig, height: int = 340):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#1e3a6e",
        font_family="Inter, Segoe UI, Helvetica, Arial, sans-serif",
        height=height,
        margin=dict(l=28, r=36, t=42, b=50),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            bgcolor="rgba(0,0,0,0)", font=dict(color=R_TENUE),
        ),
        hoverlabel=dict(bgcolor=R_AZUL_OSC, font=dict(color="#ffffff", size=12)),
        xaxis=dict(
            gridcolor=REJILLA, zerolinecolor="#d3def2", linecolor="#c9d6ee",
            tickfont=dict(color=R_TENUE, size=11),
            title_font=dict(color=R_AZUL_OSC, size=12),
            automargin=True,
        ),
        yaxis=dict(
            gridcolor=REJILLA, zerolinecolor="#d3def2", linecolor="#c9d6ee",
            tickfont=dict(color=R_TENUE, size=11),
            title_font=dict(color=R_AZUL_OSC, size=12),
            automargin=True,
        ),
    )
    # Plotly escribe las fechas en ingles ("Oct 20", "Jul 2026") y Streamlit no
    # trae su traduccion: en los ejes de fechas se usan solo numeros
    if any(_x_es_fecha(traza) for traza in fig.data):
        fig.update_xaxes(tickformat="%d/%m/%Y", hoverformat="%d/%m/%Y %H:%M")
    return fig


def _x_es_fecha(traza) -> bool:
    x = getattr(traza, "x", None)
    if x is None or len(x) == 0:
        return False
    return (pd.api.types.is_datetime64_any_dtype(pd.Series(x))
            or isinstance(x[0], (datetime, pd.Timestamp)) or hasattr(x[0], "isoformat"))


# Las cargas que corren antes de las pestañas van sin show_spinner: el aviso
# "Running ..." ocupa un lugar en la página, desplaza las pestañas y
# Streamlit las vuelve a crear, devolviendo al usuario a la primera cada vez
# que vence un cache (cargar_logs vence cada minuto). El indicador de carga
# de la esquina superior sigue visible.
@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
def cargar_csv(path_str: str) -> pd.DataFrame:
    df = pd.read_csv(path_str)
    if "consultation_time" in df.columns:
        df["consultation_time"] = pd.to_datetime(df["consultation_time"])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def cargar_historico_local(fecha_ini=None, fecha_fin=None) -> pd.DataFrame:
    """Une los CSV locales del rango como ultimo respaldo de solo lectura."""
    partes = []
    for path in listar_archivos():
        # El nombre normalizado contiene YYYYmmdd_HHMMSS. Este descarte evita
        # abrir archivos fuera del rango; el filtro final usa el timestamp real.
        try:
            fecha_archivo = datetime.strptime(
                "_".join(path.stem.rsplit("_", 2)[-2:]), "%Y%m%d_%H%M%S"
            ).date()
        except ValueError:
            fecha_archivo = None
        if fecha_archivo is not None:
            if fecha_ini is not None and fecha_archivo < fecha_ini:
                continue
            if fecha_fin is not None and fecha_archivo > fecha_fin:
                continue
        try:
            partes.append(cargar_csv(str(path)))
        except (OSError, ValueError, pd.errors.ParserError) as e:
            print(f"  [Dashboard] CSV local inválido ({path.name}): {e}")

    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    if "consultation_time" not in df.columns:
        return pd.DataFrame()
    df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
    mascara = df["consultation_time"].notna()
    if fecha_ini is not None:
        mascara &= df["consultation_time"].dt.date >= fecha_ini
    if fecha_fin is not None:
        mascara &= df["consultation_time"].dt.date <= fecha_fin
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.loc[mascara].copy()


@st.cache_data(ttl=300, show_spinner=False)
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
    fuente = "Google Sheets"
    if df.empty or "consultation_time" not in df.columns:
        df = cargar_historico_local()
        fuente = "CSV local"
    if df.empty or "consultation_time" not in df.columns:
        return None, None, None
    fechas = df["consultation_time"].dropna()
    if fechas.empty:
        return None, None, None
    return fechas.dt.date.min(), fechas.dt.date.max(), fuente


def fechas_disponibles():
    """(primera, ultima) fecha con datos para el filtro de rango, o None."""
    fecha_min, fecha_max, _ = rango_fechas_historico()
    return (fecha_min, fecha_max) if fecha_min is not None else None


@st.cache_data(ttl=300)
def cargar_historico(fecha_ini, fecha_fin) -> tuple:
    """
    Datos del periodo [fecha_ini, fecha_fin] y la fuente usada.
    PostgreSQL consulta solo el rango pedido (rapido); Sheets descarga el
    historico completo y recorta (respaldo si la BD no esta disponible).
    Un periodo vacio en PostgreSQL es un resultado valido: no descarga Sheets.
    """
    if getattr(config, "FUENTE_DASHBOARD", "sheets") == "db":
        try:
            import db  # import diferido
            return db.leer_rango(fecha_ini, fecha_fin), "PostgreSQL"
        except Exception as e:
            print(f"  [Dashboard] PostgreSQL no disponible, usando Sheets: {e}")

    df = cargar_desde_sheets(n_dias=3650)
    fuente = "Google Sheets"
    if df.empty or "consultation_time" not in df.columns:
        df = cargar_historico_local(fecha_ini, fecha_fin)
        fuente = "CSV local"
    if df.empty or "consultation_time" not in df.columns:
        return pd.DataFrame(), None
    mask = (
        (df["consultation_time"].dt.date >= fecha_ini) &
        (df["consultation_time"].dt.date <= fecha_fin)
    )
    return df[mask].copy(), fuente


@st.cache_data(ttl=300, show_spinner=False)
def cargar_historico_nodo(id_nodo, fecha_ini, fecha_fin) -> tuple:
    """Carga solo un nodo para mantener ligera la vista de analisis.

    Con PostgreSQL, una consulta vacia es un resultado valido y no activa el
    respaldo. Sheets y los CSV locales solo se usan si la base no responde.
    """
    fuente_configurada = getattr(config, "FUENTE_DASHBOARD", "sheets")
    if fuente_configurada == "db":
        try:
            import db  # import diferido
            return db.leer_nodo_rango(id_nodo, fecha_ini, fecha_fin), "PostgreSQL"
        except Exception as e:
            print(f"  [Dashboard] PostgreSQL no disponible para el nodo, usando Sheets: {e}")
        try:
            df = google_upload.leer_sheet(n_dias=3650)
            fuente = "Google Sheets"
        except Exception:
            df = pd.DataFrame()
            fuente = None
    else:
        # Reutiliza la descarga con cache que ya resolvio el rango disponible.
        df = cargar_desde_sheets(n_dias=3650)
        fuente = "Google Sheets"
    if df.empty or "consultation_time" not in df.columns:
        df = cargar_historico_local(fecha_ini, fecha_fin)
        fuente = "CSV local"
    if df.empty or "consultation_time" not in df.columns:
        return pd.DataFrame(), fuente

    df = df.copy()
    df["consultation_time"] = pd.to_datetime(
        df["consultation_time"], errors="coerce"
    )
    mascara = df["consultation_time"].notna()
    mascara &= df["consultation_time"].dt.date >= fecha_ini
    mascara &= df["consultation_time"].dt.date <= fecha_fin
    if "id_nodo" in df.columns:
        mascara &= df["id_nodo"].astype(str) == str(id_nodo)
    return df.loc[mascara].copy(), fuente


def leyenda_ratio(modo: str = "ratio"):
    """
    Renderiza una leyenda de colores debajo de las graficas.
    modo='ratio'  → explica el velocity ratio (0-1)
    modo='velocidad' → explica velocidades en km/h
    modo='proceso'   → explica OK/Error en ejecuciones
    """
    if modo == "ratio":
        # Escala de fluidez: cuatro tramos de menor a mayor ratio, cada uno con
        # su nombre y su rango, y la explicacion del indice en una sola linea
        tramos = [
            (COLOR_CONGESTIONADO, "Congestionado", f"&lt; {UMBRAL_LENTO:.2f}", "Circulación muy reducida"),
            (COLOR_LENTO, "Lento", f"{UMBRAL_LENTO:.2f} – {UMBRAL_MODERADO:.2f}", "Velocidad por debajo de lo normal"),
            (COLOR_MODERADO, "Moderado", f"{UMBRAL_MODERADO:.2f} – {UMBRAL_FLUIDO:.2f}", "Tránsito estable con algunas demoras"),
            (COLOR_FLUIDO, "Fluido", f"&gt; {UMBRAL_FLUIDO:.2f}", "Circulación cercana al flujo libre"),
        ]
        segmentos = "".join(
            f'<div class="flow-level" style="--flow-color:{color};--flow-soft:{_rgba(color, 0.12)};">'
            f'<div class="flow-level-head"><span class="flow-dot"></span>'
            f'<span class="flow-level-name">{nombre}</span></div>'
            f'<div class="flow-range">{rango}</div>'
            f'<div class="flow-note">{descripcion}</div></div>'
            for color, nombre, rango, descripcion in tramos
        )
        st.markdown(f"""
        <div class="flow-legend">
            <div class="flow-legend-head">
                <div class="flow-title-group">
                    <span class="flow-title-icon">↗</span>
                    <div><div class="flow-title">Índice de fluidez</div>
                    <div class="flow-subtitle">Escala para interpretar el estado de la vía</div></div>
                </div>
                <div class="flow-formula"><b>Cómo se calcula:</b> velocidad de circulación ÷ velocidad libre<br>
                    <span>1.0 = circulación libre · 0 = vehículo detenido</span></div>
            </div>
            <div class="flow-scale">{segmentos}</div>
        </div>
        """, unsafe_allow_html=True)

    elif modo == "velocidad":
        st.markdown(f"""
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;
                    background:{SUPERFICIE_SUAVE};border-radius:8px;
                    padding:10px 16px;margin-top:4px;border:1px solid {UTB_BORDER};">
            <span style="color:{UTB_GRAY};font-size:11px;font-weight:700;
                         letter-spacing:1px;text-transform:uppercase;">Interpretación:</span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:{UTB_WHITE};">
                <span style="width:12px;height:3px;background:{SERIE_ACTUAL};display:inline-block;"></span>
                <b style="color:{SERIE_ACTUAL};">Velocidad de circulación</b>&nbsp;— km/h medidos en tiempo real con tráfico
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:{UTB_WHITE};">
                <span style="width:12px;height:3px;background:{SERIE_LIBRE};
                             display:inline-block;border-top:2px dashed {SERIE_LIBRE};"></span>
                <b style="color:{UTB_GRAY};">Velocidad libre</b>&nbsp;— km/h que tendría la vía sin tráfico
            </span>
            <span style="color:{UTB_GRAY};font-size:11px;margin-left:auto;">
                La brecha entre ambas líneas representa el tiempo perdido por congestión
            </span>
        </div>
        """, unsafe_allow_html=True)

    elif modo == "proceso":
        st.markdown(f"""
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;
                    background:{SUPERFICIE_SUAVE};border-radius:8px;
                    padding:10px 16px;margin-top:4px;border:1px solid {UTB_BORDER};">
            <span style="color:{UTB_GRAY};font-size:11px;font-weight:700;
                         letter-spacing:1px;text-transform:uppercase;">Interpretación:</span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:{UTB_WHITE};">
                <span style="width:12px;height:12px;border-radius:3px;
                             background:{COLOR_FLUIDO};display:inline-block;"></span>
                <b style="color:{TEXTO_FLUIDO};">Consultas correctas</b>&nbsp;— nodos respondidos correctamente por TomTom
            </span>
            <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:{UTB_WHITE};">
                <span style="width:12px;height:12px;border-radius:3px;
                             background:{COLOR_CONGESTIONADO};display:inline-block;"></span>
                <b style="color:{TEXTO_CONGESTIONADO};">Errores</b>&nbsp;— nodos con fallo (red, cuota, API)
            </span>
            <span style="color:{UTB_GRAY};font-size:11px;margin-left:auto;">
                Cada barra = una ejecución del cron · 113 nodos por ejecución
            </span>
        </div>
        """, unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def cargar_catalogo() -> pd.DataFrame:
    """
    Datos fijos de cada nodo (nodos.xlsx) para el mapa y su ventana emergente.
    El barrio y el punto de referencia salen del catalogo y no de las
    mediciones: el ETL no guarda la columna 'Barrio/Lugar' del Excel.
    """
    try:
        import descargar_trafico  # import diferido: solo se usa cargar_nodos
        nodos = descargar_trafico.cargar_nodos(config.NODOS_PATH)
    except Exception as e:
        print(f"  [Dashboard] No se pudo leer el catalogo de nodos: {e}")
        return pd.DataFrame()
    return pd.DataFrame({
        "id_nodo": nodos["id_nodo"].astype(str),
        "nombre_nodo": nodos["nombre_nodo"],
        "lat": nodos["lat"],
        "lon": nodos["lon"],
        # 'Barrio/Lugar' queda como 'barriolugar' al normalizar las columnas
        "barrio": nodos.get("barriolugar", nodos["barrios_que_colinda"]),
        "punto_referencia": nodos.get("punto_referencia"),
    })


@st.cache_data(ttl=3600)
def cargar_red() -> dict:
    """
    Conexiones de la red de nodos: data/red_nodos.json (capturar_red.py) o,
    si falta, la hoja REDES en linea recta.
    """
    path = BASE_DIR / "data" / "red_nodos.json"
    pares = []
    if not path.exists():
        try:
            import descargar_trafico  # import diferido
            pares = descargar_trafico.leer_conexiones(config.NODOS_PATH)
        except Exception as e:
            print(f"  [Dashboard] No se pudo leer la hoja REDES: {e}")
    return red_nodos.cargar_red(path, cargar_catalogo(), pares)


@st.cache_data(ttl=3600)
def cargar_corredores() -> tuple:
    """
    Corredores de la hoja CORREDORES de nodos.xlsx, que llena el equipo:
    ({corredor: [id_nodo, ...]} en el orden de la hoja, [id_nodo sin catalogo]).
    """
    catalogo = cargar_catalogo()
    if catalogo.empty:
        return {}, []
    try:
        import descargar_trafico  # import diferido
        return descargar_trafico.leer_corredores(config.NODOS_PATH, catalogo["id_nodo"])
    except Exception as e:
        print(f"  [Dashboard] No se pudo leer la hoja CORREDORES: {e}")
        return {}, []


def leyenda_corredores(corredores: list) -> None:
    """Nombre y color de cada corredor dibujado, debajo del mapa de la red."""
    items = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:8px;'>"
        f"<span style='width:22px;height:6px;border-radius:3px;background:{c['color']};"
        f"flex:none;'></span>{html.escape(c['nombre'])}</span>"
        for c in corredores
    )
    st.markdown(
        f"<div style='margin:10px 0 4px;padding:12px 16px;background:#ffffff;"
        f"border:1px solid {R_LINEA};border-radius:16px;box-shadow:{R_SOMBRA};'>"
        f"<div style='color:{R_AZUL_OSC};font-size:11px;font-weight:700;"
        f"letter-spacing:.7px;text-transform:uppercase;margin-bottom:8px;'>Corredores</div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));"
        f"gap:6px 18px;color:{UTB_WHITE};font-size:13px;'>{items}</div></div>",
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=300)
def promedios_mapa(fecha_ini, fecha_fin, desde, hasta, mes, dia_semana,
                   laborables, fin_semana, quincena, ids) -> tuple:
    """
    Promedio por nodo con los filtros del mapa, y la fuente usada.
    PostgreSQL agrega en la consulta (113 filas); Sheets descarga el
    historico completo y agrega en pandas (respaldo si la BD no responde).
    """
    consulta = dict(fecha_ini=fecha_ini, fecha_fin=fecha_fin, desde=desde,
                    hasta=hasta, mes=mes, dia_semana=dia_semana,
                    laborables=laborables, fin_semana=fin_semana,
                    quincena=quincena, ids=ids)
    if getattr(config, "FUENTE_DASHBOARD", "sheets") == "db":
        try:
            import db  # import diferido
            return db.promedios_por_nodo(**consulta), "PostgreSQL"
        except Exception as e:
            print(f"  [Dashboard] PostgreSQL no disponible, usando Sheets: {e}")

    df = cargar_desde_sheets(n_dias=3650)
    return mapa_nodos.promedios_por_nodo_df(df, **consulta), "Google Sheets"


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


def render_analisis_nodo():
    """Cuatro vistas coordinadas del comportamiento de un unico nodo."""
    st.markdown("### Análisis por nodo")

    with st.spinner("Consultando datos disponibles..."):
        min_fecha, max_fecha, _ = rango_fechas_historico()
    catalogo = cargar_catalogo()
    if min_fecha is None or catalogo.empty:
        st.warning("No hay datos históricos o no se pudo leer el catálogo de nodos.")
        return

    catalogo = catalogo.drop_duplicates("id_nodo").copy()
    catalogo["id_nodo"] = catalogo["id_nodo"].astype(str)
    nombres = dict(zip(catalogo["id_nodo"], catalogo["nombre_nodo"]))
    ids_nodos = list(nombres)
    prefijo = "analisis_nodo"
    fecha_fin_default = max(min_fecha, mapa_nodos.hoy_cartagena())
    fecha_max_selector = max(max_fecha, fecha_fin_default)
    iniciales = {
        f"{prefijo}_id": ids_nodos[0],
        f"{prefijo}_fecha_ini": min_fecha,
        f"{prefijo}_fecha_fin": fecha_fin_default,
        f"{prefijo}_tipo_dia": analisis_nodo.TIPOS_DIA[0],
    }
    for clave, valor in iniciales.items():
        st.session_state.setdefault(clave, valor)

    def _restablecer():
        for clave, valor in iniciales.items():
            st.session_state[clave] = valor

    col_filtros, col_graficos = st.columns([1, 3])
    with col_filtros, mapa_nodos.tarjeta_filtros(
        prefijo, "Filtros del análisis por nodo"
    ):
        id_nodo = st.selectbox(
            "Punto de monitoreo:",
            ids_nodos,
            key=f"{prefijo}_id",
            format_func=lambda valor: nombres.get(valor, valor),
        )
        st.markdown(
            '<div class="grupo-filtro-label">Seleccionar rango de fechas</div>',
            unsafe_allow_html=True,
        )
        fecha_ini = st.date_input(
            "Desde:",
            key=f"{prefijo}_fecha_ini",
            min_value=min_fecha,
            max_value=fecha_max_selector,
            format="DD/MM/YYYY",
        )
        fecha_fin = st.date_input(
            "Hasta:",
            key=f"{prefijo}_fecha_fin",
            min_value=min_fecha,
            max_value=fecha_max_selector,
            format="DD/MM/YYYY",
        )
        if fecha_fin < fecha_ini:
            st.error("La fecha final debe ser igual o posterior a la fecha inicial.")
        tipo_dia = st.selectbox(
            "Tipo de día:",
            analisis_nodo.TIPOS_DIA,
            key=f"{prefijo}_tipo_dia",
        )
        st.button(
            "↺ Restablecer filtros",
            on_click=_restablecer,
            width="stretch",
            key=f"{prefijo}_restablecer",
        )

    if fecha_fin < fecha_ini:
        # Un rango invertido no tiene datos: no se consulta la base ni Sheets
        with col_graficos:
            st.info("Ajusta el rango de fechas para ver el análisis del nodo.")
        return

    with st.spinner("Calculando análisis del nodo..."):
        df_nodo, _ = cargar_historico_nodo(id_nodo, fecha_ini, fecha_fin)
        ejecuciones = analisis_nodo.preparar_mediciones(
            df_nodo,
            id_nodo,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            tipo_dia=tipo_dia,
        )

    with col_graficos:
        nombre_nodo = html.escape(str(nombres.get(id_nodo, id_nodo)))
        st.markdown(
            f"<div style='margin:0 0 14px 2px;'>"
            f"<div style='color:{UTB_WHITE};font-size:20px;font-weight:800;'>{nombre_nodo}</div>"
            f"<div style='color:{UTB_GRAY};font-size:12px;'>Nodo {html.escape(str(id_nodo))} · "
            f"{fecha_ini.strftime('%d/%m/%Y')}–{fecha_fin.strftime('%d/%m/%Y')}</div></div>",
            unsafe_allow_html=True,
        )
        if ejecuciones.empty:
            st.info("No hay mediciones válidas para este nodo con los filtros seleccionados.")
            return

        ratio_promedio = ejecuciones["velocidad_ratio"].mean()
        velocidad_promedio = ejecuciones["currentSpeed"].mean()
        flujo_libre_promedio = ejecuciones["freeFlowSpeed"].mean()
        estado = clasificar_ratio(ratio_promedio)[1]
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Índice de fluidez", f"{ratio_promedio:.3f}", estado)
        with m2:
            st.metric("Velocidad de circulación", f"{velocidad_promedio:.1f} km/h")
        m3, m4 = st.columns(2)
        with m3:
            st.metric("Velocidad de flujo libre", f"{flujo_libre_promedio:.1f} km/h")
        with m4:
            st.metric("Ejecuciones válidas", f"{len(ejecuciones):,}")

        diaria = analisis_nodo.serie_diaria(ejecuciones)
        hora = analisis_nodo.resumen_por_hora(ejecuciones)
        # Solo horas con corridas y en orden de dia operativo (04:00 ... 00:00):
        # el eje no muestra la franja vacia de 01 a 03
        horas = pd.DataFrame({"hora": horario.HORAS}).merge(hora, on="hora", how="left")
        horas["etiqueta"] = horas["hora"].map(lambda h: f"{h:02d}:00")
        distribucion = analisis_nodo.distribucion_congestion(
            ejecuciones,
            UMBRAL_FLUIDO,
            UMBRAL_MODERADO,
            UMBRAL_LENTO,
        )
        # Una marca cada 4 horas (04, 08 ... 20, 00) cabe incluso cuando los
        # graficos quedan en dos columnas estrechas; los datos conservan todas
        # las horas con corridas.
        ticks_hora = [f"{h:02d}:00" for h in horario.HORAS if horario.orden_hora(h) % 240 == 0]
        eje_horas = dict(
            type="category", categoryorder="array", categoryarray=list(horas["etiqueta"]),
            tickmode="array", tickvals=ticks_hora, ticktext=ticks_hora,
        )

        fila_1a, fila_1b = st.columns(2, gap="medium")
        with fila_1a, st.container(border=True):
            st.markdown(
                f"<div style='border-top:4px solid {SERIE_ACTUAL};padding-top:9px;'>"
                f"<b style='color:{R_AZUL_OSC};'>Serie temporal</b><br>"
                f"<span style='color:{UTB_GRAY};font-size:12px;'>Índice de fluidez por fecha</span></div>",
                unsafe_allow_html=True,
            )
            fig_serie = go.Figure(go.Scatter(
                x=diaria["fecha"],
                y=diaria["ratio_promedio"],
                mode="lines+markers",
                name="Índice promedio",
                line=dict(color=SERIE_ACTUAL, width=2.5),
                marker=dict(size=5, color=R_MENTA_OSC),
                customdata=diaria[["ratio_mediana", "ejecuciones"]].to_numpy(),
                connectgaps=False,
                hovertemplate=(
                    "Fecha: %{x|%d/%m/%Y}<br>Índice promedio: %{y:.3f}"
                    "<br>Mediana: %{customdata[0]:.3f}"
                    "<br>Ejecuciones: %{customdata[1]:.0f}<extra></extra>"
                ),
            ))
            fig_serie.update_layout(
                xaxis_title="Meses",
                yaxis_title="Índice de fluidez",
                showlegend=False,
            )
            fig_serie.update_yaxes(
                range=[0, max(1.05, float(diaria["ratio_promedio"].max()) * 1.08)]
            )
            fig_serie = plotly_base(fig_serie, height=330)
            mostrar_grafica(fig_serie, "nodo_serie")
            st.caption("Cada punto es el promedio de las ejecuciones válidas de un día.")

        with fila_1b, st.container(border=True):
            st.markdown(
                f"<div style='border-top:4px solid {R_MENTA_OSC};padding-top:9px;'>"
                f"<b style='color:{R_AZUL_OSC};'>Patrón horario</b><br>"
                f"<span style='color:{UTB_GRAY};font-size:12px;'>Índice de fluidez por hora</span></div>",
                unsafe_allow_html=True,
            )
            fig_patron = go.Figure(go.Scatter(
                x=horas["etiqueta"],
                y=horas["ratio_promedio"],
                mode="lines+markers",
                name="Índice promedio",
                line=dict(color=R_MENTA_OSC, width=3),
                marker=dict(size=7, color=SERIE_ACTUAL),
                customdata=horas[["ratio_mediana", "ejecuciones"]].fillna(0).to_numpy(),
                connectgaps=False,
                hovertemplate=(
                    "Hora: %{x}<br>Índice promedio: %{y:.3f}"
                    "<br>Mediana: %{customdata[0]:.3f}"
                    "<br>Ejecuciones: %{customdata[1]:.0f}<extra></extra>"
                ),
            ))
            fig_patron.update_layout(
                xaxis_title="Hora del día",
                yaxis_title="Índice de fluidez",
                showlegend=False,
            )
            fig_patron.update_xaxes(**eje_horas)
            fig_patron.update_yaxes(
                range=[0, max(1.05, float(hora["ratio_promedio"].max()) * 1.08)]
            )
            fig_patron = plotly_base(fig_patron, height=330)
            mostrar_grafica(fig_patron, "nodo_patron")
            st.caption("Las horas sin mediciones quedan vacías: no se interpolan ni se estiman.")

        fila_2a, fila_2b = st.columns(2, gap="medium")
        with fila_2a, st.container(border=True):
            st.markdown(
                f"<div style='border-top:4px solid {COLOR_MODERADO};padding-top:9px;'>"
                f"<b style='color:{R_AZUL_OSC};'>Velocidad de circulación frente a flujo libre por hora</b><br>"
                f"<span style='color:{UTB_GRAY};font-size:12px;'>km/h por hora</span></div>",
                unsafe_allow_html=True,
            )
            fig_velocidad = go.Figure()
            fig_velocidad.add_trace(go.Scatter(
                x=horas["etiqueta"],
                y=horas["flujo_libre_promedio"],
                mode="lines+markers",
                name="Flujo libre",
                line=dict(color=SERIE_LIBRE, width=2, dash="dash"),
                marker=dict(size=5),
                connectgaps=False,
                hovertemplate="Hora: %{x}<br>Flujo libre: %{y:.1f} km/h<extra></extra>",
            ))
            fig_velocidad.add_trace(go.Scatter(
                x=horas["etiqueta"],
                y=horas["velocidad_promedio"],
                mode="lines+markers",
                name="Velocidad de circulación",
                line=dict(color=SERIE_ACTUAL, width=3),
                marker=dict(size=6, color=COLOR_MODERADO),
                connectgaps=False,
                hovertemplate="Hora: %{x}<br>Velocidad de circulación: %{y:.1f} km/h<extra></extra>",
            ))
            fig_velocidad.update_layout(
                xaxis_title="Hora del día",
                yaxis_title="Velocidad (km/h)",
                legend=dict(orientation="h", y=1.12),
            )
            fig_velocidad.update_xaxes(**eje_horas)
            fig_velocidad = plotly_base(fig_velocidad, height=330)
            mostrar_grafica(fig_velocidad, "nodo_velocidad")
            st.caption("Ambas líneas usan las mismas ejecuciones; los huecos indican falta de datos.")

        with fila_2b, st.container(border=True):
            st.markdown(
                f"<div style='border-top:4px solid {COLOR_CONGESTIONADO};padding-top:9px;'>"
                f"<b style='color:{R_AZUL_OSC};'>Distribución de congestión</b><br>"
                f"<span style='color:{UTB_GRAY};font-size:12px;'>Porcentaje de ejecuciones por estado</span></div>",
                unsafe_allow_html=True,
            )
            colores = [COLOR_FLUIDO, COLOR_MODERADO, COLOR_LENTO, COLOR_CONGESTIONADO]
            fig_distribucion = go.Figure(go.Pie(
                labels=distribucion["categoria"],
                values=distribucion["mediciones"],
                hole=0.62,
                sort=False,
                direction="clockwise",
                marker=dict(colors=colores, line=dict(color="#ffffff", width=2)),
                textinfo="percent",
                textfont=dict(size=12, color="#ffffff"),
                customdata=distribucion[["porcentaje"]].to_numpy(),
                hovertemplate=(
                    "%{label}<br>Ejecuciones: %{value:,}"
                    "<br>Porcentaje: %{customdata[0]:.1f}%<extra></extra>"
                ),
            ))
            fig_distribucion.update_layout(
                legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"),
                annotations=[dict(
                    text=f"<b>{len(ejecuciones):,}</b><br><span style='font-size:11px'>ejecuciones</span>",
                    x=0.5, y=0.5, showarrow=False, font=dict(color=R_AZUL_OSC, size=16),
                )],
            )
            fig_distribucion = plotly_base(fig_distribucion, height=330)
            mostrar_grafica(fig_distribucion, "nodo_distribucion")
            st.caption("Cada ejecución válida pesa una vez en la clasificación del nodo.")


def render_analisis_temporal():
    """Vista temporal con una sola muestra estadistica para los cuatro graficos."""
    st.markdown("### Análisis temporal")

    with st.spinner("Consultando datos disponibles..."):
        min_fecha, max_fecha, fuente_rango = rango_fechas_historico()
    if min_fecha is None:
        st.warning("No hay datos históricos o no hay conexión con la fuente.")
        return

    catalogo = cargar_catalogo()
    nombres = (
        dict(zip(catalogo["id_nodo"].astype(str), catalogo["nombre_nodo"]))
        if not catalogo.empty else {}
    )
    prefijo = "temporal"
    fecha_fin_default = max(min_fecha, mapa_nodos.hoy_cartagena())
    fecha_max_selector = max(max_fecha, fecha_fin_default)
    iniciales = {
        f"{prefijo}_metrica": next(iter(analisis_temporal.METRICAS)),
        f"{prefijo}_fecha_ini": min_fecha,
        f"{prefijo}_fecha_fin": fecha_fin_default,
        f"{prefijo}_franja": mapa_nodos.TODO_EL_DIA,
        f"{prefijo}_horas": horario.DIA_COMPLETO,
        f"{prefijo}_nodos": [],
        f"{prefijo}_tipo_dia": analisis_temporal.TIPOS_DIA[0],
    }
    for clave, valor in iniciales.items():
        st.session_state.setdefault(clave, valor)

    def _al_cambiar_franja():
        horas = mapa_nodos.FRANJAS[st.session_state[f"{prefijo}_franja"]]
        if horas is not None:
            st.session_state[f"{prefijo}_horas"] = horas

    def _al_mover_horas():
        horas = tuple(st.session_state[f"{prefijo}_horas"])
        st.session_state[f"{prefijo}_franja"] = next(
            (nombre for nombre, rango in mapa_nodos.FRANJAS.items() if rango == horas),
            mapa_nodos.PERSONALIZADO,
        )

    def _restablecer():
        for clave, valor in iniciales.items():
            st.session_state[clave] = valor

    col_filtros, col_graficos = st.columns([1, 3])
    with col_filtros, mapa_nodos.tarjeta_filtros(
        prefijo, "Filtros del análisis temporal"
    ):
        metrica_label = st.selectbox(
            "Métrica a mostrar:",
            list(analisis_temporal.METRICAS),
            key=f"{prefijo}_metrica",
        )
        st.markdown(
            '<div class="grupo-filtro-label">Seleccionar rango de fechas</div>',
            unsafe_allow_html=True,
        )
        fecha_ini = st.date_input(
            "Desde:",
            key=f"{prefijo}_fecha_ini",
            min_value=min_fecha,
            max_value=fecha_max_selector,
            format="DD/MM/YYYY",
        )
        fecha_fin = st.date_input(
            "Hasta:",
            key=f"{prefijo}_fecha_fin",
            min_value=min_fecha,
            max_value=fecha_max_selector,
            format="DD/MM/YYYY",
        )
        if fecha_fin < fecha_ini:
            st.error("La fecha final debe ser igual o posterior a la fecha inicial.")
        st.selectbox(
            "Franja horaria:",
            list(mapa_nodos.FRANJAS),
            key=f"{prefijo}_franja",
            on_change=_al_cambiar_franja,
        )
        desde, hasta = mapa_nodos.barra_horas(f"{prefijo}_horas", _al_mover_horas)
        ids = st.multiselect(
            "Punto de monitoreo:",
            list(nombres),
            key=f"{prefijo}_nodos",
            format_func=lambda i: nombres.get(i, i),
            placeholder="Todos los puntos",
        )
        tipo_dia = st.selectbox(
            "Tipo de día:",
            analisis_temporal.TIPOS_DIA,
            key=f"{prefijo}_tipo_dia",
        )
        st.button(
            "↺ Restablecer filtros",
            on_click=_restablecer,
            width="stretch",
            key=f"{prefijo}_restablecer",
        )

    if fecha_fin < fecha_ini:
        # Un rango invertido no tiene datos: no se consulta la base ni Sheets
        with col_graficos:
            st.info("Ajusta el rango de fechas para ver el análisis temporal.")
        return

    meta = analisis_temporal.METRICAS[metrica_label]
    columna = meta["columna"]
    unidad = meta["unidad"]
    decimales = meta["decimales"]

    # Filtro de mes desactivado: el rango de fechas ya acota el periodo
    filtros = dict(
        fecha_ini=fecha_ini, fecha_fin=fecha_fin, desde=desde, hasta=hasta,
        tipo_dia=tipo_dia, ids=tuple(ids),
    )
    with st.spinner("Calculando análisis temporal..."):
        df_base, fuente = cargar_historico(fecha_ini, fecha_fin)
        filtrado = analisis_temporal.filtrar_mediciones(df_base, columna, **filtros)
        serie = analisis_temporal.serie_por_ejecucion(filtrado, columna)

    with col_graficos:
        if serie.empty:
            st.info("No hay mediciones válidas con la combinación de filtros seleccionada.")
            return

        promedio = serie["valor"].mean()
        mediana = serie["valor"].median()
        nodos_promedio = serie["n_nodos"].mean()
        valor_fmt = f"{{:.{decimales}f}}"
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("Promedio", f"{valor_fmt.format(promedio)} {unidad}")
        with s2:
            st.metric("Mediana", f"{valor_fmt.format(mediana)} {unidad}")
        with s3:
            st.metric("Ejecuciones", f"{len(serie):,}")
        with s4:
            st.metric("Nodos por ejecución", f"{nodos_promedio:.1f}")

        vista_tendencia, vista_box, vista_calor, vista_hora = st.tabs(
            [
                "↗ Evolución mensual",
                "▭ Distribución horaria",
                "▦ Mapa de calor",
                "▥ Comportamiento horario",
            ]
        )

        with vista_hora:
            # Una barra por corrida del cron (04:00 ... 00:00), con 05:30, 06:30... aparte
            hora = analisis_temporal.resumen_por_corrida(serie)
            etiquetas_hora = hora["corrida"]
            custom = hora[["mediana", "p25", "p75", "ejecuciones", "nodos_promedio"]].to_numpy()
            fig_hora = go.Figure()
            fig_hora.add_trace(go.Bar(
                x=etiquetas_hora,
                y=hora["promedio"],
                name="Promedio",
                marker_color=SERIE_ACTUAL,
                opacity=0.70,
                customdata=custom,
                hovertemplate=(
                    "Hora: %{x}<br>Promedio: %{y:." + str(decimales) + "f} " + unidad
                    + "<br>Mediana: %{customdata[0]:." + str(decimales) + "f} " + unidad
                    + "<br>Rango central (P25–P75): %{customdata[1]:." + str(decimales)
                    + "f}–%{customdata[2]:." + str(decimales) + "f} " + unidad
                    + "<br>Ejecuciones: %{customdata[3]:.0f}"
                    + "<br>Nodos prom.: %{customdata[4]:.1f}<extra></extra>"
                ),
            ))
            fig_hora.add_trace(go.Scatter(
                x=etiquetas_hora,
                y=hora["mediana"],
                name="Mediana",
                mode="lines+markers",
                line=dict(color=R_AZUL_OSC, width=3),
                marker=dict(size=7, color=R_MENTA_OSC),
                hovertemplate=(
                    "Hora: %{x}<br>Mediana: %{y:." + str(decimales) + "f} "
                    + unidad + "<extra></extra>"
                ),
            ))
            fig_hora.update_layout(
                xaxis_title="Hora del día",
                yaxis_title=f"{metrica_label}",
                legend=dict(orientation="h", y=1.12),
                bargap=0.22,
            )
            fig_hora.update_xaxes(type="category")
            if columna == "velocidad_ratio":
                fig_hora.update_yaxes(range=[0, max(1.05, float(hora["promedio"].max()) * 1.08)])
            fig_hora = plotly_base(fig_hora, height=430)
            mostrar_grafica(fig_hora, "temporal_hora")
            st.caption(
                "Las barras muestran el promedio entre ejecuciones; la línea muestra la "
                "mediana, menos sensible a valores extremos."
            )

        with vista_calor:
            calor, conteos = analisis_temporal.mapa_calor(serie)
            # Una columna por corrida del rango (04:00 ... 00:00): sin la franja
            # vacia de 01 a 03 y con las de 05:30, 06:30... aparte
            columnas_vista = [
                c for c in horario.CORRIDAS
                if horario.minuto_operativo(desde) <= horario.minuto_operativo(c)
                <= horario.minuto_operativo(hasta)
            ]
            calor = calor[columnas_vista]
            conteos = conteos[columnas_vista]
            filas_con_datos = calor.notna().any(axis=1)
            calor = calor.loc[filas_con_datos]
            conteos = conteos.loc[filas_con_datos]
            if calor.empty:
                st.info("No hay suficientes datos para construir el mapa de calor.")
            else:
                if columna == "velocidad_ratio":
                    escala = [
                        [0.0, COLOR_CONGESTIONADO],
                        [0.60, COLOR_LENTO],
                        [0.75, COLOR_MODERADO],
                        [0.90, COLOR_FLUIDO],
                        [1.0, "#047857"],
                    ]
                    zmin, zmax = 0, 1
                else:
                    # Velocidad de circulación y flujo libre con la misma escala: el minimo
                    # y el maximo de ambas con estos filtros. Con escalas propias,
                    # el flujo libre (casi constante) parecia variar tanto como el
                    # trafico real.
                    escala = "Blues"
                    otra = next(c for c in analisis_temporal.VELOCIDADES if c != columna)
                    calor_otra, _ = analisis_temporal.mapa_calor(
                        analisis_temporal.serie_por_ejecucion(
                            analisis_temporal.filtrar_mediciones(df_base, otra, **filtros), otra,
                        )
                    )
                    ambas = pd.concat([calor, calor_otra.reindex_like(calor)])
                    zmin = float(np.floor(np.nanmin(ambas.to_numpy(dtype=float))))
                    zmax = float(np.ceil(np.nanmax(ambas.to_numpy(dtype=float))))
                fig_calor = go.Figure(go.Heatmap(
                    z=calor.to_numpy(),
                    x=list(calor.columns),
                    y=[analisis_temporal.DIAS[i] for i in calor.index],
                    customdata=conteos.fillna(0).to_numpy(),
                    colorscale=escala,
                    zmin=zmin,
                    zmax=zmax,
                    # Escala arriba de la figura (yref container): se ve sin
                    # bajar y no choca con las horas inclinadas del eje x
                    colorbar=dict(
                        title=dict(text=unidad, side="right"),
                        orientation="h",
                        x=0.5, xanchor="center",
                        yref="container", y=1, yanchor="top", ypad=10,
                        len=0.60,
                        thickness=12,
                    ),
                    hoverongaps=False,
                    hovertemplate=(
                        "Día: %{y}<br>Hora: %{x}<br>Promedio: %{z:."
                        + str(decimales) + "f} " + unidad
                        + "<br>Ejecuciones: %{customdata:.0f}<extra></extra>"
                    ),
                ))
                fig_calor.update_layout(xaxis_title="Hora del día", yaxis_title="")
                fig_calor.update_xaxes(type="category")
                fig_calor = plotly_base(fig_calor, height=480)
                fig_calor.update_layout(margin=dict(t=80))
                mostrar_grafica(fig_calor, "temporal_calor")
                nota_escala = (
                    f" Velocidad de circulación y flujo libre usan la misma escala de color "
                    f"({zmin:.0f}–{zmax:.0f} km/h) para poder compararlas."
                    if columna in analisis_temporal.VELOCIDADES else ""
                )
                st.caption(
                    "Cada celda es el promedio de las ejecuciones observadas en esa "
                    "combinación de día de la semana y corrida del horario (incluidas "
                    "las de 5:30, 6:30...). Las celdas vacías no se estiman." + nota_escala
                )

        with vista_tendencia:
            tendencia = analisis_temporal.tendencia_mensual(serie)
            meses = tendencia["mes"].dt.strftime("%Y-%m")
            custom = tendencia[["mediana", "dias", "ejecuciones"]].to_numpy()
            fig_tendencia = go.Figure()
            fig_tendencia.add_trace(go.Scatter(
                x=meses,
                y=tendencia["promedio"],
                name="Promedio de días",
                mode="lines+markers",
                line=dict(color=SERIE_ACTUAL, width=3),
                marker=dict(size=8),
                customdata=custom,
                hovertemplate=(
                    "Mes: %{x}<br>Promedio diario: %{y:." + str(decimales) + "f} "
                    + unidad + "<br>Mediana diaria: %{customdata[0]:."
                    + str(decimales) + "f} " + unidad
                    + "<br>Días observados: %{customdata[1]:.0f}"
                    + "<br>Ejecuciones: %{customdata[2]:.0f}<extra></extra>"
                ),
            ))
            fig_tendencia.add_trace(go.Scatter(
                x=meses,
                y=tendencia["mediana"],
                name="Mediana de días",
                mode="lines+markers",
                line=dict(color=R_MENTA_OSC, width=2, dash="dash"),
                marker=dict(size=6),
                hovertemplate=(
                    "Mes: %{x}<br>Mediana diaria: %{y:." + str(decimales)
                    + "f} " + unidad + "<extra></extra>"
                ),
            ))
            fig_tendencia.update_layout(
                xaxis_title="Mes",
                yaxis_title=metrica_label,
                legend=dict(orientation="h", y=1.12),
            )
            # Los valores YYYY-MM son categorias. Forzarlo evita que Plotly
            # expanda un unico mes a milisegundos alrededor del primer dia.
            fig_tendencia.update_xaxes(type="category")
            fig_tendencia = plotly_base(fig_tendencia, height=430)
            mostrar_grafica(fig_tendencia, "temporal_tendencia")
            st.caption(
                "Primero se promedian las ejecuciones de cada día; después se resumen los "
                "días del mes. Así cada día observado tiene el mismo peso."
            )

        with vista_box:
            distribucion = analisis_temporal.distribucion_por_corrida(serie)
            # Ya viene en orden de dia operativo (04:00 ... 00:00)
            orden_horas = list(dict.fromkeys(distribucion["corrida"]))
            fig_box = px.box(
                distribucion,
                x="corrida",
                y="valor",
                points="outliers",
                category_orders={"corrida": orden_horas},
                labels={"corrida": "Hora del día", "valor": metrica_label},
                color_discrete_sequence=[SERIE_ACTUAL],
            )
            fig_box.update_traces(
                boxmean=True,
                marker=dict(size=5, opacity=0.55),
                line=dict(width=1.5),
                hovertemplate=(
                    "Hora: %{x}<br>Valor de ejecución: %{y:." + str(decimales)
                    + "f} " + unidad + "<extra></extra>"
                ),
            )
            fig_box = plotly_base(fig_box, height=430)
            mostrar_grafica(fig_box, "temporal_distribucion")
            st.caption(
                "La caja contiene el 50% central de las ejecuciones; la línea sólida es la "
                "mediana, la línea discontinua marca el promedio y los puntos son valores atípicos."
            )


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    if LOGO_UTB_SVG:
        st.markdown(f"""
        <div class="utb-sidebar-logo">
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

    archivos = listar_archivos()
    if archivos:
        # El dashboard publico siempre muestra el archivo mas reciente. La
        # seleccion manual de archivos historicos ya no se expone al usuario.
        archivo_actual = archivos[-1]
    else:
        archivo_actual = None
        st.warning("Sin archivos aun")

    # Sin boton "Recargar datos": st.cache_data.clear() vacia la cache de
    # todos los visitantes. Recargar queda en el panel administrativo.
    # Mismo boton que el pie de pagina: abre /admin, donde se pide la clave.
    # Va justo bajo el logo; su linea ya separa, sin un divisor aparte.
    st.markdown(
        """
        <a class="footer-admin-link sidebar-admin-link" href="/admin" target="_self">
            Ingresar al panel administrativo
            <span class="footer-admin-arrow">→</span>
        </a>
        """,
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
    <div class="utb-header-content">
        <div class="utb-eyebrow"><span class="utb-live-dot"></span> Plataforma de movilidad inteligente</div>
        <h1 class="utb-brand">Smart City <span class="utb-brand-accent">Cartagena</span></h1>
        <div class="utb-header-chips">
            <span class="utb-header-chip">113 nodos conectados</span>
            <span class="utb-header-chip">Monitoreo en vivo</span>
            <span class="utb-header-chip">TomTom Traffic Flow</span>
        </div>
    </div>
    <svg class="utb-route" viewBox="0 0 215 84" aria-hidden="true">
        <path d="M8 62 C45 15, 74 74, 112 34 S169 12, 207 42" fill="none" stroke="rgba(255,255,255,.38)" stroke-width="2" stroke-linecap="round" stroke-dasharray="5 7"/>
        <circle cx="10" cy="60" r="6" fill="#5eead4" stroke="rgba(255,255,255,.9)" stroke-width="2"/>
        <circle cx="112" cy="34" r="5" fill="#ffffff" stroke="rgba(94,234,212,.8)" stroke-width="3"/>
        <circle cx="205" cy="41" r="7" fill="#5eead4" stroke="rgba(255,255,255,.9)" stroke-width="2"/>
    </svg>
    <div class="utb-status">
        <div class="utb-status-label">Hora local</div>
        <div class="utb-clock">{ahora.strftime("%H:%M")} · {ahora.strftime("%d/%m/%Y")}</div>
        <div class="utb-next-run">
            Próxima ejecución: <span>{proxima_str}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Cuanto retroceder buscando el ultimo snapshot valido cuando la captura
# lleva caida mas de un dia. Acota el costo de la lectura de respaldo.
DIAS_RESPALDO_SNAPSHOT = 7


def _mascara_ok(df: pd.DataFrame) -> pd.Series:
    """
    Filas cuya consulta a TomTom fue exitosa. La columna 'ok' llega como bool
    desde PostgreSQL y como texto ("TRUE") desde Sheets y los CSV, asi que se
    normaliza en ambos casos.
    """
    if df.empty or "ok" not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    return df["ok"].astype(str).str.lower().isin(["true", "1"])


def lecturas_ultima_ejecucion(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lecturas validas de una ejecucion con las mismas columnas que los
    promedios por nodo (n = 1): la vista inicial de los mapas, como en
    produccion, antes de que el usuario toque un filtro.
    """
    columnas = ["id_nodo", "vel_actual", "vel_libre", "ratio", "n"]
    if df.empty or "id_nodo" not in df.columns:
        return pd.DataFrame(columns=columnas)
    ok = df[_mascara_ok(df)]
    return pd.DataFrame({
        "id_nodo": ok["id_nodo"].astype(str),
        "vel_actual": pd.to_numeric(ok.get("currentSpeed"), errors="coerce"),
        "vel_libre": pd.to_numeric(ok.get("freeFlowSpeed"), errors="coerce"),
        "ratio": pd.to_numeric(ok.get("velocidad_ratio"), errors="coerce"),
        "n": 1,
    }).drop_duplicates("id_nodo")[columnas]


# ============================================================
# CARGAR DATOS BASE
# ============================================================
# Aviso de carga en un lugar fijo de la pagina (existe en todas las corridas,
# asi no desplaza las pestanas como el spinner de cache; ver cargar_logs).
aviso_carga = st.empty()
aviso_carga.info("Cargando datos... la primera carga puede tardar un poco.")
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
# Sin esto el analisis de nodos filtra por ok=true y se queda sin filas sin
# explicar nada. Se guarda el diagnostico y se retrocede al ultimo snapshot
# con datos reales, rotulado como desactualizado.
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

    # La ventana normal es de 1 dia. Cuando la caida se prolonga mas que eso,
    # el ultimo dato bueno queda fuera y el mapa se quedaba sin nada que
    # mostrar. Solo entonces se paga una lectura mas amplia.
    _pool = _df_sheets_1d if not _df_sheets_1d.empty else df_actual
    if _pool.empty or not _mascara_ok(_pool).any():
        _pool_ancho = cargar_desde_sheets(n_dias=DIAS_RESPALDO_SNAPSHOT)
        if not _pool_ancho.empty and _mascara_ok(_pool_ancho).any():
            _pool = _pool_ancho

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

aviso_carga.empty()

# ============================================================
# METRICAS PRINCIPALES
# ============================================================
col1, col2, col3, col4 = st.columns(4)

_snapshot_ok = df_snapshot[_mascara_ok(df_snapshot)].copy()
_nodos_observados = (
    _snapshot_ok["id_nodo"].astype(str).nunique()
    if not _snapshot_ok.empty and "id_nodo" in _snapshot_ok.columns else 0
)
_velocidad_promedio = (
    pd.to_numeric(_snapshot_ok["currentSpeed"], errors="coerce").mean()
    if not _snapshot_ok.empty and "currentSpeed" in _snapshot_ok.columns
    else float("nan")
)
_fluidez_promedio = (
    pd.to_numeric(_snapshot_ok["velocidad_ratio"], errors="coerce").mean()
    if not _snapshot_ok.empty and "velocidad_ratio" in _snapshot_ok.columns
    else float("nan")
)
_, _estado_movilidad = clasificar_ratio(_fluidez_promedio)
_hora_snapshot = (
    pd.to_datetime(_snapshot_ok["consultation_time"], errors="coerce").max()
    if not _snapshot_ok.empty and "consultation_time" in _snapshot_ok.columns
    else pd.NaT
)

with col1:
    st.metric("Nodos observados", f"{_nodos_observados:,}", "última medición", delta_color="off")
with col2:
    st.metric(
        "Velocidad promedio",
        f"{_velocidad_promedio:.1f} km/h" if pd.notna(_velocidad_promedio) else "—",
        "red monitoreada",
        delta_color="off",
    )
with col3:
    st.metric(
        "Índice de fluidez",
        f"{_fluidez_promedio:.2f}" if pd.notna(_fluidez_promedio) else "—",
        _estado_movilidad,
        delta_color="off",
    )
with col4:
    st.metric(
        "Actualización",
        _hora_snapshot.strftime("%H:%M") if pd.notna(_hora_snapshot) else "—",
        _hora_snapshot.strftime("%d/%m/%Y") if pd.notna(_hora_snapshot) else "Sin datos",
        delta_color="off",
    )

if _snapshot_ok.empty:
    st.info("Aún no hay mediciones válidas para mostrar.")

# ============================================================
# AVISO DE CAPTURA DETENIDA
# ============================================================
# Un mapa vacio no explica nada. Si la ultima corrida no trajo un solo nodo
# valido, se dice por que y desde cuando, con el error crudo de la API.
if snapshot_degradado:
    _sd = snapshot_degradado
    _secretos = config.API_KEYS + config.API_KEYS_RESERVA + config.API_KEYS_RED
    _motivo_txt = html.escape(
        sanitizar_error(
            _sd["motivo"] or "sin detalle en error_msg",
            *_secretos,
            limite=300,
        ),
        quote=True,
    )
    _http_txt = f"HTTP {html.escape(str(_sd['http']), quote=True)} · " if _sd["http"] else ""
    _label_fallido = html.escape(str(_sd["label_fallido"]), quote=True)

    if _sd["label_valido"]:
        _seg = (datetime.now() - _sd["hora_valida"]).total_seconds()
        _dias, _resto = divmod(max(_seg, 0), 86400)
        _horas = _resto / 3600
        _antig = f"{int(_dias)} d {_horas:.0f} h" if _dias else f"{_horas:.1f} h"
        _label_valido = html.escape(str(_sd["label_valido"]), quote=True)
        _respaldo = (
            f"El análisis de nodos muestra el último dato bueno: "
            f"<b style='color:{UTB_WHITE};'>{_label_valido}</b> "
            f"(hace {_antig}). No es la situación actual del tráfico."
        )
    else:
        _respaldo = "No hay ninguna corrida reciente con datos válidos para mostrar."

    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.12);border-left:4px solid {COLOR_CONGESTIONADO};
         padding:14px 18px;border-radius:8px;margin-bottom:16px;">
        <div style="color:{TEXTO_CONGESTIONADO};font-size:13px;font-weight:800;
             letter-spacing:1px;margin-bottom:6px;">
            &#9888; CAPTURA DE DATOS DETENIDA</div>
        <div style="color:{UTB_GRAY};font-size:13px;line-height:1.6;">
            La corrida <b style="color:{UTB_WHITE};">{_label_fallido}</b> devolvio
            <b style="color:{TEXTO_CONGESTIONADO};">0 de {_sd['nodos']} nodos válidos</b>.<br/>
            {_http_txt}Respuesta de la API:
            <code style="background:{UTB_NAVY_LIGHT};color:{TEXTO_LENTO};padding:2px 6px;
             border-radius:4px;font-size:12px;">{_motivo_txt}</code><br/>
            {_respaldo}
        </div>
    </div>""", unsafe_allow_html=True)

# El footer se emite antes de las pestañas para que Streamlit no lo retenga
# mientras ejecuta el contenido de las vistas no seleccionadas. Su contenedor
# tiene un orden CSS alto, por lo que conserva su posicion visual al final.
# Oculto por ahora: el acceso al panel admin quedo en la barra lateral.
# Poner en True para volver a mostrarlo.
MOSTRAR_FOOTER = False
if MOSTRAR_FOOTER:
    with st.container(key="dashboard_footer"):
        st.markdown(f"""
        <div class="dashboard-footer">
            <div class="footer-brand">Smart City <span>Cartagena</span></div>
            <p class="footer-lead">
                Datos de movilidad convertidos en información para
                <strong>analizar el comportamiento vial de la ciudad.</strong>
            </p>
            <div class="footer-grid">
                <div>
                    <div class="footer-kicker">Qué muestra</div>
                    <p class="footer-copy">Velocidad de circulación, nivel de fluidez, demoras, rutas y comportamiento histórico de los nodos.</p>
                </div>
                <div>
                    <div class="footer-kicker">Cómo se interpreta</div>
                    <p class="footer-copy">El índice de fluidez compara la velocidad de circulación con la velocidad de flujo libre. Verde indica circulación fluida; rojo, mayor congestión.</p>
                </div>
                <div>
                    <div class="footer-kicker">Fuente y actualización</div>
                    <p class="footer-copy">TomTom Traffic Flow<br>28 consultas programadas al día<br>Consolidación de VPS 1 y VPS 2</p>
                </div>
            </div>
            <div class="footer-bottom">
                <span>Movilidad urbana basada en datos</span>
                <a class="footer-admin-link" href="/admin" target="_self">
                    Ingresar al panel administrativo
                    <span class="footer-admin-arrow">→</span>
                </a>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ============================================================
# TABS
# ============================================================
tab_mapa, tab_red, tab_simulacion, tab_datos, tab_temporal, tab_historia = st.tabs(
    [
        "Mapa de Tráfico",
        "Red de Nodos",
        "Simulaciones",
        "Análisis por Nodo",
        "Análisis Temporal",
        "Histórico",
    ]
)

# ----------------------------------------------------------------
# TAB MAPA
# ----------------------------------------------------------------
with tab_mapa:
    catalogo = cargar_catalogo()
    if catalogo.empty:
        st.info("No se pudo leer el catálogo de nodos (nodos.xlsx).")
    else:
        col_filtros, col_mapa = st.columns([1, 3])
        with col_filtros, mapa_nodos.tarjeta_filtros("mapa", "Filtros del Mapa"):
            filtros = mapa_nodos.panel_filtros(
                "mapa", dict(zip(catalogo["id_nodo"], catalogo["nombre_nodo"])),
                fechas_disponibles(), _hora_snapshot,
            )
        consulta = filtros["consulta"]
        en_vivo = filtros["en_vivo"]

        # Sin filtros de datos: la ultima ejecucion, como en produccion.
        # Al tocar fechas, horas o tipo de dia: promedios del periodo.
        if en_vivo:
            promedios = lecturas_ultima_ejecucion(df_snapshot)
        else:
            with st.spinner("Calculando promedios..."):
                promedios, _ = promedios_mapa(**consulta)

        nodos_mapa = catalogo
        if consulta["ids"]:
            nodos_mapa = catalogo[catalogo["id_nodo"].isin(consulta["ids"])]
        nodos_mapa = nodos_mapa.merge(promedios, on="id_nodo", how="left")
        n_con_datos = int(nodos_mapa["n"].notna().sum())

        with col_mapa:
            if n_con_datos == 0:
                st.info("La última ejecución no trajo lecturas válidas." if en_vivo else
                        "No hay mediciones con estos filtros. Los nodos se muestran en gris.")

            mapa = mapa_nodos.construir_mapa(
                nodos_mapa, filtros["metrica"], filtros["metrica_label"], clasificar_ratio,
                en_vivo,
            )
            st_folium(mapa, height=560, use_container_width=True,
                      returned_objects=[], key="mapa_nodos")
            st.caption("Haz clic en un nodo para ver su detalle.")
            if filtros["metrica"] == "ratio":
                leyenda_ratio("ratio")

        st.markdown("### Distribución del tráfico")
        ca, cb, cc, cd = st.columns(4)
        r_ok = nodos_mapa["ratio"].dropna()
        n_fluido   = (r_ok > UMBRAL_FLUIDO).sum()
        n_moderado = ((r_ok > UMBRAL_MODERADO) & (r_ok <= UMBRAL_FLUIDO)).sum()
        n_lento    = ((r_ok > UMBRAL_LENTO) & (r_ok <= UMBRAL_MODERADO)).sum()
        n_cong     = (r_ok <= UMBRAL_LENTO).sum()
        # Los rangos de cada categoria ya estan en la leyenda del indice, arriba
        for col_ui, n, color, label in [
            (ca, n_fluido,   COLOR_FLUIDO,        "FLUIDO"),
            (cb, n_moderado, COLOR_MODERADO,      "MODERADO"),
            (cc, n_lento,    COLOR_LENTO,         "LENTO"),
            (cd, n_cong,     COLOR_CONGESTIONADO, "CONGESTIONADO"),
        ]:
            with col_ui:
                st.markdown(f"""
                <div style="background:{UTB_NAVY_LIGHT};padding:22px 24px 20px;border-radius:28px;border:0;box-shadow:{R_SOMBRA}, inset 0 4px 0 {color};">
                    <div style="color:{UTB_GRAY};font-size:12px;font-weight:600;letter-spacing:.8px;"><span style="color:{color};">●</span> {label}</div>
                    <div style="color:{UTB_WHITE};font-size:36px;font-weight:800;margin:8px 0 0;">{n}</div>
                </div>""", unsafe_allow_html=True)

# ----------------------------------------------------------------
# TAB RED DE NODOS
# ----------------------------------------------------------------
with tab_red:
    catalogo = cargar_catalogo()
    if catalogo.empty:
        st.info("No se pudo leer el catálogo de nodos (nodos.xlsx).")
    else:
        red = cargar_red()
        nombres = dict(zip(catalogo["id_nodo"], catalogo["nombre_nodo"]))
        col_filtros, col_mapa = st.columns([1, 3])
        with col_filtros, mapa_nodos.tarjeta_filtros("red", "Filtros del Mapa de Red"):
            filtros_red = mapa_nodos.panel_filtros(
                "red", nombres, fechas_disponibles(), _hora_snapshot
            )
            mostrar_conexiones = st.checkbox("Mostrar conexiones", value=True, key="red_conexiones")
            # La clave cambia con la disponibilidad del trazado: si el JSON
            # aparece a mitad de sesion, la casilla vuelve a nacer marcada.
            seguir_vias = st.checkbox(
                "Seguir las carreteras", value=red["por_via"],
                key=f"red_vias_{red['por_via']}", disabled=not red["por_via"],
                help="Dibuja cada conexión por las vías reales (OpenStreetMap). "
                     "Si está deshabilitado, falta ejecutar capturar_red.py.",
            )

            st.markdown("#### Ruta")
            tipo_ruta = st.radio(
                "Tipo de ruta", ["Origen–Destino", "Corredor"],
                horizontal=True, key="red_tipo_ruta", label_visibility="collapsed",
            )
            origen = destino = None
            vista_corredores = []
            if tipo_ruta == "Origen–Destino":
                origen = st.selectbox("Origen", list(nombres), index=None, key="red_origen",
                                      format_func=nombres.get, placeholder="Elegir nodo")
                destino = st.selectbox("Destino", list(nombres), index=None, key="red_destino",
                                       format_func=nombres.get, placeholder="Elegir nodo")
            else:
                corredores, sin_catalogo = cargar_corredores()
                if not corredores:
                    st.info(
                        "Todavía no hay corredores. Agrégalos en la hoja CORREDORES de "
                        "nodos.xlsx: Corredor, Orden e id_nodo, una fila por nodo."
                    )
                else:
                    elegidos = st.multiselect(
                        "Corredores:", list(corredores), key="red_corredores",
                        placeholder="Todos los corredores",
                    )
                    # Se arman todos para que cada corredor conserve su color
                    vista_corredores = [
                        c for c in red_nodos.armar_corredores(corredores, red)
                        if not elegidos or c["nombre"] in elegidos
                    ]
                    if sin_catalogo:
                        st.caption("Nodos de CORREDORES que no están en el catálogo: "
                                   + ", ".join(sin_catalogo))

        # La ruta se calcula sobre toda la red: el filtro de punto de
        # monitoreo solo decide que nodos se dibujan.
        consulta_red = {**filtros_red["consulta"], "ids": ()}
        en_vivo_red = filtros_red["en_vivo"]
        # Igual que el mapa de nodos: ultima ejecucion hasta que se toque un filtro
        if en_vivo_red:
            promedios_red = lecturas_ultima_ejecucion(df_snapshot)
        else:
            with st.spinner("Calculando promedios..."):
                promedios_red, _ = promedios_mapa(**consulta_red)
        prom = promedios_red.set_index("id_nodo").to_dict("index")
        ruta = (red_nodos.ruta_mas_rapida(origen, destino, red, prom)
                if origen and destino else None)

        nodos_red = catalogo.merge(promedios_red, on="id_nodo", how="left")
        ids_vista = set(filtros_red["consulta"]["ids"])
        if ids_vista:
            ids_vista |= set(ruta["nodos"]) if ruta else set()
            ids_vista |= {n for c in vista_corredores for n in c["nodos"]}
            nodos_red = nodos_red[nodos_red["id_nodo"].isin(ids_vista)]

        with col_mapa:
            if origen and destino and origen == destino:
                st.info("El origen y el destino son el mismo nodo.")
            elif origen and destino and ruta is None:
                st.warning("No hay un camino entre esos nodos con datos para estos filtros.")

            mapa_red = red_nodos.construir_mapa_red(
                nodos_red, red, prom, filtros_red["metrica"], filtros_red["metrica_label"],
                clasificar_ratio, mostrar_conexiones, seguir_vias, ruta, en_vivo_red,
                corredores=vista_corredores,
            )
            # Los corredores van de Bayunca a Mamonal: con 560 px la ciudad se
            # ve un nivel de zoom mas lejos
            st_folium(mapa_red, height=640 if vista_corredores else 560,
                      use_container_width=True, returned_objects=[], key="mapa_red")
            if vista_corredores:
                leyenda_corredores(vista_corredores)
                sin_conexion = sum(c["sin_conexion"] for c in vista_corredores)
                if sin_conexion:
                    st.caption(f"{sin_conexion} tramo(s) de corredor sin conexión en la red se "
                               "dibujan en línea recta: falta correr "
                               "capturar_red.py --completar-corredores.")
            if filtros_red["metrica"] == "ratio":
                leyenda_ratio("ratio")

        if vista_corredores:
            st.markdown("### Corredores seleccionados")
            filas = []
            for c in vista_corredores:
                r = red_nodos.resumen_corredor(c, prom)
                minutos = r["tiempo_s"] / 60
                filas.append({
                    "Corredor": c["nombre"],
                    "Nodos": len(dict.fromkeys(c["nodos"])),
                    "Distancia (km)": r["dist_m"] / 1000,
                    "Tiempo (min)": minutos,
                    "Demora (min)": minutos - r["tiempo_libre_s"] / 60,
                    "Velocidad (km/h)": r["dist_m"] / 1000 / (minutos / 60),
                    "Fluidez": r["ratio"],
                    "Estado": clasificar_ratio(r["ratio"])[1],
                })
            st.dataframe(
                pd.DataFrame(filas).style.format({
                    "Distancia (km)": "{:.1f}", "Tiempo (min)": "{:.1f}", "Demora (min)": "{:+.1f}",
                    "Velocidad (km/h)": "{:.1f}", "Fluidez": "{:.2f}",
                }, na_rep="—"),
                width="stretch", hide_index=True,
            )
            st.caption("Cada corredor se recorre tramo a tramo en el orden de la hoja CORREDORES; "
                       "como son vías de doble sentido, cada tramo se mide en su sentido más "
                       "corto. Tiempo con las velocidades promedio de sus nodos para los filtros "
                       "elegidos. Demora: minutos de más frente al flujo libre. Fluidez: "
                       "promedio de sus nodos.")

        if ruta:
            st.markdown("### Ruta seleccionada")
            km = ruta["dist_m"] / 1000
            minutos = ruta["tiempo_s"] / 60
            extra = minutos - ruta["tiempo_libre_s"] / 60
            rc1, rc2, rc3, rc4 = st.columns(4)
            with rc1: st.metric("Distancia total", f"{km:.1f} km")
            with rc2: st.metric("Tiempo promedio de viaje", f"{minutos:.1f} min",
                                f"+{extra:.1f} min frente al flujo libre", delta_color="inverse")
            with rc3: st.metric("Velocidad promedio", f"{km / (minutos / 60):.1f} km/h")
            with rc4: st.metric("Nodos en la ruta", len(ruta["nodos"]))

            tabla_ruta = pd.DataFrame([{
                "#": i + 1,
                "Nodo": nombres[n],
                "Velocidad (km/h)": prom.get(n, {}).get("vel_actual"),
                "Índice de fluidez": prom.get(n, {}).get("ratio"),
                "Estado": clasificar_ratio(prom.get(n, {}).get("ratio"))[1],
            } for i, n in enumerate(ruta["nodos"])])
            # En rutas cortas la tabla ya muestra todos los nodos
            if len(tabla_ruta) > 3:
                criticos = tabla_ruta.nsmallest(3, "Índice de fluidez")
                st.markdown(
                    "**Mayor congestión en la ruta:** " + " · ".join(
                        f"{r['Nodo']} ({r['Índice de fluidez']:.2f}, {r['Estado'].lower()})"
                        for _, r in criticos.iterrows()
                    )
                )
            st.dataframe(
                tabla_ruta.style.format({"Velocidad (km/h)": "{:.1f}", "Índice de fluidez": "{:.2f}"}),
                width="stretch", hide_index=True,
            )

# ----------------------------------------------------------------
# TAB SIMULACION DE CIERRES
# ----------------------------------------------------------------
with tab_simulacion:
    catalogo = cargar_catalogo()
    if catalogo.empty:
        st.info("No se pudo leer el catálogo de nodos (nodos.xlsx).")
    else:
        st.markdown("### Simulación de cierres de vías")
        st.caption(
            "Selecciona dos nodos conectados directamente para cerrar temporalmente ese tramo. "
            "Puedes agregar varios cierres y definir el sentido afectado. Después, selecciona "
            "el origen y el destino de tu viaje para calcular la alternativa con menor tiempo estimado."
        )
        red_sim = cargar_red()
        nombres_sim = dict(zip(catalogo["id_nodo"], catalogo["nombre_nodo"]))
        cierres_sim = st.session_state.setdefault("sim_cierres", [])
        col_filtros_sim, col_mapa_sim = st.columns([1, 3])

        with col_filtros_sim, mapa_nodos.tarjeta_filtros("sim", "Simulación de cierres"):
            filtros_sim = mapa_nodos.panel_filtros(
                "sim", nombres_sim, fechas_disponibles(), _hora_snapshot
            )
            mostrar_conexiones_sim = st.checkbox(
                "Mostrar conexiones", value=True, key="sim_conexiones"
            )
            seguir_vias_sim = st.checkbox(
                "Seguir las carreteras", value=red_sim["por_via"],
                key=f"sim_vias_{red_sim['por_via']}", disabled=not red_sim["por_via"],
                help="Dibuja cada conexión usando la geometría real disponible.",
            )

            st.markdown("#### Agregar cierre")
            inicio_cierre = st.selectbox(
                "Nodo inicial del cierre", list(nombres_sim), index=None,
                key="sim_inicio_cierre", format_func=nombres_sim.get,
                placeholder="Elegir nodo",
            )
            vecinos = red_nodos.nodos_conectados(red_sim, inicio_cierre) if inicio_cierre else []
            fin_cierre = st.selectbox(
                "Nodo final del cierre", vecinos, index=None, key="sim_fin_cierre",
                format_func=nombres_sim.get, placeholder="Elegir nodo conectado",
                disabled=not inicio_cierre,
            )
            conexion_cierre = (red_nodos.buscar_conexion(red_sim, inicio_cierre, fin_cierre)
                               if inicio_cierre and fin_cierre else None)
            opciones_sentido = []
            if conexion_cierre:
                ida_es_ab = (inicio_cierre, fin_cierre) == (
                    conexion_cierre["a"], conexion_cierre["b"]
                )
                distancia_ida = conexion_cierre["d_ab_m" if ida_es_ab else "d_ba_m"]
                distancia_vuelta = conexion_cierre["d_ba_m" if ida_es_ab else "d_ab_m"]
                if distancia_ida is not None and distancia_vuelta is not None:
                    opciones_sentido.append(("Ambos sentidos", "ambos"))
                if distancia_ida is not None:
                    opciones_sentido.append(("Solo nodo inicial → nodo final", "ida"))
                if distancia_vuelta is not None:
                    opciones_sentido.append(("Solo nodo final → nodo inicial", "vuelta"))
            if not opciones_sentido:
                opciones_sentido = [("Ambos sentidos", "ambos")]
            etiqueta_sentido = st.selectbox(
                "Sentido afectado", [x[0] for x in opciones_sentido],
                key="sim_sentido_cierre", disabled=conexion_cierre is None,
            )
            codigo_sentido = dict(opciones_sentido)[etiqueta_sentido]

            if st.button(
                    "Agregar cierre", key="sim_agregar_cierre", use_container_width=True,
                    disabled=conexion_cierre is None):
                nuevo_cierre = {
                    "inicio": inicio_cierre, "fin": fin_cierre, "sentido": codigo_sentido,
                }
                nuevas_aristas = red_nodos.aristas_cerradas([nuevo_cierre])
                duplicado = any(
                    red_nodos.aristas_cerradas([existente]) == nuevas_aristas
                    for existente in cierres_sim
                )
                if duplicado:
                    st.warning("Ese cierre ya está en la lista.")
                else:
                    st.session_state["sim_cierres"] = [*cierres_sim, nuevo_cierre]
                    st.session_state["sim_calculo"] = None
                    st.rerun()

            st.markdown("#### Cierres agregados")
            if not cierres_sim:
                st.caption("Todavía no has agregado cierres.")
            for indice, cierre in enumerate(cierres_sim):
                if cierre["sentido"] == "ambos":
                    descripcion = (f"{nombres_sim[cierre['inicio']]} ↔ "
                                   f"{nombres_sim[cierre['fin']]} · Ambos sentidos")
                elif cierre["sentido"] == "ida":
                    descripcion = (f"{nombres_sim[cierre['inicio']]} → "
                                   f"{nombres_sim[cierre['fin']]}")
                else:
                    descripcion = (f"{nombres_sim[cierre['fin']]} → "
                                   f"{nombres_sim[cierre['inicio']]}")
                texto_cierre, boton_cierre = st.columns([5, 1])
                with texto_cierre:
                    st.caption(descripcion)
                with boton_cierre:
                    if st.button("✕", key=f"sim_eliminar_{indice}", help="Eliminar cierre"):
                        st.session_state["sim_cierres"] = [
                            c for i, c in enumerate(cierres_sim) if i != indice
                        ]
                        st.session_state["sim_calculo"] = None
                        st.rerun()
            if cierres_sim and st.button(
                    "Eliminar todos los cierres", key="sim_eliminar_todos",
                    use_container_width=True):
                st.session_state["sim_cierres"] = []
                st.session_state["sim_calculo"] = None
                st.rerun()

            st.markdown("#### Origen y destino del viaje")
            origen_sim = st.selectbox(
                "Origen del viaje", list(nombres_sim), index=None, key="sim_origen",
                format_func=nombres_sim.get, placeholder="Elegir nodo",
            )
            destinos_sim = [n for n in nombres_sim if n != origen_sim]
            destino_sim = st.selectbox(
                "Destino del viaje", destinos_sim, index=None, key="sim_destino",
                format_func=nombres_sim.get, placeholder="Elegir nodo",
            )
            seleccion_invalida = not origen_sim or not destino_sim or origen_sim == destino_sim
            if st.button(
                    "Calcular ruta alternativa", key="sim_calcular", type="primary",
                    use_container_width=True, disabled=seleccion_invalida):
                st.session_state["sim_calculo"] = {
                    "origen": origen_sim,
                    "destino": destino_sim,
                    "cierres": [dict(c) for c in cierres_sim],
                }
                st.rerun()

        consulta_sim = {**filtros_sim["consulta"], "ids": ()}
        en_vivo_sim = filtros_sim["en_vivo"]
        if en_vivo_sim:
            promedios_sim = lecturas_ultima_ejecucion(df_snapshot)
        else:
            with st.spinner("Calculando promedios..."):
                promedios_sim, _ = promedios_mapa(**consulta_sim)
        prom_sim = promedios_sim.set_index("id_nodo").to_dict("index")

        calculo_sim = st.session_state.get("sim_calculo")
        ruta_normal_sim = ruta_alternativa_sim = None
        origen_calculado = destino_calculado = None
        cierres_calculados = cierres_sim
        if calculo_sim:
            origen_calculado = calculo_sim["origen"]
            destino_calculado = calculo_sim["destino"]
            cierres_calculados = calculo_sim["cierres"]
            ruta_normal_sim = red_nodos.ruta_mas_rapida(
                origen_calculado, destino_calculado, red_sim, prom_sim
            )
            ruta_alternativa_sim = red_nodos.ruta_mas_rapida(
                origen_calculado, destino_calculado, red_sim, prom_sim,
                cierres=cierres_calculados,
            )

        nodos_sim = catalogo.merge(promedios_sim, on="id_nodo", how="left")
        ids_vista_sim = set(filtros_sim["consulta"]["ids"])
        if ids_vista_sim:
            ids_vista_sim.update(n for c in cierres_sim for n in (c["inicio"], c["fin"]))
            for ruta_sim in (ruta_normal_sim, ruta_alternativa_sim):
                if ruta_sim:
                    ids_vista_sim.update(ruta_sim["nodos"])
            nodos_sim = nodos_sim[nodos_sim["id_nodo"].isin(ids_vista_sim)]

        with col_mapa_sim:
            if calculo_sim and ruta_normal_sim is None:
                st.warning("No hay un camino normal entre esos nodos con datos para estos filtros.")
            elif calculo_sim and ruta_alternativa_sim is None:
                st.warning("No existe una ruta alternativa disponible con los cierres seleccionados.")

            mapa_sim = red_nodos.construir_mapa_simulacion(
                nodos_sim, red_sim, prom_sim, filtros_sim["metrica"],
                filtros_sim["metrica_label"], clasificar_ratio,
                mostrar_conexiones_sim, seguir_vias_sim, cierres_sim,
                ruta_normal_sim, ruta_alternativa_sim,
                origen_calculado or origen_sim, destino_calculado or destino_sim,
                en_vivo_sim,
            )
            st_folium(
                mapa_sim, height=620, use_container_width=True,
                returned_objects=[], key="mapa_simulacion_cierres",
            )
            st.caption(
                "Rojo: tramos cerrados · Gris discontinuo: ruta sin cierres · "
                "Turquesa: ruta alternativa"
            )
            if filtros_sim["metrica"] == "ratio":
                leyenda_ratio("ratio")

        if ruta_alternativa_sim:
            st.markdown("### Ruta alternativa")
            km_alt = ruta_alternativa_sim["dist_m"] / 1000
            min_alt = ruta_alternativa_sim["tiempo_s"] / 60
            vel_alt = km_alt / (min_alt / 60)
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1: st.metric("Distancia total", f"{km_alt:.1f} km")
            with m2: st.metric("Tiempo estimado", f"{min_alt:.1f} min")
            with m3: st.metric("Velocidad promedio", f"{vel_alt:.1f} km/h")
            with m4: st.metric("Nodos recorridos", len(ruta_alternativa_sim["nodos"]))
            with m5: st.metric("Tramos utilizados", len(ruta_alternativa_sim["tramos"]))
            st.markdown(
                "**Secuencia de nodos:** " + " → ".join(
                    nombres_sim.get(n, n) for n in ruta_alternativa_sim["nodos"]
                )
            )

            if ruta_normal_sim:
                st.markdown("### Impacto de los cierres")
                km_normal = ruta_normal_sim["dist_m"] / 1000
                min_normal = ruta_normal_sim["tiempo_s"] / 60
                vel_normal = km_normal / (min_normal / 60)
                misma_ruta = ruta_normal_sim["nodos"] == ruta_alternativa_sim["nodos"]
                if misma_ruta:
                    st.info("Los cierres seleccionados no afectan el recorrido entre el origen y el destino.")
                i1, i2, i3, i4 = st.columns(4)
                with i1: st.metric("Distancia adicional", f"{km_alt - km_normal:+.1f} km")
                with i2: st.metric("Aumento del tiempo", f"{min_alt - min_normal:+.1f} min")
                with i3: st.metric("Cambio de velocidad", f"{vel_alt - vel_normal:+.1f} km/h")
                with i4:
                    st.metric(
                        "Cambio de tramos",
                        f"{len(ruta_alternativa_sim['tramos']) - len(ruta_normal_sim['tramos']):+d}",
                    )
                comparacion = pd.DataFrame([
                    {
                        "Ruta": "Ruta sin cierres", "Distancia (km)": km_normal,
                        "Tiempo (min)": min_normal, "Velocidad (km/h)": vel_normal,
                        "Nodos": len(ruta_normal_sim["nodos"]),
                        "Tramos": len(ruta_normal_sim["tramos"]),
                    },
                    {
                        "Ruta": "Ruta alternativa", "Distancia (km)": km_alt,
                        "Tiempo (min)": min_alt, "Velocidad (km/h)": vel_alt,
                        "Nodos": len(ruta_alternativa_sim["nodos"]),
                        "Tramos": len(ruta_alternativa_sim["tramos"]),
                    },
                ])
                st.dataframe(
                    comparacion.style.format({
                        "Distancia (km)": "{:.1f}", "Tiempo (min)": "{:.1f}",
                        "Velocidad (km/h)": "{:.1f}",
                    }),
                    width="stretch", hide_index=True,
                )

# ----------------------------------------------------------------
# TAB ANALISIS DE NODOS
# ----------------------------------------------------------------
with tab_datos:
    render_analisis_nodo()

# ----------------------------------------------------------------
# TAB ANALISIS TEMPORAL
# ----------------------------------------------------------------
with tab_temporal:
    render_analisis_temporal()

# ----------------------------------------------------------------
# TAB HISTORICO
# ----------------------------------------------------------------
with tab_historia:
    st.markdown("### Datos históricos")
    st.caption("Incluye datos de VPS 1 (Turnos 1-2) y VPS 2 (Turnos 3-4)")

    # Rango de fechas disponible (consulta ligera; los datos del periodo se
    # cargan despues, solo para el rango que el usuario elija).
    with st.spinner("Consultando datos disponibles..."):
        min_fecha, max_fecha, fuente_rango = rango_fechas_historico()

    if min_fecha is None:
        st.warning("No hay datos históricos o no hay conexión con la fuente.")
    else:
        # Valor por defecto: ultimos 7 dias, recortado al rango disponible
        ini_default = max(min_fecha, max_fecha - timedelta(days=7))

        hf1, hf2, hf3 = st.columns(3)
        with hf1:
            fecha_ini = st.date_input(
                "Desde", value=ini_default,
                min_value=min_fecha, max_value=max_fecha, format="DD/MM/YYYY",
            )
        with hf2:
            fecha_fin = st.date_input(
                "Hasta", value=max_fecha,
                min_value=min_fecha, max_value=max_fecha, format="DD/MM/YYYY",
            )
        with hf3:
            tipo_dia = st.selectbox(
                "Tipo de día",
                ["Todos", "Solo laborables (L-V)", "Solo fin de semana",
                 "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
            )

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
                dias_idx = {"Lunes": 0, "Martes": 1, "Miércoles": 2, "Jueves": 3,
                            "Viernes": 4, "Sábado": 5, "Domingo": 6}
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
                with mc3: st.metric("Índice de fluidez promedio", f"{ratio_prom:.2f}" if pd.notna(ratio_prom) else "—")
                with mc4: st.metric("Registros totales", f"{n_reg:,}")

                # --- Grafica 1: Evolucion velocidad promedio ---
                st.markdown("### Evolución de la velocidad promedio")
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
                    indices_gap = [
                        ts - pd.Timedelta(minutes=1) for ts in evo.index[gaps]
                    ]
                    filas_gap = pd.DataFrame(
                        {
                            "vel_actual": [float("nan")] * len(indices_gap),
                            "vel_libre": [float("nan")] * len(indices_gap),
                        },
                        index=pd.DatetimeIndex(indices_gap, name=evo.index.name),
                    )
                    evo = pd.concat([evo, filas_gap]).sort_index()
                evo = evo.reset_index().rename(columns={"index": "consultation_time"})

                fig_line = go.Figure()
                fig_line.add_trace(go.Scatter(
                    x=evo["consultation_time"], y=evo["vel_libre"],
                    name="Velocidad libre", line=dict(color=SERIE_LIBRE, dash="dash", width=1.5),
                    connectgaps=False,
                ))
                fig_line.add_trace(go.Scatter(
                    x=evo["consultation_time"], y=evo["vel_actual"],
                    name="Velocidad de circulación", line=dict(color=SERIE_ACTUAL, width=2),
                    fill="tonexty", fillcolor="rgba(59,130,246,0.15)",
                    connectgaps=False,
                ))
                fig_line.update_layout(xaxis_title="Fecha/Hora", yaxis_title="km/h")
                fig_line = plotly_base(fig_line, height=320)
                mostrar_grafica(fig_line, "historico_evolucion")
                leyenda_ratio("velocidad")

                # --- Grafica 2: Top nodos mas congestionados en el periodo ---
                st.markdown("### Nodos más congestionados en el periodo")
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
                    labels={"ratio_prom": "Índice de fluidez promedio", "nombre_nodo": ""},
                    text=por_nodo["ratio_prom"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else ""),
                )
                fig_nodos.update_traces(textposition="outside")
                fig_nodos = plotly_base(fig_nodos, height=430)
                fig_nodos.update_layout(xaxis=dict(range=[0, 1.15]), showlegend=False)
                mostrar_grafica(fig_nodos, "historico_nodos")
                leyenda_ratio("ratio")

                # --- Grafica 3: Heatmap hora x dia de semana ---
                st.markdown("### Mapa de calor")
                dias_disponibles = df_periodo["consultation_time"].dt.date.nunique()
                if dias_disponibles < 2:
                    st.info("Se necesitan al menos 2 días de datos para mostrar el mapa de calor.")
                else:
                    df_heat = df_periodo.copy()
                    df_heat["hora"]    = df_heat["consultation_time"].dt.hour
                    df_heat["dia_num"] = df_heat["consultation_time"].dt.weekday  # 0=Lunes

                    pivot = (
                        df_heat.groupby(["dia_num", "hora"])["velocidad_ratio"]
                        .mean()
                        .unstack(fill_value=None)
                    )
                    # Horas del cron en orden de dia operativo: 04:00 ... 23:00, 00:00
                    pivot = pivot.reindex(columns=[h for h in horario.HORAS if h in pivot.columns])
                    dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                    y_labels = [dias_es[i] for i in pivot.index if i < 7]
                    x_labels = [f"{h:02d}:00" for h in pivot.columns]

                    fig_heat = go.Figure(go.Heatmap(
                        z=pivot.values,
                        x=x_labels,
                        y=y_labels,
                        # Cortes en los umbrales oficiales, igual que el mapa de calor
                        # del analisis temporal (antes el naranja caia en 0.5)
                        colorscale=[
                            [0.0, COLOR_CONGESTIONADO], [0.60, COLOR_LENTO], [0.75, COLOR_MODERADO],
                            [0.90, COLOR_FLUIDO], [1.0, "#047857"],
                        ],
                        zmin=0, zmax=1,
                        colorbar=dict(
                            title=dict(text="Índice", font=dict(color=R_AZUL_OSC), side="right"),
                            tickfont=dict(color=R_TENUE),
                            orientation="h",
                            x=0.5, xanchor="center",
                            # Arriba de la figura: se ve sin bajar, dentro del recuadro
                            yref="container", y=1, yanchor="top", ypad=10,
                            len=0.60,
                            thickness=12,
                        ),
                        hovertemplate="Hora: %{x}<br>Día: %{y}<br>Índice de fluidez: %{z:.2f}<extra></extra>",
                    ))
                    fig_heat.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#1e3a6e",
                        font_family="Inter, Segoe UI, Helvetica, Arial, sans-serif",
                        height=410,
                        margin=dict(l=20, r=28, t=80, b=34),
                        xaxis=dict(
                            title="Hora del día", gridcolor=REJILLA, type="category",
                            tickfont=dict(color=R_TENUE),
                            title_font=dict(color=R_AZUL_OSC), automargin=True,
                        ),
                        yaxis=dict(
                            title="", gridcolor=REJILLA,
                            tickfont=dict(color=R_TENUE), automargin=True,
                        ),
                    )
                    mostrar_grafica(fig_heat, "historico_calor")

                # ------------------------------------------------
                # Grafica 4: Hora pico vs hora valle
                # ------------------------------------------------
                st.markdown("### Hora pico frente a hora valle")
                st.caption("Velocidad promedio por franja horaria — identifica cuando fluye mejor la ciudad")

                # Las mismas franjas que los filtros (horas pico de 5:30-7:30,
                # 12:00-13:30 y 17:00-18:30), por corrida del cron
                franjas_hist = {
                    nombre: rango for nombre, rango in mapa_nodos.FRANJAS.items()
                    if nombre not in (mapa_nodos.TODO_EL_DIA, mapa_nodos.PERSONALIZADO)
                }

                filas_f = []
                for label, (desde_f, hasta_f) in franjas_hist.items():
                    sub = df_periodo[
                        horario.en_horario(df_periodo["consultation_time"], desde_f, hasta_f)
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
                    # "Hora pico AM (5:30–7:30)" -> nombre arriba y horario abajo
                    x_franjas = df_f["franja"].str.replace(" (", "<br>", regex=False).str.rstrip(")")
                    fig_franjas = go.Figure()
                    fig_franjas.add_trace(go.Bar(
                        name="Velocidad libre",
                        x=x_franjas,
                        y=df_f["vel_libre"],
                        marker_color=SERIE_LIBRE,
                        opacity=0.55,
                    ))
                    fig_franjas.add_trace(go.Bar(
                        name="Velocidad de circulación",
                        x=x_franjas,
                        y=df_f["vel_actual"],
                        # Mismo nivel que el mapa y la leyenda (0.90 / 0.75 / 0.60)
                        marker_color=[clasificar_ratio(r)[0] for r in df_f["ratio"]],
                    ))
                    # Linea de ratio superpuesta (eje Y secundario)
                    fig_franjas.add_trace(go.Scatter(
                        name="Índice de fluidez (eje →)",
                        x=x_franjas,
                        y=df_f["ratio"],
                        mode="lines+markers",
                        yaxis="y2",
                        line=dict(color=R_MENTA_OSC, width=2),
                        marker=dict(size=8, color=R_MENTA_OSC),
                    ))
                    fig_franjas.update_layout(
                        barmode="group",
                        # Etiquetas en dos lineas (nombre y horario): caben derechas
                        xaxis=dict(title="", tickangle=0, tickfont=dict(size=10)),
                        yaxis=dict(title="km/h", gridcolor=REJILLA),
                        yaxis2=dict(
                            title=dict(text="Índice de fluidez (0–1)", font=dict(color=TEXTO_MENTA)),
                            overlaying="y",
                            side="right",
                            range=[0, 1.2],
                            showgrid=False,
                            tickfont=dict(color=TEXTO_MENTA),
                        ),
                    )
                    fig_franjas = plotly_base(fig_franjas, height=370)
                    mostrar_grafica(fig_franjas, "historico_franjas")
                    leyenda_ratio("velocidad")

                    # Mini tabla resumen
                    df_f_disp = df_f.copy()
                    df_f_disp["vel_actual"]  = df_f_disp["vel_actual"].apply(lambda x: f"{x:.1f} km/h" if pd.notna(x) else "—")
                    df_f_disp["vel_libre"]   = df_f_disp["vel_libre"].apply(lambda x: f"{x:.1f} km/h" if pd.notna(x) else "—")
                    df_f_disp["ratio"]       = df_f_disp["ratio"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
                    df_f_disp = df_f_disp.rename(columns={
                        "franja": "Franja", "vel_actual": "Vel. actual",
                        "vel_libre": "Vel. libre", "ratio": "Índice de fluidez", "n_muestras": "Muestras",
                    })
                    st.dataframe(df_f_disp, width="stretch", hide_index=True)
                    st.markdown(
                        f"<div style='background:{SUPERFICIE_SUAVE};border:1px solid {UTB_BORDER};border-left:3px solid {R_MENTA};"
                        f"border-radius:6px;padding:10px 14px;margin-top:6px;font-size:12px;"
                        f"color:{UTB_GRAY};'>"
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
                st.caption("Selecciona un punto de monitoreo para ver su evolución histórica completa")

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
                        with nc2: st.metric("Índice de fluidez promedio", f"{ratio_n:.2f}" if pd.notna(ratio_n) else "—")
                        with nc3: st.metric("Demora prom.", f"{delay_n:.0f} s" if pd.notna(delay_n) else "—")
                        with nc4: st.metric("Observaciones", n_obs)

                        # Grafica de velocidad en el tiempo
                        fig_nodo = go.Figure()
                        fig_nodo.add_trace(go.Scatter(
                            x=df_nodo["consultation_time"],
                            y=df_nodo["freeFlowSpeed"],
                            name="Velocidad libre",
                            line=dict(color=SERIE_LIBRE, dash="dash", width=1.5),
                        ))
                        fig_nodo.add_trace(go.Scatter(
                            x=df_nodo["consultation_time"],
                            y=df_nodo["currentSpeed"],
                            name="Velocidad de circulación",
                            line=dict(color=SERIE_ACTUAL, width=2),
                            fill="tonexty",
                            fillcolor="rgba(59,130,246,0.15)",
                        ))
                        fig_nodo.update_layout(
                            xaxis_title="Fecha/Hora",
                            yaxis_title="km/h",
                            title=dict(text=nodo_sel, font=dict(color=UTB_WHITE, size=13)),
                        )
                        fig_nodo = plotly_base(fig_nodo, height=300)
                        mostrar_grafica(fig_nodo, "historico_nodo_serie")
                        leyenda_ratio("velocidad")

                        # Ratio promedio por hora del dia (barras)
                        df_nodo["hora_num"] = df_nodo["consultation_time"].dt.hour
                        por_hora_n = (
                            df_nodo.groupby("hora_num")
                            .agg(ratio_h=("velocidad_ratio", "mean"), vel_h=("currentSpeed", "mean"))
                            .reset_index()
                            # Dia operativo: 04:00 ... 23:00, 00:00
                            .sort_values("hora_num", key=lambda h: h.map(horario.orden_hora))
                        )

                        fig_hora_n = go.Figure()
                        fig_hora_n.add_trace(go.Bar(
                            x=[f"{h:02d}:00" for h in por_hora_n["hora_num"]],
                            y=por_hora_n["ratio_h"],
                            # Mismo nivel que la leyenda que va debajo
                            marker_color=[clasificar_ratio(r)[0] for r in por_hora_n["ratio_h"]],
                            name="Índice de fluidez por hora",
                            text=por_hora_n["ratio_h"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else ""),
                            textposition="outside",
                        ))
                        fig_hora_n.update_layout(
                            xaxis_title="Hora del día",
                            xaxis_type="category",
                            yaxis_title="Índice de fluidez",
                            yaxis=dict(range=[0, 1.2]),
                        )
                        fig_hora_n = plotly_base(fig_hora_n, height=280)
                        mostrar_grafica(fig_hora_n, "historico_nodo_hora")
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
                                    f"<div style='color:{TEXTO_CONGESTIONADO};font-size:11px;font-weight:700;'>⚠ PEOR HORA</div>"
                                    f"<div style='color:{UTB_WHITE};font-size:22px;font-weight:700;'>{int(peor['hora_num']):02d}:00</div>"
                                    f"<div style='color:{UTB_GRAY};font-size:12px;'>Índice {peor['ratio_h']:.2f} · "
                                    f"Vel. {peor['vel_h']:.1f} km/h</div></div>",
                                    unsafe_allow_html=True,
                                )
                            with ph2:
                                st.markdown(
                                    f"<div style='background:rgba(16,185,129,0.1);border-left:3px solid {COLOR_FLUIDO};"
                                    f"padding:12px 16px;border-radius:6px;'>"
                                    f"<div style='color:{TEXTO_FLUIDO};font-size:11px;font-weight:700;'>✓ MEJOR HORA</div>"
                                    f"<div style='color:{UTB_WHITE};font-size:22px;font-weight:700;'>{int(mejor['hora_num']):02d}:00</div>"
                                    f"<div style='color:{UTB_GRAY};font-size:12px;'>Índice {mejor['ratio_h']:.2f} · "
                                    f"Vel. {mejor['vel_h']:.1f} km/h</div></div>",
                                    unsafe_allow_html=True,
                                )

