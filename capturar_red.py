"""
Captura UNA sola vez la red vial entre nodos vecinos y la guarda en
data/red_nodos.json, para la vista "Red de Nodos" del dashboard.

De la hoja REDES de nodos.xlsx se toma solo que nodos son vecinos: la matriz
no representa el sentido de circulacion (comparada con las distancias por
via, la mayoria de conexiones marcadas en un solo sentido se recorren igual en
ambos, y varias marcadas en doble sentido no).

La distancia por via en cada sentido y el trazado salen de la Routing API de
TomTom: es el mismo mapa del que salen las velocidades del ETL, y respeta las
calles de un solo sentido. Como control independiente se piden tambien las
distancias de OpenStreetMap (servidor publico de OSRM, 3 consultas). Las
conexiones donde las dos fuentes no coinciden quedan en
data/red_nodos_revision.csv, con enlaces a Google Maps para revisarlas a mano.

Consumo: 2 consultas TomTom por conexion (ida con trazado, vuelta solo
distancia), unas 832 en total, una sola vez. Usa TOMTOM_API_KEYS_RED (mejor
una cuenta aparte, para no gastar el saldo del ETL) o, si esta vacia, las de
TOMTOM_API_KEYS. Con --fuente osrm captura todo con OSRM, sin gastar
creditos. El archivo anterior solo se reemplaza si la captura termina bien.

Uso (en un VPS, o local con un Python que tenga OpenSSL moderno):
    cd /home/ubuntu/proyect_r
    source venv/bin/activate
    set -a; source .env; set +a
    python3 capturar_red.py               # TomTom, con control de OSRM
    python3 capturar_red.py --fuente osrm # solo OSRM
    python3 capturar_red.py --resolver
        # repide con la ruta mas corta las conexiones donde TomTom y OSM no
        # coinciden (2 consultas por conexion)
    python3 capturar_red.py --completar-vuelta
        # agrega a un red_nodos.json existente el trazado de vuelta (path_ba)
        # de las conexiones cuya ida y vuelta difieren; una consulta por cada
        # una, sin repetir lo ya capturado

Cada conexion guarda el trazado de ida (path) y el de vuelta (path_ba): en
calles de un solo sentido el regreso va por otras vias, y dibujarlo
invirtiendo la ida mostraria un camino que no existe.
"""
import argparse
import csv
import itertools
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import config
import descargar_trafico as dt

OSRM = "https://router.project-osrm.org"
TOMTOM = "https://api.tomtom.com/routing/1/calculateRoute"
CABECERAS = {"User-Agent": "UTB-MonitorTrafico/1.0 (investigacion academica)"}
# El servidor publico de OSRM rechaza matrices de mas de ~100 puntos
PUNTOS_POR_GRUPO = 45
# Pausa entre consultas a TomTom (su plan gratuito limita las consultas por segundo)
PAUSA_TOMTOM = 0.25
# Las fuentes "no coinciden" en un sentido si difieren en mas de esto
DIF_MIN_M, DIF_REL = 400, 0.30
OUT = config.BASE_DIR / "data" / "red_nodos.json"
OUT_REVISION = config.BASE_DIR / "data" / "red_nodos_revision.csv"


class SinCreditos(Exception):
    """Ninguna llave de TomTom tiene saldo."""


# ============================================================
# OSRM (OpenStreetMap)
# ============================================================
def _osrm(ruta: str) -> dict:
    r = requests.get(f"{OSRM}/{ruta}", headers=CABECERAS, timeout=60)
    r.raise_for_status()
    datos = r.json()
    if datos.get("code") != "Ok":
        raise RuntimeError(f"OSRM: {datos.get('code')} {datos.get('message', '')}")
    return datos


def _coordenadas(nodos, indices) -> str:
    return ";".join(f"{nodos.at[i, 'lon']:.6f},{nodos.at[i, 'lat']:.6f}" for i in indices)


