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
COLORES_RUTAS = ["#14b8a6", "#f97316", "#8b5cf6"]
# Ajuste de extremos en dobles calzadas. Solo se considera otra calzada si el
# trazado legal vuelve cerca del punto con direccion opuesta y separacion
# lateral real; asi no se elimina un retorno sobre la misma calzada.
DIST_CALZADA_MIN_M = 4.0
DIST_CALZADA_MAX_M = 350.0
RECORTE_MIN_M = 40.0
RECORTE_MAX_M = 3000.0
AHORRO_MIN_M = 35.0
FACTOR_ACCESO = 2.0
VELOCIDAD_ACCESO_KMH = 18.0
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
    coordenadas = {
        str(id_nodo): [float(p["lat"]), float(p["lon"])]
        for id_nodo, p in puntos.items()
    }
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
            "penalizaciones_giro": datos.get("penalizaciones_giro", []),
            "retardos_nodo_s": datos.get(
                "retardos_nodo_s", datos.get("penalizaciones_nodo_s", {})),
            "puntos": coordenadas,
        }

    conexiones = []
    for a, b in pares_excel:
        if a in puntos and b in puntos:
            d = round(_recta_m(puntos[a], puntos[b]) * RODEO_MEDIANO)
            conexiones.append({"a": a, "b": b, "d_ab_m": d, "d_ba_m": d, "path": None})
    return {"conexiones": conexiones, "por_via": False,
            "fuente": "hoja REDES en línea recta (falta data/red_nodos.json)",
            "restricciones_giro": [], "penalizaciones_giro": [],
            "retardos_nodo_s": {}, "puntos": coordenadas}


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


def _penalizaciones_giro(red: dict) -> dict:
    """Retardos opcionales por giro, indexados como (anterior, via, siguiente)."""
    salida = {}
    for giro in red.get("penalizaciones_giro", []):
        if not isinstance(giro, dict):
            continue
        trio = (
            giro.get("anterior", giro.get("desde", giro.get("origen"))),
            giro.get("intermedio", giro.get("via")),
            giro.get("siguiente", giro.get("hacia", giro.get("destino"))),
        )
        retardo = giro.get("retardo_s", giro.get("penalizacion_s", giro.get("delay_s", 0)))
        if all(trio) and retardo is not None:
            salida[trio] = max(0.0, float(retardo))
    return salida


def _sentido_habilitado(conexion: dict, sentido: int) -> bool:
    """Aplica metadatos opcionales de sentido sin inventarlos cuando no existen."""
    clave = "permitir_ab" if sentido == 1 else "permitir_ba"
    if clave in conexion:
        return bool(conexion[clave])
    permitidos = conexion.get("sentidos_permitidos")
    if permitidos is not None:
        codigo = "ab" if sentido == 1 else "ba"
        return codigo in {str(x).lower().replace("_", "") for x in permitidos}
    unico = conexion.get("oneway", conexion.get("un_sentido"))
    if unico in (True, 1, "1", "ab", "a_b", "a->b"):
        return sentido == 1
    if unico in (-1, "-1", "ba", "b_a", "b->a"):
        return sentido == -1
    return True


def _retardo_arista_s(conexion: dict, sentido: int, destino: str, red: dict) -> float:
    """Suma retardos de infraestructura si la captura de red los proporciona."""
    sufijo = "ab" if sentido == 1 else "ba"
    retardo = 0.0
    for clave in (f"retardo_{sufijo}_s", f"penalizacion_{sufijo}_s", f"delay_{sufijo}_s"):
        if conexion.get(clave) is not None:
            retardo += max(0.0, float(conexion[clave]))
            break
    else:
        for clave in ("retardo_s", "penalizacion_s", "delay_s"):
            if conexion.get(clave) is not None:
                retardo += max(0.0, float(conexion[clave]))
                break
    retardos_nodo = red.get("retardos_nodo_s", red.get("penalizaciones_nodo_s", {}))
    if isinstance(retardos_nodo, dict) and retardos_nodo.get(destino) is not None:
        retardo += max(0.0, float(retardos_nodo[destino]))
    return retardo


def _trazo_dirigido(conexion: dict, sentido: int) -> list:
    """Geometria disponible para una arista, sin necesitar el catalogo de nodos."""
    if sentido == -1 and conexion.get("path_ba"):
        return conexion["path_ba"]
    path = conexion.get("path") or []
    return path if sentido == 1 else path[::-1]


