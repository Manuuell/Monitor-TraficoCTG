"""Mapa geografico de calor para el analisis temporal de Cartagena.

La superficie usa interpolacion IDW solo cerca de nodos con datos reales y
de la red vial observada. La transparencia fuera de esa cobertura evita
presentar como medidos sectores sin puntos de monitoreo.
"""
from __future__ import annotations

import html
import math

import folium
import numpy as np
import pandas as pd
from branca.colormap import LinearColormap
from folium.raster_layers import ImageOverlay

import analisis_temporal
import mapa_nodos


COBERTURA_NODO_M = 1400.0
COBERTURA_RED_M = 500.0
RESOLUCION_VERTICAL = 170

CONFIG_INDICADORES = {
    "currentSpeed": {
        "valor": "vel_actual",
        "titulo": "Velocidad de circulación",
        "unidad": "km/h",
        "vmin": mapa_nodos.VEL_MIN,
        "vmax": mapa_nodos.VEL_MAX,
        "paradas": [
            (mapa_nodos.VEL_MIN, "#1e3a8a"),
            ((mapa_nodos.VEL_MIN + mapa_nodos.VEL_MAX) / 2, "#3b82f6"),
            (mapa_nodos.VEL_MAX, "#93c5fd"),
        ],
        "ticks": [10, 20, 30, 40, 50, 60, 75],
    },
    "freeFlowSpeed": {
        "valor": "vel_libre",
        "titulo": "Velocidad de flujo libre",
        "unidad": "km/h",
        "vmin": mapa_nodos.VEL_MIN,
        "vmax": mapa_nodos.VEL_MAX,
        "paradas": [
            (mapa_nodos.VEL_MIN, "#1e3a8a"),
            ((mapa_nodos.VEL_MIN + mapa_nodos.VEL_MAX) / 2, "#3b82f6"),
            (mapa_nodos.VEL_MAX, "#93c5fd"),
        ],
        "ticks": [10, 20, 30, 40, 50, 60, 75],
    },
    "velocidad_ratio": {
        "valor": "ratio",
        "titulo": "Índice de fluidez",
        "unidad": "índice",
        "vmin": 0.0,
        "vmax": 1.0,
        "paradas": analisis_temporal.ESCALA_FLUIDEZ,
        "ticks": ["0", "0,60", "0,75", "0,90", "1"],
    },
}


def resumir_nodos(datos: pd.DataFrame, catalogo: pd.DataFrame,
                   columna_metrica: str) -> pd.DataFrame:
    """Promedios reales por nodo para el mismo conjunto filtrado de la vista."""
    columnas = [
        "id_nodo", "nombre_nodo", "punto_referencia", "barrio", "lat", "lon",
        "vel_actual", "vel_libre", "ratio", "valor", "n_mediciones",
    ]
    if (datos.empty or catalogo.empty or columna_metrica not in CONFIG_INDICADORES
            or "id_nodo" not in datos.columns):
        return pd.DataFrame(columns=columnas)

    medidas = datos.copy()
    medidas["id_nodo"] = medidas["id_nodo"].astype(str)
    for columna in ("currentSpeed", "freeFlowSpeed", "velocidad_ratio"):
        if columna not in medidas.columns:
            medidas[columna] = np.nan
        medidas[columna] = pd.to_numeric(medidas[columna], errors="coerce")

    # filtrar_mediciones ya aplico estado, fecha, hora, tipo de dia y nodos.
    # Esta comprobacion adicional garantiza que el conteo sea el del indicador.
    medidas = medidas[medidas[columna_metrica].notna()].copy()
    if medidas.empty:
        return pd.DataFrame(columns=columnas)

    resumen = (
        medidas.groupby("id_nodo", as_index=False)
        .agg(
            vel_actual=("currentSpeed", "mean"),
            vel_libre=("freeFlowSpeed", "mean"),
            ratio=("velocidad_ratio", "mean"),
            n_mediciones=(columna_metrica, "count"),
        )
    )
    resumen["valor"] = resumen[CONFIG_INDICADORES[columna_metrica]["valor"]]

    ubicaciones = catalogo.copy()
    ubicaciones["id_nodo"] = ubicaciones["id_nodo"].astype(str)
    salida = ubicaciones.merge(resumen, on="id_nodo", how="inner")
    salida["lat"] = pd.to_numeric(salida["lat"], errors="coerce")
    salida["lon"] = pd.to_numeric(salida["lon"], errors="coerce")
    salida = salida.dropna(subset=["lat", "lon", "valor"])
    return salida.reindex(columns=columnas).reset_index(drop=True)


