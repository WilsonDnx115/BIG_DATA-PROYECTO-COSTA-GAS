"""Interfaz normalizada que WP 0.8 espera de WP 0.2/Gold, no de data/raw."""
from __future__ import annotations

import pandas as pd

from src.common import lake_io, rutas

ENTRADAS = {
    'compras': (('silver', 'compras_glp'), ['factura_id', 'fecha', 'proveedor_id', 'codigo_scop',
                                         'kg', 'precio_usd_kg', 'tipo_cambio']),
    'unidades': (('silver', 'unidades'), ['unidad_id', 'habilitada']),
    'unidad_mes': (('gold', 'fact_unidad_mes'), ['unidad_id', 'rol', 'anio', 'mes', 'kg_vendidos',
                                              'kg_transportados', 'gasto_combustible', 'gasto_total']),
    'produccion': (('silver', 'produccion_diaria'), ['fecha', 'stock_inicial', 'produccion', 'ventas',
                                                  'bonificaciones', 'stock_final', 'stock_final_es_calculado']),
    'tc': (('silver', 'referencia', 'tipo_cambio'), ['fecha', 'tc_oficial']),
}
CLAVES = {'compras': ['factura_id'], 'unidades': ['unidad_id'],
          'unidad_mes': ['unidad_id', 'anio', 'mes'], 'produccion': ['fecha'], 'tc': ['fecha']}
OPCIONALES = {'compras': ['unidad_id', 'rol', 'precio_pactado_usd_kg']}


def validar(df: pd.DataFrame, nombre: str) -> pd.DataFrame:
    """Exige columnas, grano único y fechas/períodos válidos sin imprimir filas."""
    faltan = set(ENTRADAS[nombre][1]) - set(df.columns)
    if faltan:
        raise ValueError(f'{nombre}: faltan columnas del contrato WP 0.8: {sorted(faltan)}')
    permitidas = ENTRADAS[nombre][1] + OPCIONALES.get(nombre, [])
    df = df[[c for c in permitidas if c in df]].copy().reset_index(drop=True)
    if 'fecha' in df:
        df['fecha'] = pd.to_datetime(df.fecha, errors='coerce').dt.normalize()
        if df.fecha.isna().any():
            raise ValueError(f'{nombre}: fecha inválida')
    if df[CLAVES[nombre]].isna().any().any() or df.duplicated(CLAVES[nombre]).any():
        raise ValueError(f'{nombre}: clave ausente o duplicada; revisar el grano de WP 0.2')
    for col in ('factura_id', 'unidad_id', 'proveedor_id'):
        if col in df and df[col].astype('string').str.strip().eq('').any():
            raise ValueError(f'{nombre}: identificador vacío')
    if nombre == 'unidad_mes':
        for c in ('anio', 'mes'):
            v = pd.to_numeric(df[c], errors='coerce')
            if v.isna().any() or v.mod(1).ne(0).any():
                raise ValueError(f'{nombre}: {c} debe ser entero')
            df[c] = v.astype(int)
        if not df.mes.between(1, 12).all() or not df.anio.between(1900, 9999).all():
            raise ValueError('unidad_mes: período inválido')
        if not df.rol.isin(['reparto', 'transporte']).all():
            raise ValueError('unidad_mes: rol debe ser reparto o transporte')
    for c in ('habilitada', 'stock_final_es_calculado'):
        if c in df and not df[c].dropna().map(lambda v: isinstance(v, bool) or type(v).__name__ == 'bool_').all():
            raise ValueError(f'{nombre}: {c} debe ser booleano o nulo')
    return df


def leer_entradas() -> dict[str, pd.DataFrame]:
    """Carga únicamente Silver y Gold; falla si falta una tabla prioritaria."""
    tablas, ausentes = {}, []
    for nombre, (partes, columnas) in ENTRADAS.items():
        try:
            df = lake_io.leer_parquet(rutas.ruta(*partes))
        except FileNotFoundError:
            df = pd.DataFrame()
        if df.empty:
            ausentes.append('/'.join(partes))
        else:
            tablas[nombre] = validar(df, nombre)
    if ausentes:
        raise FileNotFoundError('Faltan tablas WP 0.8 de WP 0.2/Gold: ' + ', '.join(ausentes))
    return tablas
