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
from src.signals.contratos import validar


def z_robusto(x: pd.Series) -> pd.Series:
    """Conserva índice/nulos; MAD cero o entrada no finita no produce un puntaje."""
    x = pd.to_numeric(x, errors='coerce').astype(float)
    x = x.where(np.isfinite(x))
    validos = x.dropna()
    if validos.empty:
        return pd.Series(np.nan, index=x.index, dtype=float)
    mediana = validos.median()
    mad = (validos - mediana).abs().median()
    if mad == 0:
        return pd.Series(np.nan, index=x.index, dtype=float)
    return 0.6745 * (x - mediana) / mad


def puntuar(um: pd.DataFrame, umbral: float = config.UMBRAL_Z_MAD) -> pd.DataFrame:
    """Transporte usa carga y reparto venta; no sustituye volumen cero ni negativo."""
    if not np.isfinite(umbral) or umbral <= 0:
        raise ValueError('El umbral MAD debe ser positivo y finito')
    df = validar(um, 'unidad_mes')
    for col in ('kg_vendidos', 'kg_transportados', 'gasto_combustible'):
        booleanos = df[col].map(lambda v: isinstance(v, (bool, np.bool_)))
        df[col] = pd.to_numeric(df[col], errors='coerce').astype(float).mask(booleanos)
    volumen = df.kg_vendidos.where(df.rol.eq('reparto'), df.kg_transportados)
    gasto = df.gasto_combustible
    validos = volumen.gt(0) & gasto.gt(0) & np.isfinite(volumen) & np.isfinite(gasto)
    df['kg_base_rol'] = volumen
    ratio = gasto / (volumen.where(validos) / 1000)
    ratio = ratio.where(np.isfinite(ratio) & ratio.gt(0))
    df['soles_comb_por_t'] = ratio
    df['log_combustible_por_t'] = np.log(ratio)
    df['z'] = df.groupby('rol')['log_combustible_por_t'].transform(z_robusto)
    df['puntaje'] = df.z.abs()
    df['alerta_base'] = df.puntaje.gt(umbral).fillna(False)
    df['estado_puntaje'] = np.where(~validos | ratio.isna(), 'sin_combustible_o_volumen_positivo',
                                    np.where(df.z.isna(), 'mad_cero_o_sin_grupo_evaluable', 'evaluable'))
    return df


def precision_at_k(puntaje: pd.Series, y: pd.Series, k: int = config.TOP_K) -> float | None:
    """Utilidad matemática: no convierte etiquetas débiles en revisión documental."""
    if k <= 0 or not puntaje.index.is_unique or not y.index.is_unique:
        raise ValueError('k positivo e índices únicos son obligatorios')
    p = pd.to_numeric(puntaje, errors='coerce')
    top = p[np.isfinite(p)].sort_values(ascending=False, kind='stable').head(k).index
    etiquetas = y.reindex(top)
    if len(top) < k or etiquetas.isna().any():
        return None
    if not etiquetas.isin([0, 1]).all():
        raise ValueError('Las etiquetas deben ser 0 o 1')
    return float(etiquetas.mean())
