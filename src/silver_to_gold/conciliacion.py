"""Job `gold_conciliacion` (paso 3.3.6). Escalado HORIZONTAL con Glue Spark.

La conciliación es un problema Map → Shuffle → Reduce (S3):
  * Map:     cada movimiento → clave (placa_norm, fecha, id_producto), valor (kg…, 1)
  * Shuffle: agrupa por clave; única fase que cruza la red
  * Reduce:  suma kilos y operaciones por clave
`groupBy().agg()` agrega dentro de cada partición antes del shuffle, como el
Combiner de MapReduce o `reduceByKey` frente a `groupByKey` (S3, S4).

Técnicas de S4/S5 aplicadas y verificables con explain():
  partition pruning (filtro por anio), column pruning (select), predicate
  pushdown (filtro por producto), broadcast() de la flota, cache() de la
  conciliación, AQE para el skew. Nunca collect(): se inspecciona con show()/take().

Motores:  --motor spark  (Glue / pyspark local)   --motor pandas  (Lambda / sin JVM)
Ambos producen el mismo contrato `fact_conciliacion_unidad`.

Uso local:  python -m src.silver_to_gold.conciliacion --motor pandas --anio 2020
En Glue:    argumentos --LAKE_URI s3://... --ANIO 2020
"""
from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from src.common import config, lake_io, rutas, schemas

CLAVE = ["placa_norm", "fecha", "id_producto"]
COLS_MOV = CLAVE + ["kg_comprados", "kg_despachados", "kg_vendidos", "anio", "mes"]


# --- Motor Spark (Glue) --------------------------------------------------------
def conciliar_spark(spark, anios: list[int] | None = None, producto: str | None = None,
                    usar_broadcast: bool = True, guardar_explain: bool = True):
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    from src.common.spark import guardar_plan  # noqa: PLC0415

    movs = (spark.read
            .schema(schemas.CONTRATOS["movimientos"].spark())     # esquema declarado, sin inferSchema (S5)
            .parquet(rutas.ruta_spark("silver", "movimientos")))
    if anios:
        movs = movs.filter(F.col("anio").isin(anios))              # partition pruning
    if producto:
        movs = movs.filter(F.col("id_producto") == producto)       # predicate pushdown
    movs = movs.select(*COLS_MOV)                                  # column pruning

    if config.SALTING_BUCKETS > 0:                                 # salting solo si AQE no basta (S3)
        movs = movs.withColumn("_sal", (F.rand(config.SEMILLA) * config.SALTING_BUCKETS).cast("int"))
        parcial = (movs.groupBy(*CLAVE, "anio", "mes", "_sal")
                   .agg(F.sum("kg_comprados").alias("kg_comprados"),
                        F.sum("kg_despachados").alias("kg_despachados"),
                        F.sum("kg_vendidos").alias("kg_vendidos"),
                        F.count(F.lit(1)).alias("n_operaciones")))
        conc = (parcial.groupBy(*CLAVE, "anio", "mes")
                .agg(F.sum("kg_comprados").alias("kg_comprados"),
                     F.sum("kg_despachados").alias("kg_despachados"),
                     F.sum("kg_vendidos").alias("kg_vendidos"),
                     F.sum("n_operaciones").alias("n_operaciones")))
    else:
        conc = (movs.groupBy(*CLAVE, "anio", "mes")                # clave del Map → Shuffle
                .agg(F.sum("kg_comprados").alias("kg_comprados"),  # Reduce (con Combiner)
                     F.sum("kg_despachados").alias("kg_despachados"),
                     F.sum("kg_vendidos").alias("kg_vendidos"),
                     F.count(F.lit(1)).alias("n_operaciones")))

    conc = (conc
            .withColumn("kg_diferencia", F.col("kg_comprados") - F.col("kg_vendidos"))
            .withColumn("pct_diferencia",
                        F.when(F.col("kg_comprados") > 0, F.col("kg_diferencia") / F.col("kg_comprados")))
            .withColumn("valor_ref_soles", F.col("kg_diferencia") * F.lit(config.PRECIO_REF_KG)))

    flota = (spark.read.schema(schemas.CONTRATOS["flota"].spark())
             .parquet(rutas.ruta_spark("silver", "flota", "dis_01_vehiculos"))
             .select("placa_norm", "capacidad_kg", "habilitada"))
    conc = conc.join(broadcast(flota) if usar_broadcast else flota, "placa_norm", "left_outer")
    conc = conc.select(*schemas.CONTRATOS["fact_conciliacion_unidad"].columnas())
    conc.cache()                                                   # se reutiliza en varias señales (S4)
    if guardar_explain:
        guardar_plan(conc, "conciliacion" + ("_broadcast" if usar_broadcast else "_sortmerge"))
    return conc


