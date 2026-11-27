"""W06: `fact_balance_planta`, la diferencia no explicada por producto y mes.

Lo que importa de estas pruebas es que nada se rellena solo. Sin stock fisico
`delta_stock_kg` queda nulo, no en cero, y sin merma declarada los kg no
explicados son exactamente la diferencia bruta.
"""
from __future__ import annotations

import datetime as dt

import pytest

from src.glue import balance

ESQUEMA_COMPRAS = ("anio int, mes int, tipo string, kg_glp_e double, kg_glp_g double, "
                   "kg double, monto_usd double, tipo_cambio double, tc_valido boolean")
ESQUEMA_VENTAS = ("anio int, mes int, fecha date, articulo string, es_glp boolean, kg double")

# Un mes: 10 000 kg de envasado comprados y 9 000 vendidos.
COMPRAS = [(2020, 5, None, 10000.0, None, 10000.0, 5000.0, 3.5, True)]
VENTAS = [(2020, 5, dt.date(2020, 5, 10), "GLP ENVASE DE 10 KLG", True, 9000.0)]


@pytest.fixture()
def datos(spark):
    compras = spark.createDataFrame(COMPRAS, ESQUEMA_COMPRAS)
    ventas = spark.createDataFrame(VENTAS, ESQUEMA_VENTAS)
    return compras, ventas


def _fila(df, producto="GLP-E"):
    return next(f for f in df.take(10) if f["producto"] == producto)


def test_sin_stock_ni_merma_lo_no_explicado_es_la_diferencia_bruta(spark, datos):
    compras, ventas = datos

    fila = _fila(balance.construir(spark, compras, ventas, merma_pct=None))

    assert fila["kg_comprados"] == pytest.approx(10000.0)
    assert fila["kg_vendidos"] == pytest.approx(9000.0)
    assert fila["diferencia_bruta_kg"] == pytest.approx(1000.0)
    assert fila["kg_no_explicados"] == pytest.approx(1000.0)
    assert fila["pct_no_explicado"] == pytest.approx(0.1)


def test_con_merma_del_uno_por_ciento_resta_el_uno_por_ciento_de_lo_comprado(spark, datos):
    compras, ventas = datos

    fila = _fila(balance.construir(spark, compras, ventas, merma_pct=0.01))

    assert fila["merma_tecnica_kg"] == pytest.approx(100.0)       # 1 % de 10 000
    assert fila["kg_no_explicados"] == pytest.approx(900.0)       # 1 000 - 100


def test_sin_fuente_de_produccion_el_delta_de_stock_queda_nulo_no_en_cero(spark, datos):
    """Un cero diria que el stock no se movio, y eso no se midio nunca."""
    compras, ventas = datos

    fila = _fila(balance.construir(spark, compras, ventas))

    assert fila["delta_stock_kg"] is None


def test_con_stock_fisico_se_descuenta_la_variacion(spark, datos):
    compras, ventas = datos
    produccion = spark.createDataFrame(
        [("GLP-E", 2020, 5, 300.0, 600.0)],
        "producto string, anio int, mes int, stock_inicial_kg double, stock_final_kg double")

    fila = _fila(balance.construir(spark, compras, ventas, produccion, merma_pct=None))

    assert fila["delta_stock_kg"] == pytest.approx(300.0)         # 600 - 300
    assert fila["kg_no_explicados"] == pytest.approx(700.0)       # 1 000 - 300


def test_produccion_sin_las_columnas_de_stock_falla_con_mensaje_claro(spark, datos):
    compras, ventas = datos
    produccion = spark.createDataFrame([("GLP-E", 2020, 5, 1.0)],
                                       "producto string, anio int, mes int, otra double")

    with pytest.raises(ValueError, match="stock_inicial_kg"):
        balance.construir(spark, compras, ventas, produccion)


def test_el_valor_sale_del_precio_de_compra_del_mes_no_de_una_referencia(spark, datos):
    """5 000 USD x 3.5 / 10 000 kg = 1.75 S/ por kg, medido de la factura."""
    compras, ventas = datos

    fila = _fila(balance.construir(spark, compras, ventas, merma_pct=None))

    assert fila["valor_soles"] == pytest.approx(1000.0 * 1.75)


def test_sin_tipo_de_cambio_valido_el_valor_queda_nulo(spark):
    """No se inventa un precio: el mes sin tipo de cambio no se valoriza."""
    compras = spark.createDataFrame(
        [(2020, 5, None, 10000.0, None, 10000.0, 5000.0, 1.0, False)], ESQUEMA_COMPRAS)
    ventas = spark.createDataFrame(VENTAS, ESQUEMA_VENTAS)

    fila = _fila(balance.construir(spark, compras, ventas, merma_pct=None))

    assert fila["valor_soles"] is None
    assert fila["kg_no_explicados"] == pytest.approx(1000.0)      # el kg si se mide


def test_un_mes_con_compras_y_sin_ventas_queda_marcado_incompleto(spark):
    compras = spark.createDataFrame(COMPRAS, ESQUEMA_COMPRAS)
    ventas = spark.createDataFrame([], ESQUEMA_VENTAS)

    fila = _fila(balance.construir(spark, compras, ventas, merma_pct=None))

    assert fila["mes_completo"] is False
    assert fila["kg_vendidos"] == pytest.approx(0.0)


def test_la_tabla_lleva_las_columnas_del_paquete(spark, datos):
    compras, ventas = datos

    assert balance.construir(spark, compras, ventas).columns == list(balance.COLUMNAS)


def test_escribir_dos_veces_no_duplica_el_mes(spark_iceberg, datos):
    """El MERGE por producto, anio y mes deja una sola fila por llave."""
    compras, ventas = datos
    df = balance.construir(spark_iceberg, compras, ventas)

    balance.escribir(spark_iceberg, df)
    tabla = balance.escribir(spark_iceberg, df)

    filas = spark_iceberg.table(tabla).take(10)
    assert len(filas) == 1
    assert filas[0]["producto"] == "GLP-E"
