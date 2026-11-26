"""W04: esqueleto del job de Gold y MERGE idempotente en Iceberg."""
from __future__ import annotations

import pytest

from src.glue import gold_job, iceberg

LLAVES = ["producto", "anio", "mes"]


class SparkFalso:
    """Solo responde `table()`: basta para comprobar cómo se arma el nombre."""

    def __init__(self):
        self.pedidas = []

    def table(self, nombre):
        self.pedidas.append(nombre)
        return nombre


def test_argumentos_por_defecto_y_los_de_glue():
    a = gold_job.argumentos(["--JOB_NAME", "costagas-gold-conciliacion"])
    assert a.modo == "evento"

    a = gold_job.argumentos(["--modo", "operacion", "--lake_uri", "s3://lago/op"])
    assert (a.modo, a.lake_uri) == ("operacion", "s3://lago/op")


def test_modo_invalido():
    with pytest.raises(SystemExit):
        gold_job.argumentos(["--modo", "otro"])


def test_leer_silver_usa_el_catalogo():
    s = SparkFalso()
    gold_job.leer_silver(s, "compras_glp")
    gold_job.leer_silver(s, "otra_base.ventas_detalle")
    assert s.pedidas == ["costagas_silver.compras_glp", "otra_base.ventas_detalle"]


def test_cada_modo_tiene_su_funcion_y_sus_pendientes():
    assert set(gold_job.DESPACHO) == set(gold_job.MODOS)
    for modo in ("entrenar", "operacion"):       # «evento» ya escribe: necesita Spark
        resumen = gold_job.DESPACHO[modo](None, gold_job.argumentos(["--modo", modo]))
        assert resumen["modo"] == modo
        assert resumen["escrito"] == []
        assert resumen["pendientes"]


def test_el_modo_evento_ya_no_tiene_pendiente_el_mapreduce():
    assert not [p for p in gold_job.PENDIENTES["evento"] if "W05" in p]
    assert [p for p in gold_job.PENDIENTES["evento"] if "W06" in p]


def test_nombre_califica_la_tabla():
    assert iceberg.nombre("fact_alerta") == "glue_catalog.costagas_gold.fact_alerta"
    assert iceberg.nombre("otro.base.tabla") == "otro.base.tabla"


def test_escribir_merge_exige_las_llaves():
    class DF:
        columns = ["producto", "kg"]

    with pytest.raises(ValueError, match="llaves"):
        iceberg.escribir_merge(None, DF(), "fact_balance_planta", ["producto", "anio"])
    with pytest.raises(ValueError, match="al menos una llave"):
        iceberg.escribir_merge(None, DF(), "fact_balance_planta", [])


def _balance(spark, filas):
    return spark.createDataFrame(
        filas, "producto string, anio int, mes int, kg_comprados double"
    )


def test_merge_dos_veces_deja_una_fila_por_llave(spark_iceberg):
    """Idempotencia: reprocesar un mes actualiza su fila, no la duplica."""
    tabla = "fact_balance_planta"
    primera = _balance(spark_iceberg, [("GLP-E", 2020, 1, 100.0), ("GLP-G", 2020, 1, 50.0)])
    iceberg.escribir_merge(spark_iceberg, primera, tabla, LLAVES, base="pruebas")

    segunda = _balance(spark_iceberg, [("GLP-E", 2020, 1, 180.0), ("GLP-E", 2020, 2, 70.0)])
    iceberg.escribir_merge(spark_iceberg, segunda, tabla, LLAVES, base="pruebas")

    completo = iceberg.nombre(tabla, base="pruebas")
    assert spark_iceberg.table(completo).count() == 3          # no se duplico la llave repetida
    fila = (spark_iceberg.table(completo)
            .where("producto = 'GLP-E' AND anio = 2020 AND mes = 1").take(1))
    assert fila[0]["kg_comprados"] == 180.0                    # se actualizo con el valor nuevo


def test_instantanea_actual(spark_iceberg):
    assert iceberg.instantanea_actual(spark_iceberg, "no_existe", base="pruebas") is None
    iceberg.escribir_merge(spark_iceberg, _balance(spark_iceberg, [("GLP-E", 2021, 3, 10.0)]),
                           "fact_instantanea", LLAVES, base="pruebas")
    assert isinstance(iceberg.instantanea_actual(spark_iceberg, "fact_instantanea",
                                                 base="pruebas"), int)
