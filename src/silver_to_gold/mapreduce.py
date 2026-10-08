"""Conciliación como MapReduce explícito sobre RDD de Spark (S3 · MapReduce, S4 · RDD).

Es el mismo cálculo que `conciliacion.py`, escrito con las fases a la vista:

  Map      cada movimiento → ((placa, fecha, producto), (kg_comprados, kg_vendidos, 1))
  Combiner reduceByKey suma dentro de cada partición ANTES del shuffle
  Shuffle  los pares con la misma clave viajan a la misma partición
  Reduce   suma final por clave → kg_diferencia

`groupByKey` se incluye como contraejemplo: no combina, envía al shuffle todos
los valores de cada clave. La comparación de bytes de shuffle entre ambas
variantes (leída de las métricas de Spark) es la evidencia del Combiner.

Uso:  python -m src.silver_to_gold.mapreduce --anio 2020
"""
from __future__ import annotations

import argparse
import json
import time

from src.common import rutas, schemas

CLAVE = ("placa_norm", "fecha", "id_producto")


def mapear(fila) -> tuple:
    """Fase Map: un movimiento → (clave, valor)."""
    return ((fila.placa_norm, fila.fecha, fila.id_producto),
            (fila.kg_comprados or 0.0, fila.kg_vendidos or 0.0, 1))


def sumar(a: tuple, b: tuple) -> tuple:
    """Fase Reduce (y Combiner): asociativa y conmutativa, por eso puede combinarse en el Map."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def a_registro(par) -> tuple:
    (placa, fecha, producto), (comprados, vendidos, n) = par
    return (placa, fecha, producto, comprados, vendidos, n, comprados - vendidos)


def leer_movimientos(spark, anios: list[int] | None = None):
    from pyspark.sql import functions as F  # noqa: PLC0415

    df = (spark.read.schema(schemas.CONTRATOS["movimientos"].spark())
          .parquet(rutas.ruta_spark("silver", "movimientos")))
    if anios:
        df = df.filter(F.col("anio").isin(anios))                  # partition pruning antes del Map
    return df.select(*CLAVE, "kg_comprados", "kg_vendidos")       # column pruning


def conciliar_reduce_by_key(spark, anios=None):
    """MapReduce con Combiner (reduceByKey)."""
    rdd = leer_movimientos(spark, anios).rdd
    return rdd.map(mapear).reduceByKey(sumar).map(a_registro)


def conciliar_group_by_key(spark, anios=None):
    """MapReduce SIN Combiner (groupByKey): todo valor cruza el shuffle."""
    rdd = leer_movimientos(spark, anios).rdd
    return (rdd.map(mapear).groupByKey()
            .mapValues(lambda vals: sumar_todos(vals)).map(a_registro))


def sumar_todos(valores) -> tuple:
    total = (0.0, 0.0, 0)
    for v in valores:
        total = sumar(total, v)
    return total


def _shuffle_bytes(spark, job_group: str) -> int:
    """Bytes escritos al shuffle por los jobs del grupo, leídos de la API REST de la Spark UI."""
    import urllib.request  # noqa: PLC0415

    sc = spark.sparkContext
    if not sc.uiWebUrl:
        return -1
    base = f"{sc.uiWebUrl}/api/v1/applications/{sc.applicationId}"
    leer = lambda p: json.load(urllib.request.urlopen(f"{base}/{p}"))  # noqa: E731,S310
    etapas = {s for j in leer("jobs") if j.get("jobGroup") == job_group for s in j["stageIds"]}
    return sum(s.get("shuffleWriteBytes", 0) for s in leer("stages") if s["stageId"] in etapas)


def comparar(spark, anios=None) -> dict:
    """Ejecuta ambas variantes y mide tiempo, filas y bytes de shuffle."""
    sc = spark.sparkContext
    res = {}
    for nombre, fn in (("reduceByKey_con_combiner", conciliar_reduce_by_key),
                       ("groupByKey_sin_combiner", conciliar_group_by_key)):
        sc.setJobGroup(nombre, nombre)
        t0 = time.perf_counter()
        n = fn(spark, anios).count()                             # acción: dispara el DAG
        res[nombre] = {"claves": n, "segundos": round(time.perf_counter() - t0, 2),
                       "shuffle_write_bytes": _shuffle_bytes(spark, nombre)}
    a, b = res["reduceByKey_con_combiner"], res["groupByKey_sin_combiner"]
    res["mismo_resultado"] = a["claves"] == b["claves"]
    if b["shuffle_write_bytes"]:
        res["reduccion_shuffle"] = round(1 - a["shuffle_write_bytes"] / b["shuffle_write_bytes"], 3)
    return res


if __name__ == "__main__":
    from src.common.spark import obtener_spark

    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, nargs="*", default=None)
    a = ap.parse_args()
    spark = obtener_spark("mapreduce_conciliacion")
    print(json.dumps(comparar(spark, a.anio), indent=2))
    print(conciliar_reduce_by_key(spark, a.anio).take(5))       # inspección sin collect()
