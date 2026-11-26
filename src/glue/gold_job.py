"""Job de Gold: unico script del trabajo `costagas-gold-conciliacion` (W04).

Tres modos, un solo script, porque Glue cobra por corrida y no por tarea:

  --modo evento      lo normal: puntua lo que llego desde la ultima instantanea
  --modo entrenar    reentrenamiento semanal del clasificador S12 (FLEX)
  --modo operacion   medicion mes a mes sobre el lago `op/` (W18)

Este commit deja el esqueleto: la sesion con el catalogo Iceberg, la lectura de
Silver por catalogo y el despacho por modo. Cada paso lo llenan los commits
siguientes (W05 a W08, W12 y W14); mientras tanto cada uno se anuncia como
pendiente y el job corre de principio a fin sin escribir nada.

Uso local (pruebas):
    python -m src.glue.gold_job --modo evento --lake_uri file://data/lake
"""
from __future__ import annotations

import argparse

from src.common import config, spark as spark_comun
from src.glue import iceberg

BASE_SILVER = "costagas_silver"
MODOS = ("evento", "entrenar", "operacion")

# Pasos que llenan los commits siguientes, en el orden en que corren.
PENDIENTES = {
    "evento": ["mapreduce_balance (W05)", "fact_balance_planta (W06)",
               "fact_unidad_mes (W07)", "dimensiones (W08)", "fact_alerta (W12)"],
    "entrenar": ["tabla de modelado (F-ML)", "entrenamiento S12", "registro del modelo (W13)"],
    "operacion": ["entregas mensuales (W18)", "fact_operacion"],
}


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Argumentos del job. Ignora los que agrega Glue (--JOB_NAME y demas)."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--modo", choices=MODOS, default="evento")
    p.add_argument("--lake_uri", default=config.LAKE_URI)
    p.add_argument("--catalogo", default=iceberg.CATALOGO)
    args, _ = p.parse_known_args(argv)
    return args


def crear_sesion(lake_uri: str | None = None, catalogo: str = iceberg.CATALOGO,
                 almacen: str | None = None, tipo: str | None = None, app: str = "costagas-gold"):
    """Sesion de Spark con el catalogo Iceberg.

    En AWS el catalogo es el de Glue; en las pruebas, un catalogo `hadoop` sobre
    una carpeta temporal.
    """
    from pyspark.sql import SparkSession  # noqa: PLC0415

    uri = lake_uri or config.LAKE_URI
    if tipo is None:
        tipo = "glue" if uri.startswith("s3://") else "hadoop"
    b = (SparkSession.builder.appName(app)
         .config("spark.sql.adaptive.enabled", "true")
         .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
         .config("spark.sql.adaptive.skewJoin.enabled", "true")
         .config("spark.sql.shuffle.partitions", str(config.SPARK_SHUFFLE_PARTITIONS))
         .config("spark.sql.parquet.compression.codec", "snappy")
         .config("spark.sql.session.timeZone", "America/Lima"))
    if not uri.startswith("s3://"):
        b = b.master("local[*]")
    return iceberg.configurar(b, catalogo, almacen or uri, tipo).getOrCreate()


def leer_silver(spark, tabla: str, base: str = BASE_SILVER):
    """Lee una tabla de Silver por catalogo: el esquema viene del DDL, no se infiere."""
    return spark.table(tabla if "." in tabla else f"{base}.{tabla}")


def _pendiente(modo: str) -> dict:
    for paso in PENDIENTES[modo]:
        print(f"[{modo}] pendiente: {paso}")
    return {"modo": modo, "escrito": [], "pendientes": list(PENDIENTES[modo])}


def modo_evento(spark, args) -> dict:
    """Corrida normal por evento. La llenan W05-W08, W12 y W14."""
    return _pendiente("evento")


def modo_entrenar(spark, args) -> dict:
    """Reentrenamiento semanal del clasificador S12."""
    return _pendiente("entrenar")


def modo_operacion(spark, args) -> dict:
    """Medicion mes a mes sobre el lago `op/` (W18)."""
    return _pendiente("operacion")


DESPACHO = {"evento": modo_evento, "entrenar": modo_entrenar, "operacion": modo_operacion}


def ejecutar(spark, args) -> dict:
    return DESPACHO[args.modo](spark, args)


def main(argv: list[str] | None = None) -> dict:
    args = argumentos(argv)
    spark = crear_sesion(args.lake_uri, args.catalogo)
    try:
        resumen = ejecutar(spark, args)
    finally:
        if not args.lake_uri.startswith("s3://"):
            spark.stop()                 # en Glue la sesion la cierra el servicio
    print(resumen)
    return resumen


if __name__ == "__main__":
    main()