def _delta_xy_m(p: list, q: list) -> tuple:
    """Desplazamiento local aproximado este/norte entre dos [lat, lon]."""
    lat_media = math.radians((p[0] + q[0]) / 2)
    return ((q[1] - p[1]) * 111320 * math.cos(lat_media),
            (q[0] - p[0]) * 111320)


def _distancia_puntos_m(p: list, q: list) -> float:
    """Distancia local entre dos coordenadas [lat, lon]."""
    return math.hypot(*_delta_xy_m(p, q))


def _longitud_trazo_m(path: list) -> float:
    """Longitud geometrica de una polilinea en metros."""
    return sum(_distancia_puntos_m(p, q) for p, q in zip(path, path[1:]))


def _proyecciones_sobre_trazo(path: list, punto: list) -> list:
    """Proyecta un punto sobre cada segmento y conserva distancia y direccion."""
    salida, acumulado = [], 0.0
    for indice, (a, b) in enumerate(zip(path, path[1:])):
        dx, dy = _delta_xy_m(a, b)
        largo = math.hypot(dx, dy)
        if largo <= 0:
            continue
        px, py = _delta_xy_m(a, punto)
        fraccion = min(1.0, max(0.0, (px * dx + py * dy) / (largo * largo)))
        proyectado = [
            a[0] + (b[0] - a[0]) * fraccion,
            a[1] + (b[1] - a[1]) * fraccion,
        ]
        salida.append({
            "segmento": indice,
            "fraccion": fraccion,
            "punto": proyectado,
            "progreso_m": acumulado + largo * fraccion,
            "acceso_m": _distancia_puntos_m(punto, proyectado),
            "direccion": (dx / largo, dy / largo),
        })
        acumulado += largo
    return salida


def _ancla_base(path: list, punto: list, inicio: bool) -> dict:
    """Ancla original que entrego el motor de ruteo en un extremo."""
    if inicio:
        a, b, segmento, fraccion = path[0], path[1], 0, 0.0
        progreso = 0.0
    else:
        a, b = path[-2], path[-1]
        segmento, fraccion = len(path) - 2, 1.0
        progreso = _longitud_trazo_m(path)
    dx, dy = _delta_xy_m(a, b)
    largo = math.hypot(dx, dy) or 1.0
    extremo = path[0] if inicio else path[-1]
    return {
        "segmento": segmento, "fraccion": fraccion,
        "punto": list(extremo), "progreso_m": progreso,
        "acceso_m": _distancia_puntos_m(punto, extremo),
        "direccion": (dx / largo, dy / largo),
    }


def _anclas_extremo(path: list, punto: list, inicio: bool) -> list:
    """
    Ancla original y posibles calzadas paralelas recorridas legalmente por el
    mismo trazado. La direccion opuesta y la separacion lateral impiden
    confundir un retorno necesario sobre la misma calzada con otra calzada.
    """
    base = _ancla_base(path, punto, inicio)
    total = _longitud_trazo_m(path)
    candidatos = [base]
    for candidato in _proyecciones_sobre_trazo(path, punto):
        recorte = (candidato["progreso_m"] if inicio
                   else total - candidato["progreso_m"])
        separacion = _distancia_puntos_m(base["punto"], candidato["punto"])
        producto = sum(x * y for x, y in zip(
            base["direccion"], candidato["direccion"]))
        if not (RECORTE_MIN_M <= recorte <= RECORTE_MAX_M):
            continue
        if not (DIST_CALZADA_MIN_M <= separacion <= DIST_CALZADA_MAX_M):
            continue
        if candidato["acceso_m"] > DIST_CALZADA_MAX_M or producto > -0.2:
            continue
        candidatos.append(candidato)
    return candidatos


def _recortar_trazo(path: list, ancla_inicio: dict, ancla_fin: dict) -> list:
    """Recorta una polilinea entre dos proyecciones e inserta ambos puntos."""
    salida = [ancla_inicio["punto"]]
    for indice in range(ancla_inicio["segmento"] + 1,
                        ancla_fin["segmento"] + 1):
        salida.append(list(path[indice]))
    salida.append(ancla_fin["punto"])
    limpia = []
    for punto in salida:
        if not limpia or _distancia_puntos_m(limpia[-1], punto) > 0.05:
            limpia.append(punto)
    return limpia


