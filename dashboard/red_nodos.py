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
from folium.plugins import PolyLineTextPath

import mapa_nodos

# Via / linea recta: mediana medida con OSRM sobre las 416 conexiones. Solo se
# usa para estimar distancias cuando falta data/red_nodos.json.
RODEO_MEDIANO = 1.26
COLOR_RUTA = "#2dd4bf"        # --mint del dashboard R
# Borde oscuro bajo la ruta: hace que el cyan se lea sobre el mapa claro
# y sobre el oscuro, y sobre conexiones de cualquier color
COLOR_BORDE_RUTA = "#12307a"  # --ink del dashboard R
COLOR_CIERRE = "#ef4444"
COLOR_RUTA_NORMAL = "#64748b"
# Un color por corredor en el orden de la hoja CORREDORES (PALETA_AVENIDAS
# del dashboard R): el color de cada uno no cambia al filtrar
PALETA_CORREDORES = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#0891b2",
    "#f032e6", "#9a6324", "#800000", "#808000", "#000075", "#d4a017",
    "#2dd4bf", "#7c3aed", "#fb7185", "#475569", "#65a30d", "#0ea5e9",
    "#c026d3", "#b45309",
]


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
        return {
            "conexiones": conexiones,
            "por_via": True,
            "fuente": fuente,
            # La red actual no trae restricciones de giro, pero se conserva el
            # campo si se agrega en una captura futura. Cada restriccion puede
            # ser [anterior, intermedio, siguiente] o un dict equivalente.
            "restricciones_giro": datos.get("restricciones_giro", []),
        }

    conexiones = []
    for a, b in pares_excel:
        if a in puntos and b in puntos:
            d = round(_recta_m(puntos[a], puntos[b]) * RODEO_MEDIANO)
            conexiones.append({"a": a, "b": b, "d_ab_m": d, "d_ba_m": d, "path": None})
    return {"conexiones": conexiones, "por_via": False,
            "fuente": "hoja REDES en línea recta (falta data/red_nodos.json)",
            "restricciones_giro": []}


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


def aristas_cerradas(cierres: list | tuple | None) -> set:
    """Convierte los cierres de la interfaz en pares dirigidos (origen, destino)."""
    bloqueadas = set()
    for cierre in cierres or ():
        inicio, fin = cierre["inicio"], cierre["fin"]
        sentido = cierre.get("sentido", "ambos")
        if sentido in ("ambos", "ida"):
            bloqueadas.add((inicio, fin))
        if sentido in ("ambos", "vuelta"):
            bloqueadas.add((fin, inicio))
    return bloqueadas


def nodos_conectados(red: dict, id_nodo: str) -> list:
    """Nodos unidos directamente a ``id_nodo`` por al menos un sentido valido."""
    vecinos = set()
    for c in red["conexiones"]:
        if c["a"] == id_nodo and (c.get("d_ab_m") is not None or c.get("d_ba_m") is not None):
            vecinos.add(c["b"])
        elif c["b"] == id_nodo and (c.get("d_ab_m") is not None or c.get("d_ba_m") is not None):
            vecinos.add(c["a"])
    return sorted(vecinos)


def _giros_restringidos(red: dict) -> set:
    """Normaliza restricciones de giro opcionales como (anterior, via, siguiente)."""
    salida = set()
    for giro in red.get("restricciones_giro", []):
        if isinstance(giro, dict):
            trio = (
                giro.get("anterior", giro.get("desde", giro.get("origen"))),
                giro.get("intermedio", giro.get("via")),
                giro.get("siguiente", giro.get("hacia", giro.get("destino"))),
            )
        else:
            trio = tuple(giro) if len(giro) == 3 else (None, None, None)
        if all(trio):
            salida.add(trio)
    return salida