def matriz_osrm(nodos) -> list:
    """Distancia por via (m) de cada nodo a cada otro segun OpenStreetMap."""
    n = len(nodos)
    grupos = [list(range(i, min(i + PUNTOS_POR_GRUPO, n)))
              for i in range(0, n, PUNTOS_POR_GRUPO)]
    # Cada consulta junta dos grupos: asi todo par de nodos cae en alguna
    pares = list(itertools.combinations(range(len(grupos)), 2)) or [(0, 0)]
    dist = [[None] * n for _ in range(n)]
    for g1, g2 in pares:
        sel = grupos[g1] + (grupos[g2] if g2 != g1 else [])
        datos = _osrm(f"table/v1/driving/{_coordenadas(nodos, sel)}?annotations=distance")
        for a, i in enumerate(sel):
            for b, j in enumerate(sel):
                dist[i][j] = datos["distances"][a][b]
        time.sleep(1)
    return dist


def trazado_osrm(nodos, i: int, j: int) -> list:
    """Puntos [lat, lon] de la ruta por via de i a j (simplificada)."""
    datos = _osrm(f"route/v1/driving/{_coordenadas(nodos, [i, j])}"
                  "?overview=simplified&geometries=geojson")
    return [[round(lat, 5), round(lon, 5)]
            for lon, lat in datos["routes"][0]["geometry"]["coordinates"]]


# ============================================================
# TOMTOM
# ============================================================
class Llaves:
    """Recorre las llaves en orden y salta a la siguiente cuando una se agota."""

    def __init__(self, llaves: list):
        self.llaves, self.actual = list(llaves), 0

    def llave(self) -> str:
        if self.actual >= len(self.llaves):
            raise SinCreditos("todas las llaves de TomTom estan agotadas o rechazadas")
        return self.llaves[self.actual]

    def descartar(self, motivo: str) -> None:
        print(f"  Llave {self.actual + 1}/{len(self.llaves)} descartada: {motivo}")
        self.actual += 1


def _adelgazar(puntos: list, min_m: float = 10) -> list:
    """Quita puntos a menos de min_m del anterior conservado (achica el JSON)."""
    salida = [puntos[0]]
    for p in puntos[1:-1]:
        q = salida[-1]
        dy = (p[0] - q[0]) * 111_320
        dx = (p[1] - q[1]) * 111_320 * math.cos(math.radians(q[0]))
        if math.hypot(dx, dy) >= min_m:
            salida.append(p)
    return salida + [puntos[-1]] if len(puntos) > 1 else salida


def ruta_tomtom(nodos, i: int, j: int, llaves: Llaves, con_trazado: bool,
                tipo: str = "fastest") -> tuple:
    """
    (distancia_m, trazado [lat, lon] o None) de la ruta en auto de i a j.
    tipo: "fastest" (mas rapida) o "shortest" (mas corta; ambas respetan
    los sentidos viales).
    """
    url = (f"{TOMTOM}/{nodos.at[i, 'lat']:.6f},{nodos.at[i, 'lon']:.6f}:"
           f"{nodos.at[j, 'lat']:.6f},{nodos.at[j, 'lon']:.6f}/json")
    params = {
        "travelMode": "car", "routeType": tipo, "traffic": "false",
        "routeRepresentation": "polyline" if con_trazado else "summaryOnly",
    }
    for intento in range(5):
        r = requests.get(url, params={**params, "key": llaves.llave()},
                         headers=CABECERAS, timeout=config.TIMEOUT_SEG)
        if r.status_code == 429:          # demasiadas consultas por segundo
            time.sleep(2 * (intento + 1))
            continue
        if r.status_code in (401, 403):   # sin saldo o llave invalida
            llaves.descartar(f"HTTP {r.status_code} {r.text[:80]}")
            continue
        r.raise_for_status()
        ruta = r.json()["routes"][0]
        trazado = None
        if con_trazado:
            trazado = _adelgazar([[round(p["latitude"], 5), round(p["longitude"], 5)]
                                  for p in ruta["legs"][0]["points"]])
        return ruta["summary"]["lengthInMeters"], trazado
    raise RuntimeError("TomTom no respondio tras 5 intentos")