def _muestras_trazo(path: list, paso_m: float = 8.0) -> list:
    """Muestrea una polilinea e incluye la direccion local de cada punto."""
    muestras = []
    for p, q in zip(path, path[1:]):
        dx, dy = _delta_xy_m(p, q)
        largo = math.hypot(dx, dy)
        if largo <= 0:
            continue
        ux, uy = dx / largo, dy / largo
        partes = max(1, math.ceil(largo / paso_m))
        for i in range(partes):
            f = i / partes
            muestras.append((p[0] + (q[0] - p[0]) * f,
                             p[1] + (q[1] - p[1]) * f, ux, uy))
    if len(path) > 1:
        p, q = path[-2], path[-1]
        dx, dy = _delta_xy_m(p, q)
        largo = math.hypot(dx, dy) or 1.0
        muestras.append((q[0], q[1], dx / largo, dy / largo))
    return muestras


def _indice_geometrias_cerradas(red: dict, cierres) -> dict:
    """Indice espacial ligero de los trazados rojos, separado por sentido."""
    indice = {}
    for cierre in cierres or ():
        conexion = buscar_conexion(red, cierre["inicio"], cierre["fin"])
        if not conexion:
            continue
        for u, w in aristas_cerradas([cierre]):
            sentido = 1 if (u, w) == (conexion["a"], conexion["b"]) else -1
            for lat, lon, ux, uy in _muestras_trazo(_trazo_dirigido(conexion, sentido)):
                celda = (round(lat / 0.0001), round(lon / 0.0001))
                indice.setdefault(celda, []).append((lat, lon, ux, uy))
    return indice


def _reutiliza_geometria_cerrada(path: list, indice: dict,
                                  tolerancia_m: float = 12.0,
                                  minimo_m: float = 24.0) -> bool:
    """Detecta un tramo continuo que coincide con la geometria roja cerrada."""
    if not indice or len(path) < 2:
        return False
    # Se mide la distancia real entre muestras: cerca de los cruces el trazado
    # trae vertices cada pocos metros y contar muestras como pasos de 8 m
    # bloqueaba tramos que solo tocan el cierre al llegar al mismo nodo.
    recorrido_m = 0.0
    anterior = None
    for lat, lon, ux, uy in _muestras_trazo(path):
        base = (round(lat / 0.0001), round(lon / 0.0001))
        coincide = False
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for clat, clon, cux, cuy in indice.get((base[0] + di, base[1] + dj), ()):
                    dx, dy = _delta_xy_m([lat, lon], [clat, clon])
                    misma_direccion = ux * cux + uy * cuy > 0.35
                    if misma_direccion and math.hypot(dx, dy) <= tolerancia_m:
                        coincide = True
                        break
                if coincide:
                    break
            if coincide:
                break
        if not coincide:
            recorrido_m, anterior = 0.0, None
            continue
        if anterior is not None:
            recorrido_m += math.hypot(*_delta_xy_m(anterior, [lat, lon]))
        anterior = [lat, lon]
        if recorrido_m >= minimo_m:
            return True
    return False


def _aristas_para_rutas(red: dict, promedios: dict,
                        cierres: list | tuple | None = None) -> dict:
    """Arma una sola vez las aristas dirigidas y sus costos de viaje."""
    bloqueadas = aristas_cerradas(cierres)
    geometrias_cerradas = _indice_geometrias_cerradas(red, cierres)
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
            if (d is None or not _sentido_habilitado(c, sentido)
                    or (u, w) in bloqueadas
                    or _reutiliza_geometria_cerrada(
                        _trazo_dirigido(c, sentido), geometrias_cerradas)):
                continue
            retardo = _retardo_arista_s(c, sentido, w, red)
            aristas.setdefault(u, []).append({
                "hacia": w, "d": d, "t": d / (v / 3.6) + retardo,
                "t_libre": ((d / (v_libre / 3.6) if not pd.isna(v_libre)
                              else d / (v / 3.6)) + retardo),
                "retardo_s": retardo,
                "conexion": c, "sentido": sentido,
                "v": v, "v_libre": v_libre,
            })
    return aristas