def ruta_mas_rapida(origen: str, destino: str, red: dict, promedios: dict,
                    cierres: list | tuple | None = None):
    """
    Camino de menor tiempo de origen a destino con las velocidades promedio
    del periodo filtrado (Dijkstra). Cada conexion da dos aristas, una por
    sentido, con su propia distancia por via. Las conexiones con un nodo sin
    datos se descartan.

    ``cierres`` no altera la red: solo excluye temporalmente los sentidos
    seleccionados. Si la red incluye ``restricciones_giro``, tambien se
    descartan esos movimientos.

    Devuelve None si no hay camino, o un dict con nodos (en orden), tramos
    (conexion y sentido de cada paso), dist_m, tiempo_s y tiempo_libre_s.
    """
    if not origen or not destino or origen == destino:
        return None

    bloqueadas = aristas_cerradas(cierres)
    giros_restringidos = _giros_restringidos(red)
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
            if d is None or (u, w) in bloqueadas:
                continue
            aristas.setdefault(u, []).append({
                "hacia": w, "d": d, "t": d / (v / 3.6),
                "t_libre": d / (v_libre / 3.6) if not pd.isna(v_libre) else d / (v / 3.6),
                "conexion": c, "sentido": sentido,
            })

    # El estado conserva el nodo anterior para poder validar el giro al tomar
    # la siguiente arista. En el primer paso es None.
    inicio = (None, origen)
    tiempos, previo = {inicio: 0.0}, {}
    cola = [(0.0, "", origen)]
    estado_final = None
    while cola:
        t, anterior_orden, u = heapq.heappop(cola)
        anterior = anterior_orden or None
        estado = (anterior, u)
        if u == destino:
            estado_final = estado
            break
        if t > tiempos.get(estado, float("inf")):
            continue
        for a in aristas.get(u, []):
            if anterior is not None and (anterior, u, a["hacia"]) in giros_restringidos:
                continue
            siguiente = (u, a["hacia"])
            nuevo = t + a["t"]
            if nuevo < tiempos.get(siguiente, float("inf")):
                tiempos[siguiente] = nuevo
                previo[siguiente] = (estado, a)
                heapq.heappush(cola, (nuevo, u, a["hacia"]))

    if estado_final is None:
        return None

    pasos, estado = [], estado_final
    while estado != inicio:
        estado, arista = previo[estado]
        pasos.append(arista)
    pasos.reverse()
    return {
        "nodos": [origen] + [p["hacia"] for p in pasos],
        "tramos": [(p["conexion"], p["sentido"]) for p in pasos],
        "dist_m": sum(p["d"] for p in pasos),
        "tiempo_s": sum(p["t"] for p in pasos),
        "tiempo_libre_s": sum(p["t_libre"] for p in pasos),
    }


def buscar_conexion(red: dict, inicio: str, fin: str):
    """Devuelve la conexion fisica entre dos nodos, sin importar su orden."""
    return next((c for c in red["conexiones"]
                 if {c["a"], c["b"]} == {inicio, fin}), None)


def _sentido_corto(conexion: dict) -> int:
    """
    Sentido mas corto de una conexion (1 = a->b, -1 = b->a). Un corredor es
    una via de doble sentido: el sentido mas largo suele dar la vuelta a una
    manzana o buscar un retorno porque el nodo quedo en la otra calzada
    (Bazurto -> Uma: 1.502 m; Uma -> Bazurto: 653 m).
    """
    d_ab, d_ba = conexion["d_ab_m"], conexion["d_ba_m"]
    return -1 if d_ba is not None and (d_ab is None or d_ba < d_ab) else 1


def armar_corredores(corredores: dict, red: dict) -> list:
    """
    Cada corredor ({nombre: [id_nodo, ...]}, de la hoja CORREDORES) con su
    color y sus tramos (conexion, sentido) en el orden de la hoja. Cada tramo
    se dibuja y se mide en su sentido mas corto, sin importar el del recorrido.
    Un par seguido que no es conexion de la red queda en linea recta y sin
    distancia: falta correr capturar_red.py --completar-corredores.
    """
    por_par = {}
    for c in red["conexiones"]:
        por_par[frozenset((c["a"], c["b"]))] = c
    salida = []
    for k, (nombre, nodos) in enumerate(corredores.items()):
        tramos = []
        for x, y in zip(nodos, nodos[1:]):
            c = por_par.get(frozenset((x, y)))
            tramos.append((c, _sentido_corto(c)) if c else
                          ({"a": x, "b": y, "d_ab_m": None, "d_ba_m": None, "path": None}, 1))
        salida.append({
            "nombre": nombre, "color": PALETA_CORREDORES[k % len(PALETA_CORREDORES)],
            "nodos": nodos, "tramos": tramos,
            "sin_conexion": sum(c["d_ab_m"] is None for c, _ in tramos),
        })
    return salida


