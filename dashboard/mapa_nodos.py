"""
Mapa de solo nodos: filtros, ventana emergente y mapa Folium.

Seccion 2 del documento "Arquitectura y visualizacion del proyecto". El panel
de filtros usa un prefijo en sus claves de session_state para poder repetirlo
en las secciones que aplican los mismos filtros (red de nodos, analisis
temporal) sin que los widgets choquen entre si.
"""
import html
from urllib.parse import urlencode

import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from branca.element import MacroElement
from folium.elements import JSCSSMixin
from jinja2 import Template

import config

# ============================================================
# OPCIONES DE LOS FILTROS (tal como las define el documento)
# ============================================================
METRICAS = {
    "Velocidad actual (km/h)": "vel_actual",
    "Velocidad de flujo libre (km/h)": "vel_libre",
    "Ratio (Índice de fluidez)": "ratio",
}

TODO_EL_DIA = "Todo el día (0:00 – 23:59)"
PERSONALIZADO = "Personalizado"
FRANJAS = {
    TODO_EL_DIA:               (0, 23),
    PERSONALIZADO:             None,      # rango libre con la barra de horas
    "Madrugada (02–05)":       (2, 5),
    "Mañana temprano (06–07)": (6, 7),
    "Hora pico AM (08–09)":    (8, 9),
    "Media mañana (10–11)":    (10, 11),
    "Hora pico medio (12–13)": (12, 13),
    "Tarde (14–15)":           (14, 15),
    "Pre-pico PM (16)":        (16, 16),
    "Hora pico PM (17–18)":    (17, 18),
    "Noche (19–23)":           (19, 23),
}