def _ajustar_arista_extremos(arista: dict, origen: str, destino: str,
                              u: str, red: dict) -> dict:
    """Recorta el rodeo inicial/final de una arista y recalcula su costo."""
    w = arista["hacia"]
    ajustar_inicio, ajustar_fin = u == origen, w == destino
    path = _trazo_dirigido(arista["conexion"], arista["sentido"])
    puntos = red.get("puntos", {})
    if (len(path) < 2 or (ajustar_inicio and origen not in puntos)
            or (ajustar_fin and destino not in puntos)
            or not (ajustar_inicio or ajustar_fin)):
        return arista

    total_geom = _longitud_trazo_m(path)
    if total_geom <= 0:
        return arista
    if ajustar_inicio:
        anclas_inicio = _anclas_extremo(path, puntos[origen], True)
        inicio_base = anclas_inicio[0]
    else:
        inicio_base = _ancla_base(path, path[0], True)
        anclas_inicio = [inicio_base]
    if ajustar_fin:
        anclas_fin = _anclas_extremo(path, puntos[destino], False)
        fin_base = anclas_fin[0]
    else:
        fin_base = _ancla_base(path, path[-1], False)
        anclas_fin = [fin_base]

    opciones = []
    for ancla_inicio in anclas_inicio:
        for ancla_fin in anclas_fin:
            recorrido = ancla_fin["progreso_m"] - ancla_inicio["progreso_m"]
            if recorrido <= 1.0:
                continue
            acceso = ((ancla_inicio["acceso_m"] if ajustar_inicio else 0.0)
                      + (ancla_fin["acceso_m"] if ajustar_fin else 0.0))
            opciones.append((recorrido + FACTOR_ACCESO * acceso,
                             recorrido, acceso, ancla_inicio, ancla_fin))
    if not opciones:
        return arista
    opciones.sort(key=lambda x: (x[0], x[1], x[2]))
    mejor = opciones[0]
    base = next((x for x in opciones
                 if x[3] is inicio_base and x[4] is fin_base), opciones[-1])
    # Un ahorro pequeño puede ser ruido de la geometria simplificada. En ese
    # caso se conserva el anclaje original y solo se suma su acceso lateral.
    if base[0] - mejor[0] < AHORRO_MIN_M:
        mejor = base
    _, recorrido_geom, acceso_m, ancla_inicio, ancla_fin = mejor
    distancia_via = arista["d"] * recorrido_geom / total_geom
    velocidad = arista["v"]
    velocidad_libre = arista["v_libre"]
    if pd.isna(velocidad_libre):
        velocidad_libre = velocidad
    tiempo_acceso = acceso_m / (VELOCIDAD_ACCESO_KMH / 3.6)
    ajustada = {
        **arista,
        "d": distancia_via + acceso_m,
        "t": distancia_via / (velocidad / 3.6) + tiempo_acceso + arista["retardo_s"],
        "t_libre": (distancia_via / (velocidad_libre / 3.6)
                     + tiempo_acceso + arista["retardo_s"]),
        "path_ajustado": _recortar_trazo(path, ancla_inicio, ancla_fin),
        "acceso_m": acceso_m,
        "recorte_m": max(0.0, arista["d"] - distancia_via),
    }
    if ajustar_inicio:
        ajustada["punto_origen"] = ancla_inicio["punto"]
        ajustada["calzada_origen_ajustada"] = ancla_inicio is not inicio_base
    if ajustar_fin:
        ajustada["punto_destino"] = ancla_fin["punto"]
        ajustada["calzada_destino_ajustada"] = ancla_fin is not fin_base
    return ajustada


def _ajustar_extremos(aristas: dict, origen: str, destino: str, red: dict) -> dict:
    """Aplica el anclaje de calzada a las aristas que salen/llegan al viaje."""
    return {
        u: [_ajustar_arista_extremos(a, origen, destino, u, red) for a in salidas]
        for u, salidas in aristas.items()
    }


