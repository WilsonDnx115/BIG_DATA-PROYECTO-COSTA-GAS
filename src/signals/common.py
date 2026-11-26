"""Catálogo y salida de alertas WP 0.8; sin campos personales ni pérdidas imputadas."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from src.common import config, schemas

COLUMNAS = schemas.CONTRATOS['fact_alerta_base'].columnas()
HITO = ('S2', 'S3', 'S6', 'S7', 'S9', 'S11')

def cargar_catalogo() -> dict:
    with (Path(__file__).with_name('catalogo.yaml')).open(encoding='utf-8') as f:
        catalogo = yaml.safe_load(f)
    senales = catalogo['senales']
    if set(senales) != {f'S{i}' for i in range(1, 13)} or senales['S8']['estado'] != 'no_resoluble':
        raise ValueError('El catálogo debe declarar S1–S12 y S8 no resoluble')
    for regla in senales.values():
        if not {'descripcion', 'resolucion', 'fuentes', 'ventana', 'estado', 'evidencia', 'hipotesis'} <= regla.keys():
            raise ValueError('Definición de señal incompleta')
    return senales


def _numero(s):
    n = pd.to_numeric(s, errors='coerce').astype(float)
    return n.where(np.isfinite(n)).mask(s.map(lambda v: isinstance(v, (bool, np.bool_))))


def _ventana(df, senal):
    if senal in ('S2', 'S3'):
        f = df.fecha
        return f.between('2020-01-01', '2020-12-31') | f.between('2022-02-01', '2023-08-31')
    if senal == 'S6':
        return df.fecha.between('2022-02-01', '2023-08-31')
    if senal == 'S11':
        return df.fecha.between('2018-10-01', '2018-10-31')
    return df.anio.eq(2020)


def _emitir(df, senal, motivo, puntaje=1.0, tipo='regla', valor=None):
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS)
    regla = cargar_catalogo()[senal]
    out = pd.DataFrame(index=df.index)
    out['senal'], out['tipo'], out['resolucion'] = senal, tipo, regla['resolucion']
    out['fecha'] = df.fecha if 'fecha' in df else pd.to_datetime(dict(year=df.anio, month=df.mes, day=1))
    for col in ('unidad_id', 'rol', 'factura_id', 'codigo_scop'):
        out[col] = df[col] if col in df else None
    out['kg'] = _numero(df.kg) if 'kg' in df else _numero(df.kg_base_rol) if 'kg_base_rol' in df else np.nan
    out['valor_soles'] = valor if valor is not None else np.nan  # no monetizar movimiento como pérdida
    out['puntaje'] = puntaje
    out['grado_evidencia'] = 'alto' if regla['evidencia'] == 'alta' else 'medio'
    out['estado_revision'], out['motivo'] = 'pendiente', motivo
    out['fuentes'] = ','.join(regla['fuentes'])
    out['anio'], out['mes'] = out.fecha.dt.year, out.fecha.dt.month
    claves = ['senal', 'tipo', 'resolucion', 'fecha', 'unidad_id', 'factura_id', 'motivo']
    out['id_alerta'] = [hashlib.sha256(json.dumps([None if pd.isna(v) else str(v) for v in fila],
                            ensure_ascii=False).encode()).hexdigest()[:24] for fila in out[claves].itertuples(index=False, name=None)]
    return out[COLUMNAS].reset_index(drop=True)


