"""Panel administrativo de Smart City Cartagena."""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DASHBOARD_DIR.parent
sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import admin_services as servicios  # noqa: E402
import config  # noqa: E402
import horario  # noqa: E402
from security_utils import clave_valida, huella_clave  # noqa: E402


st.set_page_config(
    page_title="Administración · Smart City Cartagena",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

AZUL = "#1f48b8"
AZUL_OSC = "#12307a"
MENTA = "#2dd4bf"
TINTA = "#111113"
TENUE = "#58585d"
LINEA = "#e7e7eb"
FONDO = "#fcfcfd"
VERDE = "#10b981"
AMBAR = "#f59e0b"
NARANJA = "#f97316"
ROJO = "#ef4444"


def texto_html(valor: object) -> str:
    """Escapa datos externos antes de interpolarlos en HTML habilitado."""
    return html.escape(str(valor), quote=True)


st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [data-testid="stAppViewContainer"], .stApp {{ overflow-x:hidden; }}
    .stApp {{ background:{FONDO}; color:{TINTA}; color-scheme:light; }}
    .stApp, .stApp button, .stApp input, .stApp textarea {{
        font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif !important;
    }}
    .block-container {{ max-width:1360px; padding-top:1.2rem; padding-bottom:3rem; }}
    [data-testid="stToolbar"], [data-testid="stDecoration"],
    [data-testid="stSidebarNav"] {{ display:none !important; }}
    /* El panel no usa barra lateral: vacia solo dejaba una franja gris */
    [data-testid="stSidebar"] {{ display:none !important; }}
    /* La barra superior de Streamlit mide 60 px, es opaca (color del fondo) y
       va por encima del contenido: tapaba la parte de arriba del encabezado.
       Se vuelve transparente y deja pasar los clics, salvo los de sus botones
       (no se le quita el alto: ahi vive el boton de la barra lateral). */
    [data-testid="stHeader"] {{ background:transparent !important; }}
    [data-testid="stHeader"], [data-testid="stHeader"] * {{ pointer-events:none !important; }}
    [data-testid="stHeader"] button, [data-testid="stHeader"] a {{ pointer-events:auto !important; }}
    .admin-hero {{
        position:relative; overflow:hidden; display:flex; justify-content:space-between;
        align-items:center; gap:28px; padding:30px 36px; margin-bottom:24px;
        border-radius:32px; color:white;
        background:linear-gradient(120deg,#172f86 0%,#285bd0 58%,#3b78ec 100%);
        box-shadow:0 20px 45px -25px rgba(18,48,122,.6);
    }}
    .admin-hero:after {{ content:""; position:absolute; width:360px; height:360px;
        right:-125px; top:-190px; border:1px solid rgba(255,255,255,.18); border-radius:50%; }}
    .admin-kicker {{ color:#a7f3e8; font-size:11px; font-weight:800;
        letter-spacing:1.7px; text-transform:uppercase; margin-bottom:8px; }}
    .admin-title {{ font-size:38px; line-height:1.05; font-weight:800; margin:0 0 9px; }}
    .admin-subtitle {{ color:rgba(255,255,255,.74); font-size:14px; margin:0; }}
    .admin-back {{ position:relative; z-index:2; display:inline-flex; align-items:center; gap:8px;
        padding:12px 18px; border-radius:999px; background:white; color:{AZUL_OSC} !important;
        text-decoration:none !important; font-size:13px; font-weight:800; white-space:nowrap; }}
    /* ── Inicio de sesion: panel de marca a la izquierda y tarjeta de acceso ── */
    /* Centra la composicion en la pantalla (unos 600 px de alto) */
    .login-espacio {{ height:max(12px, calc((100vh - 640px) / 2)); }}
    .login-panel {{
        position:relative; overflow:hidden; min-height:540px; padding:38px 40px 30px;
        display:flex; flex-direction:column; border-radius:32px; color:white;
        background:linear-gradient(140deg,#172f86 0%,#1f48b8 55%,#2f66e0 100%);
        box-shadow:0 30px 60px -34px rgba(18,48,122,.75);
    }}
    .login-panel:before {{ content:""; position:absolute; width:440px; height:440px; right:-190px; bottom:-230px;
        border:1px solid rgba(255,255,255,.16); border-radius:50%; box-shadow:0 0 0 70px rgba(255,255,255,.03); }}
    .login-logo svg {{ display:block; width:170px; height:auto; }}
    .login-ruta {{ position:absolute; top:34px; right:34px; width:190px; }}
    .login-kicker {{ position:relative; margin:38px 0 10px; color:#a7f3e8; font-size:11px; font-weight:800;
        letter-spacing:1.7px; text-transform:uppercase; }}
    .login-title {{ position:relative; margin:0 0 12px; color:#fff; font-size:36px; line-height:1.08;
        font-weight:800; letter-spacing:-.5px; }}
    .login-copy {{ position:relative; max-width:440px; margin:0; color:rgba(255,255,255,.8);
        font-size:14px; line-height:1.6; }}
    .login-lista {{ position:relative; list-style:none; margin:28px 0 0; padding:0; display:grid; gap:12px; }}
    .login-lista li {{ display:flex; align-items:center; gap:12px; margin:0; color:#eaf1ff;
        font-size:13px; font-weight:600; }}
    .login-lista span {{ width:30px; height:30px; flex-shrink:0; display:grid; place-items:center;
        border-radius:10px; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.2);
        color:{MENTA}; font-size:14px; font-weight:800; }}
    .login-pie {{ position:relative; margin-top:auto; padding-top:28px; color:rgba(255,255,255,.62);
        font-size:11px; letter-spacing:.3px; }}
    .st-key-admin_login_card {{
        padding:34px 34px 28px; background:#fff; border:1px solid {LINEA}; border-radius:28px;
        box-shadow:0 30px 60px -40px rgba(17,17,19,.55);
    }}
    .login-candado {{ width:48px; height:48px; display:grid; place-items:center; margin-bottom:16px;
        border-radius:15px; background:#eef3ff; }}
    .login-card-title {{ color:{TINTA}; font-size:24px; font-weight:800; letter-spacing:-.3px; margin-bottom:6px; }}
    .login-card-copy {{ color:{TENUE}; font-size:13px; line-height:1.55; margin-bottom:18px; }}
    .st-key-admin_login_card [data-testid="stTextInput"] input {{
        min-height:50px; background:#f7f9fc !important; border-radius:12px !important;
    }}
    .st-key-admin_login_card .stButton button {{ width:100%; min-height:50px; margin-top:4px; }}
    .login-volver {{ display:inline-block; margin-top:18px; color:{AZUL} !important; font-size:13px;
        font-weight:700; text-decoration:none !important; }}
    .login-volver:hover {{ text-decoration:underline !important; }}
    .section-title {{ margin:26px 0 12px; padding-left:12px; border-left:5px solid {MENTA};
        color:{TINTA}; font-size:18px; font-weight:800; letter-spacing:.2px; }}
    .status-card {{ background:white; border:1px solid {LINEA}; border-radius:24px;
        padding:20px 22px; box-shadow:0 12px 26px -20px rgba(17,17,19,.35); height:100%; }}
    .status-row {{ display:flex; align-items:center; justify-content:space-between; gap:14px; }}
    .status-title {{ color:{TINTA}; font-size:15px; font-weight:800; }}
    .status-copy {{ color:{TENUE}; font-size:12px; line-height:1.55; margin-top:7px; }}
    .status-pill {{ padding:6px 10px; border-radius:999px; font-size:11px; font-weight:800;
        letter-spacing:.5px; white-space:nowrap; }}
    .progress-track {{ background:#e7eefb; height:10px; border-radius:99px; overflow:hidden; margin:14px 0 8px; }}
    .progress-fill {{ height:100%; border-radius:99px; }}
    .quota-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }}
    .quota-card {{ background:white; border:1px solid {LINEA}; border-radius:24px; padding:20px 22px;
        box-shadow:inset 4px 0 0 var(--quota),0 12px 26px -20px rgba(17,17,19,.35); }}
    .quota-meta {{ display:flex; justify-content:space-between; color:{TENUE}; font-size:12px; }}
    .api-key-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
    .api-key-card {{ background:white; border:1px solid {LINEA}; border-radius:22px; padding:18px 20px;
        box-shadow:inset 4px 0 0 var(--key-color),0 12px 26px -20px rgba(17,17,19,.35); }}
    .api-key-id {{ color:{AZUL_OSC}; font-size:20px; font-weight:800; letter-spacing:.4px; }}
    .vps-keys-head {{ display:flex; align-items:baseline; gap:12px; margin:22px 0 4px;
        padding-bottom:8px; border-bottom:1px solid {LINEA}; }}
    .vps-keys-name {{ color:{AZUL_OSC}; font-size:18px; font-weight:800; }}
    .vps-keys-meta {{ color:{TENUE}; font-size:12px; }}
    .key-group-title {{ color:{TENUE}; font-size:11px; font-weight:800; letter-spacing:1px;
        text-transform:uppercase; margin:14px 0 8px; }}
    .api-key-service {{ color:{TENUE}; font-size:11px; margin-top:3px; }}
    .quick-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .quick-link {{ display:flex; align-items:center; gap:13px; border:1px solid {LINEA};
        border-radius:18px; padding:15px 16px; background:#fff; color:{TINTA} !important;
        text-decoration:none !important; transition:transform .15s,border-color .15s; }}
    .quick-link:hover {{ transform:translateY(-2px); border-color:#b9c9ef; }}
    .quick-icon {{ width:38px; height:38px; display:grid; place-items:center; border-radius:12px;
        background:#eef3ff; font-size:18px; }}
    .quick-title {{ font-size:13px; font-weight:800; }}
    .quick-copy {{ font-size:11px; color:{TENUE}; margin-top:2px; }}
    [data-testid="stMetric"] {{ background:#fff; border:1px solid {LINEA}; border-radius:24px;
        padding:17px 20px; box-shadow:0 12px 26px -20px rgba(17,17,19,.35); }}
    [data-testid="stMetricLabel"] {{ color:{TENUE} !important; font-weight:700; }}
    [data-testid="stMetricValue"] {{ color:{AZUL_OSC} !important; font-weight:800; }}
    [data-testid="stMetricDelta"] {{ color:{TENUE} !important; }}
    [data-testid="stMetricDelta"] svg {{ display:none !important; }}
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{ background:white; border:1px solid {LINEA};
        border-radius:999px; padding:6px; gap:4px; box-shadow:0 8px 24px -20px rgba(17,17,19,.5); }}
    [data-testid="stTabs"] button[role="tab"] {{ border-radius:999px; padding:10px 20px; }}
    [data-testid="stTabs"] button[aria-selected="true"] {{ background:#111113; color:white; }}
    [data-testid="stDataFrame"] {{ border:1px solid {LINEA}; border-radius:18px; overflow:hidden; }}
    div.stButton > button, div.stDownloadButton > button {{ border-radius:999px; font-weight:800; }}
    @media (max-width:760px) {{
        .block-container {{ padding-left:1rem; padding-right:1rem; }}
        .admin-hero {{ align-items:flex-start; flex-direction:column; padding:25px 24px; border-radius:26px; }}
        .admin-title {{ font-size:31px; }}
        /* En el celular el formulario debe verse sin hacer scroll: panel compacto */
        .login-espacio {{ height:12px; }}
        .login-panel {{ min-height:auto; padding:26px 24px; border-radius:24px; }}
        .login-kicker {{ margin-top:22px; }}
        .login-title {{ font-size:28px; }}
        .login-copy {{ font-size:13px; }}
        .login-ruta, .login-lista, .login-pie {{ display:none; }}
        .st-key-admin_login_card {{ padding:24px 22px; border-radius:22px; }}
        .quota-grid, .quick-grid, .api-key-grid {{ grid-template-columns:1fr; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# Logo UTB (blanco) para el panel de marca del inicio de sesion. El tamaño va
# por CSS: reemplazar width="183" tambien encoge su clipPath y corta el texto.
_RUTA_LOGO = DASHBOARD_DIR / "assets" / "utb-logo.svg"
LOGO_UTB = _RUTA_LOGO.read_text(encoding="utf-8") if _RUTA_LOGO.exists() else ""

def proteger_panel() -> None:
    """Pide la contraseña de ADMIN_PASSWORD; sin ella el panel queda cerrado."""
    esperada = os.environ.get("ADMIN_PASSWORD", "")
    if not esperada:
        # Falla cerrado: un despliegue sin la variable no debe dejar el panel
        # abierto en Internet (el dashboard publico lo enlaza en el pie).
        st.error(
            "Panel administrativo deshabilitado: falta configurar `ADMIN_PASSWORD` "
            "en el .env de este servidor."
        )
        st.stop()
    huella = huella_clave(esperada)
    if st.session_state.get("admin_auth") == huella:
        return
    st.markdown('<div class="login-espacio"></div>', unsafe_allow_html=True)
    _, izquierda, derecha, _ = st.columns(
        [0.05, 1.12, 0.9, 0.05], gap="large", vertical_alignment="center",
    )
    with izquierda:
        st.markdown(
            f"""
            <div class="login-panel">
                <div class="login-logo">{LOGO_UTB}</div>
                <svg class="login-ruta" viewBox="0 0 215 84" aria-hidden="true">
                    <path d="M8 62 C45 15, 74 74, 112 34 S169 12, 207 42" fill="none" stroke="rgba(255,255,255,.38)" stroke-width="2" stroke-linecap="round" stroke-dasharray="5 7"/>
                    <circle cx="10" cy="60" r="6" fill="#5eead4" stroke="rgba(255,255,255,.9)" stroke-width="2"/>
                    <circle cx="112" cy="34" r="5" fill="#ffffff" stroke="rgba(94,234,212,.8)" stroke-width="3"/>
                    <circle cx="205" cy="41" r="7" fill="#5eead4" stroke="rgba(255,255,255,.9)" stroke-width="2"/>
                </svg>
                <div class="login-kicker">Smart City Cartagena · Acceso protegido</div>
                <div class="login-title">Centro de control administrativo</div>
                <p class="login-copy">Consulta conexiones, cuotas, servidores y estado operativo
                    desde un espacio reservado para administradores.</p>
                <ul class="login-lista">
                    <li><span>✓</span>Verifica que la información de tráfico se guarde sin interrupciones</li>
                    <li><span>✓</span>Consulta cuánto del servicio de datos se ha usado este mes</li>
                    <li><span>✓</span>Detecta a tiempo cualquier falla en la recolección de datos</li>
                </ul>
                <div class="login-pie">Universidad Tecnológica de Bolívar · Monitoreo de tráfico urbano</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with derecha:
        with st.container(key="admin_login_card"):
            st.markdown(
                f"""
                <div class="login-candado">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="{AZUL}"
                         stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>
                    </svg>
                </div>
                <div class="login-card-title">Acceso administrativo</div>
                <div class="login-card-copy">Ingresa la contraseña de administrador para continuar.</div>
                """,
                unsafe_allow_html=True,
            )
            clave = st.text_input(
                "Contraseña",
                type="password",
                autocomplete="current-password",
                placeholder="Ingresa tu contraseña",
            )
            if st.button("Ingresar", type="primary", width="stretch"):
                if clave_valida(clave, esperada):
                    st.session_state["admin_auth"] = huella
                    st.rerun()
                st.error("Contraseña incorrecta.")
            st.markdown(
                '<a class="login-volver" href="/" target="_self">← Volver al tablero</a>',
                unsafe_allow_html=True,
            )
    st.stop()


def estado_cuota(usado: int, limite: int) -> tuple[str, str]:
    porcentaje = usado / limite if limite else 0
    if porcentaje >= .95:
        return ROJO, "CRÍTICO"
    if porcentaje >= .80:
        return NARANJA, "ALTO"
    if porcentaje >= .60:
        return AMBAR, "MODERADO"
    return VERDE, "Correcto"


def tarjeta_cuota(nombre: str, datos: dict) -> str:
    limite = config.LIMITE_API_DIARIO
    usado = int(datos["llamadas"])
    porcentaje = min(usado / limite, 1) if limite else 0
    color, estado = estado_cuota(usado, limite)
    restantes = max(limite - usado, 0)
    ultima = datos.get("ultima")
    ultima_txt = ultima.strftime("%d/%m %H:%M") if pd.notna(ultima) else "Sin ejecución"
    return (
        f'<div class="quota-card" style="--quota:{color}">'
        f'<div class="status-row"><div class="status-title">{texto_html(nombre)} · TomTom API</div>'
        f'<span class="status-pill" style="background:{color}18;color:{color}">{estado}</span></div>'
        f'<div class="progress-track"><div class="progress-fill" '
        f'style="width:{porcentaje*100:.1f}%;background:{color}"></div></div>'
        f'<div class="quota-meta"><span>{usado:,} / {limite:,} llamadas</span>'
        f'<span>{restantes:,} restantes</span></div>'
        f'<div class="status-copy">{datos["ejecuciones"]} ejecuciones hoy · '
        f'última: {ultima_txt} · {datos["fallidas"]:,} fallidas</div></div>'
    )


# Motivo de descarte del ETL (rotacion_llaves) en palabras para el panel
MOTIVOS_AGOTADA = {
    "sin_creditos": "sin saldo en TomTom",
    "bloqueada": "rechazada por TomTom",
    "limite": "límite de consultas por minuto",
}


def tarjeta_api_key(datos: dict) -> str:
    """Tarjeta de una llave TomTom: estado y consumo del mes frente a su limite."""
    pct = datos.get("pct")
    estado = datos["estado"]
    if estado == "AGOTADA":
        color = ROJO
    elif pct is not None and pct >= 80:
        color = NARANJA
    elif estado == "RESERVA":
        color = AZUL
    else:
        color = VERDE
    # El papel configurado (principal o reserva) no cambia; el grupo y la
    # etiqueta muestran su uso real en este momento
    rol = "Llave principal" if datos["tipo"] == "principal" else "Llave de reserva"
    if estado == "EN USO" and datos["tipo"] == "reserva":
        rol += " · cubre a las principales agotadas"
    progreso = min(float(pct), 100) if pct is not None else 0
    limite = f"{pct:.1f}% del límite mensual" if pct is not None else "Sin límite configurado"
    identificador = texto_html(datos["identificador"])
    if datos.get("agotada"):
        # agotada_desde es el ultimo descarte: el ETL la reprueba cada pocas
        # horas y lo actualiza, asi que no marca desde cuando esta agotada
        motivo = MOTIVOS_AGOTADA.get(datos.get("motivo"), "sin saldo")
        intento = datos.get("agotada_desde")
        try:
            intento = datetime.strptime(str(intento), "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        except ValueError:
            intento = None
        detalle = motivo[:1].upper() + motivo[1:] + (f" · último intento {intento}" if intento else "")
    else:
        detalle = f"Último uso: {datos['ultima_vez']}"
    return (
        f'<div class="api-key-card" style="--key-color:{color}">'
        f'<div class="status-row"><div><div class="api-key-id">ID · {identificador}</div>'
        f'<div class="api-key-service">TomTom Traffic Flow · {texto_html(rol)}</div></div>'
        f'<span class="status-pill" style="background:{color}18;color:{color}">{estado}</span></div>'
        f'<div class="progress-track"><div class="progress-fill" style="width:{progreso:.1f}%;background:{color}"></div></div>'
        f'<div class="quota-meta"><span>{datos["consumo"]:,} / {datos["cuota"]:,} llamadas</span><span>{limite}</span></div>'
        f'<div class="status-copy">{texto_html(detalle)}</div></div>'
    )


proteger_panel()

st.markdown(
    f"""
    <div class="admin-hero">
        <div>
            <div class="admin-kicker">Centro de control operativo</div>
            <h1 class="admin-title">Panel administrativo</h1>
            <p class="admin-subtitle">Conexiones, infraestructura, cuotas y salud del sistema.</p>
        </div>
        <a class="admin-back" href="/" target="_self">← Volver al tablero</a>
    </div>
    """,
    unsafe_allow_html=True,
)

# El primer render solo usa PostgreSQL agregado y archivos locales. Consultar
# Drive y la metadata de cada Sheet aqui hacia que el formulario de acceso
# quedara atenuado durante varios segundos despues de ingresar la contraseña.
with st.spinner("Cargando monitor operativo..."):
    ejecuciones, fuente_ejecuciones = servicios.cargar_ejecuciones_recientes(7)
    resumen = servicios.resumen_operativo_ejecuciones(ejecuciones)
    api_keys = servicios.estado_api_keys()

# Google se comprueba por cron tres veces al dia. El panel solo lee el ultimo
# resultado persistido: no hace llamadas externas ni retrasa el ingreso.
estado_google_guardado = servicios.cargar_estado_google()
google = estado_google_guardado["google"]
sheets = estado_google_guardado["sheets"]
google_actualizado = estado_google_guardado.get("actualizado")
try:
    google_actualizado_dt = datetime.fromisoformat(google_actualizado)
    google_revision = google_actualizado_dt.strftime("%d/%m %H:%M")
except (TypeError, ValueError):
    google_revision = "pendiente automática"
sheet = servicios.capacidad_sheet(sheets) if sheets.get("ok") else {}

proxima = servicios.proxima_ejecucion()
ultima = resumen["ultima"]

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Google", google["estado"], google_revision, delta_color="off")
with m2:
    st.metric("Ejecuciones hoy", resumen["ejecuciones"], "28 programadas", delta_color="off")
with m3:
    st.metric(
        "Última ejecución",
        ultima.strftime("%H:%M") if pd.notna(ultima) else "—",
        ultima.strftime("%d/%m/%Y") if pd.notna(ultima) else "Sin datos",
        delta_color="off",
    )
with m4:
    st.metric(
        "Próxima ejecución",
        proxima.strftime("%H:%M") if proxima else "—",
        proxima.strftime("%d/%m/%Y") if proxima else "Sin programación",
        delta_color="off",
    )

tab_resumen, tab_ejecuciones, tab_diagnostico = st.tabs(
    ["Resumen operativo", "Ejecuciones y errores", "Diagnóstico"]
)

with tab_resumen:
    izquierda, derecha = st.columns([1.35, 1])
    with izquierda:
        st.markdown('<div class="section-title">Servicios conectados</div>', unsafe_allow_html=True)
        color_google = VERDE if google["ok"] is True else (ROJO if google["ok"] is False else AMBAR)
        estado_google = texto_html(google["estado"])
        detalle_google = texto_html(
            f"{google['detalle']} Última verificación: {google_revision}."
        )
        st.markdown(
            f"""
            <div class="status-card">
                <div class="status-row">
                    <div class="status-title">Conexión con Google</div>
                    <span class="status-pill" style="background:{color_google}18;color:{color_google}">{estado_google}</span>
                </div>
                <div class="status-copy">{detalle_google}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if sheets.get("ok"):
            for libro in sheets.get("partes", []):
                porcentaje_sheet = min(float(libro["pct"]), 100)
                color_sheet = ROJO if porcentaje_sheet >= 90 else (NARANJA if porcentaje_sheet >= 75 else VERDE)
                proyeccion = (
                    f"Rotación estimada: {libro['fecha_llena']} · {libro['dias']} días"
                    if libro.get("dias") is not None and libro.get("activa")
                    else "Libro histórico; solo lectura"
                )
                etiqueta = "ACTIVA" if libro.get("activa") else f"{porcentaje_sheet:.1f}%"
                parte = texto_html(libro["parte"])
                nombre_libro = texto_html(libro["nombre"])
                proyeccion_html = texto_html(proyeccion)
                st.markdown(
                    f"""
                    <div class="status-card">
                        <div class="status-row">
                            <div class="status-title">Google Sheets · Parte {parte}</div>
                            <span class="status-pill" style="background:{color_sheet}18;color:{color_sheet}">{etiqueta}</span>
                        </div>
                        <div class="progress-track"><div class="progress-fill" style="width:{porcentaje_sheet:.1f}%;background:{color_sheet}"></div></div>
                        <div class="quota-meta"><span>{libro['celdas']:,} celdas asignadas</span><span>{porcentaje_sheet:.1f}% de {libro['limite']:,}</span></div>
                        <div class="status-copy">{nombre_libro} · {libro['filas']:,} filas × {libro['columnas']} columnas · {proyeccion_html}</div>
                    </div>
                    <div style="height:12px"></div>
                    """,
                    unsafe_allow_html=True,
                )
            if sheets.get("errores"):
                st.warning("Algunas partes no pudieron consultarse: " + " · ".join(sheets["errores"]))
        elif google.get("ok") is False:
            st.error(f"No se pudo consultar la capacidad de Sheets: {sheets.get('detalle', 'Sin detalle')}")
        else:
            st.info(
                "La verificación automática de Google se ejecuta a las "
                "06:15, 14:15 y 22:15."
            )

    with derecha:
        st.markdown('<div class="section-title">Accesos rápidos</div>', unsafe_allow_html=True)
        drive_id = quote(str(config.DRIVE_FOLDER_ID), safe="")
        drive_url = f"https://drive.google.com/drive/folders/{drive_id}"
        # Un acceso por libro del historico (Parte 1, Parte 2, ...); si Drive
        # no responde, al menos el libro activo
        libros = [
            (libro["parte"], libro["sheet_id"], libro.get("activa"))
            for libro in sheets.get("partes", []) if libro.get("sheet_id")
        ] or [(None, sheet.get("sheet_id", config.SHEET_ID), True)]
        enlaces_sheets = "".join(
            f'<a class="quick-link" href="https://docs.google.com/spreadsheets/d/{quote(str(sheet_id), safe="")}" '
            f'target="_blank" rel="noopener noreferrer">'
            f'<span class="quick-icon">📊</span><span><div class="quick-title">Google Sheets'
            f'{f" · Parte {texto_html(parte)}" if parte else ""}</div><div class="quick-copy">'
            f'{"Libro activo de mediciones" if activa else "Libro histórico (solo lectura)"}</div></span></a>'
            for parte, sheet_id, activa in libros
        )
        st.markdown(
            f"""
            <div class="quick-grid">
                <a class="quick-link" href="{drive_url}" target="_blank" rel="noopener noreferrer">
                    <span class="quick-icon">📁</span><span><div class="quick-title">Google Drive</div><div class="quick-copy">Archivos CSV y respaldos</div></span>
                </a>
                {enlaces_sheets}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="section-title">Acciones seguras</div>', unsafe_allow_html=True)
        if st.button("↻ Actualizar monitor operativo", width="stretch", type="primary"):
            servicios.cargar_logs.clear()
            servicios.cargar_ejecuciones_recientes.clear()
            servicios.estado_api_keys.clear()
            st.rerun()
        diagnostico_json = json.dumps(
            {
                "generado": datetime.now().isoformat(timespec="seconds"),
                "google_actualizado": google_actualizado,
                "google": google,
                "sheets": [
                    {k: v for k, v in libro.items() if k != "sheet_id"}
                    for libro in sheets.get("partes", [])
                ],
                "api_keys": api_keys,
                "operacion": {
                    "vps1": {k: str(v) for k, v in resumen["vps1"].items()},
                    "vps2": {k: str(v) for k, v in resumen["vps2"].items()},
                },
                "configuracion": servicios.diagnostico_configuracion(),
            },
            ensure_ascii=False,
            indent=2,
        )
        st.download_button(
            "Descargar diagnóstico JSON",
            diagnostico_json.encode("utf-8"),
            file_name=f"diagnostico_{datetime.now():%Y%m%d_%H%M%S}.json",
            mime="application/json",
            width="stretch",
        )

    st.markdown('<div class="section-title">Cuota diaria de la API TomTom</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="quota-grid">'
        + tarjeta_cuota("VPS 1", resumen["vps1"])
        + tarjeta_cuota("VPS 2", resumen["vps2"])
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Llaves de la API de TomTom por servidor</div>', unsafe_allow_html=True)
    if not api_keys["vps"]:
        st.warning(
            "No hay estado de llaves publicado ni llaves en este servidor"
            + (f" ({api_keys['error']})." if api_keys.get("error") else ".")
        )
    for vps in api_keys["vps"]:
        turnos = " y ".join(vps["turnos"]) if vps["turnos"] else "sin turnos asignados"
        vps_id = texto_html(vps["vps_id"])
        turnos_html = texto_html(turnos)
        actualizado = texto_html(vps["actualizado"])
        st.markdown(
            f'<div class="vps-keys-head"><span class="vps-keys-name">VPS {vps_id}</span>'
            f'<span class="vps-keys-meta">{turnos_html} · actualizado {actualizado}</span></div>',
            unsafe_allow_html=True,
        )
        if not vps["en_uso"]:
            st.error(f"VPS {vps['vps_id']}: ninguna llave tiene saldo. Las corridas fallarán hasta que alguna se recargue.")
        elif vps["usando_reserva"]:
            st.warning(
                f"VPS {vps['vps_id']} funciona con llaves de reserva: sus llaves principales "
                "se quedaron sin saldo. Vuelven a usarse solas cuando TomTom las recargue."
            )
        for grupo, titulo in (("en_uso", "En uso"), ("reserva", "Reserva")):
            if vps[grupo]:
                st.markdown(
                    f'<div class="key-group-title">{titulo} · {len(vps[grupo])}</div>'
                    '<div class="api-key-grid">'
                    + "".join(tarjeta_api_key(datos) for datos in vps[grupo])
                    + "</div>",
                    unsafe_allow_html=True,
                )

    st.markdown('<div class="section-title">Horarios y responsables</div>', unsafe_allow_html=True)
    horarios = []
    for vps, turnos in config.VPS_TURNOS.items():
        for turno in turnos:
            horarios.append({
                "VPS": f"VPS {vps}",
                "Turno": turno,
                "Ejecuciones": len(config.HORARIOS.get(turno, [])),
                "Horarios": " · ".join(config.HORARIOS.get(turno, [])),
            })
    st.dataframe(pd.DataFrame(horarios), width="stretch", hide_index=True)

with tab_ejecuciones:
    st.markdown('<div class="section-title">Monitor del proceso</div>', unsafe_allow_html=True)
    st.caption(
        f"Ventana móvil de 7 días · Fuente: {fuente_ejecuciones}. "
        "Una ejecución agrupa todos los nodos consultados por un VPS en el mismo instante."
    )

    errores = servicios.errores_recientes(ejecuciones, 7)
    total_parciales = int((errores["estado"] == "PARCIAL").sum()) if not errores.empty else 0
    total_fallidas = int((errores["estado"] == "ERROR").sum()) if not errores.empty else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Ejecuciones · 7 días", len(ejecuciones))
    k2.metric("Parciales · 7 días", total_parciales)
    k3.metric("Fallidas · 7 días", total_fallidas)

    st.markdown(
        '<div class="section-title">Últimas 20 ejecuciones por VPS</div>',
        unsafe_allow_html=True,
    )
    tab_vps1, tab_vps2 = st.tabs(["VPS 1", "VPS 2"])
    for contenedor, vps_id in ((tab_vps1, "1"), (tab_vps2, "2")):
        with contenedor:
            recientes = servicios.ultimas_ejecuciones(ejecuciones, vps_id, 20)
            if recientes.empty:
                st.info(f"No hay ejecuciones del VPS {vps_id} en los últimos 7 días.")
                continue
            tabla = recientes.rename(columns={
                "timestamp": "Fecha y hora",
                "total_nodos": "Nodos",
                "consultas_ok": "Correctas",
                "consultas_error": "Fallidas",
                "estado": "Estado",
                "error": "Detalle",
            })[["Fecha y hora", "Nodos", "Correctas", "Fallidas", "Estado", "Detalle"]]
            st.dataframe(
                tabla,
                width="stretch",
                hide_index=True,
                column_config={
                    "Fecha y hora": st.column_config.DatetimeColumn(
                        "Fecha y hora", format="DD/MM/YYYY HH:mm:ss"
                    ),
                    "Detalle": st.column_config.TextColumn("Detalle", width="large"),
                },
            )

    if not ejecuciones.empty:
        st.download_button(
            "Descargar ejecuciones de los últimos 7 días",
            ejecuciones.sort_values("timestamp", ascending=False).to_csv(index=False).encode("utf-8"),
            file_name=f"ejecuciones_7_dias_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
        )

    st.markdown(
        '<div class="section-title">Ejecuciones por hora · últimos 7 días</div>',
        unsafe_allow_html=True,
    )
    por_hora = servicios.ejecuciones_por_hora(ejecuciones, 7)
    if por_hora.empty:
        st.info("No hay datos suficientes para construir el gráfico por hora.")
    else:
        # Horas del cron (sin la franja 01-03, que nunca tiene corridas) mas
        # cualquier hora con una corrida fuera de horario, que si interesa ver,
        # en orden de dia operativo: 04:00 ... 23:00, 00:00. Una hora
        # programada sin barras sigue apareciendo vacia: es la alerta.
        horas_eje = sorted(
            {f"{hora:02d}:00" for hora in horario.HORAS} | set(por_hora["hora"]),
            key=lambda etiqueta: horario.orden_hora(int(etiqueta[:2])),
        )
        figura = go.Figure()
        figura.add_bar(
            x=por_hora["hora"], y=por_hora["completas"],
            name="Completas", marker_color=VERDE,
            hovertemplate="%{x}<br>Completas: %{y}<extra></extra>",
        )
        figura.add_bar(
            x=por_hora["hora"], y=por_hora["parciales"],
            name="Parciales", marker_color=AMBAR,
            hovertemplate="%{x}<br>Parciales: %{y}<extra></extra>",
        )
        figura.add_bar(
            x=por_hora["hora"], y=por_hora["fallidas"],
            name="Fallidas", marker_color=ROJO,
            hovertemplate="%{x}<br>Fallidas: %{y}<extra></extra>",
        )
        figura.update_layout(
            barmode="stack",
            height=360,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color=AZUL_OSC,
            margin=dict(l=20, r=20, t=30, b=45),
            xaxis=dict(
                title="Hora del día",
                categoryorder="array",
                categoryarray=horas_eje,
                gridcolor="#e3eaf7",
            ),
            # automargin: con margen fijo el titulo se encimaba con los numeros
            yaxis=dict(
                title="Número de ejecuciones", gridcolor="#e3eaf7", dtick=1, automargin=True,
            ),
            legend=dict(orientation="h", y=1.12, x=0),
            hovermode="x unified",
        )
        st.plotly_chart(
            figura,
            width="stretch",
            theme=None,
            config={"displayModeBar": False},
        )

    st.markdown(
        '<div class="section-title">Errores de los últimos 7 días</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Incluye fallos totales del proceso y ejecuciones parciales con uno o más nodos fallidos."
    )
    if errores.empty:
        st.success("Sin errores ni ejecuciones parciales durante los últimos 7 días.")
    else:
        tabla_errores = errores.rename(columns={
            "timestamp": "Fecha y hora",
            "vps_id": "VPS",
            "consultas_ok": "Correctas",
            "consultas_error": "Nodos fallidos",
            "estado": "Estado",
            "error": "Detalle",
        })[["Fecha y hora", "VPS", "Estado", "Correctas", "Nodos fallidos", "Detalle"]]
        st.dataframe(
            tabla_errores,
            width="stretch",
            hide_index=True,
            column_config={
                "Fecha y hora": st.column_config.DatetimeColumn(
                    "Fecha y hora", format="DD/MM/YYYY HH:mm:ss"
                ),
                "Detalle": st.column_config.TextColumn("Detalle", width="large"),
            },
        )

with tab_diagnostico:
    st.markdown('<div class="section-title">Configuración y servicios</div>', unsafe_allow_html=True)
    configuracion = servicios.diagnostico_configuracion()
    tabla_config = pd.DataFrame([
        {
            "Componente": clave,
            "Estado": ("Sí" if valor else "No") if isinstance(valor, bool) else str(valor),
        }
        for clave, valor in configuracion.items()
    ])
    st.dataframe(tabla_config, width="stretch", hide_index=True)

    c_db, c_archivos = st.columns([1, 1.4])
    with c_db:
        st.markdown('<div class="section-title">PostgreSQL</div>', unsafe_allow_html=True)
        st.caption("La prueba es de solo lectura y no modifica la base de datos.")
        if st.button("Probar conexión PostgreSQL", width="stretch"):
            resultado_db = servicios.probar_postgresql()
            if resultado_db["ok"]:
                st.success(resultado_db["detalle"])
                st.caption(f"Rango: {resultado_db['desde']} → {resultado_db['hasta']}")
            else:
                st.error(f"Conexión no disponible: {resultado_db['detalle']}")

    with c_archivos:
        st.markdown('<div class="section-title">Archivos recientes</div>', unsafe_allow_html=True)
        archivos = servicios.archivos_recientes()
        if archivos.empty:
            st.info("No hay archivos CSV locales.")
        else:
            st.dataframe(archivos, width="stretch", hide_index=True)
