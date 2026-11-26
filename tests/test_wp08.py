"""Pruebas de WP 0.8 con tablas pequeñas; no generan evidencias reales."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.common import config, lake_io, rutas
from src.models import base_mad, evaluacion_base as ev
from src.signals import senales
from src.signals.contratos import validar, leer_entradas, ENTRADAS


def compras(precios=(100, 100, 120), fechas=None):
    n = len(precios)
    return pd.DataFrame({'factura_id': [f'FACT-{i}' for i in range(n)], 'fecha': fechas or ['2022-02-01'] * n,
                         'proveedor_id': ['PROV-01'] * n, 'codigo_scop': [f'SCOP-{i}' for i in range(n)],
                         'kg': [1000] * n, 'precio_usd_kg': precios, 'tipo_cambio': [3.5] * n})


def unidades_mes(logs=(0, .1, -.1, .2, -.2, 10, -10), rol='reparto'):
    n = len(logs)
    return pd.DataFrame({'unidad_id': [f'{rol}-{i}' for i in range(n)], 'rol': [rol] * n,
                         'anio': [2020] * n, 'mes': [1] * n, 'kg_vendidos': [1000] * n,
                         'kg_transportados': [2000] * n, 'gasto_combustible': 100 * np.exp(logs),
                         'gasto_total': 200 * np.exp(logs)})


def produccion():
    return pd.DataFrame({'fecha': ['2018-10-01', '2018-10-02', '2018-10-03', '2018-10-04'],
                         'stock_inicial': [10, 10, 10, 10], 'produccion': [5, -10, 5, 5],
                         'ventas': [3, 0, 3, 3], 'bonificaciones': [2, 0, 2, 2],
                         'stock_final': [10, 0, 10, 10], 'stock_final_es_calculado': [True, True, False, None]})


def tablas():
    um = unidades_mes()
    u = pd.DataFrame({'unidad_id': um.unidad_id, 'habilitada': [False] + [True] * (len(um) - 1)})
    c = compras(); c.loc[0, 'codigo_scop'] = None
    c.loc[1, 'tipo_cambio'] = 1
    return {'compras': c, 'unidad_mes': um, 'unidades': u, 'produccion': produccion(),
            'tc': pd.DataFrame({'fecha': ['2022-02-01'], 'tc_oficial': [3.5]})}


def test_catalogo_completo_y_s8_no_resoluble():
    cat = senales.cargar_catalogo()
    assert len(cat) == 12
    assert cat['S8']['estado'] == 'no_resoluble'
    assert cat['S12']['implementacion'] == 'wp_0.11_pendiente'
    assert {s for s, d in cat.items() if d['implementacion'] == 'wp_0.8'} == set(senales.HITO)


def test_s2_faltante_repetido_y_ventana():
    c = compras((100, 100, 100, 100, 100), ['2020-01-01'] * 4 + ['2024-04-01'])
    c['codigo_scop'] = [None, '  DUP ', 'DUP', 'OK', None]
    a = senales.s2(c)
    assert set(a.factura_id) == {'FACT-0', 'FACT-1', 'FACT-2'}
    assert a.id_alerta.is_unique
    assert set(a.motivo) == {'compra_sin_scop', 'scop_repetido'}


def test_s3_mediana_pactado_monedas_y_control_manual():
    c = compras()
    a = senales.s3(c)
    assert a.factura_id.tolist() == ['FACT-2']
    assert a.puntaje.iloc[0] == pytest.approx(.2)
    c['precio_pactado_usd_kg'] = [50, np.nan, 120]
    assert senales.s3(c).factura_id.tolist() == ['FACT-0']
    control = pd.DataFrame({'factura_id': ['F-A', 'F-B'], 'fecha': ['2020-01-01'] * 2,
                            'monto_facturado_soles': [120, 90], 'monto_pactado_soles': [100, 100]})
    assert senales.s3_control(control).valor_soles.tolist() == [20]
    assert senales.s3_control(control).motivo.tolist() == ['sobrecobro_control_F08']
    with pytest.raises(ValueError):
        senales.s3_control(control.drop(columns='fecha'))


def test_s6_sin_referencia_no_inventa_tipo_cambio():
    c = compras(fechas=['2022-02-01', '2022-02-02', '2020-01-01'])
    c['tipo_cambio'] = [1, 1, 1]
    tc = pd.DataFrame({'fecha': ['2022-02-01'], 'tc_oficial': [3.5]})
    assert senales.s6(c, tc).factura_id.tolist() == ['FACT-0']
    with pytest.raises(ValueError, match='duplicada'):
        senales.s6(c, pd.concat([tc, tc]))


def test_s7_incluye_gastos_y_no_asume_habilitacion_desconocida():
    um = unidades_mes(logs=(0, 0, 0))
    um[['kg_vendidos', 'kg_transportados', 'gasto_combustible']] = 0
    u = pd.DataFrame({'unidad_id': um.unidad_id, 'habilitada': [False, None, True]})
    a = senales.s7(um, u)
    assert a.unidad_id.tolist() == ['reparto-0']  # gasto total positivo sin venta
    u.loc[0, 'habilitada'] = None
    assert senales.s7(um, u).empty


def test_mad_log_por_rol_y_ambas_colas():
    reparto = unidades_mes()
    transporte = unidades_mes(rol='transporte')
    transporte['gasto_combustible'] *= 10000
    # Cambiar volumen que no corresponde al rol no debe alterar el puntaje.
    reparto['kg_transportados'] = 1e9
    transporte['kg_vendidos'] = 1e9
    p = base_mad.puntuar(pd.concat([reparto, transporte], ignore_index=True))
    assert p.alerta_base.sum() == 4
    assert p.loc[p.alerta_base, 'z'].lt(0).sum() == 2
    assert p.loc[p.rol.eq('reparto'), 'z'].to_numpy() == pytest.approx(p.loc[p.rol.eq('transporte'), 'z'].to_numpy())
    assert p.loc[0, 'soles_comb_por_t'] == 100
    assert p.loc[7, 'soles_comb_por_t'] == 500000


def test_mad_cero_nulos_volumen_y_s9_sin_venta():
    um = unidades_mes(logs=(0, 0, 0, 0, 0))
    um.loc[0, 'kg_vendidos'] = 0
    um.loc[1, 'kg_vendidos'] = None
    um.loc[2, 'gasto_combustible'] = 0
    p = base_mad.puntuar(um)
    assert p.z.isna().all() and not p.alerta_base.any()
    assert senales.s9(um).unidad_id.tolist() == ['reparto-0']
    x = pd.Series([1, 1, np.inf, None], index=[8, 9, 10, 11])
    assert base_mad.z_robusto(x).isna().all()
    assert base_mad.z_robusto(x).index.tolist() == [8, 9, 10, 11]
    with pytest.raises(ValueError):
        base_mad.puntuar(um, umbral=0)


def test_s11_exige_procedencia_calculada_no_solo_residuo_cero():
    a = senales.s11(produccion())
    assert len(a) == 2
    assert set(a.motivo) == {'cierre_calculado_con_ajuste', 'cierre_calculado_sin_medicion_independiente'}
    p = produccion(); p.loc[0, 'stock_inicial'] = 1e9; p.loc[0, 'stock_final'] = 1e9 - 1
    assert len(senales.s11(p)) == 1  # no tolerancia relativa a un stock grande
    p.loc[1, 'stock_final'] = None
    assert senales.s11(p).empty


def test_calcular_seis_senales_ids_estables_sin_s8_s12_y_guardar(lago):
    t = tablas()
    a = senales.calcular(t)
    assert set(a.senal) == set(senales.HITO)
    assert a.id_alerta.is_unique
    assert a.id_alerta.tolist() == senales.calcular(t).id_alerta.tolist()
    assert a.estado_revision.eq('pendiente').all()
    assert a.valor_soles.isna().all()  # no se monetiza movimiento como pérdida
    destino = senales.guardar(a)
    b = lake_io.leer_parquet(destino)
    assert set(b.id_alerta) == set(a.id_alerta)
    assert senales.resumen(a).alertas.sum() == len(a)
    with pytest.raises(ValueError):
        senales.calcular({})


def test_contratos_invalidos_y_lectura_de_silver_gold(lago):
    t = tablas()
    for nombre, df in t.items():
        with pytest.raises(ValueError, match='columnas'):
            validar(df.drop(columns=ENTRADAS[nombre][1][0]), nombre)
        partes, _ = ENTRADAS[nombre]
        lake_io.escribir_parquet(df, rutas.ruta(*partes))
    leidas = leer_entradas()
    assert set(leidas) == set(t)
    assert len(senales.calcular(leidas)) == len(senales.calcular(t))
    assert len(senales.calcular_todas()) == len(senales.calcular(t))
    control = pd.DataFrame({'factura_id': ['F08-TEST'], 'fecha': ['2020-01-01'],
                            'monto_facturado_soles': [120], 'monto_pactado_soles': [100]})
    lake_io.escribir_parquet(control, rutas.ruta('silver', 'control_sobrecobros'))
    con_control = senales.calcular_todas()
    assert len(con_control) == len(senales.calcular(t)) + 1
    assert con_control.loc[con_control.factura_id.eq('F08-TEST'), 'valor_soles'].tolist() == [20]
    um = t['unidad_mes'].copy(); um.loc[0, 'rol'] = 'desconocido'
    with pytest.raises(ValueError, match='rol'):
        validar(um, 'unidad_mes')
    with pytest.raises(ValueError, match='duplicada'):
        validar(pd.concat([t['unidades'], t['unidades']]), 'unidades')


def alertas_revision(n=32):
    base = senales.calcular(tablas()).iloc[[0]]
    a = pd.concat([base] * n, ignore_index=True)
    a['id_alerta'] = [f'ID-{i:03d}' for i in range(n)]
    a['puntaje'] = np.arange(n, dtype=float)
    return a


def test_top20_ciego_control_aleatorio_y_metricas_documentales():
    a = alertas_revision()
    top = ev.priorizar(a)
    ciega, azar = ev.muestra_ciega(a, top)
    assert len(top) == 20 and len(ciega) == 30 and len(azar) == 10
    assert not {'puntaje', 'grado_evidencia', 'seleccion', 'posicion'} & set(ciega)
    assert set(azar).isdisjoint(top.id_alerta)
    assert ev.muestra_ciega(a, top)[1] == azar
    periodos = pd.DataFrame({'anio': [2022, 2022], 'mes': [2, 3]})
    m = ev.metricas(a, top, azar, periodos)
    assert m['precision@20_documental'] is None
    assert m['recuperacion_casos_conocidos'] is None
    assert m['pct_kg_cubiertos'] is None
    assert m['alertas_por_mes'] == {'2022-02': 32, '2022-03': 0}
    revisiones = pd.DataFrame({'id_alerta': ciega.id_alerta, 'confirmada': ciega.id_alerta.isin(top.id_alerta),
                              'revisor_id': 'revisor-independiente', 'evidencia_ref': 'documento-independiente'})
    casos = pd.DataFrame({'caso_id': ['C1', 'C2'], 'id_alerta': [a.id_alerta.iloc[0], 'AUN-NO-DETECTADO'],
                         'confirmado_documentalmente': True, 'revisor_id': 'revisor-independiente',
                         'evidencia_ref': 'control-independiente'})
    diferencias = pd.DataFrame({'caso_id': ['D1', 'D2'], 'id_alerta': [a.id_alerta.iloc[0], None],
                                'kg_diferencia': [30, 70], 'evidencia_ref': 'balance-independiente'})
    m = ev.metricas(a, top, azar, periodos, revisiones, 'autor-modelo', casos, diferencias)
    assert m['precision@20_documental'] == 1
    assert m['tasa_base_control_aleatorio'] == 0
    assert m['recuperacion_casos_conocidos'] == .5
    assert m['pct_kg_cubiertos'] == .3
    revisiones['revisor_id'] = 'AUTOR-MODELO'
    with pytest.raises(ValueError, match='revisor distinto'):
        ev.metricas(a, top, azar, periodos, revisiones, 'autor-modelo')


def test_metricas_incompletas_no_usan_etiquetas_debiles():
    a = alertas_revision(n=2); top = ev.priorizar(a)
    per = pd.DataFrame({'anio': [2022], 'mes': [2]})
    r = pd.DataFrame({'id_alerta': a.id_alerta, 'confirmada': [True, None],
                      'revisor_id': 'otro', 'evidencia_ref': 'segundo-registro'})
    m = ev.metricas(a, top, [], per, r, 'autor')
    assert m['precision@20_documental'] is None and m['top_revisadas'] == 1
    assert base_mad.precision_at_k(pd.Series([2, 1]), pd.Series([1, None]), k=2) is None
    assert base_mad.precision_at_k(pd.Series([2]), pd.Series([1]), k=20) is None
    with pytest.raises(ValueError):
        ev.metricas(a, top, [], per, pd.concat([r, r]), 'autor')
    with pytest.raises(ValueError):
        ev.metricas(a, top, list(top.id_alerta), per)


def test_ejecucion_exporta_sin_falsos_resultados_reales(tmp_path, lago):
    t = tablas()
    t['unidad_mes']['nombre_personal'] = 'DATO-QUE-NO-DEBE-SALIR'
    r = ev.ejecutar(t, 'prueba', tmp_path)
    assert r['tipo_datos'] == 'prueba'
    assert r['estado'] == 'calculado_pendiente_validacion'
    j = json.loads((tmp_path / 'linea_base_tecnica.json').read_text())
    assert j['metricas']['precision@20_documental'] is None
    assert len(pd.read_csv(tmp_path / 'top20_base.csv')) == sum(r['senales'].values())
    assert not {'puntaje', 'grado_evidencia'} & set(pd.read_csv(tmp_path / 'expedientes_revision.csv'))
    assert (tmp_path / 'puntajes_unidad_mes.parquet').exists()
    assert 'nombre_personal' not in pd.read_parquet(tmp_path / 'puntajes_unidad_mes.parquet')
    assert r['evaluabilidad']['S6']['comparables'] == 3
    assert r['evaluabilidad']['S11']['sin_procedencia_del_stock'] == 1
    with pytest.raises(ValueError, match='versionadas'):
        ev.ejecutar(tablas(), 'prueba', config.RAIZ_REPO / 'docs/evidencias')


def test_prerrequisitos_ausentes_no_fabrican_cero(lago):
    with pytest.raises(FileNotFoundError, match='Faltan tablas WP 0.8'):
        leer_entradas()