# ============================================================
# COMPARACION
# ============================================================
def _difieren(d1, d2) -> bool:
    if d1 is None or d2 is None:
        return True
    return abs(d1 - d2) > max(DIF_MIN_M, DIF_REL * min(d1, d2))


def _asimetrica(ab, ba) -> bool:
    """Un sentido exige un rodeo claro frente al otro (calle de un solo sentido)."""
    return max(ab, ba) > 1.5 * min(ab, ba) and abs(ab - ba) > DIF_MIN_M


def motivo_revision(c: dict) -> str:
    """Por que las dos fuentes no coinciden en esta conexion, o '' si coinciden."""
    if not (_difieren(c["d_ab_m"], c["d_ab_osm"]) or _difieren(c["d_ba_m"], c["d_ba_osm"])):
        return ""
    if None in (c["d_ab_osm"], c["d_ba_osm"]):
        return "sin dato de OpenStreetMap"
    tt = _asimetrica(c["d_ab_m"], c["d_ba_m"])
    osm = _asimetrica(c["d_ab_osm"], c["d_ba_osm"])
    if tt != osm:
        return ("TomTom ve un solo sentido, OpenStreetMap doble" if tt
                else "OpenStreetMap ve un solo sentido, TomTom doble")
    return "distancia distinta"


def _enlace_google(nodos, i: int, j: int) -> str:
    return ("https://www.google.com/maps/dir/?api=1&travelmode=driving"
            f"&origin={nodos.at[i, 'lat']:.6f},{nodos.at[i, 'lon']:.6f}"
            f"&destination={nodos.at[j, 'lat']:.6f},{nodos.at[j, 'lon']:.6f}")


