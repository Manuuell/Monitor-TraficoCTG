"""
Red de nodos: conexiones entre nodos vecinos, metrica por conexion, ruta mas
rapida entre dos nodos y su mapa Folium.

Seccion 3 del documento "Arquitectura y visualizacion del proyecto". Las
conexiones salen de data/red_nodos.json (capturar_red.py): la vecindad de la
hoja REDES, con la distancia por via en cada sentido y el trazado tomados de
OpenStreetMap. Sin ese archivo la red se arma desde REDES en linea recta.
"""
import heapq
import json
import math

import folium
import pandas as pd

import mapa_nodos

# Via / linea recta: mediana medida con OSRM sobre las 416 conexiones. Solo se
# usa para estimar distancias cuando falta data/red_nodos.json.
RODEO_MEDIANO = 1.26
COLOR_RUTA = "#2dd4bf"        # --mint del dashboard R
# Borde oscuro bajo la ruta: hace que el cyan se lea sobre el mapa claro
# y sobre el oscuro, y sobre conexiones de cualquier color
COLOR_BORDE_RUTA = "#12307a"  # --ink del dashboard R


def _recta_m(p: dict, q: dict) -> float:
    """Distancia en linea recta (haversine) entre dos nodos, en metros."""
    la1, lo1, la2, lo2 = map(math.radians, [p["lat"], p["lon"], q["lat"], q["lon"]])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 6371000 * 2 * math.asin(math.sqrt(h))


def cargar_red(path_json, catalogo: pd.DataFrame, pares_excel: list) -> dict:
    """
    {"conexiones": [...], "por_via": bool, "fuente": str}. Cada conexion trae
    a, b, d_ab_m, d_ba_m y path ([lat, lon] por via, o None). Solo quedan las
    conexiones con ambos nodos en el catalogo.

    pares_excel: vecinos de la hoja REDES, para armar la red en linea recta si
    no existe el JSON.
    """
    puntos = catalogo.set_index("id_nodo")[["lat", "lon"]].to_dict("index")
    if path_json.exists():
        with open(path_json, encoding="utf-8") as f:
            datos = json.load(f)
        conexiones = [c for c in datos["conexiones"] if c["a"] in puntos and c["b"] in puntos]
        fuente = f"{datos.get('fuente', 'OSRM')} · {datos.get('capturado', '')}"
        return {"conexiones": conexiones, "por_via": True, "fuente": fuente}

    conexiones = []
    for a, b in pares_excel:
        if a in puntos and b in puntos:
            d = round(_recta_m(puntos[a], puntos[b]) * RODEO_MEDIANO)
            conexiones.append({"a": a, "b": b, "d_ab_m": d, "d_ba_m": d, "path": None})
    return {"conexiones": conexiones, "por_via": False,
            "fuente": "hoja REDES en línea recta (falta data/red_nodos.json)"}


def _armonica(va, vb) -> float:
    """Media armonica de dos velocidades: la que da el tiempo real de recorrido."""
    if any(v is None or pd.isna(v) or v <= 0 for v in (va, vb)):
        return float("nan")
    return 2 / (1 / va + 1 / vb)


def metrica_conexion(promedios: dict, a: str, b: str, metrica: str) -> float:
    """
    Valor de la metrica en la conexion a-b a partir de los promedios de sus
    dos nodos. promedios: {id_nodo: {"vel_actual", "vel_libre", ...}}.
    """
    pa, pb = promedios.get(a, {}), promedios.get(b, {})
    actual = _armonica(pa.get("vel_actual"), pb.get("vel_actual"))
    if metrica == "vel_actual":
        return actual
    libre = _armonica(pa.get("vel_libre"), pb.get("vel_libre"))
    if metrica == "vel_libre":
        return libre
    return actual / libre if libre and not pd.isna(libre) else float("nan")


def ruta_mas_rapida(origen: str, destino: str, red: dict, promedios: dict):
    """
    Camino de menor tiempo de origen a destino con las velocidades promedio
    del periodo filtrado (Dijkstra). Cada conexion da dos aristas, una por
    sentido, con su propia distancia por via. Las conexiones con un nodo sin
    datos se descartan.

    Devuelve None si no hay camino, o un dict con nodos (en orden), tramos
    (conexion y sentido de cada paso), dist_m, tiempo_s y tiempo_libre_s.
    """
    aristas = {}
    for c in red["conexiones"]:
        v = _armonica(promedios.get(c["a"], {}).get("vel_actual"),
                      promedios.get(c["b"], {}).get("vel_actual"))
        if pd.isna(v):
            continue
        v_libre = _armonica(promedios.get(c["a"], {}).get("vel_libre"),
                            promedios.get(c["b"], {}).get("vel_libre"))
        for u, w, d, sentido in ((c["a"], c["b"], c["d_ab_m"], 1),
                                 (c["b"], c["a"], c["d_ba_m"], -1)):
            if d is None:
                continue
            aristas.setdefault(u, []).append({
                "hacia": w, "d": d, "t": d / (v / 3.6),
                "t_libre": d / (v_libre / 3.6) if not pd.isna(v_libre) else d / (v / 3.6),
                "conexion": c, "sentido": sentido,
            })

    tiempos, previo = {origen: 0.0}, {}
    cola = [(0.0, origen)]
    while cola:
        t, u = heapq.heappop(cola)
        if u == destino:
            break
        if t > tiempos.get(u, float("inf")):
            continue
        for a in aristas.get(u, []):
            nuevo = t + a["t"]
            if nuevo < tiempos.get(a["hacia"], float("inf")):
                tiempos[a["hacia"]] = nuevo
                previo[a["hacia"]] = (u, a)
                heapq.heappush(cola, (nuevo, a["hacia"]))

    if destino not in tiempos or origen == destino:
        return None

    pasos, nodo = [], destino
    while nodo != origen:
        nodo, arista = previo[nodo]
        pasos.append(arista)
    pasos.reverse()
    return {
        "nodos": [origen] + [p["hacia"] for p in pasos],
        "tramos": [(p["conexion"], p["sentido"]) for p in pasos],
        "dist_m": sum(p["d"] for p in pasos),
        "tiempo_s": sum(p["t"] for p in pasos),
        "tiempo_libre_s": sum(p["t_libre"] for p in pasos),
    }


