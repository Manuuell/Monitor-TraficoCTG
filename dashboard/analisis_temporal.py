"""Calculos reproducibles para la vista de analisis temporal.

La unidad estadistica de los graficos es una ejecucion del ETL, no una fila.
Primero se consolida cada nodo dentro de la ejecucion y despues se calcula el
promedio espacial de los nodos seleccionados. Asi una fila duplicada o una
ejecucion con mas nodos validos no recibe mas peso que las demas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


METRICAS = {
    "Velocidad actual (km/h)": {
        "columna": "currentSpeed",
        "unidad": "km/h",
        "decimales": 1,
        "sentido": "alto_mejor",
    },
    "Velocidad de flujo libre (km/h)": {
        "columna": "freeFlowSpeed",
        "unidad": "km/h",
        "decimales": 1,
        "sentido": "alto_mejor",
    },
    "Índice de fluidez (0–1)": {
        "columna": "velocidad_ratio",
        "unidad": "índice",
        "decimales": 2,
        "sentido": "alto_mejor",
    },
    "Retraso (s)": {
        "columna": "delay_abs_seg",
        "unidad": "s",
        "decimales": 1,
        "sentido": "bajo_mejor",
    },
    "Retraso relativo (%)": {
        "columna": "delay_rel_pct",
        "unidad": "%",
        "decimales": 1,
        "sentido": "bajo_mejor",
    },
}

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
TIPOS_DIA = ["Todos", "Días laborables (L–V)", "Fin de semana", "Quincena"] + DIAS


def _mascara_ok(df: pd.DataFrame) -> pd.Series:
    """Acepta booleanos y las representaciones usadas por Sheets/PostgreSQL."""
    if "ok" not in df.columns:
        return pd.Series(True, index=df.index, dtype=bool)
    return df["ok"].astype(str).str.strip().str.lower().isin(["true", "1"])


def filtrar_mediciones(
    df: pd.DataFrame,
    columna_metrica: str,
    fecha_ini=None,
    fecha_fin=None,
    hora_ini: int = 0,
    hora_fin: int = 23,
    mes: int | None = None,
    tipo_dia: str = "Todos",
    ids: tuple = (),
) -> pd.DataFrame:
    """Devuelve solo observaciones validas que cumplen todos los filtros."""
    requeridas = {"consultation_time", columna_metrica}
    if df.empty or not requeridas.issubset(df.columns):
        return pd.DataFrame(columns=list(df.columns))

    datos = df.copy()
    datos["consultation_time"] = pd.to_datetime(
        datos["consultation_time"], errors="coerce"
    )
    datos[columna_metrica] = pd.to_numeric(datos[columna_metrica], errors="coerce")
    ts = datos["consultation_time"]
    valores = datos[columna_metrica]
    mascara = _mascara_ok(datos) & ts.notna() & valores.notna()
    mascara &= pd.Series(np.isfinite(valores), index=datos.index)
    mascara &= ts.dt.hour.between(int(hora_ini), int(hora_fin))

    if fecha_ini is not None:
        mascara &= ts.dt.date >= fecha_ini
    if fecha_fin is not None:
        mascara &= ts.dt.date <= fecha_fin
    if mes is not None:
        mascara &= ts.dt.month == int(mes)
    if ids and "id_nodo" in datos.columns:
        mascara &= datos["id_nodo"].astype(str).isin([str(i) for i in ids])

    weekday = ts.dt.weekday
    if tipo_dia == "Días laborables (L–V)":
        mascara &= weekday < 5
    elif tipo_dia == "Fin de semana":
        mascara &= weekday >= 5
    elif tipo_dia == "Quincena":
        mascara &= (ts.dt.day == 15) | ts.dt.is_month_end
    elif tipo_dia in DIAS:
        mascara &= weekday == DIAS.index(tipo_dia)

    return datos.loc[mascara].copy()


def serie_por_ejecucion(df: pd.DataFrame, columna_metrica: str) -> pd.DataFrame:
    """Promedio espacial por ejecucion, neutralizando duplicados por nodo."""
    columnas = ["consultation_time", "valor", "n_nodos"]
    if df.empty:
        return pd.DataFrame(columns=columnas)

    datos = df[["consultation_time", columna_metrica] + (
        ["id_nodo"] if "id_nodo" in df.columns else []
    )].copy()
    if "id_nodo" not in datos.columns:
        datos["id_nodo"] = datos.index.astype(str)
    datos["id_nodo"] = datos["id_nodo"].astype(str)

    por_nodo = (
        datos.groupby(["consultation_time", "id_nodo"], as_index=False)
        .agg(valor_nodo=(columna_metrica, "mean"))
    )
    return (
        por_nodo.groupby("consultation_time", as_index=False)
        .agg(valor=("valor_nodo", "mean"), n_nodos=("id_nodo", "nunique"))
        .sort_values("consultation_time")
        .reset_index(drop=True)[columnas]
    )


def resumen_por_hora(serie: pd.DataFrame) -> pd.DataFrame:
    """Media, mediana y dispersion entre ejecuciones para cada hora."""
    columnas = ["hora", "promedio", "mediana", "p25", "p75", "ejecuciones", "nodos_promedio"]
    if serie.empty:
        return pd.DataFrame(columns=columnas)
    datos = serie.copy()
    datos["hora"] = datos["consultation_time"].dt.hour
    return (
        datos.groupby("hora", as_index=False)
        .agg(
            promedio=("valor", "mean"),
            mediana=("valor", "median"),
            p25=("valor", lambda s: s.quantile(0.25)),
            p75=("valor", lambda s: s.quantile(0.75)),
            ejecuciones=("valor", "size"),
            nodos_promedio=("n_nodos", "mean"),
        )[columnas]
    )


def mapa_calor(serie: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matrices hora x dia de semana para promedio y numero de ejecuciones."""
    horas = list(range(24))
    dias = list(range(7))
    if serie.empty:
        vacia = pd.DataFrame(index=dias, columns=horas, dtype=float)
        return vacia, vacia.copy()

    datos = serie.copy()
    datos["dia_num"] = datos["consultation_time"].dt.weekday
    datos["hora"] = datos["consultation_time"].dt.hour
    promedio = datos.pivot_table(
        index="dia_num", columns="hora", values="valor", aggfunc="mean"
    ).reindex(index=dias, columns=horas)
    conteo = datos.pivot_table(
        index="dia_num", columns="hora", values="valor", aggfunc="size"
    ).reindex(index=dias, columns=horas)
    return promedio, conteo