def _hex_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _rgba_valores(valores: np.ndarray, paradas: list[tuple[float, str]],
                  vmin: float, vmax: float) -> np.ndarray:
    """Convierte valores a la escala fija mediante interpolacion RGB lineal."""
    posiciones = np.asarray([p for p, _ in paradas], dtype=float)
    rgb = np.asarray([_hex_rgb(c) for _, c in paradas], dtype=float)
    planos = np.clip(valores.ravel(), vmin, vmax)
    salida = np.zeros((planos.size, 4), dtype=np.uint8)
    for canal in range(3):
        salida[:, canal] = np.interp(planos, posiciones, rgb[:, canal]).round().astype(np.uint8)
    salida[:, 3] = 210
    return salida.reshape((*valores.shape, 4))


def _distancias_m(lat: np.ndarray, lon: np.ndarray, puntos: np.ndarray) -> np.ndarray:
    """Distancia euclidiana local en metros entre grilla y puntos de Cartagena."""
    lat_ref = float(np.nanmean(lat))
    y = lat * 111_320.0
    x = lon * 111_320.0 * math.cos(math.radians(lat_ref))
    py = puntos[:, 0] * 111_320.0
    px = puntos[:, 1] * 111_320.0 * math.cos(math.radians(lat_ref))
    return (x[:, None] - px[None, :]) ** 2 + (y[:, None] - py[None, :]) ** 2


def _puntos_red(red: dict, catalogo: pd.DataFrame) -> np.ndarray:
    """Muestrea la geometria vial cada ~200 m para limitar la cobertura al suelo observado."""
    ubicaciones = catalogo.set_index("id_nodo")[["lat", "lon"]].to_dict("index")
    puntos = []
    for conexion in red.get("conexiones", []):
        trazo = conexion.get("path")
        if not trazo:
            a, b = ubicaciones.get(conexion.get("a")), ubicaciones.get(conexion.get("b"))
            trazo = ([[a["lat"], a["lon"]], [b["lat"], b["lon"]]] if a and b else [])
        if not trazo:
            continue
        elegido = [trazo[0]]
        ultimo = np.asarray(trazo[0], dtype=float)
        for punto in trazo[1:-1]:
            actual = np.asarray(punto, dtype=float)
            dy = (actual[0] - ultimo[0]) * 111_320.0
            dx = (actual[1] - ultimo[1]) * 109_400.0
            if math.hypot(dx, dy) >= 200.0:
                elegido.append(punto)
                ultimo = actual
        elegido.append(trazo[-1])
        puntos.extend(elegido)
    if not puntos:
        return np.empty((0, 2), dtype=float)
    return np.unique(np.round(np.asarray(puntos, dtype=float), 5), axis=0)


def _distancia_minima(lat: np.ndarray, lon: np.ndarray, puntos: np.ndarray,
                      lote: int = 700) -> np.ndarray:
    if puntos.size == 0:
        return np.full(lat.shape, np.inf, dtype=float)
    salida = np.empty(lat.size, dtype=float)
    for inicio in range(0, lat.size, lote):
        fin = min(inicio + lote, lat.size)
        salida[inicio:fin] = np.sqrt(
            _distancias_m(lat[inicio:fin], lon[inicio:fin], puntos).min(axis=1)
        )
    return salida


