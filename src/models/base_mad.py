"""Modelo base: puntaje z robusto (pasos 4.2.2 a 4.2.4).

z = 0.6745·(x − mediana) / MAD, por producto o por grupo; alerta si |z| > 3.5
(Iglewicz y Hoaglin). Se usa mediana/MAD porque unas pocas unidades con
diferencias grandes distorsionarían media y desviación estándar.

Métricas sin etiquetas (Tabla 4.4): precision@20 (validación de la gerencia o,
mientras tanto, etiqueta débil = coincidencia con señal de evidencia alta S1/S8),
% de kg de diferencia cubiertos y alertas por mes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config


def z_robusto(x: pd.Series) -> pd.Series:
    x = x.astype(float)
    mediana = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - mediana)) or 1e-9
    return 0.6745 * (x - mediana) / mad


def puntuar(um: pd.DataFrame, columna: str = "pct_diferencia", grupo: str | None = None,
            umbral: float = config.UMBRAL_Z_MAD) -> pd.DataFrame:
    df = um.copy()
    df["z"] = df.groupby(grupo)[columna].transform(z_robusto) if grupo else z_robusto(df[columna])
    df["puntaje"] = df["z"]                     # solo faltantes (z>0): un sobrante no es pérdida
    df["alerta_base"] = df["z"] > umbral
    return df


def etiqueta_debil(um: pd.DataFrame, alertas: pd.DataFrame, senales=("S1", "S8")) -> pd.Series:
    """1 si la unidad-mes tiene alguna alerta de evidencia alta (declarado en el informe)."""
    a = alertas[alertas["senal"].isin(senales)][["placa_norm", "anio", "mes"]].drop_duplicates()
    a["_y"] = 1
    m = um[["placa_norm", "anio", "mes"]].merge(a, on=["placa_norm", "anio", "mes"], how="left")
    return m["_y"].fillna(0).astype(int).set_axis(um.index)


def precision_at_k(puntaje: pd.Series, y: pd.Series, k: int = config.TOP_K) -> float:
    top = puntaje.sort_values(ascending=False).head(k).index
    return float(y.loc[top].mean()) if len(top) else 0.0


def metricas(df: pd.DataFrame, y: pd.Series, col_alerta: str = "alerta_base",
             col_puntaje: str = "puntaje", k: int = config.TOP_K) -> dict:
    faltante = df["kg_diferencia"].clip(lower=0)
    cubierto = faltante[df[col_alerta]].sum() / faltante.sum() if faltante.sum() else 0.0
    por_mes = df[df[col_alerta]].groupby(["anio", "mes"]).size()
    return {
        f"precision@{k}": round(precision_at_k(df[col_puntaje], y, k), 3),
        "pct_kg_cubiertos": round(float(cubierto), 3),
        "alertas_por_mes_media": round(float(por_mes.mean()) if len(por_mes) else 0.0, 2),
        "alertas_por_mes_max": int(por_mes.max()) if len(por_mes) else 0,
        "alertas_total": int(df[col_alerta].sum()),
        "etiqueta": "debil (S1/S8 evidencia alta) hasta validación de gerencia",
    }


def top_k(df: pd.DataFrame, k: int = config.TOP_K, col: str = "puntaje") -> pd.DataFrame:
    cols = ["placa_norm", "anio", "mes", "kg_comprados", "kg_vendidos", "kg_diferencia",
            "pct_diferencia", col]
    return df.sort_values(col, ascending=False).head(k)[cols]
