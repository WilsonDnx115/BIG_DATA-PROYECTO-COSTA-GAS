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


# Ventanas de fecha de cada señal (catálogo, columna «ventana»). Las que no figuran aquí
# se evalúan por año: 2020, el piloto. Lo usan las señales en pandas y en Spark.
VENTANAS_FECHA = {
    'S2': (('2020-01-01', '2020-12-31'), ('2022-02-01', '2023-08-31')),
    'S3': (('2020-01-01', '2020-12-31'), ('2022-02-01', '2023-08-31')),
    'S6': (('2022-02-01', '2023-08-31'),),
    'S11': (('2018-10-01', '2018-10-31'),),
    'S12': (('2022-02-01', '2023-07-31'),),
}
ANIO_VENTANA = 2020

# Grado de evidencia de la señal (dim_senal) → grado que lleva cada alerta.
GRADO_ALERTA = {'alta': 'alto', 'media': 'medio', 'indicio': 'indicio'}


def grado_evidencia(regla: dict) -> str:
    """Grado de evidencia de una señal según el catálogo: «indicio», «alta» o «media».

    Las señales con muestra mínima (S1, S4 y S7: de 2 a 9 casos; informe v16,
    Tablas 4.3 y 5.3) son «indicio» aunque su fuente sea fuerte. Las demás toman la
    evidencia del catálogo; «alta_si_existe_…» cuenta como alta (S8).
    """
    if regla.get('muestra_minima'):
        return 'indicio'
    return 'alta' if str(regla['evidencia']).startswith('alta') else 'media'


def grado_alerta(regla: dict) -> str:
    """Grado con que sale cada alerta de la señal: «alto», «medio» o «indicio»."""
    return GRADO_ALERTA[grado_evidencia(regla)]


def _numero(s):
    n = pd.to_numeric(s, errors='coerce').astype(float)
    return n.where(np.isfinite(n)).mask(s.map(lambda v: isinstance(v, (bool, np.bool_))))


def _ventana(df, senal):
    if senal in VENTANAS_FECHA:
        mascara = pd.Series(False, index=df.index)
        for ini, fin in VENTANAS_FECHA[senal]:
            mascara |= df.fecha.between(ini, fin)
        return mascara
    return df.anio.eq(ANIO_VENTANA)


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
    out['grado_evidencia'] = grado_alerta(regla)
    out['estado_revision'], out['motivo'] = 'pendiente', motivo
    out['fuentes'] = ','.join(regla['fuentes'])
    out['anio'], out['mes'] = out.fecha.dt.year, out.fecha.dt.month
    claves = ['senal', 'tipo', 'resolucion', 'fecha', 'unidad_id', 'factura_id', 'motivo']
    out['id_alerta'] = [hashlib.sha256(json.dumps([None if pd.isna(v) else str(v) for v in fila],
                            ensure_ascii=False).encode()).hexdigest()[:24] for fila in out[claves].itertuples(index=False, name=None)]
    return out[COLUMNAS].reset_index(drop=True)