def interpolar_superficie(nodos: pd.DataFrame, columna_metrica: str,
                          puntos_red: np.ndarray | None = None) -> dict:
    """Crea un raster IDW recortado por cercania a nodos y a la red vial."""
    if nodos.empty or columna_metrica not in CONFIG_INDICADORES:
        return {}
    config_ind = CONFIG_INDICADORES[columna_metrica]
    lat_n = nodos["lat"].to_numpy(dtype=float)
    lon_n = nodos["lon"].to_numpy(dtype=float)
    valores = nodos["valor"].to_numpy(dtype=float)

    margen_lat = COBERTURA_NODO_M / 111_320.0
    margen_lon = COBERTURA_NODO_M / (111_320.0 * math.cos(math.radians(lat_n.mean())))
    sur, norte = lat_n.min() - margen_lat, lat_n.max() + margen_lat
    oeste, este = lon_n.min() - margen_lon, lon_n.max() + margen_lon
    proporcion = ((este - oeste) * math.cos(math.radians(lat_n.mean()))) / (norte - sur)
    alto = RESOLUCION_VERTICAL
    ancho = int(np.clip(round(alto * proporcion), 120, 300))
    grilla_lat = np.linspace(norte, sur, alto)
    grilla_lon = np.linspace(oeste, este, ancho)
    lon2d, lat2d = np.meshgrid(grilla_lon, grilla_lat)
    lat_plana, lon_plana = lat2d.ravel(), lon2d.ravel()

    dist2_nodos = _distancias_m(
        lat_plana, lon_plana, np.column_stack([lat_n, lon_n])
    )
    distancia_nodo = np.sqrt(dist2_nodos.min(axis=1))
    # El radio de influencia es mayor que el de cobertura para suavizar la
    # transicion, pero nunca hace visible una celda fuera de la cobertura.
    pesos = np.where(
        dist2_nodos <= (COBERTURA_NODO_M * 2.2) ** 2,
        1.0 / np.maximum(dist2_nodos, 25.0 ** 2),
        0.0,
    )
    suma_pesos = pesos.sum(axis=1)
    estimado = np.divide(
        pesos @ valores,
        suma_pesos,
        out=np.full(lat_plana.shape, np.nan, dtype=float),
        where=suma_pesos > 0,
    )

    puntos_red = np.asarray(puntos_red if puntos_red is not None else [], dtype=float)
    distancia_red = _distancia_minima(lat_plana, lon_plana, puntos_red)
    cerca_red = distancia_red <= COBERTURA_RED_M if puntos_red.size else True
    mascara = (distancia_nodo <= COBERTURA_NODO_M) & cerca_red & np.isfinite(estimado)
    matriz = estimado.reshape(alto, ancho)
    rgba = _rgba_valores(
        matriz, config_ind["paradas"], config_ind["vmin"], config_ind["vmax"]
    )
    mascara_2d = mascara.reshape(alto, ancho)
    # Opacidad constante en la zona fiable; solo se desvanece el ultimo 20 %
    # del borde para que el limite de cobertura no parezca una medicion exacta.
    borde_nodo = np.clip(
        (COBERTURA_NODO_M - distancia_nodo) / (COBERTURA_NODO_M * 0.20), 0, 1
    )
    if puntos_red.size:
        borde_red = np.clip(
            (COBERTURA_RED_M - distancia_red) / (COBERTURA_RED_M * 0.25), 0, 1
        )
        borde = np.minimum(borde_nodo, borde_red)
    else:
        borde = borde_nodo
    alpha = (210 * borde).round().astype(np.uint8).reshape(alto, ancho)
    rgba[:, :, 3] = np.where(mascara_2d, alpha, 0)
    return {
        "imagen": rgba,
        "bounds": [[sur, oeste], [norte, este]],
        "celdas_cubiertas": int(mascara.sum()),
        "celdas_totales": int(mascara.size),
    }


def _trazo_conexion(conexion: dict, puntos: dict) -> list:
    if conexion.get("path"):
        return conexion["path"]
    a, b = puntos.get(conexion.get("a")), puntos.get(conexion.get("b"))
    return ([[a["lat"], a["lon"]], [b["lat"], b["lon"]]] if a and b else [])


