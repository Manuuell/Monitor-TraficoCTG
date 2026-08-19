"""
Captura UNA sola vez la geometria (traza real) de cada segmento vial desde
TomTom y la guarda en data/nodos_geometria.json.

La geometria de una calle no cambia entre ejecuciones, por eso se captura
una vez y el dashboard la reutiliza para dibujar las calles coloreadas
segun el ratio de congestion de cada momento (incluido el historico).

Uso (en un VPS con clave API, o local con TOMTOM_API_KEY):
    cd /home/ubuntu/proyect_r
    source venv/bin/activate
    set -a; source .env; set +a
    python3 capturar_geometria.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import config
import descargar_trafico as dt

OUT = config.BASE_DIR / "data" / "nodos_geometria.json"


def main() -> int:
    if not config.API_KEY:
        print("ERROR: TOMTOM_API_KEY no configurada.")
        return 1

    print("Cargando catalogo de nodos...")
    nodos = dt.cargar_nodos(config.NODOS_PATH)
    total = len(nodos)
    print(f"Nodos a consultar: {total}")

    geo = {}
    ok = 0
    for idx, n in nodos.iterrows():
        resp = dt.consultar_flow(n["lat"], n["lon"], config.API_KEY)
        if resp["ok"] and resp["data"]:
            fsd = resp["data"].get("flowSegmentData", {}) or {}
            coords = (fsd.get("coordinates", {}) or {}).get("coordinate", []) or []
            # Convertir a formato [lon, lat] que usa el mapa
            path = [[c["longitude"], c["latitude"]] for c in coords
                    if "longitude" in c and "latitude" in c]
            if path:
                geo[str(n["id_nodo"])] = {
                    "nombre": n.get("nombre_nodo"),
                    "categoria": n.get("categoria"),
                    "zona": n.get("zona"),
                    "path": path,
                }
                ok += 1
        time.sleep(0.05)
        if (idx + 1) % 20 == 0:
            print(f"  Progreso: {idx + 1}/{total} ({ok} con geometria)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)

    print(f"\nListo. Geometrias guardadas: {ok}/{total}")
    print(f"Archivo: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