def escribir_spark(conc) -> None:
    (conc.write.mode("overwrite").partitionBy(*config.PARTICIONES)   # dynamic partition overwrite
     .parquet(rutas.ruta_spark("gold", "fact_conciliacion_unidad")))


# --- Motor pandas (Lambda / local) ---------------------------------------------
def conciliar_pandas(anios: list[int] | None = None, producto: str | None = None) -> pd.DataFrame:
    filtros = [("anio", "in", anios)] if anios else None
    if producto:
        filtros = (filtros or []) + [("id_producto", "=", producto)]
    movs = lake_io.leer_parquet(rutas.ruta("silver", "movimientos"), filtros=filtros, columnas=COLS_MOV)
    conc = (movs.groupby(CLAVE + ["anio", "mes"], as_index=False, observed=True)
            .agg(kg_comprados=("kg_comprados", "sum"), kg_despachados=("kg_despachados", "sum"),
                 kg_vendidos=("kg_vendidos", "sum"), n_operaciones=("kg_vendidos", "size")))
    conc["kg_diferencia"] = conc["kg_comprados"] - conc["kg_vendidos"]
    conc["pct_diferencia"] = (conc["kg_diferencia"] / conc["kg_comprados"]).where(conc["kg_comprados"] > 0)
    conc["valor_ref_soles"] = conc["kg_diferencia"] * config.PRECIO_REF_KG
    flota = lake_io.leer_parquet(rutas.ruta("silver", "flota", "dis_01_vehiculos"),
                                 columnas=["placa_norm", "capacidad_kg", "habilitada"])
    conc = conc.merge(flota, on="placa_norm", how="left")         # left_outer
    conc["n_operaciones"] = conc["n_operaciones"].astype("int64")
    return conc[schemas.CONTRATOS["fact_conciliacion_unidad"].columnas()]


def ejecutar(motor: str = "pandas", anios: list[int] | None = None) -> dict:
    t0 = time.perf_counter()
    if motor == "spark":
        from src.common.spark import obtener_spark  # noqa: PLC0415

        spark = obtener_spark("gold_conciliacion")
        conc = conciliar_spark(spark, anios)
        escribir_spark(conc)
        conc.show(5, truncate=False)                              # inspección sin collect()
        filas = conc.count()
    else:
        conc = conciliar_pandas(anios)
        lake_io.escribir_parquet(conc, rutas.ruta("gold", "fact_conciliacion_unidad"),
                                 contrato="fact_conciliacion_unidad")
        filas = len(conc)
    return {"motor": motor, "anios": anios, "filas": filas, "segundos": round(time.perf_counter() - t0, 2)}


def _args_glue() -> dict:
    """En Glue los parámetros llegan como --CLAVE valor."""
    try:
        from awsglue.utils import getResolvedOptions  # noqa: PLC0415

        return getResolvedOptions(sys.argv, ["LAKE_URI", "ANIO"])
    except ImportError:
        return {}


if __name__ == "__main__":
    glue = _args_glue()
    if glue:
        import os

        os.environ["LAKE_URI"] = glue["LAKE_URI"]
        config.LAKE_URI = glue["LAKE_URI"]
        print(ejecutar("spark", [int(glue["ANIO"])] if glue.get("ANIO") not in (None, "", "todos") else None))
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument("--motor", choices=["pandas", "spark"], default="pandas")
        ap.add_argument("--anio", type=int, nargs="*", default=None)
        a = ap.parse_args()
        print(ejecutar(a.motor, a.anio))