def _popup_nodo(fila: dict, clasificar_ratio) -> str:
    _, estado = clasificar_ratio(fila.get("ratio"))
    nombre = fila.get("nombre_nodo") or fila.get("punto_referencia") or fila["id_nodo"]
    referencia = fila.get("punto_referencia") or "—"

    def numero(valor, decimales=1):
        return "—" if pd.isna(valor) else f"{valor:.{decimales}f}"

    return (
        f"<div style='font-family:Inter,Arial,sans-serif;min-width:250px'>"
        f"<b>{html.escape(str(nombre))}</b><br>"
        f"<span style='color:#64748b'>{html.escape(str(referencia))}</span><hr>"
        f"Velocidad de circulación: <b>{numero(fila.get('vel_actual'))} km/h</b><br>"
        f"Velocidad de flujo libre: <b>{numero(fila.get('vel_libre'))} km/h</b><br>"
        f"Índice de fluidez: <b>{numero(fila.get('ratio'), 2)}</b><br>"
        f"Estado del tráfico: <b>{html.escape(str(estado))}</b><br>"
        f"Mediciones utilizadas: <b>{int(fila.get('n_mediciones') or 0):,}</b>"
        f"</div>"
    )


def construir_mapa(nodos: pd.DataFrame, catalogo: pd.DataFrame, red: dict,
                   columna_metrica: str, clasificar_ratio) -> tuple[folium.Map, dict]:
    """Mapa Folium con superficie, red vial y nodos en capas independientes."""
    config_ind = CONFIG_INDICADORES[columna_metrica]
    puntos_red = _puntos_red(red, catalogo)
    superficie = interpolar_superficie(nodos, columna_metrica, puntos_red)
    mapa = mapa_nodos.mapa_base(nodos)

    capa_calor = folium.FeatureGroup(
        name="Superficie estimada (cobertura cercana)", show=True, control=True
    ).add_to(mapa)
    ImageOverlay(
        image=superficie["imagen"],
        bounds=superficie["bounds"],
        origin="upper",
        opacity=0.82,
        pixelated=False,
        name="Intensidad del indicador",
        control=False,
    ).add_to(capa_calor)

    puntos_catalogo = catalogo.set_index("id_nodo")[["lat", "lon"]].to_dict("index")
    capa_red = folium.FeatureGroup(name="Red vial disponible", show=True).add_to(mapa)
    for conexion in red.get("conexiones", []):
        trazo = _trazo_conexion(conexion, puntos_catalogo)
        if trazo:
            folium.PolyLine(
                trazo, color="#475569", weight=2, opacity=0.55,
                tooltip="Conexión de la red monitoreada",
            ).add_to(capa_red)

    capa_nodos = folium.FeatureGroup(name="Nodos utilizados", show=True).add_to(mapa)
    escala_puntos = LinearColormap(
        [color for _, color in config_ind["paradas"]],
        index=[valor for valor, _ in config_ind["paradas"]],
        vmin=config_ind["vmin"], vmax=config_ind["vmax"],
    )
    for fila in nodos.to_dict("records"):
        valor = float(np.clip(fila["valor"], config_ind["vmin"], config_ind["vmax"]))
        folium.CircleMarker(
            [fila["lat"], fila["lon"]], radius=5,
            color="#ffffff", weight=1.5,
            fill=True, fill_color=escala_puntos(valor), fill_opacity=1,
            tooltip=(f"{mapa_nodos.texto_html(fila.get('nombre_nodo'))} · "
                     f"{fila['valor']:.2f} {config_ind['unidad']}"),
            popup=folium.Popup(_popup_nodo(fila, clasificar_ratio), max_width=360),
        ).add_to(capa_nodos)

    leyenda = LinearColormap(
        [color for _, color in config_ind["paradas"]],
        index=[valor for valor, _ in config_ind["paradas"]],
        vmin=config_ind["vmin"], vmax=config_ind["vmax"],
        caption=f"{config_ind['titulo']} ({config_ind['unidad']})",
        tick_labels=config_ind["ticks"],
    )
    leyenda.add_to(mapa)
    return mapa_nodos.terminar_mapa(
        mapa, nodos["lat"], nodos["lon"], encuadrar_todos=True
    ), superficie

