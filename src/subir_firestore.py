"""
Sube el snapshot mas reciente de trafico a Firestore (app TransCaribe).

La app usa estos nodos como fuente de velocidades reales para su motor
propio de tiempos de llegada (posicion GPS del bus + trafico TomTom).

Requiere:
  - firebase-admin (pip install firebase-admin)
  - credenciales/firebase_transcaribe.json  (service account del proyecto
    Firebase de TransCaribe: Consola Firebase > Configuracion del proyecto >
    Cuentas de servicio > Generar nueva clave privada)

El documento escrito es `traffic/latest` (se sobreescribe en cada corrida,
28 escrituras/dia — dentro de la cuota gratuita de Firestore).
"""
import math

import pandas as pd

import config


def _num(val):
    """float o None (maneja NaN de pandas)."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def subir_snapshot(df: pd.DataFrame) -> dict:
    """Sube el snapshot de nodos con datos validos a traffic/latest."""
    if not config.FIREBASE_CRED_FILE.exists():
        return {
            "ok": False,
            "count": 0,
            "error": f"No existe {config.FIREBASE_CRED_FILE}",
        }

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        return {
            "ok": False,
            "count": 0,
            "error": "firebase-admin no instalado (pip install firebase-admin)",
        }

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(str(config.FIREBASE_CRED_FILE))
            firebase_admin.initialize_app(cred)
        db = firestore.client()

        nodes = []
        for _, row in df.iterrows():
            cs = _num(row.get("currentSpeed"))
            lat = _num(row.get("lat"))
            lon = _num(row.get("lon"))
            if not row.get("ok") or cs is None or lat is None or lon is None:
                continue
            nodes.append({
                "id": str(row.get("id_nodo")),
                "lat": lat,
                "lon": lon,
                "cs": cs,                                  # currentSpeed km/h
                "ffs": _num(row.get("freeFlowSpeed")),     # freeFlow km/h
                "ratio": _num(row.get("velocidad_ratio")),
                "closed": bool(row.get("roadClosure") or False),
            })

        if not nodes:
            return {"ok": False, "count": 0, "error": "Sin nodos validos"}

        db.document("traffic/latest").set({
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "consultationTime": str(df["consultation_time"].iloc[0]),
            "vpsId": str(config.VPS_ID),
            "nodeCount": len(nodes),
            "nodes": nodes,
        })
        return {"ok": True, "count": len(nodes), "error": None}
    except Exception as e:  # noqa: BLE001 — no interrumpir el ETL
        return {"ok": False, "count": 0, "error": str(e)}
