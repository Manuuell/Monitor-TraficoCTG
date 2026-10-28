"""
Mapa de solo nodos: filtros, ventana emergente y mapa Folium.

Seccion 2 del documento "Arquitectura y visualizacion del proyecto". El panel
de filtros usa un prefijo en sus claves de session_state para poder repetirlo
en las secciones que aplican los mismos filtros (red de nodos, analisis
temporal) sin que los widgets choquen entre si.
"""
import html
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from branca.element import MacroElement
from folium.elements import JSCSSMixin
from folium.plugins import Fullscreen
from jinja2 import Template

import config
import horario

# ============================================================
# OPCIONES DE LOS FILTROS (tal como las define el documento)
# ============================================================
METRICAS = {
    "Velocidad de circulación (km/h)": "vel_actual",
    "Velocidad de flujo libre (km/h)": "vel_libre",
    "Ratio (Índice de fluidez)": "ratio",
}

TODO_EL_DIA = "Todo el día (4:00 – 0:00)"
PERSONALIZADO = "Personalizado"
# Rangos de corridas del cron (desde, hasta), sin huecos ni solapes. Las horas
# pico son las de las corridas extra de media hora: 5:30-7:30 en la manana,
# 12:00-13:30 al medio dia y 17:00-18:30 en la tarde.
FRANJAS = {
    TODO_EL_DIA:                    horario.DIA_COMPLETO,
    PERSONALIZADO:                  None,      # rango libre con la barra de horas
    "Madrugada (4:00–5:00)":        ("04:00", "05:00"),
    "Hora pico AM (5:30–7:30)":     ("05:30", "07:30"),
    "Mañana (8:00–11:00)":          ("08:00", "11:00"),
    "Medio día (12:00–13:30)":      ("12:00", "13:30"),
    "Tarde (14:00–16:00)":          ("14:00", "16:00"),
    "Hora pico PM (17:00–18:30)":   ("17:00", "18:30"),
    "Noche (19:00–0:00)":           ("19:00", "00:00"),
}

