"""Señales determinísticas (paso 4.2.1, Tabla 4.3).

Cada señal compara DOS registros del mismo hecho y devuelve filas con el
contrato `fact_alerta`. El grado de evidencia es «alto» cuando el segundo
registro es externo (Osinergmin/SCOP, MTC, SUNAT) y «medio» si es interno.

  S1  placa cargada ≠ facturada                (ABA-02)               alto   H1/H2
  S4  carga > capacidad autorizada del vehículo (ABA-02 × DIS-01)     medio* H1
  S5  entrega > capacidad autorizada del local  (COM-19 × RED-02)     medio* H1
  S7  volumen a unidad no habilitada para GLP   (left_anti DIS-01)    medio  H1
  S8  venta cuyo SCOP no cierra con una compra  (left_anti COM-19)    alto   H1
  S10 precio bajo la mediana del canal          (COM-19)              medio  H4
  (*) «alto» cuando exista el dato externo del MTC / Registro de Hidrocarburos.
"""

from __future__ import annotations
import pandas as pd
from src.common import lake_io, rutas
from src.signals.contratos import validar, leer_entradas
from src.signals.common import COLUMNAS, HITO, cargar_catalogo, _numero, _ventana
from src.signals.s2 import s2
from src.signals.s3 import s3, s3_control
from src.signals.s6 import s6
from src.signals.s7 import s7
from src.signals.s9 import s9
from src.signals.s11 import s11

def calcular(tablas: dict) -> pd.DataFrame:
    requeridas = {'compras', 'tc', 'unidades', 'unidad_mes', 'produccion'}
    if not requeridas <= tablas.keys():
        raise ValueError('Faltan tablas de entrada WP 0.8')
    partes = [s2(tablas['compras']), s3(tablas['compras']), s6(tablas['compras'], tablas['tc']),
              s7(tablas['unidad_mes'], tablas['unidades']), s9(tablas['unidad_mes']), s11(tablas['produccion'])]
    if 'sobrecobros' in tablas:
        partes.append(s3_control(tablas['sobrecobros']))
    no_vacias = [p for p in partes if not p.empty]
    return pd.concat(no_vacias, ignore_index=True) if no_vacias else pd.DataFrame(columns=COLUMNAS)


def calcular_todas() -> pd.DataFrame:
    tablas = leer_entradas()
    control = lake_io.leer_parquet(rutas.ruta('silver', 'control_sobrecobros'))
    if not control.empty:
        tablas['sobrecobros'] = control
    return calcular(tablas)


def evaluabilidad(tablas: dict) -> dict:
    """Distingue ausencia de referencia/procedencia de una regla sin alertas."""
    c = validar(tablas['compras'], 'compras')
    c6 = c.loc[_ventana(c, 'S6')].merge(validar(tablas['tc'], 'tc'), on='fecha', how='left', validate='many_to_one')
    valido_tc = _numero(c6.tc_oficial).gt(0) & _numero(c6.tipo_cambio).gt(0)
    um = validar(tablas['unidad_mes'], 'unidad_mes')
    um = um.loc[_ventana(um, 'S7')].merge(validar(tablas['unidades'], 'unidades'), on='unidad_id', how='left', validate='many_to_one')
    p = validar(tablas['produccion'], 'produccion')
    p = p.loc[_ventana(p, 'S11')]
    numeros = p[['stock_inicial', 'produccion', 'ventas', 'bonificaciones', 'stock_final']].apply(_numero)
    c3 = c.loc[_ventana(c, 'S3')]
    return {
        'S2': {'filas_en_ventana': int(_ventana(c, 'S2').sum())},
        'S3': {'filas_en_ventana': len(c3), 'precios_ausentes_o_no_positivos': int((~_numero(c3.precio_usd_kg).gt(0)).sum()),
               'control_F08_disponible': 'sobrecobros' in tablas},
        'S6': {'filas_en_ventana': len(c6), 'comparables': int(valido_tc.sum()), 'sin_tc_comparable': int((~valido_tc).sum())},
        'S7': {'unidad_mes_en_ventana': len(um), 'habilitacion_desconocida': int(um.habilitada.isna().sum())},
        'S9': {'unidad_mes_en_ventana': len(um), 'nota': 'Ver estado_puntaje; volumen desconocido no equivale a cero.'},
        'S11': {'dias_en_ventana': len(p), 'sin_procedencia_del_stock': int(p.stock_final_es_calculado.isna().sum()),
                'sin_terminos_numericos_completos': int((~numeros.notna().all(axis=1)).sum())},
    }


def resumen(alertas):
    return alertas.groupby('senal').agg(alertas=('id_alerta', 'nunique')).reindex(HITO, fill_value=0).reset_index()


def guardar(alertas):
    destino = rutas.ruta('gold', 'fact_alerta_base')
    if set(alertas) != set(COLUMNAS) or alertas.id_alerta.duplicated().any():
        raise ValueError('Contrato de alertas WP 0.8 inválido')
    lake_io.escribir_parquet(alertas, destino, contrato='fact_alerta_base')
    return destino


if __name__ == '__main__':
    a = calcular_todas()
    guardar(a)
    print(resumen(a).to_string(index=False))