def _dijkstra_pasos(origen: str, destino: str, aristas: dict, red: dict,
                     anterior_inicial: str | None = None,
                     nodos_bloqueados: set | None = None,
                     aristas_bloqueadas: set | None = None):
    """Dijkstra reutilizable para el camino principal y los desvíos de Yen."""
    nodos_bloqueados = nodos_bloqueados or set()
    aristas_bloqueadas = aristas_bloqueadas or set()
    giros_restringidos = _giros_restringidos(red)
    penalizaciones_giro = _penalizaciones_giro(red)
    inicio = (anterior_inicial, origen)
    tiempos, previo = {inicio: 0.0}, {}
    cola = [(0.0, anterior_inicial or "", origen)]
    estado_final = None
    while cola:
        t, anterior_orden, u = heapq.heappop(cola)
        anterior = anterior_orden or None
        estado = (anterior, u)
        if t > tiempos.get(estado, float("inf")):
            continue
        if u == destino:
            estado_final = estado
            break
        for a in aristas.get(u, []):
            w = a["hacia"]
            if (w in nodos_bloqueados or (u, w) in aristas_bloqueadas
                    or (anterior is not None
                        and (anterior, u, w) in giros_restringidos)):
                continue
            siguiente = (u, w)
            retardo_giro = penalizaciones_giro.get((anterior, u, w), 0.0)
            nuevo = t + a["t"] + retardo_giro
            if nuevo < tiempos.get(siguiente, float("inf")):
                tiempos[siguiente] = nuevo
                previo[siguiente] = (estado, {**a, "retardo_giro_s": retardo_giro})
                heapq.heappush(cola, (nuevo, u, w))
    if estado_final is None:
        return None
    pasos, estado = [], estado_final
    while estado != inicio:
        estado, arista = previo[estado]
        pasos.append(arista)
    return list(reversed(pasos))


def _resumir_pasos(origen: str, pasos: list) -> dict:
    """Convierte una secuencia de aristas en el formato público de ruta."""
    resumen = {
        "nodos": [origen] + [p["hacia"] for p in pasos],
        "tramos": [(p["conexion"], p["sentido"]) for p in pasos],
        "trazos": [p.get("path_ajustado") or _trazo_dirigido(
            p["conexion"], p["sentido"]) for p in pasos],
        "dist_m": sum(p["d"] for p in pasos),
        "tiempo_s": sum(p["t"] + p.get("retardo_giro_s", 0) for p in pasos),
        "tiempo_libre_s": sum(
            p["t_libre"] + p.get("retardo_giro_s", 0) for p in pasos),
        "retardo_s": sum(
            p.get("retardo_s", 0) + p.get("retardo_giro_s", 0) for p in pasos),
        "acceso_m": sum(p.get("acceso_m", 0) for p in pasos),
        "recorte_m": sum(p.get("recorte_m", 0) for p in pasos),
        "_pasos": pasos,
    }
    if pasos and pasos[0].get("punto_origen"):
        resumen["punto_origen"] = pasos[0]["punto_origen"]
        resumen["calzada_origen_ajustada"] = pasos[0].get(
            "calzada_origen_ajustada", False)
    if pasos and pasos[-1].get("punto_destino"):
        resumen["punto_destino"] = pasos[-1]["punto_destino"]
        resumen["calzada_destino_ajustada"] = pasos[-1].get(
            "calzada_destino_ajustada", False)
    return resumen


def rutas_mas_rapidas(origen: str, destino: str, red: dict, promedios: dict,
                       cantidad: int = 3,
                       cierres: list | tuple | None = None) -> list:
    """
    Devuelve hasta ``cantidad`` caminos simples y distintos, ordenados por
    tiempo. Usa Yen sobre el mismo costo dirigido de Dijkstra, por lo que
    conserva sentidos, giros, retardos, cierres y velocidades filtradas.
    """
    if not origen or not destino or origen == destino or cantidad < 1:
        return []
    aristas = _aristas_para_rutas(red, promedios, cierres)
    aristas = _ajustar_extremos(aristas, origen, destino, red)
    primeros_pasos = _dijkstra_pasos(origen, destino, aristas, red)
    if primeros_pasos is None:
        return []

    rutas = [_resumir_pasos(origen, primeros_pasos)]
    secuencias_aceptadas = {tuple(rutas[0]["nodos"])}
    candidatos, secuencias_candidatas = [], set()
    orden = 0

    while len(rutas) < cantidad:
        base = rutas[-1]
        for i in range(len(base["nodos"]) - 1):
            raiz_nodos = base["nodos"][:i + 1]
            raiz_pasos = base["_pasos"][:i]
            aristas_bloqueadas = {
                (ruta["nodos"][i], ruta["nodos"][i + 1])
                for ruta in rutas
                if len(ruta["nodos"]) > i + 1
                and ruta["nodos"][:i + 1] == raiz_nodos
            }
            desvio = _dijkstra_pasos(
                raiz_nodos[-1], destino, aristas, red,
                anterior_inicial=raiz_nodos[-2] if len(raiz_nodos) > 1 else None,
                nodos_bloqueados=set(raiz_nodos[:-1]),
                aristas_bloqueadas=aristas_bloqueadas,
            )
            if desvio is None:
                continue
            pasos = raiz_pasos + desvio
            candidata = _resumir_pasos(origen, pasos)
            secuencia = tuple(candidata["nodos"])
            if (len(secuencia) != len(set(secuencia))
                    or secuencia in secuencias_aceptadas
                    or secuencia in secuencias_candidatas):
                continue
            orden += 1
            heapq.heappush(
                candidatos, (candidata["tiempo_s"], secuencia, orden, candidata))
            secuencias_candidatas.add(secuencia)

        if not candidatos:
            break
        _, secuencia, _, elegida = heapq.heappop(candidatos)
        secuencias_candidatas.discard(secuencia)
        rutas.append(elegida)
        secuencias_aceptadas.add(secuencia)
    return rutas


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
    rutas = rutas_mas_rapidas(origen, destino, red, promedios, 1, cierres)
    return rutas[0] if rutas else None


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