def resumen_corredor(corredor: dict, promedios: dict) -> dict:
    """
    Distancia, tiempo y tiempo a flujo libre de recorrer el corredor tramo a
    tramo (cada uno en el sentido que eligio armar_corredores), con las
    velocidades promedio del periodo como en ruta_mas_rapida, y la fluidez
    promedio de sus nodos. Un tramo sin distancia o sin datos deja vacio lo
    que depende de el.
    """
    dist = tiempo = tiempo_libre = 0.0
    for c, sentido in corredor["tramos"]:
        d = c.get("d_corredor_m")
        if d is None:
            d = c["d_ab_m"] if sentido == 1 else c["d_ba_m"]
        pa, pb = promedios.get(c["a"], {}), promedios.get(c["b"], {})
        v = _armonica(pa.get("vel_actual"), pb.get("vel_actual"))
        v_libre = _armonica(pa.get("vel_libre"), pb.get("vel_libre"))
        d = float("nan") if d is None else d
        dist += d
        tiempo += d / (v / 3.6)
        tiempo_libre += d / (v_libre / 3.6)
    ratios = pd.Series([promedios.get(n, {}).get("ratio") for n in dict.fromkeys(corredor["nodos"])],
                       dtype=float)
    return {"dist_m": dist, "tiempo_s": tiempo, "tiempo_libre_s": tiempo_libre,
            "ratio": ratios.mean()}


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


def _trazo_corredor(conexion: dict, puntos: dict, por_via: bool,
                    sentido: int = 1) -> list:
    """
    Trazado visual de un corredor. Si la conexion tiene path_corredor, usa
    esa geometria TomTom sin sentido y deja path/path_ba exclusivamente para
    las conexiones y las rutas Origen-Destino.
    """
    if por_via and conexion.get("path_corredor"):
        path = conexion["path_corredor"]
        return path if sentido == 1 else path[::-1]
    return _trazo(conexion, puntos, por_via, sentido)


def construir_mapa_red(df: pd.DataFrame, red: dict, promedios: dict, metrica: str,
                       metrica_label: str, clasificar_ratio, mostrar_conexiones: bool,
                       por_via: bool, ruta=None, en_vivo: bool = False,
                       corredores=None) -> folium.Map:
    """
    Mapa de la red: conexiones coloreadas por la metrica, la ruta elegida
    resaltada encima y los nodos (con su popup) arriba de todo. Con una ruta
    elegida, el resto de la red se atenua para que la ruta se lea.

    df: nodos a mostrar (catalogo + promedios), como en mapa_nodos.construir_mapa.
    Solo se dibujan las conexiones entre nodos de df.
    corredores: lista de armar_corredores; se dibujan en vez de la ruta, cada
    uno con su color, y sus nodos llevan el borde de ese color.
    """
    m = mapa_nodos.mapa_base(df)
    escala = mapa_nodos.escala_metrica(m, metrica, metrica_label)
    puntos = df.set_index("id_nodo")[["lat", "lon"]].to_dict("index")
    nombres = dict(zip(df["id_nodo"], df["nombre_nodo"]))
    resaltar = bool(ruta or corredores)

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
                weight=3 if resaltar else 4, opacity=0.18 if resaltar else 0.85,
                tooltip=(f"{mapa_nodos.texto_html(nombres[c['a']])} – "
                         f"{mapa_nodos.texto_html(nombres[c['b']])} · {valor_txt} · {dist:.1f} km"),
            ).add_to(capa)

    if corredores:
        # Nodos fuera de los corredores atenuados, luego las lineas y arriba
        # los nodos de los corredores, con el borde del primero que los usa
        bordes = {}
        for corredor in corredores:
            for id_nodo in corredor["nodos"]:
                bordes.setdefault(id_nodo, corredor["color"])
        en_corredor = df["id_nodo"].isin(bordes)
        mapa_nodos.agregar_nodos(m, df[~en_corredor], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="atenuado")
        capa_corredores = folium.FeatureGroup(name="Corredores", control=False).add_to(m)
        for corredor in corredores:
            nombre = mapa_nodos.texto_html(corredor["nombre"])
            for (conexion, sentido), x, y in zip(corredor["tramos"], corredor["nodos"],
                                                 corredor["nodos"][1:]):
                folium.PolyLine(
                    _trazo_corredor(conexion, puntos, por_via, sentido),
                    color=corredor["color"], weight=6, opacity=0.9,
                    tooltip=(f"<b>{nombre}</b><br>{mapa_nodos.texto_html(nombres[x])} → "
                             f"{mapa_nodos.texto_html(nombres[y])}"),
                ).add_to(capa_corredores)
        mapa_nodos.agregar_nodos(m, df[en_corredor], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="corredor", bordes=bordes)
        return mapa_nodos.terminar_mapa(m, df[en_corredor]["lat"], df[en_corredor]["lon"],
                                        encuadrar_todos=True)

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


