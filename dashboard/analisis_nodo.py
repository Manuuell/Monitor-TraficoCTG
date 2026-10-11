"""Calculos reproducibles para la vista de analisis por nodo.

La unidad estadistica es una ejecucion del ETL para un unico nodo. Si una
ejecucion contiene filas repetidas del nodo, primero se consolidan sus
velocidades y despues se recalcula el indice de fluidez. De esta manera una
fila duplicada no altera los promedios ni la distribucion de congestion.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
TIPOS_DIA = ["Todos", "Días laborables (L–V)", "Fin de semana", "Quincena"] + DIAS
CATEGORIAS = ["Fluido", "Moderado", "Lento", "Congestionado"]


def _mascara_ok(df: pd.DataFrame) -> pd.Series:
    """Acepta booleanos y las representaciones guardadas en Sheets/CSV."""
    if "ok" not in df.columns:
        return pd.Series(True, index=df.index, dtype=bool)
    return df["ok"].astype(str).str.strip().str.lower().isin(["true", "1"])


def _filtrar_tipo_dia(mascara: pd.Series, ts: pd.Series, tipo_dia: str) -> pd.Series:
    weekday = ts.dt.weekday
    if tipo_dia == "Días laborables (L–V)":
        mascara &= weekday < 5
    elif tipo_dia == "Fin de semana":
        mascara &= weekday >= 5
    elif tipo_dia == "Quincena":
        mascara &= (ts.dt.day == 15) | ts.dt.is_month_end
    elif tipo_dia in DIAS:
        mascara &= weekday == DIAS.index(tipo_dia)
    return mascara


def preparar_mediciones(
    df: pd.DataFrame,
    id_nodo: str,
    fecha_ini=None,
    fecha_fin=None,
    tipo_dia: str = "Todos",
) -> pd.DataFrame:
    """Devuelve una fila valida por ejecucion para el nodo seleccionado.

    El indice almacenado no se reutiliza: se calcula otra vez a partir de las
    velocidades ya consolidadas para que todos los graficos usen exactamente
    la misma definicion y precision.
    """
    columnas = [
        "consultation_time", "currentSpeed", "freeFlowSpeed",
        "velocidad_ratio", "delay_abs_seg",
    ]
    requeridas = {"consultation_time", "currentSpeed", "freeFlowSpeed"}
    if df.empty or not requeridas.issubset(df.columns):
        return pd.DataFrame(columns=columnas)

    datos = df.copy()
    datos["consultation_time"] = pd.to_datetime(
        datos["consultation_time"], errors="coerce"
    )
    for columna in ["currentSpeed", "freeFlowSpeed", "delay_abs_seg"]:
        if columna not in datos.columns:
            datos[columna] = np.nan
        datos[columna] = pd.to_numeric(datos[columna], errors="coerce")

    ts = datos["consultation_time"]
    actual = datos["currentSpeed"]
    libre = datos["freeFlowSpeed"]
    mascara = _mascara_ok(datos) & ts.notna() & actual.notna() & libre.notna()
    mascara &= pd.Series(np.isfinite(actual), index=datos.index) & (actual >= 0)
    mascara &= pd.Series(np.isfinite(libre), index=datos.index) & (libre > 0)
    if "id_nodo" in datos.columns:
        mascara &= datos["id_nodo"].astype(str) == str(id_nodo)
    if fecha_ini is not None:
        mascara &= ts.dt.date >= fecha_ini
    if fecha_fin is not None:
        mascara &= ts.dt.date <= fecha_fin
    mascara = _filtrar_tipo_dia(mascara, ts, tipo_dia)

    validas = datos.loc[mascara, [
        "consultation_time", "currentSpeed", "freeFlowSpeed", "delay_abs_seg"
    ]]
    if validas.empty:
        return pd.DataFrame(columns=columnas)

    # En una ejecucion, una fila repetida del mismo nodo solo aporta una vez.
    ejecuciones = (
        validas.groupby("consultation_time", as_index=False)
        .agg(
            currentSpeed=("currentSpeed", "mean"),
            freeFlowSpeed=("freeFlowSpeed", "mean"),
            delay_abs_seg=("delay_abs_seg", "mean"),
        )
        .sort_values("consultation_time")
        .reset_index(drop=True)
    )
    ejecuciones["velocidad_ratio"] = (
        ejecuciones["currentSpeed"] / ejecuciones["freeFlowSpeed"]
    )
    ejecuciones = ejecuciones[
        np.isfinite(ejecuciones["velocidad_ratio"])
    ].copy()
    return ejecuciones[columnas]


def serie_diaria(ejecuciones: pd.DataFrame) -> pd.DataFrame:
    """Serie cronologica: un punto diario resume las ejecuciones de ese dia."""
    columnas = [
        "fecha", "ratio_promedio", "ratio_mediana", "velocidad_promedio",
        "flujo_libre_promedio", "ejecuciones",
    ]
    if ejecuciones.empty:
        return pd.DataFrame(columns=columnas)
    datos = ejecuciones.copy()
    datos["fecha"] = datos["consultation_time"].dt.normalize()
    return (
        datos.groupby("fecha", as_index=False)
        .agg(
            ratio_promedio=("velocidad_ratio", "mean"),
            ratio_mediana=("velocidad_ratio", "median"),
            velocidad_promedio=("currentSpeed", "mean"),
            flujo_libre_promedio=("freeFlowSpeed", "mean"),
            ejecuciones=("velocidad_ratio", "size"),
        )[columnas]
    )


def resumen_por_hora(ejecuciones: pd.DataFrame) -> pd.DataFrame:
    """Patron horario y velocidades; solo devuelve horas observadas."""
    columnas = [
        "hora", "ratio_promedio", "ratio_mediana", "velocidad_promedio",
        "flujo_libre_promedio", "ejecuciones",
    ]
    if ejecuciones.empty:
        return pd.DataFrame(columns=columnas)
    datos = ejecuciones.copy()
    datos["hora"] = datos["consultation_time"].dt.hour
    return (
        datos.groupby("hora", as_index=False)
        .agg(
            ratio_promedio=("velocidad_ratio", "mean"),
            ratio_mediana=("velocidad_ratio", "median"),
            velocidad_promedio=("currentSpeed", "mean"),
            flujo_libre_promedio=("freeFlowSpeed", "mean"),
            ejecuciones=("velocidad_ratio", "size"),
        )[columnas]
    )


def distribucion_congestion(
    ejecuciones: pd.DataFrame,
    umbral_fluido: float = 0.90,
    umbral_moderado: float = 0.75,
    umbral_lento: float = 0.60,
) -> pd.DataFrame:
    """Conteo y porcentaje de ejecuciones en cada nivel de congestion."""
    columnas = ["categoria", "mediciones", "porcentaje"]
    if ejecuciones.empty:
        return pd.DataFrame({
            "categoria": CATEGORIAS,
            "mediciones": [0] * len(CATEGORIAS),
            "porcentaje": [0.0] * len(CATEGORIAS),
        })[columnas]

    ratio = ejecuciones["velocidad_ratio"]
    etiquetas = np.select(
        [
            ratio > umbral_fluido,
            ratio > umbral_moderado,
            ratio > umbral_lento,
        ],
        CATEGORIAS[:3],
        default="Congestionado",
    )
    conteos = pd.Series(etiquetas).value_counts().reindex(CATEGORIAS, fill_value=0)
    total = int(conteos.sum())
    return pd.DataFrame({
        "categoria": CATEGORIAS,
        "mediciones": conteos.astype(int).tolist(),
        "porcentaje": (conteos / total * 100).tolist(),
    })[columnas]
