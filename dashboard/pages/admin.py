"""Panel administrativo de Smart City Cartagena."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DASHBOARD_DIR.parent
sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import admin_services as servicios  # noqa: E402
import config  # noqa: E402


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
    .admin-login-hero {{
        position:relative; overflow:hidden; max-width:760px; margin:42px auto 22px;
        padding:30px 34px; border-radius:28px; color:white;
        background:linear-gradient(125deg,#172f86 0%,#285bd0 62%,#3b78ec 100%);
        box-shadow:0 24px 55px -32px rgba(18,48,122,.72);
    }}
    .admin-login-hero:after {{ content:""; position:absolute; width:250px; height:250px;
        right:-85px; top:-145px; border:1px solid rgba(255,255,255,.2); border-radius:50%; }}
    .admin-login-badge {{ color:#a7f3e8; font-size:10px; font-weight:800;
        letter-spacing:1.6px; text-transform:uppercase; margin-bottom:10px; }}
    .admin-login-title {{ position:relative; z-index:1; margin:0 0 7px;
        color:#fff; font-size:31px; line-height:1.1; font-weight:800; }}
    .admin-login-copy {{ position:relative; z-index:1; max-width:570px; margin:0;
        color:rgba(255,255,255,.74); font-size:13px; line-height:1.55; }}
    .st-key-admin_login_card {{
        padding:22px 24px 24px;
        background:#fff;
        border:1px solid {LINEA};
        border-radius:24px;
        box-shadow:0 20px 46px -34px rgba(17,17,19,.6);
    }}
    .login-card-title {{ color:{TINTA}; font-size:18px; font-weight:800; margin-bottom:4px; }}
    .login-card-copy {{ color:{TENUE}; font-size:12px; line-height:1.5; margin-bottom:12px; }}
    .st-key-admin_login_card [data-testid="stTextInput"] {{ margin-top:4px; }}
    .st-key-admin_login_card [data-testid="stTextInput"] input {{
        min-height:48px; background:#f7f9fc !important; border-radius:12px !important;
    }}
    .st-key-admin_login_card .stButton button {{ width:100%; min-height:46px; }}
    .section-title {{ margin:26px 0 12px; padding-left:12px; border-left:5px solid {MENTA};
        color:{TINTA}; font-size:18px; font-weight:800; letter-spacing:.2px; }}
    .status-card, .admin-card {{ background:white; border:1px solid {LINEA}; border-radius:24px;
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
        .admin-login-hero {{ margin-top:16px; padding:25px 24px; border-radius:24px; }}
        .admin-login-title {{ font-size:27px; }}
        .st-key-admin_login_card {{ padding:18px; border-radius:20px; }}
        .quota-grid, .quick-grid, .api-key-grid {{ grid-template-columns:1fr; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


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
    huella = hashlib.sha256(esperada.encode("utf-8")).hexdigest()
    if st.session_state.get("admin_auth") == huella:
        return
    st.markdown(
        """
        <div class="admin-login-hero">
            <div class="admin-login-badge">Smart City Cartagena · Acceso protegido</div>
            <div class="admin-login-title">Centro de control administrativo</div>
            <p class="admin-login-copy">Consulta conexiones, cuotas, servidores y estado operativo desde un espacio reservado para administradores.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, columna_acceso, _ = st.columns([1, 1.25, 1])
    with columna_acceso:
        with st.container(key="admin_login_card"):
            st.markdown(
                """
                <div class="login-card-title">Acceso administrativo</div>
                <div class="login-card-copy">Ingresa la contraseña temporal. La verificación con Google se habilitará como segundo factor.</div>
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
                if hmac.compare_digest(clave, esperada):
                    st.session_state["admin_auth"] = huella
                    st.rerun()
                st.error("Contraseña incorrecta.")
    st.stop()


def estado_cuota(usado: int, limite: int) -> tuple[str, str]:
    porcentaje = usado / limite if limite else 0
    if porcentaje >= .95:
        return ROJO, "CRÍTICO"
    if porcentaje >= .80:
        return NARANJA, "ALTO"
    if porcentaje >= .60:
        return AMBAR, "MODERADO"
    return VERDE, "OK"


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
        f'<div class="status-row"><div class="status-title">{nombre} · TomTom API</div>'
        f'<span class="status-pill" style="background:{color}18;color:{color}">{estado}</span></div>'
        f'<div class="progress-track"><div class="progress-fill" '
        f'style="width:{porcentaje*100:.1f}%;background:{color}"></div></div>'
        f'<div class="quota-meta"><span>{usado:,} / {limite:,} llamadas</span>'
        f'<span>{restantes:,} restantes</span></div>'
        f'<div class="status-copy">{datos["ejecuciones"]} ejecuciones hoy · '
        f'última: {ultima_txt} · {datos["fallidas"]:,} fallidas</div></div>'
    )


def tarjeta_api_key(datos: dict) -> str:
    pct = datos.get("pct")
    consumo_hoy = datos.get("consumo_hoy")
    estado = datos.get("estado", "CONFIGURADA")
    if estado == "AGOTADA":
        color = ROJO
    elif pct is not None and pct >= 80:
        color = NARANJA
    elif datos.get("servicio", "").startswith("Google"):
        color = AZUL
    else:
        color = VERDE
    if pct is None:
        uso = (
            f"{consumo_hoy:,} llamadas hoy"
            if consumo_hoy is not None else "Telemetría no disponible"
        )
        progreso = 0
        cuota = (
            "Requiere Cloud Monitoring"
            if datos.get("servicio", "").startswith("Google")
            else "Mensual no sincronizado"
        )
    else:
        progreso = min(float(pct), 100)
        uso = f"{datos['consumo']:,} / {datos['cuota']:,} llamadas"
        cuota = f"{pct:.1f}% de la cuota mensual"
    uso_hoy = (
        f" · Hoy: {consumo_hoy:,}"
        if consumo_hoy is not None and pct is not None else ""
    )
    return (
        f'<div class="api-key-card" style="--key-color:{color}">'
        f'<div class="status-row"><div><div class="api-key-id">ID · {datos["identificador"]}</div>'
        f'<div class="api-key-service">{datos["servicio"]} · {datos["proposito"]}</div></div>'
        f'<span class="status-pill" style="background:{color}18;color:{color}">{estado}</span></div>'
        f'<div class="progress-track"><div class="progress-fill" style="width:{progreso:.1f}%;background:{color}"></div></div>'
        f'<div class="quota-meta"><span>{uso}</span><span>{cuota}</span></div>'
        f'<div class="status-copy">Último uso: {datos["ultima_vez"]}{uso_hoy} · {datos["detalle"]}</div></div>'
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
        <a class="admin-back" href="/" target="_self">← Volver al dashboard</a>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.spinner("Actualizando estado operativo..."):
    logs = servicios.cargar_logs()
    mediciones, fuente_mediciones = servicios.cargar_mediciones_recientes(1)
    resumen = servicios.resumen_operativo(logs, mediciones)
    ejecuciones = servicios.combinar_ejecuciones(logs, mediciones)
    google = servicios.verificar_google()
    sheets = servicios.capacidad_sheets()
    sheet = servicios.capacidad_sheet(sheets)
    api_keys = servicios.estado_api_keys(mediciones)

proxima = servicios.proxima_ejecucion()
ultima = resumen["ultima"]

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Google", google["estado"], "Drive + Sheets", delta_color="off")
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
        color_google = VERDE if google["ok"] else ROJO
        st.markdown(
            f"""
            <div class="status-card">
                <div class="status-row">
                    <div class="status-title">Conexión con Google</div>
                    <span class="status-pill" style="background:{color_google}18;color:{color_google}">{google['estado']}</span>
                </div>
                <div class="status-copy">{google['detalle']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
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
                st.markdown(
                    f"""
                    <div class="status-card">
                        <div class="status-row">
                            <div class="status-title">Google Sheets · Parte {libro['parte']}</div>
                            <span class="status-pill" style="background:{color_sheet}18;color:{color_sheet}">{etiqueta}</span>
                        </div>
                        <div class="progress-track"><div class="progress-fill" style="width:{porcentaje_sheet:.1f}%;background:{color_sheet}"></div></div>
                        <div class="quota-meta"><span>{libro['celdas']:,} celdas asignadas</span><span>{porcentaje_sheet:.1f}% de {libro['limite']:,}</span></div>
                        <div class="status-copy">{libro['nombre']} · {libro['filas']:,} filas × {libro['columnas']} columnas · {proyeccion}</div>
                    </div>
                    <div style="height:12px"></div>
                    """,
                    unsafe_allow_html=True,
                )
            if sheets.get("errores"):
                st.warning("Algunas partes no pudieron consultarse: " + " · ".join(sheets["errores"]))
        else:
            st.error(f"No se pudo consultar la capacidad de Sheets: {sheets.get('detalle', 'Sin detalle')}")

    with derecha:
        st.markdown('<div class="section-title">Accesos rápidos</div>', unsafe_allow_html=True)
        drive_url = f"https://drive.google.com/drive/folders/{config.DRIVE_FOLDER_ID}"
        sheet_id = sheet.get("sheet_id", config.SHEET_ID)
        sheets_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        st.markdown(
            f"""
            <div class="quick-grid">
                <a class="quick-link" href="{drive_url}" target="_blank">
                    <span class="quick-icon">📁</span><span><div class="quick-title">Google Drive</div><div class="quick-copy">Archivos CSV y respaldos</div></span>
                </a>
                <a class="quick-link" href="{sheets_url}" target="_blank">
                    <span class="quick-icon">📊</span><span><div class="quick-title">Google Sheets</div><div class="quick-copy">Libro activo de mediciones</div></span>
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="section-title">Acciones seguras</div>', unsafe_allow_html=True)
        if st.button("↻ Actualizar todos los indicadores", width="stretch", type="primary"):
            st.cache_data.clear()
            st.rerun()
        diagnostico_json = json.dumps(
            {
                "generado": datetime.now().isoformat(timespec="seconds"),
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

    st.markdown('<div class="section-title">API keys configuradas y consumo mensual</div>', unsafe_allow_html=True)
    st.caption(
        f"Periodo {api_keys['mes']} · Se muestran IDs de seguimiento, nunca las claves completas. "
        "El uso de hoy sale de Google Sheets; el mensual se toma del estado de cada VPS cuando está sincronizado."
    )
    if api_keys.get("sin_identificar"):
        st.info(
            f"{api_keys['sin_identificar']:,} llamadas de hoy pertenecen a registros antiguos "
            "que todavía no incluían el ID de la clave."
        )
    if api_keys.get("claves"):
        st.markdown(
            '<div class="api-key-grid">'
            + "".join(tarjeta_api_key(datos) for datos in api_keys["claves"])
            + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.warning("No hay API keys cargadas en este entorno.")

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
    st.caption(f"VPS 1 desde el log local · VPS 2 reconstruido desde {fuente_mediciones}")
    if ejecuciones.empty:
        st.info("No hay ejecuciones registradas.")
    else:
        columnas_visibles = [
            columna for columna in [
                "timestamp", "vps_id", "total_nodos", "consultas_ok",
                "consultas_error", "estado", "error",
            ] if columna in ejecuciones.columns
        ]
        recientes = ejecuciones.tail(30).sort_values("timestamp", ascending=False)
        st.dataframe(recientes[columnas_visibles], width="stretch", hide_index=True)
        st.download_button(
            "Descargar registro de ejecuciones",
            ejecuciones.to_csv(index=False).encode("utf-8"),
            file_name=f"ejecuciones_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
        )

        hoy = datetime.now().date()
        ejecuciones_hoy = ejecuciones[ejecuciones["timestamp"].dt.date == hoy].copy()
        if not ejecuciones_hoy.empty:
            ejecuciones_hoy["hora"] = ejecuciones_hoy["timestamp"].dt.strftime("%H:%M")
            por_hora = ejecuciones_hoy.groupby("hora").agg(
                consultas_ok=("consultas_ok", "sum"),
                consultas_error=("consultas_error", "sum"),
            ).reset_index()
            figura = go.Figure()
            figura.add_bar(
                x=por_hora["hora"], y=por_hora["consultas_ok"],
                name="Correctas", marker_color=VERDE,
            )
            figura.add_bar(
                x=por_hora["hora"], y=por_hora["consultas_error"],
                name="Fallidas", marker_color=ROJO,
            )
            figura.update_layout(
                barmode="stack", height=320, paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", font_color=AZUL_OSC,
                margin=dict(l=20, r=20, t=40, b=35),
                xaxis=dict(title="Hora", gridcolor="#e3eaf7"),
                yaxis=dict(title="Consultas", gridcolor="#e3eaf7"),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(figura, theme=None, config={"displayModeBar": False})

        desde = datetime.now() - timedelta(days=7)
        errores = ejecuciones[
            (ejecuciones["timestamp"] >= desde)
            & (ejecuciones["estado"].astype(str).str.upper() == "ERROR")
        ]
        st.markdown('<div class="section-title">Errores de los últimos 7 días</div>', unsafe_allow_html=True)
        if errores.empty:
            st.success("Sin errores registrados durante los últimos 7 días.")
        else:
            st.dataframe(errores.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)

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

    st.markdown('<div class="section-title">Funciones administrativas disponibles</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="admin-card">
            <b>Incluidas ahora</b><br><br>
            • Estado de Google Drive y Sheets.<br>
            • Capacidad y rotación del libro activo.<br>
            • Cuota diaria TomTom por VPS.<br>
            • Ejecuciones, errores y descarga de registros.<br>
            • Horarios asignados por servidor.<br>
            • Diagnóstico de PostgreSQL, archivos y configuración.<br>
            • Actualización manual de indicadores sin ejecutar nuevas llamadas a TomTom.<br><br>
            <b>Siguiente etapa recomendada</b><br><br>
            Gestión de usuarios y roles, alertas automáticas, rotación asistida de llaves y
            ejecución manual del ETL con confirmación y auditoría.
        </div>
        """,
        unsafe_allow_html=True,
    )