def construir_mapa_simulacion(
        df: pd.DataFrame, red: dict, promedios: dict, metrica: str,
        metrica_label: str, clasificar_ratio, mostrar_conexiones: bool,
        por_via: bool, cierres: list | tuple, ruta_normal=None,
        ruta_alternativa=None, origen: str | None = None,
        destino: str | None = None, en_vivo: bool = False) -> folium.Map:
    """Mapa independiente para comparar la ruta normal y la alternativa."""
    m = mapa_nodos.mapa_base(df)
    escala = mapa_nodos.escala_metrica(m, metrica, metrica_label)
    puntos = df.set_index("id_nodo")[["lat", "lon"]].to_dict("index")
    nombres = dict(zip(df["id_nodo"], df["nombre_nodo"]))

    if mostrar_conexiones:
        capa = folium.FeatureGroup(name="Conexiones disponibles", control=False).add_to(m)
        for c in red["conexiones"]:
            if c["a"] not in puntos or c["b"] not in puntos:
                continue
            valor = metrica_conexion(promedios, c["a"], c["b"], metrica)
            color, valor_txt = mapa_nodos.color_y_texto(valor, escala, clasificar_ratio)
            distancias = [d for d in (c.get("d_ab_m"), c.get("d_ba_m")) if d is not None]
            if not distancias:
                continue
            folium.PolyLine(
                _trazo(c, puntos, por_via), color=color, weight=3, opacity=0.28,
                tooltip=(f"{mapa_nodos.texto_html(nombres[c['a']])} – "
                         f"{mapa_nodos.texto_html(nombres[c['b']])} · {valor_txt} · "
                         f"{min(distancias) / 1000:.1f} km"),
            ).add_to(capa)

    ids_destacados = {n for cierre in cierres for n in (cierre["inicio"], cierre["fin"])}
    for ruta in (ruta_normal, ruta_alternativa):
        if ruta:
            ids_destacados.update(ruta["nodos"])
    en_destacado = df["id_nodo"].isin(ids_destacados)
    if ids_destacados:
        mapa_nodos.agregar_nodos(m, df[~en_destacado], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="atenuado")
        mapa_nodos.agregar_nodos(m, df[en_destacado], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="resaltado")
    else:
        mapa_nodos.agregar_nodos(m, df, metrica, escala, clasificar_ratio, en_vivo)

    if ruta_normal:
        capa_normal = folium.FeatureGroup(name="Ruta sin cierres", control=False).add_to(m)
        for conexion, sentido in ruta_normal["tramos"]:
            folium.PolyLine(
                _trazo(conexion, puntos, por_via, sentido), color=COLOR_RUTA_NORMAL,
                weight=6, opacity=0.75, dash_array="10 8", tooltip="Ruta sin cierres",
            ).add_to(capa_normal)

    if ruta_alternativa:
        capa_alt = folium.FeatureGroup(name="Ruta alternativa", control=False).add_to(m)
        for color, grosor in ((COLOR_BORDE_RUTA, 13), (COLOR_RUTA, 7)):
            for conexion, sentido in ruta_alternativa["tramos"]:
                folium.PolyLine(
                    _trazo(conexion, puntos, por_via, sentido), color=color,
                    weight=grosor, opacity=1, tooltip="Ruta alternativa",
                ).add_to(capa_alt)

    capa_cierres = folium.FeatureGroup(name="Cierres", control=False).add_to(m)
    for cierre in cierres:
        conexion = buscar_conexion(red, cierre["inicio"], cierre["fin"])
        if not conexion or conexion["a"] not in puntos or conexion["b"] not in puntos:
            continue
        for u, w in sorted(aristas_cerradas([cierre])):
            sentido = 1 if (u, w) == (conexion["a"], conexion["b"]) else -1
            linea = folium.PolyLine(
                _trazo(conexion, puntos, por_via, sentido), color=COLOR_CIERRE,
                weight=8, opacity=0.95,
                tooltip=(f"Cierre: {mapa_nodos.texto_html(nombres.get(u, u))} → "
                         f"{mapa_nodos.texto_html(nombres.get(w, w))}"),
            ).add_to(capa_cierres)
            PolyLineTextPath(
                linea, "  →  ", repeat=True, offset=7,
                attributes={"fill": COLOR_CIERRE, "font-weight": "bold", "font-size": "16"},
            ).add_to(m)

    for id_nodo, etiqueta, color in (
            (origen, "Origen", "#22c55e"), (destino, "Destino", "#f59e0b")):
        if id_nodo in puntos:
            p = puntos[id_nodo]
            folium.CircleMarker(
                location=[p["lat"], p["lon"]], radius=14, color=color, weight=5,
                fill=False, tooltip=folium.Tooltip(etiqueta, permanent=True),
            ).add_to(m)

    foco = df[df["id_nodo"].isin(ids_destacados)]
    if not foco.empty:
        return mapa_nodos.terminar_mapa(m, foco["lat"], foco["lon"], encuadrar_todos=True)
    return mapa_nodos.terminar_mapa(m, df["lat"], df["lon"])