# El indice de cada mes es su numero (1-12)
MESES = ["Todos", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# indice + 1 = dia ISO (1 = Lunes), igual que EXTRACT(ISODOW) en PostgreSQL
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
QUINCENA = "Quincena"   # dia 15 y ultimo dia de cada mes
LABORABLES = "Días laborables (L–V)"
FIN_SEMANA = "Fin de semana"
TIPOS_DIA = ["Todos", LABORABLES, FIN_SEMANA, QUINCENA] + DIAS

# Dominio fijo de la escala de velocidades: los promedios por nodo van de
# ~10 a ~75 km/h. Fijo para que cambiar un filtro no recoloree el mapa solo
# porque cambio el minimo o el maximo.
VEL_MIN, VEL_MAX = 10, 75
COLOR_SIN_DATO = "#94a3b8"
ZONA_CARTAGENA = ZoneInfo("America/Bogota")


def hoy_cartagena():
    """Fecha vigente en Cartagena, independiente de la zona horaria del VPS."""
    return datetime.now(ZONA_CARTAGENA).date()

# Estilo vectorial del modo oscuro: el mismo CARTO Dark Matter que dibujaba
# pydeck en produccion. Sus mosaicos vectoriales no piden llave (los raster
# de CARTO si), por eso se dibuja con MapLibre dentro de Leaflet.
_ESTILO_OSCURO = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"


# ============================================================
# TARJETA DE FILTROS (aspecto de menu, como el panel del documento)
# ============================================================
# Se aplica a todo contenedor con clave "tarjeta_*": Streamlit le agrega la
# clase st-key-<clave>. Tarjeta con la paleta del dashboard R: caja blanca
# (.box), titulo en tinta con filete azul (.box-primary) y campos celestes.
_T = '[class*="st-key-tarjeta_"]'
# Mismos colores que monitor.py
_TINTA, _AZUL, _MENTA, _MENTA_OSC = "#12307a", "#1f48b8", "#2dd4bf", "#14b8a6"
_LINEA, _TENUE = "#ececf0", "#58585d"
_CSS_TARJETA = f"""
<style>
{_T} {{
    background: #ffffff;
    border: 0; border-radius: 28px;
    padding: 0 20px 20px; gap: 0.7rem;
    box-shadow: 0 1px 2px rgba(17,17,19,.06), 0 12px 28px -12px rgba(17,17,19,.14);
}}
{_T} .tarjeta-titulo {{
    margin: 0 -20px 4px; padding: 22px 24px 12px; border-radius: 28px 28px 0 0;
    color: #111113 !important; font-size: 16px; font-weight: 700;
    letter-spacing: -0.02em; text-transform: none;
}}
{_T} .tarjeta-titulo::before {{
    content: ""; display: inline-block; width: 9px; height: 9px;
    margin-right: 9px; border-radius: 999px; background: {_MENTA};
}}
/* Etiquetas como las del R: gris azulado, mayusculas */
{_T} [data-testid="stWidgetLabel"] p, {_T} .stSelectbox label,
{_T} .stDateInput label, {_T} .stMultiSelect label {{
    color: {_TENUE} !important; font-size: 11px !important;
    font-weight: 700 !important; text-transform: uppercase !important;
    letter-spacing: 0.7px !important;
}}
{_T} .grupo-filtro-label {{
    color: {_TENUE}; font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.7px; margin: 2px 0 -4px;
}}
/* Casillas y opciones en tinta, sin mayusculas (como .checkbox del R) */
{_T} [data-testid="stCheckbox"] p, {_T} [data-testid="stRadio"] [role="radiogroup"] p {{
    color: {_TINTA} !important; font-size: 13px !important; font-weight: 500 !important;
    text-transform: none !important; letter-spacing: 0 !important;
}}
{_T} h4 {{ color: {_TINTA} !important; font-size: 15px !important; margin-top: 4px; }}
/* Campos celestes con borde suave y foco menta */
{_T} [data-baseweb="select"] > div, {_T} [data-baseweb="input"] {{
    background: #f6f6f8 !important;
    border: 1px solid #e3e3e7 !important; border-radius: 14px !important;
}}
{_T} [data-baseweb="input"] > div, {_T} input {{ background: transparent !important; }}
/* Streamlit conserva colores de texto del tema oscuro dentro de BaseWeb.
   Se fijan explicitamente para que los valores se lean sobre el campo claro. */
{_T} [data-baseweb="select"] span,
{_T} [data-baseweb="select"] div {{
    color: {_TINTA} !important;
    -webkit-text-fill-color: {_TINTA} !important;
}}
{_T} [data-baseweb="select"] svg {{
    color: {_TENUE} !important;
    fill: {_TENUE} !important;
}}
{_T} [data-baseweb="input"] input,
{_T} .stDateInput input {{
    color: {_TINTA} !important;
    -webkit-text-fill-color: {_TINTA} !important;
    opacity: 1 !important;
}}
{_T} input::placeholder {{
    color: {_TENUE} !important;
    -webkit-text-fill-color: {_TENUE} !important;
    opacity: .75 !important;
}}
/* El rango del mapa nace vacio: sustituye la mascara tecnica de Streamlit
   por una instruccion clara dentro del propio campo. */
{_T} [class*="st-key-"][class*="_fechas"] [data-baseweb="input"]:has(input:placeholder-shown) {{
    position: relative;
}}
{_T} [class*="st-key-"][class*="_fechas"] input:placeholder-shown {{
    color: transparent !important;
    -webkit-text-fill-color: transparent !important;
}}
{_T} [class*="st-key-"][class*="_fechas"] input:placeholder-shown::placeholder {{
    color: transparent !important;
    -webkit-text-fill-color: transparent !important;
    opacity: 0 !important;
}}
{_T} [class*="st-key-"][class*="_fechas"] [data-baseweb="input"]:has(input:placeholder-shown)::after {{
    content: "Seleccionar rango de fechas";
    position: absolute; left: 16px; top: 50%; transform: translateY(-50%);
    color: {_TINTA}; font-size: 14px; pointer-events: none;
}}
{_T} [aria-disabled="true"], {_T} [disabled] {{ opacity: 1 !important; }}
{_T} [data-baseweb="select"] > div:focus-within, {_T} [data-baseweb="input"]:focus-within {{
    border-color: {_MENTA_OSC} !important; box-shadow: 0 0 0 3px rgba(45,212,191,.25);
}}
{_T} [data-baseweb="tag"] {{ background: #d9f7f1 !important; border-radius: 6px !important; }}
{_T} [data-baseweb="tag"] span {{ color: #0b5d57 !important; }}
/* Restablecer: accion principal en azul institucional. */
{_T} .stButton button {{
    background: {_AZUL}; color: #ffffff; border: 1px solid {_AZUL};
    border-radius: 999px; font-weight: 600;
}}
{_T} .stButton button:hover {{
    background: {_TINTA}; color: #ffffff; border-color: {_TINTA}; box-shadow: none; transform: translateY(-1px);
}}
/* Barra de horas: riel menta, valores en recuadro azul (.irs--shiny del R)
   y escala debajo (la escala de Streamlit se oculta) */
{_T} [data-testid="stSliderThumbValue"] {{
    background: {_AZUL}; color: #ffffff !important; padding: 1px 5px;
    border-radius: 4px; font-size: 11px; font-weight: 700;
}}
{_T} [data-baseweb="slider"] [role="slider"] {{
    width: 20px; height: 20px; background: #ffffff;
    border: 2px solid {_AZUL}; box-shadow: 0 0 0 3px rgba(31,72,184,0.15);
}}
{_T} [data-baseweb="slider"] > div > div {{ height: 6px !important; border-radius: 3px; }}
{_T} [data-testid="stSliderTickBar"] {{ display: none; }}
/* Escala legible: numeros mas grandes y oscuros, separados del filtro de abajo */
.escala-horas {{ position: relative; height: 30px; margin: -8px 0 10px; }}
.escala-horas .marca {{
    position: absolute; top: 0; width: 1px; height: 5px; background: #b8c6e3;
}}
.escala-horas .marca.mayor {{ width: 2px; height: 9px; background: #6f84ad; }}
.escala-horas .num {{
    position: absolute; top: 12px; transform: translateX(-50%);
    font-size: 11px; font-weight: 600; color: #3d4f73;
}}
/* Los extremos no se salen de la tarjeta */
.escala-horas .num.inicio {{ transform: none; }}
.escala-horas .num.fin {{ transform: translateX(-100%); }}
</style>
"""


def tarjeta_filtros(clave: str, titulo: str):
    """Contenedor con aspecto de menu para los filtros; usar con `with`."""
    tarjeta = st.container(key=f"tarjeta_{clave}")
    tarjeta.markdown(f'{_CSS_TARJETA}<div class="tarjeta-titulo">{html.escape(titulo)}</div>',
                     unsafe_allow_html=True)
    return tarjeta


def _escala_horas() -> str:
    """Una marca por corrida bajo la barra; numero cada 4 horas: 4, 8 ... 20, 0."""
    corridas = horario.CORRIDAS
    partes = []
    for i, corrida in enumerate(corridas):
        hora, minutos = int(corrida[:2]), corrida[3:]
        mayor = minutos == "00" and horario.orden_hora(hora) % 240 == 0
        izq = f"{i / (len(corridas) - 1) * 100:.2f}%"
        partes.append(f'<span class="marca{" mayor" if mayor else ""}" style="left:{izq}"></span>')
        if mayor:
            extremo = " inicio" if i == 0 else " fin" if i == len(corridas) - 1 else ""
            partes.append(f'<span class="num{extremo}" style="left:{izq}">{hora}</span>')
    return f'<div class="escala-horas">{"".join(partes)}</div>'


def barra_horas(clave: str, on_change) -> tuple:
    """Barra de rango sobre las corridas del cron, de 4:00 a 0:00.

    Devuelve (desde, hasta) como "HH:MM". Ofrece cada corrida (tambien las de
    5:30, 6:30...) y no tiene la franja vacia de 01 a 03.

    A diferencia de st.slider, select_slider solo sabe que es de rango por
    `value`: sin el, al mover la barra devuelve una sola corrida. El valor real
    sigue saliendo de session_state (franjas y Restablecer lo escriben); el
    aviso de Streamlit por usar ambos se apaga en .streamlit/config.toml.
    """
    desde, hasta = st.select_slider(
        "Rango de horas:", options=horario.CORRIDAS, key=clave,
        value=horario.DIA_COMPLETO, on_change=on_change,
        format_func=horario.etiqueta,
    )
    st.markdown(_escala_horas(), unsafe_allow_html=True)
    return desde, hasta


def _corrida_ultima(ultima_ejecucion):
    """Corrida del cron correspondiente a la ultima medicion disponible."""
    if ultima_ejecucion is None or pd.isna(ultima_ejecucion):
        return None
    ts = pd.Timestamp(ultima_ejecucion)
    corrida = f"{ts.hour:02d}:{(ts.minute // 30) * 30:02d}"
    if corrida in horario.CORRIDAS:
        return corrida
    minuto = horario.minuto_operativo(corrida)
    return min(
        horario.CORRIDAS,
        key=lambda valor: abs(horario.minuto_operativo(valor) - minuto),
    )


def _etiqueta_ultima(corrida):
    return f"Última ejecución ({horario.etiqueta(corrida)})" if corrida else None


def _fecha_ultima(fechas, ultima_ejecucion):
    if ultima_ejecucion is not None and not pd.isna(ultima_ejecucion):
        return pd.Timestamp(ultima_ejecucion).date()
    return max(fechas[0], hoy_cartagena()) if fechas else None


def _valores_iniciales(prefijo: str, fechas, ultima_ejecucion=None) -> dict:
    corrida_ultima = _corrida_ultima(ultima_ejecucion)
    etiqueta_ultima = _etiqueta_ultima(corrida_ultima)
    iniciales = {
        # Como en produccion: la vista inicial se colorea por indice de fluidez
        f"{prefijo}_metrica": "Ratio (Índice de fluidez)",
        f"{prefijo}_franja":  etiqueta_ultima or TODO_EL_DIA,
        f"{prefijo}_horas":   (
            (corrida_ultima, corrida_ultima) if corrida_ultima else horario.DIA_COMPLETO
        ),
        f"{prefijo}_nodos":   [],
        f"{prefijo}_dia":     TIPOS_DIA[0],
    }
    if fechas:
        iniciales[f"{prefijo}_fechas"] = ()
    return iniciales


def panel_filtros(prefijo: str, nodos: dict, fechas=None, ultima_ejecucion=None) -> dict:
    """
    Dibuja los filtros y devuelve la seleccion.

    nodos:  {id_nodo: nombre_nodo} para el selector de punto de monitoreo.
    fechas: (primera, ultima) fecha con datos, o None si no se conoce (sin
            filtro de rango de fechas).
    ultima_ejecucion: timestamp de la captura que se muestra al entrar. Las
            fechas y la barra horaria se inicializan en ese punto.
    Devuelve {"metrica", "metrica_label", "consulta", "en_vivo"}; "consulta"
    son los argumentos de db.promedios_por_nodo / promedios_por_nodo_df.
    "en_vivo" es True mientras no se toque ningun filtro de datos (fechas,
    horas, tipo de dia): entonces se muestra la ultima ejecucion, como
    en produccion, y no promedios. Metrica y punto de monitoreo no cuentan:
    solo cambian el color o que nodos se ven.
    """
    corrida_ultima = _corrida_ultima(ultima_ejecucion)
    etiqueta_ultima = _etiqueta_ultima(corrida_ultima)
    opciones_franja = ([etiqueta_ultima] if etiqueta_ultima else []) + list(FRANJAS)
    iniciales = _valores_iniciales(prefijo, fechas, ultima_ejecucion)
    for clave, valor in iniciales.items():
        st.session_state.setdefault(clave, valor)

    def _al_cambiar_franja():
        seleccion = st.session_state[f"{prefijo}_franja"]
        rango = (
            (corrida_ultima, corrida_ultima)
            if etiqueta_ultima and seleccion == etiqueta_ultima
            else FRANJAS[seleccion]
        )
        if rango is not None:
            st.session_state[f"{prefijo}_horas"] = rango

    def _al_mover_horas():
        # Mover la barra elige la franja fija con esas horas, o Personalizado
        rango = tuple(st.session_state[f"{prefijo}_horas"])
        if etiqueta_ultima and rango == (corrida_ultima, corrida_ultima):
            st.session_state[f"{prefijo}_franja"] = etiqueta_ultima
        else:
            st.session_state[f"{prefijo}_franja"] = next(
                (nombre for nombre, horas in FRANJAS.items() if horas == rango), PERSONALIZADO)

    def _restablecer():
        for clave, valor in iniciales.items():
            st.session_state[clave] = valor

    metrica = st.selectbox("Métrica a mostrar:", list(METRICAS), key=f"{prefijo}_metrica")
    fecha_ini = fecha_fin = None
    rango = ()
    if fechas:
        fecha_max_selector = max(fechas[1], hoy_cartagena())
        rango = st.date_input(
            "Seleccionar rango de fechas",
            key=f"{prefijo}_fechas",
            min_value=fechas[0], max_value=fecha_max_selector, format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        fecha_default = _fecha_ultima(fechas, ultima_ejecucion)
        if rango and len(rango) == 2:
            fecha_ini, fecha_fin = rango
        else:
            fecha_ini = fecha_fin = fecha_default
    st.selectbox(
        "Franja horaria:", opciones_franja,
        key=f"{prefijo}_franja", on_change=_al_cambiar_franja,
    )
    # La barra siempre se puede mover; elegir una franja fija la ajusta sola
    desde, hasta = barra_horas(f"{prefijo}_horas", _al_mover_horas)
    ids = st.multiselect(
        "Punto de monitoreo:", list(nodos), key=f"{prefijo}_nodos",
        format_func=lambda i: nodos.get(i, i), placeholder="Todos los puntos",
    )
    dia = st.selectbox("Tipo de día:", TIPOS_DIA, key=f"{prefijo}_dia")
    st.button(
        "↺ Restablecer filtros", on_click=_restablecer,
        width="stretch", key=f"{prefijo}_restablecer",
    )

    consulta = {
        "fecha_ini": fecha_ini,
        "fecha_fin": fecha_fin,
        "desde": desde,
        "hasta": hasta,
        # Filtro de mes desactivado en el panel: el rango de fechas ya acota
        # el periodo. La consulta lo conserva para reactivarlo sin tocar la BD.
        "mes": None,
        "dia_semana": DIAS.index(dia) + 1 if dia in DIAS else None,
        "laborables": dia == LABORABLES,
        "fin_semana": dia == FIN_SEMANA,
        "quincena": dia == QUINCENA,
        "ids": tuple(ids),
    }
    filtrando = (
        (fechas is not None and rango and len(rango) == 2 and (
            fecha_ini, fecha_fin
        ) != (_fecha_ultima(fechas, ultima_ejecucion),) * 2)
        or (desde, hasta) != tuple(iniciales[f"{prefijo}_horas"])
        or consulta["dia_semana"] is not None
        or consulta["laborables"]
        or consulta["fin_semana"]
        or consulta["quincena"]
    )
    return {
        "metrica": METRICAS[metrica],
        "metrica_label": metrica,
        "consulta": consulta,
        "en_vivo": not filtrando,
    }


def promedios_por_nodo_df(
    df: pd.DataFrame, fecha_ini=None, fecha_fin=None, desde: str = None,
    hasta: str = None, mes: int = None, dia_semana: int = None,
    laborables: bool = False, fin_semana: bool = False,
    quincena: bool = False, ids: tuple = (),
) -> pd.DataFrame:
    """
    Version pandas de db.promedios_por_nodo, para cuando el historico viene de
    Google Sheets. Mismos filtros y mismas columnas de salida.
    """
    columnas = ["id_nodo", "vel_actual", "vel_libre", "ratio", "n"]
    if df.empty or "consultation_time" not in df.columns:
        return pd.DataFrame(columns=columnas)

    ts = df["consultation_time"]
    # 'ok' llega como bool desde PostgreSQL y como texto desde Sheets
    mascara = (
        df["ok"].astype(str).str.lower().isin(["true", "1"])
        & ts.notna()
        & horario.en_horario(ts, desde, hasta)
    )
    if fecha_ini is not None:
        mascara &= ts.dt.date >= fecha_ini
    if fecha_fin is not None:
        mascara &= ts.dt.date <= fecha_fin
    if mes is not None:
        mascara &= ts.dt.month == mes
    if dia_semana is not None:
        mascara &= ts.dt.weekday + 1 == dia_semana
    if laborables:
        mascara &= ts.dt.weekday < 5
    elif fin_semana:
        mascara &= ts.dt.weekday >= 5
    if quincena:
        mascara &= (ts.dt.day == 15) | ts.dt.is_month_end
    if ids:
        mascara &= df["id_nodo"].astype(str).isin(ids)

    return (
        df[mascara].groupby("id_nodo")
        .agg(vel_actual=("currentSpeed", "mean"), vel_libre=("freeFlowSpeed", "mean"),
             ratio=("velocidad_ratio", "mean"), n=("id_nodo", "size"))
        .reset_index()[columnas]
    )


# ============================================================
# VENTANA EMERGENTE
# ============================================================
def url_streetview(lat: float, lon: float):
    """URL de la foto de Street View del punto, o None si no hay llave."""
    if not config.GOOGLE_STREETVIEW_KEY:
        return None
    params = {
        "size": "320x180",
        "location": f"{lat:.6f},{lon:.6f}",
        "fov": 90,
        "source": "outdoor",          # evita fotos del interior de locales
        "return_error_code": "true",  # sin cobertura responde 404, no una imagen gris
        "key": config.GOOGLE_STREETVIEW_KEY,
    }
    return "https://maps.googleapis.com/maps/api/streetview?" + urlencode(params)


def texto_html(valor) -> str:
    if valor is None or pd.isna(valor) or not str(valor).strip():
        return "—"
    return html.escape(str(valor).strip())


def popup_html(fila: dict, clasificar_ratio, en_vivo: bool = False) -> str:
    """HTML de la ventana emergente de un nodo (ultima ejecucion o promedios)."""
    foto = ""
    url = url_streetview(fila["lat"], fila["lon"])
    if url:
        # loading=lazy: la foto se pide al abrir el popup, no al cargar el mapa.
        # Si Google no tiene cobertura (404) la imagen se quita.
        foto = (f'<img src="{html.escape(url)}" loading="lazy" width="320" height="180" '
                f'alt="Vista de calle" onerror="this.remove()">')

    filas = [
        ("Punto de referencia", texto_html(fila.get("punto_referencia"))),
        ("Barrio", texto_html(fila.get("barrio"))),
    ]
    if fila.get("n") and fila["n"] > 0:
        color, etiqueta = clasificar_ratio(fila["ratio"])
        vel = fila["vel_actual"]
        ratio = fila["ratio"]
        filas += [
            ("Velocidad de circulación" if en_vivo else "Velocidad promedio",
             f"{vel:.1f} km/h" if pd.notna(vel) else "—"),
            ("Índice de fluidez",
             f'<span class="np-punto" style="background:{color};"></span>'
             f'{ratio:.2f} · {etiqueta}' if pd.notna(ratio) else "—"),
        ]
        if not en_vivo:
            filas.append(("Mediciones", f"{int(fila['n']):,}"))
    else:
        filas.append(("Datos", "Sin lectura en la ultima ejecucion" if en_vivo
                      else "Sin mediciones con estos filtros"))

    tabla = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in filas)
    return (
        f'<div class="nodo-popup">{foto}'
        f'<div class="np-titulo">{texto_html(fila.get("nombre_nodo"))}</div>'
        f'<div class="np-id">{texto_html(fila.get("id_nodo"))}</div>'
        f'<table>{tabla}</table></div>'
    )


# Paleta del dashboard R (ventana blanca, tinta azul). Las reglas de Leaflet
# llevan el prefijo .leaflet-container para ganarle a leaflet.css, que se
# carga despues de este bloque.
_CSS_POPUP = """
<style>
.leaflet-container .leaflet-popup-content-wrapper, .leaflet-container .leaflet-popup-tip {
    box-shadow: 0 2px 12px rgba(18,48,122,.20);
    background: #ffffff; color: #12307a;
    border: 1px solid #d9e4f7;
}
.leaflet-container .leaflet-popup-content { margin: 12px 14px; font-family: 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif; }
.leaflet-container .leaflet-popup-content-wrapper { border-radius: 12px; }
.leaflet-container .leaflet-popup a.leaflet-popup-close-button { color: #5b6b8c; }
.nodo-popup img { display: block; width: 100%; height: auto; border-radius: 6px; margin-bottom: 8px; }
.np-titulo { color: #1f48b8; font-weight: 700; font-size: 14px; }
.np-id { color: #5b6b8c; font-size: 11px; margin-bottom: 6px; }
.nodo-popup table { border-collapse: collapse; font-size: 12px; }
.nodo-popup td { padding: 2px 0; vertical-align: top; }
.nodo-popup td:first-child { color: #5b6b8c; padding-right: 10px; white-space: nowrap; }
.np-punto { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; }
/* Tamaños fijos: dentro de streamlit-folium la letra base es 16 px y Leaflet
   usa 0.75rem, asi que leyenda, selector y escala salian agrandados */
.folium-map.leaflet-container,
.leaflet-container .leaflet-tooltip { font-size: 12px; }
.leaflet-container .leaflet-control-layers,
.leaflet-container .leaflet-control-scale-line { font-size: 11px; }
.legend.leaflet-control text { font-size: 10px; }
/* Leyenda de velocidades: fondo claro (se lee en Calles y en Oscuro) y alto
   real, porque su texto se dibuja por debajo del svg y tapaba el selector */
.legend.leaflet-control { background: rgba(255,255,255,0.95); border-radius: 12px; padding: 6px 10px 12px; box-shadow: 0 2px 12px rgba(18,48,122,.20); }
.legend.leaflet-control svg { overflow: visible; }
/* Atribucion de los mapas (obligatoria) en letra pequeña y discreta */
.leaflet-container .leaflet-control-attribution {
    font-size: 9px; background: rgba(255,255,255,0.45); color: #555; padding: 0 4px;
}
.leaflet-container .leaflet-control-attribution a { color: #555; }
</style>
"""


# ============================================================
# MAPA (piezas que tambien usa la red de nodos)
# ============================================================
class _CapaOscura(JSCSSMixin, MacroElement):
    """
    Modo oscuro en el selector de capas, y memoria de la eleccion: el mapa se
    vuelve a dibujar con cada cambio de filtro, asi que la capa elegida se
    guarda en localStorage y se restaura al cargar.
    """
    _template = Template("""
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.maplibreGL({
            style: {{ this.estilo|tojson }},
            attribution: "&copy; CARTO &copy; OpenStreetMap contributors"
        });
        {{ this.control }}.addBaseLayer({{ this.get_name() }}, "Oscuro");
        {{ this.mapa }}.on("baselayerchange", function (e) {
            try { localStorage.setItem("mapa_base", e.name); } catch (err) {}
        });
        try {
            if (localStorage.getItem("mapa_base") === "Oscuro") {
                {{ this.mapa }}.removeLayer({{ this.calles }});
                {{ this.get_name() }}.addTo({{ this.mapa }});
            }
        } catch (err) {}
        {% endmacro %}
    """)
    default_js = [
        ("maplibre_gl", "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"),
        ("maplibre_gl_leaflet",
         "https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.0.22/leaflet-maplibre-gl.js"),
    ]
    default_css = [("maplibre_gl_css", "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css")]

    def __init__(self, mapa, control, calles):
        super().__init__()
        self._name = "CapaOscura"
        self.estilo = _ESTILO_OSCURO
        self.mapa, self.control, self.calles = mapa.get_name(), control.get_name(), calles.get_name()


class _SinPrefijoLeaflet(MacroElement):
    """Quita el enlace "Leaflet" (con su bandera) de la esquina del mapa. La
    atribucion de OpenStreetMap / CARTO se queda: sus condiciones la exigen."""
    _template = Template("""
        {% macro script(this, kwargs) %}
        {{ this._parent.get_name() }}.attributionControl.setPrefix(false);
        {% endmacro %}
    """)


class _Reencuadre(MacroElement):
    """
    Un mapa en una pestaña que no se ve nace sin tamaño y el encuadre sale
    mal. Si es asi, se vuelve a encuadrar la primera vez que la
    pestaña se muestra. Va como elemento del mapa (corre justo despues de
    crearlo) y no en el evento load, que streamlit-folium ya dejo pasar.
    """
    _template = Template("""
        {% macro script(this, kwargs) %}
        (function () {
            var mapa = {{ this._parent.get_name() }};
            var caja = mapa.getContainer();
            // Oculto puede tener ancho pero 0 de alto (streamlit-folium), o 0 de
            // ambos (iframe srcdoc): basta con que falte uno para encuadrar mal
            var visible = function () { return caja.clientWidth > 0 && caja.clientHeight > 0; };
            if (visible()) return;
            // Espera a que el tamaño se estabilice: al abrir la pestaña crece en
            // varios pasos y encuadrar en el primero aleja el zoom
            var espera;
            var obs = new ResizeObserver(function () {
                if (!visible()) return;
                clearTimeout(espera);
                espera = setTimeout(function () {
                    obs.disconnect();
                    mapa.invalidateSize();
                    mapa.fitBounds({{ this.limites|tojson }}, {padding: [20, 20], maxZoom: 15});
                }, 250);
            });
            obs.observe(caja);
        })();
        {% endmacro %}
    """)

    def __init__(self, limites):
        super().__init__()
        self._name = "Reencuadre"
        self.limites = limites


def mapa_base(df: pd.DataFrame) -> folium.Map:
    """Mapa centrado en los nodos, con Calles (OpenStreetMap) de fondo por defecto."""
    m = folium.Map(
        location=[df["lat"].mean(), df["lon"].mean()],
        zoom_start=12, tiles=None, control_scale=True,
    )
    # terminar_mapa agrega el modo oscuro y necesita esta capa para alternar
    m.capa_calles = folium.TileLayer("OpenStreetMap", name="Calles (OSM)").add_to(m)
    return m


def escala_metrica(m: folium.Map, metrica: str, metrica_label: str):
    """Escala de color de las velocidades (con su leyenda), o None para el ratio."""
    if metrica == "ratio":
        return None
    # Azul de claro (lento) a oscuro (rapido): rojo y verde quedan solo para el
    # indice de fluidez. Con rojo-verde, una calle del centro despejada a
    # 30 km/h salia roja y se leia como trancon. Parte de un azul medio para
    # que los puntos lentos se vean sobre el mapa claro.
    escala = LinearColormap(
        ["#93c5fd", "#3b82f6", "#1e3a8a"],
        vmin=VEL_MIN, vmax=VEL_MAX, caption=metrica_label,
    )
    escala.add_to(m)
    return escala


def color_y_texto(valor, escala, clasificar_ratio) -> tuple:
    """(color, texto) de un valor de la metrica: ratio por categorias o km/h por escala."""
    if valor is None or pd.isna(valor):
        return COLOR_SIN_DATO, "sin datos"
    if escala is None:
        return clasificar_ratio(valor)[0], f"{valor:.2f}"
    return escala(min(max(valor, VEL_MIN), VEL_MAX)), f"{valor:.1f} km/h"


def agregar_nodos(m: folium.Map, df: pd.DataFrame, metrica: str, escala,
                  clasificar_ratio, en_vivo: bool = False, estilo: str = "normal") -> None:
    """
    Un circulo por nodo, coloreado segun la metrica, con tooltip y popup.
    estilo: "normal"; "atenuado" (pequeño y casi transparente, para que una
    ruta elegida se lea encima); o "resaltado" (los nodos de esa ruta).
    """
    radio, borde, opacidad, relleno = {
        "normal":    (8, 1, 0.6, 0.9),
        "atenuado":  (5, 1, 0.25, 0.25),
        "resaltado": (9, 2, 1.0, 1.0),
    }[estilo]
    for fila in df.to_dict("records"):
        color, valor_txt = color_y_texto(fila.get(metrica), escala, clasificar_ratio)
        folium.CircleMarker(
            location=[fila["lat"], fila["lon"]],
            radius=radio, color="#ffffff", weight=borde, opacity=opacidad,
            fill=True, fill_color=color, fill_opacity=relleno,
            tooltip=f"{texto_html(fila.get('nombre_nodo'))} · {valor_txt}",
            popup=folium.Popup(popup_html(fila, clasificar_ratio, en_vivo), max_width=340),
        ).add_to(m)


def terminar_mapa(m: folium.Map, lat: pd.Series, lon: pd.Series) -> folium.Map:
    """Selector de mapa, encuadre sobre los puntos dados y estilos del popup."""
    Fullscreen(
        position="topleft",
        title="Expandir mapa",
        title_cancel="Salir de pantalla completa",
        force_separate_button=True,
    ).add_to(m)
    # Selector siempre visible (no detras del boton de capas): Calles / Oscuro
    control = folium.LayerControl(collapsed=False).add_to(m)
    _CapaOscura(m, control, m.capa_calles).add_to(m)
    # Con muchos puntos se encuadra el 94 % central: los nodos aislados del
    # norte (Bayunca, Ramblas) alejaban el zoom y la ciudad se veia diminuta.
    # Con pocos (una seleccion o una ruta) se encuadran todos.
    q = (0.03, 0.97) if len(lat) > 20 else (0, 1)
    lat, lon = lat.quantile(q), lon.quantile(q)
    limites = [[float(lat.iloc[0]), float(lon.iloc[0])],
               [float(lat.iloc[1]), float(lon.iloc[1])]]
    m.fit_bounds(limites, padding=(20, 20), max_zoom=15)
    m.get_root().header.add_child(folium.Element(_CSS_POPUP))
    _Reencuadre(limites).add_to(m)
    _SinPrefijoLeaflet().add_to(m)
    return m


def construir_mapa(df: pd.DataFrame, metrica: str, metrica_label: str,
                   clasificar_ratio, en_vivo: bool = False) -> folium.Map:
    """
    Mapa Folium con un circulo por nodo, coloreado segun la metrica.

    df: una fila por nodo con id_nodo, nombre_nodo, lat, lon, barrio,
    punto_referencia y los promedios (vel_actual, vel_libre, ratio, n).
    """
    m = mapa_base(df)
    escala = escala_metrica(m, metrica, metrica_label)
    agregar_nodos(m, df, metrica, escala, clasificar_ratio, en_vivo)
    return terminar_mapa(m, df["lat"], df["lon"])