def _trazos_de_ruta(ruta: dict, puntos: dict, por_via: bool) -> list:
    """Geometrias de una ruta, con los extremos recortados cuando aplica."""
    if por_via and len(ruta.get("trazos", [])) == len(ruta["tramos"]):
        return ruta["trazos"]
    return [_trazo(conexion, puntos, por_via, sentido)
            for conexion, sentido in ruta["tramos"]]


def construir_mapa_red(df: pd.DataFrame, red: dict, promedios: dict, metrica: str,
                       metrica_label: str, clasificar_ratio, mostrar_conexiones: bool,
                       por_via: bool, ruta=None, en_vivo: bool = False,
                       corredores=None, rutas=None,
                       ruta_seleccionada: int = 0) -> folium.Map:
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
    rutas_mapa = rutas or ([ruta] if ruta else [])
    ruta_seleccionada = min(max(ruta_seleccionada, 0), len(rutas_mapa) - 1) if rutas_mapa else 0
    ruta_activa = rutas_mapa[ruta_seleccionada] if rutas_mapa else None
    resaltar = bool(rutas_mapa or corredores)

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

    if not rutas_mapa:
        mapa_nodos.agregar_nodos(m, df, metrica, escala, clasificar_ratio, en_vivo)
    else:
        # Las rutas no elegidas quedan visibles para comparar; la seleccionada
        # se dibuja al final, con mayor grosor y sus nodos encima.
        en_ruta = df["id_nodo"].isin(ruta_activa["nodos"])
        mapa_nodos.agregar_nodos(m, df[~en_ruta], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="atenuado")
        capa_ruta = folium.FeatureGroup(name="Rutas alternativas", control=False).add_to(m)
        orden_rutas = [i for i in range(len(rutas_mapa)) if i != ruta_seleccionada]
        orden_rutas.append(ruta_seleccionada)
        for indice in orden_rutas:
            opcion = rutas_mapa[indice]
            color = COLORES_RUTAS[indice % len(COLORES_RUTAS)]
            if indice == ruta_seleccionada:
                for trazado in _trazos_de_ruta(opcion, puntos, por_via):
                    folium.PolyLine(
                        trazado,
                        color=COLOR_BORDE_RUTA, weight=12, opacity=0.9,
                    ).add_to(capa_ruta)
            for trazado in _trazos_de_ruta(opcion, puntos, por_via):
                folium.PolyLine(
                    trazado,
                    color=color,
                    weight=7 if indice == ruta_seleccionada else 4,
                    opacity=1 if indice == ruta_seleccionada else 0.48,
                    tooltip=f"Ruta {indice + 1}",
                ).add_to(capa_ruta)
        mapa_nodos.agregar_nodos(m, df[en_ruta], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="resaltado")

        etiquetas = ["recomendada", "segunda alternativa", "tercera alternativa"]
        items = "".join(
            f'<div style="margin:4px 0"><span style="display:inline-block;width:24px;'
            f'border-top:5px solid {COLORES_RUTAS[i]};margin-right:7px"></span>'
            f'Ruta {i + 1}: {etiquetas[i]}</div>'
            for i in range(len(rutas_mapa))
        )
        m.get_root().html.add_child(folium.Element(
            '<div style="position:fixed;bottom:28px;left:52px;z-index:9999;'
            'background:white;padding:9px 12px;border-radius:9px;box-shadow:0 2px 8px #0003;'
            f'font:12px Arial;color:#172554">{items}</div>'))

    if ruta_activa:
        color_activo = COLORES_RUTAS[ruta_seleccionada % len(COLORES_RUTAS)]
        for id_nodo, etiqueta in ((ruta_activa["nodos"][0], "Origen"),
                                  (ruta_activa["nodos"][-1], "Destino")):
            coordenada = (ruta_activa.get("punto_origen") if etiqueta == "Origen"
                          else ruta_activa.get("punto_destino")) if por_via else None
            p = ({"lat": coordenada[0], "lon": coordenada[1]}
                 if coordenada else puntos[id_nodo])
            folium.CircleMarker(
                location=[p["lat"], p["lon"]], radius=14, color=color_activo, weight=4,
                fill=False, tooltip=folium.Tooltip(etiqueta, permanent=True),
            ).add_to(m)
        ids_rutas = {n for opcion in rutas_mapa for n in opcion["nodos"]}
        en_rutas = df[df["id_nodo"].isin(ids_rutas)]
        return mapa_nodos.terminar_mapa(m, en_rutas["lat"], en_rutas["lon"],
                                        encuadrar_todos=True)
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
    ids_ruta_alt = set(ruta_alternativa["nodos"]) if ruta_alternativa else set()
    ids_nodos_superiores = ids_ruta_alt or ids_destacados
    en_superior = df["id_nodo"].isin(ids_nodos_superiores)
    if ids_nodos_superiores:
        mapa_nodos.agregar_nodos(m, df[~en_superior], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="atenuado")

    if ruta_normal:
        capa_normal = folium.FeatureGroup(name="Ruta sin cierres", control=False).add_to(m)
        for trazado in _trazos_de_ruta(ruta_normal, puntos, por_via):
            folium.PolyLine(
                trazado, color=COLOR_RUTA_NORMAL,
                weight=6, opacity=0.75, dash_array="10 8", tooltip="Ruta sin cierres",
            ).add_to(capa_normal)

    if ruta_alternativa:
        capa_alt = folium.FeatureGroup(name="Ruta alternativa", control=False).add_to(m)
        for color, grosor in ((COLOR_BORDE_RUTA, 13), (COLOR_RUTA, 7)):
            for trazado in _trazos_de_ruta(ruta_alternativa, puntos, por_via):
                folium.PolyLine(
                    trazado, color=color,
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

    # Igual que Origen-Destino en Red de Nodos: los marcadores de todos los
    # nodos de la alternativa se agregan despues de las lineas para que queden
    # visibles directamente encima del trazado.
    if ids_nodos_superiores:
        mapa_nodos.agregar_nodos(m, df[en_superior], metrica, escala, clasificar_ratio,
                                 en_vivo, estilo="resaltado")
    else:
        mapa_nodos.agregar_nodos(m, df, metrica, escala, clasificar_ratio, en_vivo)

    for id_nodo, etiqueta, color in (
            (origen, "Origen", "#22c55e"), (destino, "Destino", "#f59e0b")):
        if id_nodo in puntos:
            ruta_marcadores = ruta_alternativa or ruta_normal or {}
            coordenada = (ruta_marcadores.get("punto_origen") if etiqueta == "Origen"
                          else ruta_marcadores.get("punto_destino")) if por_via else None
            p = ({"lat": coordenada[0], "lon": coordenada[1]}
                 if coordenada else puntos[id_nodo])
            folium.CircleMarker(
                location=[p["lat"], p["lon"]], radius=14, color=color, weight=5,
                fill=False, tooltip=folium.Tooltip(etiqueta, permanent=True),
            ).add_to(m)

    foco = df[df["id_nodo"].isin(ids_destacados)]
    if not foco.empty:
        return mapa_nodos.terminar_mapa(m, foco["lat"], foco["lon"], encuadrar_todos=True)
    return mapa_nodos.terminar_mapa(m, df["lat"], df["lon"])
