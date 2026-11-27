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

from src.common import config
from src.glue import balance, dimensiones, iceberg, interfaces, mapreduce_sql
from src.glue import senales_spark

BASE_SILVER = "costagas_silver"
MODOS = ("evento", "entrenar", "operacion")

TABLA_ALERTA = "fact_alerta"
LLAVE_ALERTA = ("id_alerta",)

# Que necesita cada senal de regla para poder calcularse (WR06). Las entradas son
# las del WP 0.8 que arma `src/glue/interfaces.py`, mas `tesoreria`, que es Silver
# `pedidos_proveedor`. Una senal cuya entrada falta no se calcula y se dice por
# que: devolver cero alertas seria afirmar que no hay nada que mirar.
ENTRADAS_SENAL = {
    "S2": ("compras",),
    "S3": ("compras",),
    "S6": ("compras", "tc"),
    "S7": ("unidad_mes", "unidades"),
    "S9": ("unidad_mes",),
    "S11": ("produccion",),
    "S12": ("tesoreria", "compras"),
}

# Por que falta cada entrada que hoy no existe, para que el log lo diga una vez y
# no haya que buscarlo en el repositorio.
MOTIVO_ENTRADA = {
    "unidad_mes": "fact_unidad_mes espera contracts/gastos.yaml (WR02)",
    "produccion": "silver/produccion_diaria no esta cubierta en la entrega",
    "tc": "falta la extraccion del BCRP en landing/externo/bcrp/",
}

# Pasos que llenan los commits siguientes, en el orden en que corren.
PENDIENTES = {
    # W05, W06, W08 y las senales de regla (WR06) ya corren. Lo que falta de
    # `fact_alerta` es la puntuacion del modelo S12 y el aviso al tema (WR11).
    "evento": ["fact_unidad_mes (W07)", "probabilidad del modelo S12 en fact_alerta (WR11)"],
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


def paso_mapreduce(spark, args) -> str:
    """W05: balance por producto y mes con el patron MapReduce, hacia gold/mr/."""
    balance = mapreduce_sql.construir(spark, leer_silver(spark, "compras_glp"),
                                      leer_silver(spark, "ventas_detalle"))
    return mapreduce_sql.escribir(balance, args.lake_uri)


def paso_balance(spark, args) -> str:
    """W06: `fact_balance_planta` por producto y mes, en Iceberg.

    Sin fuente de produccion: `delta_stock_kg` queda nulo, que es lo que
    corresponde mientras la entrega no traiga cierres fisicos.
    """
    return balance.construir_y_escribir(spark, leer_silver(spark, "compras_glp"),
                                        leer_silver(spark, "ventas_detalle"))


def senales_calculables(disponibles) -> tuple[list[str], dict[str, str]]:
    """Separa las senales que se pueden calcular de las que no, con el motivo.

    No toca Spark: recibe los nombres de las entradas que hay y decide. Asi la
    regla se puede probar sin una sesion.
    """
    listas, omitidas = [], {}
    for senal, necesita in ENTRADAS_SENAL.items():
        faltan = [e for e in necesita if e not in disponibles]
        if faltan:
            omitidas[senal] = "; ".join(MOTIVO_ENTRADA.get(e, f"falta {e}") for e in faltan)
        else:
            listas.append(senal)
    return listas, omitidas


def entradas_de_senales(spark, args) -> dict:
    """Las entradas del WP 0.8 que hoy se pueden armar desde Silver.

    `tesoreria` es Silver `pedidos_proveedor` tal cual: S12 cruza el documento
    con la misma llave de factura que logistica, no una interfaz aparte.
    """
    silver = {t: leer_silver(spark, t) for t in ("compras_glp", "unidades")}
    entradas = interfaces.construir(spark, silver, args.lake_uri)
    entradas["tesoreria"] = leer_silver(spark, "pedidos_proveedor")
    return entradas


def alertas_de_regla(entradas: dict):
    """Une las alertas de las senales calculables. Devuelve (df | None, omitidas)."""
    from functools import reduce  # noqa: PLC0415

    calculables, omitidas = senales_calculables(set(entradas))
    partes = []
    for senal in calculables:
        funcion = getattr(senales_spark, senal.lower())
        partes.append(funcion(*[entradas[e] for e in ENTRADAS_SENAL[senal]]))
    if not partes:
        return None, omitidas
    return reduce(lambda a, b: a.unionByName(b), partes), omitidas


def paso_senales(spark, args) -> dict:
    """WR06: `fact_alerta` con las alertas de regla, por MERGE sobre `id_alerta`.

    El id es el SHA-256 determinista que arma `senales_spark._alertas`, asi que
    dos corridas sobre el mismo universo dejan una sola fila por alerta.

    `probabilidad` se escribe nula: la pone el modelo S12 en el WR11. La columna
    va aqui porque el DDL de la tabla la declara y el MERGE compara el esquema
    completo; el contrato `fact_alerta_base` sigue siendo el de las senales.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    alertas, omitidas = alertas_de_regla(entradas_de_senales(spark, args))
    for senal, motivo in sorted(omitidas.items()):
        print(f"[evento] {senal} sin fuente: {motivo}")
    if alertas is None:
        return {"tabla": None, "senales": [], "omitidas": omitidas}

    alertas = alertas.withColumn("probabilidad", F.lit(None).cast("double"))
    tabla = iceberg.escribir_merge(spark, alertas, TABLA_ALERTA, LLAVE_ALERTA)
    return {"tabla": tabla, "senales": sorted(set(ENTRADAS_SENAL) - set(omitidas)),
            "omitidas": omitidas}


def paso_dimensiones(spark, args) -> list[str]:
    """W08: las seis dimensiones del modelo estrella, en Iceberg."""
    return dimensiones.construir_y_escribir(spark, {
        "unidades": leer_silver(spark, "unidades"),
        "compras": leer_silver(spark, "compras_glp"),
        "ventas": leer_silver(spark, "ventas_detalle"),
    })


def modo_evento(spark, args) -> dict:
    """Corrida normal por evento. Falta lo que llenan W07 y W11."""
    resumen = _pendiente("evento")
    resumen["escrito"].append(paso_mapreduce(spark, args))
    resumen["escrito"].extend(paso_dimensiones(spark, args))
    resumen["escrito"].append(paso_balance(spark, args))
    senales = paso_senales(spark, args)
    if senales["tabla"]:
        resumen["escrito"].append(senales["tabla"])
    resumen["senales"] = senales["senales"]
    resumen["senales_sin_fuente"] = senales["omitidas"]
    return resumen


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