def completar_vuelta(llaves) -> int:
    """
    Agrega path_ba (trazado b->a) a las conexiones del JSON existente cuya
    ida y vuelta difieren y aun no lo tienen. En las demas el regreso va por
    la misma via y basta con invertir la ida. Con llaves usa TomTom; sin
    ellas, OSRM.
    """
    if not OUT.exists():
        print(f"ERROR: no existe {OUT}; corre primero la captura completa.")
        return 1
    with open(OUT, encoding="utf-8") as f:
        datos = json.load(f)

    nodos = dt.cargar_nodos(config.NODOS_PATH)
    nodos["id_nodo"] = nodos["id_nodo"].astype(str)
    indice = {id_nodo: i for i, id_nodo in enumerate(nodos["id_nodo"])}

    pendientes = [
        c for c in datos["conexiones"]
        if not c.get("path_ba") and c["a"] in indice and c["b"] in indice
        and _difieren(c["d_ab_m"], c["d_ba_m"])
    ]
    fuente = "TomTom" if llaves else "OSRM"
    print(f"Conexiones con ida y vuelta distintas sin trazado de vuelta: "
          f"{len(pendientes)} ({len(pendientes)} consultas a {fuente})")
    pausa = PAUSA_TOMTOM if llaves else 1
    for k, c in enumerate(pendientes, start=1):
        i, j = indice[c["a"]], indice[c["b"]]
        if llaves:
            _, c["path_ba"] = ruta_tomtom(nodos, j, i, llaves, con_trazado=True)
        else:
            c["path_ba"] = trazado_osrm(nodos, j, i)
        if k % 50 == 0:
            print(f"  Progreso: {k}/{len(pendientes)}")
        time.sleep(pausa)

    datos["vuelta_completada"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Se escribe al final: si se corta, el archivo queda como estaba
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Listo. Trazados de vuelta agregados: {len(pendientes)}")
    print(f"Archivo: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


def lista_revision(conexiones: list, nodos, indice: dict) -> list:
    """Filas del CSV de revision: conexiones donde TomTom y OSM no coinciden."""
    revision = []
    for c in conexiones:
        motivo = motivo_revision(c)
        if motivo:
            i, j = indice[c["a"]], indice[c["b"]]
            revision.append({
                "a": c["a"], "nombre_a": nodos.at[i, "nombre_nodo"],
                "b": c["b"], "nombre_b": nodos.at[j, "nombre_nodo"],
                "tomtom_ab_m": c["d_ab_m"], "tomtom_ba_m": c["d_ba_m"],
                "osm_ab_m": c["d_ab_osm"], "osm_ba_m": c["d_ba_osm"],
                "motivo": motivo,
                "google_maps_ab": _enlace_google(nodos, i, j),
                "google_maps_ba": _enlace_google(nodos, j, i),
            })
    return revision


def escribir_revision(revision: list) -> None:
    with open(OUT_REVISION, "w", encoding="utf-8", newline="") as f:
        campos = list(revision[0]) if revision else ["a", "b", "motivo"]
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(revision)


def resolver_diferencias(llaves) -> int:
    """
    Vuelve a pedir a TomTom, con la ruta MAS CORTA, las conexiones donde no
    coincide con OpenStreetMap. La ruta mas rapida entre dos nodos vecinos a
    veces da un rodeo por avenidas (en las diferencias, TomTom era el mas
    largo en ~80 % de los casos); la mas corta respeta igual los sentidos
    viales, asi que una calle de un solo sentido real sigue mostrando su
    rodeo. Guarda los valores anteriores en d_ab_rapida / d_ba_rapida.
    """
    if not llaves:
        print("ERROR: --resolver necesita llaves de TomTom.")
        return 1
    with open(OUT, encoding="utf-8") as f:
        datos = json.load(f)
    nodos = dt.cargar_nodos(config.NODOS_PATH)
    nodos["id_nodo"] = nodos["id_nodo"].astype(str)
    indice = {id_nodo: i for i, id_nodo in enumerate(nodos["id_nodo"])}

    pendientes = [c for c in datos["conexiones"]
                  if c["a"] in indice and c["b"] in indice and motivo_revision(c)]
    print(f"Conexiones donde TomTom y OpenStreetMap no coinciden: {len(pendientes)} "
          f"({2 * len(pendientes)} consultas a TomTom, ruta mas corta)")
    for k, c in enumerate(pendientes, start=1):
        i, j = indice[c["a"]], indice[c["b"]]
        d_ab, path = ruta_tomtom(nodos, i, j, llaves, con_trazado=True, tipo="shortest")
        time.sleep(PAUSA_TOMTOM)
        d_ba, path_ba = ruta_tomtom(nodos, j, i, llaves, con_trazado=True, tipo="shortest")
        c.setdefault("d_ab_rapida", c["d_ab_m"])
        c.setdefault("d_ba_rapida", c["d_ba_m"])
        c.update(d_ab_m=d_ab, d_ba_m=d_ba, path=path, path_ba=path_ba, tipo_ruta="shortest")
        if k % 25 == 0:
            print(f"  Progreso: {k}/{len(pendientes)}")
        time.sleep(PAUSA_TOMTOM)

    revision = lista_revision(datos["conexiones"], nodos, indice)
    datos["por_revisar"] = len(revision)
    datos["diferencias_resueltas"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Se escribe al final: si se corta, el archivo queda como estaba
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    escribir_revision(revision)
    print(f"\nListo. Antes no coincidian {len(pendientes)}; ahora {len(revision)}.")
    print(f"Archivo: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


# ============================================================
# MAIN
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Captura la red vial entre nodos vecinos.")
    parser.add_argument("--fuente", choices=["tomtom", "osrm"], default="tomtom")
    parser.add_argument("--completar-vuelta", action="store_true",
                        help="solo agrega path_ba a las conexiones asimetricas del JSON existente")
    parser.add_argument("--resolver", action="store_true",
                        help="repide con la ruta mas corta las conexiones donde TomTom y OSM no coinciden")
    args = parser.parse_args()
    fuente = args.fuente
    llaves = None
    if fuente == "tomtom":
        claves = config.API_KEYS_RED or config.API_KEYS
        if not claves:
            print("ERROR: configura TOMTOM_API_KEYS_RED o TOMTOM_API_KEYS (o usa --fuente osrm).")
            return 1
        origen = "TOMTOM_API_KEYS_RED" if config.API_KEYS_RED else "TOMTOM_API_KEYS (saldo del ETL)"
        print(f"Fuente: TomTom con {len(claves)} llave(s) de {origen}")
        llaves = Llaves(claves)

    if args.completar_vuelta:
        return completar_vuelta(llaves)
    if args.resolver:
        return resolver_diferencias(llaves)

    print("Cargando catalogo y conexiones...")
    nodos = dt.cargar_nodos(config.NODOS_PATH)
    nodos["id_nodo"] = nodos["id_nodo"].astype(str)
    indice = {id_nodo: i for i, id_nodo in enumerate(nodos["id_nodo"])}

    conexiones = dt.leer_conexiones(config.NODOS_PATH)
    sin_coords = sorted({x for par in conexiones for x in par if x not in indice})
    conexiones = [(a, b) for a, b in conexiones if a in indice and b in indice]
    print(f"Conexiones: {len(conexiones)} entre {len(nodos)} nodos")
    if sin_coords:
        print(f"  AVISO: en REDES pero no en NODOS (se ignoran): {', '.join(sin_coords)}")

    print("Distancias de OpenStreetMap (OSRM)...")
    osm = matriz_osrm(nodos)

    pausa = PAUSA_TOMTOM if fuente == "tomtom" else 1
    print(f"Ruta de cada conexion con {'TomTom' if llaves else 'OSRM'}...")
    salida = []
    for k, (a, b) in enumerate(conexiones, start=1):
        i, j = indice[a], indice[b]
        d_ab_osm = round(osm[i][j]) if osm[i][j] is not None else None
        d_ba_osm = round(osm[j][i]) if osm[j][i] is not None else None
        if llaves:
            d_ab, path = ruta_tomtom(nodos, i, j, llaves, con_trazado=True)
            time.sleep(pausa)
            d_ba, path_ba = ruta_tomtom(nodos, j, i, llaves, con_trazado=True)
        else:
            d_ab, d_ba, path = d_ab_osm, d_ba_osm, trazado_osrm(nodos, i, j)
            time.sleep(pausa)
            path_ba = trazado_osrm(nodos, j, i)
        salida.append({"a": a, "b": b, "d_ab_m": d_ab, "d_ba_m": d_ba,
                       "d_ab_osm": d_ab_osm, "d_ba_osm": d_ba_osm,
                       "path": path, "path_ba": path_ba})
        if k % 50 == 0:
            print(f"  Progreso: {k}/{len(conexiones)}")
        time.sleep(pausa)

    revision = lista_revision(salida, nodos, indice) if llaves else []

    # Se escribe al final: si la captura se corta, queda el archivo anterior
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "fuente": "TomTom Routing API" if llaves else "OSRM sobre OpenStreetMap",
            "control": "OSRM sobre OpenStreetMap",
            "capturado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "por_revisar": len(revision),
            "conexiones": salida,
        }, f, ensure_ascii=False, separators=(",", ":"))
    if llaves:
        escribir_revision(revision)

    print(f"\nListo. Conexiones: {len(salida)}")
    print(f"Archivo: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    if llaves:
        print(f"No coinciden TomTom y OpenStreetMap en {len(revision)}: {OUT_REVISION}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SinCreditos as e:
        print(f"\nERROR: {e}. No se modifico {OUT}.")
        sys.exit(1)
