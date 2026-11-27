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


def test_el_modo_evento_ya_no_tiene_pendiente_el_mapreduce_ni_el_balance():
    for hecho in ("W05", "W06"):
        assert not [p for p in gold_job.PENDIENTES["evento"] if hecho in p]
    assert [p for p in gold_job.PENDIENTES["evento"] if "W07" in p]


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


# --- WR06: las senales de regla dentro del job --------------------------------

TODAS = ("compras", "unidades", "tesoreria", "tc", "unidad_mes", "produccion")


def test_con_todas_las_entradas_se_calculan_las_siete_senales_de_regla():
    calculables, omitidas = gold_job.senales_calculables(set(TODAS))

    assert calculables == list(gold_job.ENTRADAS_SENAL)
    assert omitidas == {}


def test_ninguna_senal_se_pierde_por_el_camino():
    """O se calcula, o queda omitida con su motivo. Nunca desaparece sin decirlo."""
    for disponibles in ((), ("compras",), ("compras", "tc"), TODAS):
        calculables, omitidas = gold_job.senales_calculables(set(disponibles))

        assert set(calculables) | set(omitidas) == set(gold_job.ENTRADAS_SENAL)
        assert not set(calculables) & set(omitidas)
        assert all(omitidas.values()), "una senal omitida sin motivo"


def test_lo_que_falta_hoy_dice_a_quien_le_toca():
    """S7 y S9 esperan el contrato de gastos; S11 no tiene fuente en la entrega."""
    _, omitidas = gold_job.senales_calculables({"compras", "unidades", "tesoreria", "tc"})

    assert set(omitidas) == {"S7", "S9", "S11"}
    assert "gastos.yaml" in omitidas["S7"] and "gastos.yaml" in omitidas["S9"]
    assert "no esta cubierta" in omitidas["S11"]


def test_cada_senal_declarada_existe_en_senales_spark():
    from src.glue import senales_spark

    for senal in gold_job.ENTRADAS_SENAL:
        assert callable(getattr(senales_spark, senal.lower()))


def test_sin_ninguna_entrada_no_se_escribe_una_tabla_vacia():
    """Cero alertas por falta de fuentes se veria igual que cero alertas reales."""
    alertas, omitidas = gold_job.alertas_de_regla({})

    assert alertas is None
    assert set(omitidas) == set(gold_job.ENTRADAS_SENAL)


def test_la_tabla_de_alertas_se_mezcla_por_el_id_y_no_por_la_fecha():
    """Con otra llave, la misma alerta en dos corridas quedaria duplicada."""
    assert gold_job.LLAVE_ALERTA == ("id_alerta",)


def test_lo_que_escribe_el_job_es_el_esquema_del_ddl_de_fact_alerta():
    """El contrato de las senales mas `probabilidad`, que el DDL declara y W11 llena."""
    from src.common import schemas
    from tests.test_ddl_gold import columnas as columnas_ddl
    from tests.test_ddl_gold import ddl

    esperadas = schemas.CONTRATOS["fact_alerta_base"].columnas() + ["probabilidad"]

    assert sorted(columnas_ddl(ddl("fact_alerta"))) == sorted(esperadas)


def test_el_modo_evento_ya_no_tiene_pendiente_el_calculo_de_las_senales():
    pendientes = " ".join(gold_job.PENDIENTES["evento"])

    assert "W12" not in pendientes                 # las alertas de regla ya se escriben
    assert "WR11" in pendientes                    # falta la probabilidad del modelo
    assert "W07" in pendientes                     # y fact_unidad_mes


FILAS_COMPRAS_WR06 = [
    # Dentro de la ventana de S2 (2020). La primera no trae SCOP: la dispara.
    ("PETROPERU SA", "F001", "0000123", "2020-03-02", "", 9000.0, 4500.0, 3.45, "T1A111"),
    ("PETROPERU SA", "F001", "0000124", "2020-03-09", "SCOP-2", 8000.0, 4000.0, 3.47, "T2B222"),
]
ESQUEMA_COMPRAS_WR06 = ("proveedor string, serie string, numero string, fecha_factura date, "
                        "nro_scop string, kg double, monto_usd double, tipo_cambio double, "
                        "placa_norm string")


@pytest.fixture()
def compras_wr06(spark_iceberg):
    import datetime as dt

    from src.glue import interfaces

    filas = [(p, s, n, dt.date.fromisoformat(f), sc, kg, usd, tc, pl)
             for p, s, n, f, sc, kg, usd, tc, pl in FILAS_COMPRAS_WR06]
    return interfaces.compras(spark_iceberg.createDataFrame(filas, ESQUEMA_COMPRAS_WR06))


def test_dos_corridas_no_duplican_una_alerta(spark_iceberg, compras_wr06, lago):
    """La evidencia del WR06: el id determinista mas el MERGE hacen la corrida idempotente."""
    from pyspark.sql import functions as F

    alertas, omitidas = gold_job.alertas_de_regla({"compras": compras_wr06})
    assert "S2" in set(gold_job.ENTRADAS_SENAL) - set(omitidas)
    alertas = alertas.withColumn("probabilidad", F.lit(None).cast("double"))

    iceberg.escribir_merge(spark_iceberg, alertas, gold_job.TABLA_ALERTA, gold_job.LLAVE_ALERTA)
    tabla = iceberg.escribir_merge(spark_iceberg, alertas, gold_job.TABLA_ALERTA,
                                   gold_job.LLAVE_ALERTA)

    filas = spark_iceberg.table(tabla).take(100)
    assert len(filas) == len({f.id_alerta for f in filas})
    assert {f.senal for f in filas} <= {"S2", "S3"}
    assert all(f.probabilidad is None for f in filas)      # la pone el modelo en WR11
    assert all(f.valor_soles is None for f in filas)        # unos kg no son una perdida