def tendencia_mensual(serie: pd.DataFrame) -> pd.DataFrame:
    """Tendencia mensual donde cada dia aporta el mismo peso al mes."""
    columnas = ["mes", "promedio", "mediana", "dias", "ejecuciones"]
    if serie.empty:
        return pd.DataFrame(columns=columnas)

    datos = serie.copy()
    datos["fecha"] = datos["consultation_time"].dt.normalize()
    diario = (
        datos.groupby("fecha", as_index=False)
        .agg(valor_dia=("valor", "mean"), ejecuciones_dia=("valor", "size"))
    )
    diario["mes"] = diario["fecha"].dt.to_period("M").dt.to_timestamp()
    return (
        diario.groupby("mes", as_index=False)
        .agg(
            promedio=("valor_dia", "mean"),
            mediana=("valor_dia", "median"),
            dias=("fecha", "nunique"),
            ejecuciones=("ejecuciones_dia", "sum"),
        )[columnas]
    )


def distribucion_por_hora(serie: pd.DataFrame) -> pd.DataFrame:
    """Valores por ejecucion usados por el boxplot; nunca filas crudas."""
    if serie.empty:
        return pd.DataFrame(columns=["hora", "hora_label", "valor", "n_nodos"])
    datos = serie.copy()
    datos["hora"] = datos["consultation_time"].dt.hour
    datos["hora_label"] = datos["hora"].map(lambda h: f"{h:02d}:00")
    return datos[["hora", "hora_label", "valor", "n_nodos"]]
