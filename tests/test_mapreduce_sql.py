"""W05: patrón MapReduce en Spark SQL y su equivalencia con la versión RDD."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.glue import mapreduce_sql as mr

ESQUEMA_COMPRAS = ("anio int, mes int, kg_glp_e double, kg_glp_g double, "
                   "kg double, tipo string")
ESQUEMA_VENTAS = "anio int, mes int, articulo string, es_glp boolean, kg double"

COMPRAS = [
    (2020, 1, 100.0, None, 100.0, "GLP-E"),
    (2020, 1, None, 50.0, 50.0, "GLP-G"),
    (2020, 1, None, None, 30.0, "GLP-E"),      # 2020: solo kg y tipo
    (2020, 2, 10.0, None, 10.0, "GLP-E"),
]
VENTAS = [
    (2020, 1, "GLP ENVASE DE 10 KLG", True, 40.0),
    (2020, 1, "GLP A GRANEL", True, 20.0),
    (2020, 1, "ARROZ COSTEÑO 5 KG", False, 5.0),   # no es GLP: fuera del balance
    (2020, 1, "GLP 10 KG", True, 0.0),             # sin kg: no emite par
]


def test_el_patron_se_escapa_para_spark_sql():
    assert mr.PATRON_SQL.count(chr(92)) == 2 * mr.PATRON_PRESENTACION.count(chr(92))
    assert "regexp_extract" in mr.SQL_MAPA_VENTAS


def test_la_llave_de_reduccion_es_producto_anio_mes():
    assert mr.LLAVE == ("producto", "anio", "mes")
    assert mr.DESTINO == ("gold", "mr", "balance")


@pytest.fixture()
def datos(spark):
    return (spark.createDataFrame(COMPRAS, ESQUEMA_COMPRAS),
            spark.createDataFrame(VENTAS, ESQUEMA_VENTAS))


def test_el_mapeo_emite_kg_con_signo(spark, datos):
    pares = mr.mapear(spark, *datos)
    filas = {(f.producto, f.anio, f.mes, f.kg_firmado) for f in pares.take(20)}

    assert ("GLP-E", 2020, 1, 100.0) in filas          # compra en positivo
    assert ("GLP-E", 2020, 1, -40.0) in filas          # venta envasada en negativo
    assert ("GLP-G", 2020, 1, -20.0) in filas          # venta a granel
    assert ("GLP-E", 2020, 1, 30.0) in filas           # fila de 2020 con kg y tipo
    assert not [f for f in filas if f[3] == 5.0]       # el arroz no entra
    assert not [f for f in filas if f[3] == 0.0]       # las lineas sin kg tampoco


def test_la_reduccion_agrupa_por_producto_anio_y_mes(spark, datos):
    balance = {(f.producto, f.anio, f.mes): f for f in mr.construir(spark, *datos).take(20)}

    e1 = balance[("GLP-E", 2020, 1)]
    assert (e1.kg_comprados, e1.kg_vendidos, e1.kg_neto, e1.n_lineas) == (130.0, 40.0, 90.0, 3)
    g1 = balance[("GLP-G", 2020, 1)]
    assert (g1.kg_comprados, g1.kg_vendidos, g1.kg_neto) == (50.0, 20.0, 30.0)
    assert balance[("GLP-E", 2020, 2)].kg_neto == 10.0


def test_sql_y_rdd_dan_los_mismos_totales(spark, datos):
    sql = {(f.producto, f.anio, f.mes): f.kg_neto for f in mr.construir(spark, *datos).take(50)}
    rdd = dict(mr.mapear_reducir_rdd(spark, *datos).take(50))

    assert sql == pytest.approx(rdd)


def test_escribe_particionado_por_anio_y_mes(spark, datos, lago):
    destino = mr.escribir(mr.construir(spark, *datos))

    raiz = Path(destino.replace("file:///", ""))
    assert sorted(p.name for p in raiz.glob("anio=*")) == ["anio=2020"]
    assert sorted(p.name for p in (raiz / "anio=2020").glob("mes=*")) == ["mes=1", "mes=2"]
    assert not list(raiz.glob("producto=*"))        # nunca se particiona por producto
