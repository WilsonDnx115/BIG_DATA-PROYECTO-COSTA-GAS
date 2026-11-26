"""Las señales en Spark disparan sobre los mismos documentos que la versión pandas (F02)."""
import pandas as pd
import pytest

from src.bronze_to_silver import handler
from src.common import lake_io, muestra, rutas, schemas
from src.ingest import internos
from src.signals import senales

SENALES = ("S1", "S4", "S5", "S7", "S8", "S10")


@pytest.fixture()
def silver(lago):
    """Silver de la muestra sintética, leído en pandas (Spark no escribe ni lee archivos aquí)."""
    origen = lago / "entrega"
    muestra.generar(n_unidades=8, semilla=7, destino=origen)
    for a in internos.ingerir(origen, fecha_carga="2026-10-07"):
        handler.procesar_archivo(a)
    leer = lambda *p: lake_io.leer_parquet(rutas.ruta("silver", *p))  # noqa: E731
    return {"compras": leer("compras", "aba_02_ordenes_scop"), "ventas": leer("ventas", "com_19_lineas"),
            "flota": leer("flota", "dis_01_vehiculos"), "maestro": leer("maestro", "red_02_distribuidores")}


def _a_spark(spark, pdf: pd.DataFrame):
    """pandas → Spark por Arrow: la conversión ocurre en la JVM, sin lanzar procesos de Python."""
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return spark.createDataFrame(pdf)


def _documentos(df_pandas, senal):
    return set(df_pandas.loc[df_pandas["senal"] == senal, "documento"].astype(str))


def test_catalogo_tiene_las_12_senales():
    from src.glue import senales_spark

    assert list(senales_spark.CATALOGO) == [f"S{i}" for i in range(1, 13)]
    assert {g for _, g in senales_spark.CATALOGO.values()} <= {"alta", "media", "indicio"}
    assert senales_spark.CATALOGO["S1"][1] == "indicio"


def test_equivalencia_con_pandas(spark, silver):
    from src.glue import senales_spark

    sp = {k: _a_spark(spark, v) for k, v in silver.items()}
    esperado = pd.concat([senales.s1(silver["compras"]), senales.s4(silver["compras"], silver["flota"]),
                          senales.s5(silver["ventas"], silver["maestro"]),
                          senales.s7(silver["compras"], silver["flota"]),
                          senales.s8(silver["ventas"], silver["compras"]), senales.s10(silver["ventas"])])
    obtenido = senales_spark.calcular(sp["compras"], sp["ventas"], sp["flota"], sp["maestro"])

    assert obtenido.columns == schemas.CONTRATOS["fact_alerta"].columnas()
    por_senal = {r["senal"]: r["n"] for r in obtenido.groupBy("senal").count()
                 .withColumnRenamed("count", "n").take(20)}
    for s in SENALES:
        docs = {r["documento"] for r in obtenido.filter(obtenido.senal == s).select("documento").take(10_000)}
        assert docs == _documentos(esperado, s), s
        assert por_senal.get(s, 0) == int((esperado["senal"] == s).sum()), s
    assert por_senal.get("S1", 0) > 0 and por_senal.get("S7", 0) > 0   # la muestra inyecta ambos casos


def test_id_alerta_deterministico(spark, silver):
    from src.glue import senales_spark

    c = _a_spark(spark, silver["compras"])
    a = {r["id_alerta"] for r in senales_spark.s1(c).select("id_alerta").take(1000)}
    b = {r["id_alerta"] for r in senales_spark.s1(c).select("id_alerta").take(1000)}
    assert a == b and all(len(i) == 12 for i in a)
