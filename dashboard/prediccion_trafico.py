"""Prediccion de velocidades por nodo para la pestaña Simulaciones."""
from __future__ import annotations

from datetime import datetime, time

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


MAX_FILAS_ENTRENAMIENTO = 60000
_NUMERICAS = [
    "hora_sin", "hora_cos", "semana_sin", "semana_cos",
    "anio_sin", "anio_cos", "fin_semana", "vel_libre", "lat", "lon",
]


def _mascara_ok(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.lower().isin(["true", "1"])


def _features(ids, timestamps, vel_libre, lat, lon) -> pd.DataFrame:
    ts = pd.DatetimeIndex(pd.to_datetime(timestamps, errors="coerce"))
    hora = ts.hour + ts.minute / 60
    semana = ts.day_of_week
    dia_anio = ts.day_of_year
    return pd.DataFrame({
        "id_nodo": pd.Series(ids, dtype=str).to_numpy(),
        "hora_sin": np.sin(2 * np.pi * hora / 24),
        "hora_cos": np.cos(2 * np.pi * hora / 24),
        "semana_sin": np.sin(2 * np.pi * semana / 7),
        "semana_cos": np.cos(2 * np.pi * semana / 7),
        "anio_sin": np.sin(2 * np.pi * dia_anio / 365.25),
        "anio_cos": np.cos(2 * np.pi * dia_anio / 365.25),
        "fin_semana": (semana >= 5).astype(int),
        "vel_libre": np.asarray(vel_libre, dtype=float),
        "lat": np.asarray(lat, dtype=float),
        "lon": np.asarray(lon, dtype=float),
    })


def preparar_entrenamiento(historico: pd.DataFrame, catalogo: pd.DataFrame) -> tuple:
    """Limpia el historico y devuelve X, y y la referencia fija por nodo."""
    requeridas = {"id_nodo", "consultation_time", "currentSpeed", "freeFlowSpeed"}
    if historico.empty or not requeridas.issubset(historico.columns):
        raise ValueError("No hay mediciones históricas suficientes para entrenar el modelo.")

    df = historico.copy()
    df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
    for col in ("currentSpeed", "freeFlowSpeed", "lat", "lon"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    mascara = df["consultation_time"].notna()
    if "ok" in df.columns:
        mascara &= _mascara_ok(df["ok"])
    mascara &= df["currentSpeed"].gt(0) & df["freeFlowSpeed"].gt(0)
    df = df.loc[mascara].copy()
    df["id_nodo"] = df["id_nodo"].astype(str)

    cat = catalogo[["id_nodo", "lat", "lon"]].drop_duplicates("id_nodo").copy()
    cat["id_nodo"] = cat["id_nodo"].astype(str)
    if "lat" not in df.columns or "lon" not in df.columns:
        df = df.merge(cat, on="id_nodo", how="left")
    else:
        coordenadas = cat.rename(columns={"lat": "lat_catalogo", "lon": "lon_catalogo"})
        df = df.merge(coordenadas, on="id_nodo", how="left")
        df["lat"] = df["lat"].fillna(df["lat_catalogo"])
        df["lon"] = df["lon"].fillna(df["lon_catalogo"])
    df = df.dropna(subset=["lat", "lon"])
    if len(df) < 500:
        raise ValueError("Se necesitan al menos 500 mediciones válidas para Random Forest.")

    referencia = (
        df.groupby("id_nodo", as_index=False)
        .agg(vel_libre=("freeFlowSpeed", "median"),
             lat=("lat", "median"), lon=("lon", "median"))
    )
    if len(df) > MAX_FILAS_ENTRENAMIENTO:
        df = df.sample(MAX_FILAS_ENTRENAMIENTO, random_state=42)
    X = _features(
        df["id_nodo"], df["consultation_time"], df["freeFlowSpeed"],
        df["lat"], df["lon"],
    )
    y = df["currentSpeed"].astype(float).to_numpy()
    return X, y, referencia


def entrenar_random_forest(historico: pd.DataFrame, catalogo: pd.DataFrame) -> dict:
    """Entrena un Random Forest reproducible y devuelve el modelo y sus metadatos."""
    X, y, referencia = preparar_entrenamiento(historico, catalogo)
    preprocesador = ColumnTransformer([
        ("nodo", OneHotEncoder(handle_unknown="ignore"), ["id_nodo"]),
        ("numericas", StandardScaler(), _NUMERICAS),
    ])
    bosque = RandomForestRegressor(
        n_estimators=80,
        max_depth=18,
        min_samples_leaf=3,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
    )
    pipeline = Pipeline([("preprocesador", preprocesador), ("modelo", bosque)])
    pipeline.fit(X, y)
    fechas = pd.to_datetime(historico["consultation_time"], errors="coerce").dropna()
    return {
        "pipeline": pipeline,
        "referencia": referencia,
        "filas": len(X),
        "entrenado_desde": fechas.min() if not fechas.empty else None,
        "entrenado_hasta": fechas.max() if not fechas.empty else None,
    }


def predecir_velocidades(modelo: dict, catalogo: pd.DataFrame,
                         fecha, corrida: str) -> pd.DataFrame:
    """Predice velocidad, flujo libre e indice para todos los nodos del catalogo."""
    hora, minuto = map(int, corrida.split(":"))
    instante = datetime.combine(fecha, time(hora, minuto))
    base = catalogo[["id_nodo", "lat", "lon"]].drop_duplicates("id_nodo").copy()
    base["id_nodo"] = base["id_nodo"].astype(str)
    referencia = modelo["referencia"].rename(
        columns={"lat": "lat_modelo", "lon": "lon_modelo"})
    base = base.merge(referencia, on="id_nodo", how="left")
    mediana_libre = float(referencia["vel_libre"].median())
    base["vel_libre"] = base["vel_libre"].fillna(mediana_libre)
    base["lat"] = base["lat"].fillna(base["lat_modelo"])
    base["lon"] = base["lon"].fillna(base["lon_modelo"])
    X = _features(
        base["id_nodo"], [instante] * len(base), base["vel_libre"],
        base["lat"], base["lon"],
    )
    pred = modelo["pipeline"].predict(X)
    limite_superior = np.maximum(base["vel_libre"].to_numpy() * 1.15, 20.0)
    pred = np.clip(pred, 1.0, limite_superior)
    salida = pd.DataFrame({
        "id_nodo": base["id_nodo"],
        "vel_actual": pred,
        "vel_libre": base["vel_libre"].to_numpy(),
        "n": 1,
        "predicho": True,
    })
    salida["ratio"] = salida["vel_actual"] / salida["vel_libre"]
    return salida


def resumir_corrida_real(datos: pd.DataFrame, fecha, corrida: str) -> pd.DataFrame:
    """Promedia solo la corrida exacta seleccionada y conserva todos sus nodos."""
    columnas = ["id_nodo", "vel_actual", "vel_libre", "ratio", "n", "predicho"]
    if datos.empty or "consultation_time" not in datos.columns:
        return pd.DataFrame(columns=columnas)
    hora, minuto = map(int, corrida.split(":"))
    df = datos.copy()
    df["consultation_time"] = pd.to_datetime(df["consultation_time"], errors="coerce")
    for col in ("currentSpeed", "freeFlowSpeed"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    mascara = df["consultation_time"].notna()
    mascara &= df["consultation_time"].dt.date == fecha
    mascara &= df["consultation_time"].dt.hour == hora
    mascara &= df["consultation_time"].dt.minute == minuto
    if "ok" in df.columns:
        mascara &= _mascara_ok(df["ok"])
    df = df.loc[mascara & df["currentSpeed"].gt(0) & df["freeFlowSpeed"].gt(0)].copy()
    if df.empty:
        return pd.DataFrame(columns=columnas)
    salida = (
        df.assign(id_nodo=df["id_nodo"].astype(str))
        .groupby("id_nodo", as_index=False)
        .agg(vel_actual=("currentSpeed", "mean"),
             vel_libre=("freeFlowSpeed", "mean"), n=("id_nodo", "size"))
    )
    salida["ratio"] = salida["vel_actual"] / salida["vel_libre"]
    salida["predicho"] = False
    return salida[columnas]