def _trazo(conexion: dict, puntos: dict, por_via: bool, sentido: int = 1) -> list:
    """
    Puntos [lat, lon] de una conexion en el sentido pedido (1 = a->b,
    -1 = b->a): por via si se pide y existe, o en linea recta. De vuelta se
    usa path_ba, el trazado propio de b->a: en calles de un solo sentido el
    regreso va por otras vias (AER_CRE-TUN_CRE: 7,9 km de ida y 1,6 de vuelta).
    Solo si falta se invierte el de ida.
    """
    if por_via and sentido == -1 and conexion.get("path_ba"):
        return conexion["path_ba"]
    if por_via and conexion.get("path"):
        path = conexion["path"]
    else:
        a, b = puntos[conexion["a"]], puntos[conexion["b"]]
        path = [[a["lat"], a["lon"]], [b["lat"], b["lon"]]]
    return path if sentido == 1 else path[::-1]


def construir_mapa_red(df: pd.DataFrame, red: dict, promedios: dict, metrica: str,
                       metrica_label: str, clasificar_ratio, mostrar_conexiones: bool,
                       por_via: bool, ruta=None, en_vivo: bool = False) -> folium.Map:
    """
    Mapa de la red: conexiones coloreadas por la metrica, la ruta elegida
    resaltada encima y los nodos (con su popup) arriba de todo. Con una ruta
    elegida, el resto de la red se atenua para que la ruta se lea.

    df: nodos a mostrar (catalogo + promedios), como en mapa_nodos.construir_mapa.
    Solo se dibujan las conexiones entre nodos de df.
    """
    m = mapa_nodos.mapa_base(df)
    escala = mapa_nodos.escala_metrica(m, metrica, metrica_label)
    puntos = df.set_index("id_nodo")[["lat", "lon"]].to_dict("index")
    nombres = dict(zip(df["id_nodo"], df["nombre_nodo"]))

    if mostrar_conexiones:
        # Fuera del selector de mapa: se prenden con "Mostrar conexiones"
        capa = folium.FeatureGroup(name="Conexiones", control=False).add_to(m)
        for c in red["conexiones"]:
            if c["a"] not in puntos or c["b"] not in puntos:
                continue
            valor = metrica_conexion(promedios, c["a"], c["b"], metrica)
            color, valor_txt = mapa_nodos.color_y_texto(valor, escala, clasificar_ratio)
            dist = min(d for d in (c["d_ab_m"], c["d_ba_m"]) if d is not None) / 1000
            folium.PolyLine(
                _trazo(c, puntos, por_via), color=color,
                weight=3 if ruta else 4, opacity=0.18 if ruta else 0.85,
                tooltip=(f"{mapa_nodos.texto_html(nombres[c['a']])} – "
                         f"{mapa_nodos.texto_html(nombres[c['b']])} · {valor_txt} · {dist:.1f} km"),
            ).add_to(capa)

    if not ruta:
        mapa_nodos.agregar_nodos(m, df, metrica, escala, clasificar_ratio, en_vivo)
    else:
        # Orden de dibujo: nodos fuera de la ruta (atenuados) abajo, luego la
        # ruta con su borde, y los nodos de la ruta arriba de todo
        en_ruta = df["id_nodo"].isin(ruta["nodos"])
        mapa_nodos.agregar_nodos(m, df[~en_ruta], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="atenuado")
        capa_ruta = folium.FeatureGroup(name="Ruta", control=False).add_to(m)
        for color, grosor in ((COLOR_BORDE_RUTA, 13), (COLOR_RUTA, 7)):
            for conexion, sentido in ruta["tramos"]:
                folium.PolyLine(
                    _trazo(conexion, puntos, por_via, sentido),
                    color=color, weight=grosor, opacity=1,
                ).add_to(capa_ruta)
        mapa_nodos.agregar_nodos(m, df[en_ruta], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="resaltado")

    if ruta:
        for id_nodo, etiqueta in ((ruta["nodos"][0], "Origen"), (ruta["nodos"][-1], "Destino")):
            p = puntos[id_nodo]
            folium.CircleMarker(
                location=[p["lat"], p["lon"]], radius=14, color=COLOR_RUTA, weight=4,
                fill=False, tooltip=folium.Tooltip(etiqueta, permanent=True),
            ).add_to(m)
        en_ruta = df[df["id_nodo"].isin(ruta["nodos"])]
        return mapa_nodos.terminar_mapa(m, en_ruta["lat"], en_ruta["lon"])
    return mapa_nodos.terminar_mapa(m, df["lat"], df["lon"])