# El indice de cada mes es su numero (1-12)
MESES = ["Todos", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# indice + 1 = dia ISO (1 = Lunes), igual que EXTRACT(ISODOW) en PostgreSQL
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
QUINCENA = "Quincena"   # dia 15 y ultimo dia de cada mes
TIPOS_DIA = ["Todos", QUINCENA] + DIAS

# Dominio fijo de la escala de velocidades: los promedios por nodo van de
# ~10 a ~75 km/h. Fijo para que cambiar un filtro no recoloree el mapa solo
# porque cambio el minimo o el maximo.
VEL_MIN, VEL_MAX = 10, 75
COLOR_SIN_DATO = "#94a3b8"

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
{_T} [aria-disabled="true"], {_T} [disabled] {{ opacity: 1 !important; }}
{_T} [data-baseweb="select"] > div:focus-within, {_T} [data-baseweb="input"]:focus-within {{
    border-color: {_MENTA_OSC} !important; box-shadow: 0 0 0 3px rgba(45,212,191,.25);
}}
{_T} [data-baseweb="tag"] {{ background: #d9f7f1 !important; border-radius: 6px !important; }}
{_T} [data-baseweb="tag"] span {{ color: #0b5d57 !important; }}
/* Restablecer: boton blanco con borde azul (.btn-default del R) */
{_T} .stButton button {{
    background: #111113; color: #ffffff; border: 1px solid #111113;
    border-radius: 999px; font-weight: 600;
}}
{_T} .stButton button:hover {{
    background: {_AZUL}; color: #ffffff; border-color: {_AZUL}; box-shadow: none; transform: translateY(-1px);
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
.escala-horas {{ position: relative; height: 24px; margin: -12px 0 0; }}
.escala-horas .marca {{
    position: absolute; top: 0; width: 1px; height: 4px; background: #c9d6ee;
}}
.escala-horas .marca.mayor {{ height: 7px; background: #93a6c9; }}
.escala-horas .num {{
    position: absolute; top: 10px; transform: translateX(-50%);
    font-size: 10px; color: {_TENUE};
}}
</style>
"""


def tarjeta_filtros(clave: str, titulo: str):
    """Contenedor con aspecto de menu para los filtros; usar con `with`."""
    tarjeta = st.container(key=f"tarjeta_{clave}")
    tarjeta.markdown(f'{_CSS_TARJETA}<div class="tarjeta-titulo">{html.escape(titulo)}</div>',
                     unsafe_allow_html=True)
    return tarjeta


def _escala_horas() -> str:
    """Marcas de 0 a 23 bajo la barra de horas, con numero cada 3 horas y en 23."""
    partes = []
    for h in range(24):
        mayor = h % 3 == 0 or h == 23
        izq = f"{h / 23 * 100:.2f}%"
        partes.append(f'<span class="marca{" mayor" if mayor else ""}" style="left:{izq}"></span>')
        if mayor:
            partes.append(f'<span class="num" style="left:{izq}">{h}</span>')
    return f'<div class="escala-horas">{"".join(partes)}</div>'


def _valores_iniciales(prefijo: str, fechas) -> dict:
    iniciales = {
        # Como en produccion: la vista inicial se colorea por indice de fluidez
        f"{prefijo}_metrica": "Ratio (Índice de fluidez)",
        f"{prefijo}_franja":  TODO_EL_DIA,
        f"{prefijo}_horas":   (0, 23),
        f"{prefijo}_nodos":   [],
        f"{prefijo}_mes":     MESES[0],
        f"{prefijo}_dia":     TIPOS_DIA[0],
    }
    if fechas:
        iniciales[f"{prefijo}_fechas"] = tuple(fechas)
    return iniciales


def panel_filtros(prefijo: str, nodos: dict, fechas=None) -> dict:
    """
    Dibuja los filtros y devuelve la seleccion.

    nodos:  {id_nodo: nombre_nodo} para el selector de punto de monitoreo.
    fechas: (primera, ultima) fecha con datos, o None si no se conoce (sin
            filtro de rango de fechas).
    Devuelve {"metrica", "metrica_label", "consulta", "en_vivo"}; "consulta"
    son los argumentos de db.promedios_por_nodo / promedios_por_nodo_df.
    "en_vivo" es True mientras no se toque ningun filtro de datos (fechas,
    horas, mes, tipo de dia): entonces se muestra la ultima ejecucion, como
    en produccion, y no promedios. Metrica y punto de monitoreo no cuentan:
    solo cambian el color o que nodos se ven.
    """
    iniciales = _valores_iniciales(prefijo, fechas)
    for clave, valor in iniciales.items():
        st.session_state.setdefault(clave, valor)

    def _al_cambiar_franja():
        rango = FRANJAS[st.session_state[f"{prefijo}_franja"]]
        if rango is not None:
            st.session_state[f"{prefijo}_horas"] = rango

    def _al_mover_horas():
        # Mover la barra elige la franja fija con esas horas, o Personalizado
        rango = tuple(st.session_state[f"{prefijo}_horas"])
        st.session_state[f"{prefijo}_franja"] = next(
            (nombre for nombre, horas in FRANJAS.items() if horas == rango), PERSONALIZADO)

    def _restablecer():
        for clave, valor in iniciales.items():
            st.session_state[clave] = valor

    metrica = st.selectbox("Métrica a mostrar:", list(METRICAS), key=f"{prefijo}_metrica")
    fecha_ini = fecha_fin = None
    if fechas:
        rango = st.date_input(
            "Rango de fechas:", key=f"{prefijo}_fechas",
            min_value=fechas[0], max_value=fechas[1], format="DD/MM/YYYY",
        )
        # Mientras se elige el rango llega una sola fecha: cuenta como ese dia
        if rango:
            fecha_ini, fecha_fin = rango[0], rango[-1]
    st.selectbox(
        "Franja horaria:", list(FRANJAS),
        key=f"{prefijo}_franja", on_change=_al_cambiar_franja,
    )
    # La barra siempre se puede mover; elegir una franja fija la ajusta sola
    hora_ini, hora_fin = st.slider(
        "Rango de horas:", 0, 23, key=f"{prefijo}_horas",
        on_change=_al_mover_horas, format="%d:00",
    )
    st.markdown(_escala_horas(), unsafe_allow_html=True)
    ids = st.multiselect(
        "Punto de monitoreo:", list(nodos), key=f"{prefijo}_nodos",
        format_func=lambda i: nodos.get(i, i), placeholder="Todos los puntos",
    )
    mes = st.selectbox("Mes:", MESES, key=f"{prefijo}_mes")
    dia = st.selectbox("Tipo de día:", TIPOS_DIA, key=f"{prefijo}_dia")
    st.button(
        "↺ Restablecer filtros", on_click=_restablecer,
        width="stretch", key=f"{prefijo}_restablecer",
    )

    consulta = {
        "fecha_ini": fecha_ini,
        "fecha_fin": fecha_fin,
        "hora_ini": hora_ini,
        "hora_fin": hora_fin,
        "mes": MESES.index(mes) or None,
        "dia_semana": DIAS.index(dia) + 1 if dia in DIAS else None,
        "quincena": dia == QUINCENA,
        "ids": tuple(ids),
    }
    filtrando = (
        (fechas is not None and (fecha_ini, fecha_fin) != tuple(fechas))
        or (hora_ini, hora_fin) != (0, 23)
        or consulta["mes"] is not None
        or consulta["dia_semana"] is not None
        or consulta["quincena"]
    )
    return {
        "metrica": METRICAS[metrica],
        "metrica_label": metrica,
        "consulta": consulta,
        "en_vivo": not filtrando,
    }


def promedios_por_nodo_df(
    df: pd.DataFrame, fecha_ini=None, fecha_fin=None, hora_ini: int = 0,
    hora_fin: int = 23, mes: int = None, dia_semana: int = None,
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
        & ts.dt.hour.between(hora_ini, hora_fin)
    )
    if fecha_ini is not None:
        mascara &= ts.dt.date >= fecha_ini
    if fecha_fin is not None:
        mascara &= ts.dt.date <= fecha_fin
    if mes is not None:
        mascara &= ts.dt.month == mes
    if dia_semana is not None:
        mascara &= ts.dt.weekday + 1 == dia_semana
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
            ("Velocidad actual" if en_vivo else "Velocidad promedio",
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
