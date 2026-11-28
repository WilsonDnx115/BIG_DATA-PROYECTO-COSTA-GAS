"""Job de Gold: unico script del trabajo `costagas-gold-conciliacion` (W04).

Tres modos, un solo script, porque Glue cobra por corrida y no por tarea:

  --modo evento      lo normal: puntua lo que llego desde la ultima instantanea
  --modo entrenar    reentrenamiento semanal del clasificador S12 (FLEX)
  --modo operacion   medicion mes a mes sobre el lago `op/` (W18)

El modo evento escribe balance, dimensiones, alertas y hechos unidad-mes en
Iceberg. Las señales sin fuente cubierta se informan con su motivo.

Uso local (pruebas):
    python -m src.glue.gold_job --modo evento --lake_uri file://data/lake
"""
from __future__ import annotations

import argparse

from src.common import config
from src.glue import balance, dimensiones, iceberg, interfaces, mapreduce_sql
from src.glue import unidad_mes as hecho_unidad_mes
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
    "S5": ("ventas_detalle", "distribuidores", "puente_clientes"),
    "S10": ("ventas_detalle",),
}

# S5 y S10 corren sobre Silver ventas_detalle (FR16 y FR17), no sobre la muestra antigua
# que leen `senales_spark.s5` y `s10`; las demas se llaman como la senal.
FUNCIONES_SENAL = {"S5": senales_spark.s5_distribuidores, "S10": senales_spark.s10_ventas}

# Por que falta cada entrada que hoy no existe, para que el log lo diga una vez y
# no haya que buscarlo en el repositorio.
MOTIVO_ENTRADA = {
    "produccion": "silver/produccion_diaria no esta cubierta en la entrega",
    "tc": "falta la extraccion del BCRP en landing/externo/bcrp/",
    "puente_clientes": "falta Silver clientes o la sal de seudonimizacion (SEUDONIMO_SAL o SSM)",
}

TABLA_OPERACION = "fact_operacion"
LLAVE_OPERACION = ("anio", "mes", "tramo", "medida")

# Pasos que llenan los commits siguientes, en el orden en que corren.
PENDIENTES = {
    # W05-W08 y las señales de regla ya corren; S12 depende del modelo vigente.
    "evento": [],
    # El reentrenamiento corre completo (entrenamiento.entrenar_y_registrar).
    "entrenar": [],
    # fact_operacion se mide sobre las tablas de Gold; las entregas del lago op/ las
    # genera la Lambda costagas-entregas-mensuales.
    "operacion": ["entregas mensuales en op/landing/ (W18)"],
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
         .config("spark.sql.session.timeZone", "America/Lima")
         # El lago ya contiene Parquet con fechas escritas antes de Spark 3;
         # LEGACY las rebasa al calendario proleptico al leer y evita perderlas
         # o abortar los MERGE de Iceberg por ambiguedad de calendario.
         .config("spark.sql.parquet.datetimeRebaseModeInRead", "LEGACY")
         .config("spark.sql.parquet.int96RebaseModeInRead", "LEGACY"))
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
    entradas["ventas_detalle"] = leer_silver(spark, "ventas_detalle")
    entradas["distribuidores"] = leer_silver(spark, "distribuidores")
    try:
        from src.common import limpieza  # noqa: PLC0415

        entradas["puente_clientes"] = senales_spark.puente_cliente_distribuidor(
            leer_silver(spark, "clientes"), limpieza.obtener_sal())
    except Exception as e:                  # noqa: BLE001 - sin clientes o sin sal: S5 queda sin fuente
        print(f"[evento] puente de clientes no disponible: {type(e).__name__}")
    return entradas


def alertas_de_regla(entradas: dict):
    """Une las alertas de las senales calculables. Devuelve (df | None, omitidas)."""
    from functools import reduce  # noqa: PLC0415

    calculables, omitidas = senales_calculables(set(entradas))
    partes = []
    for senal in calculables:
        funcion = FUNCIONES_SENAL.get(senal) or getattr(senales_spark, senal.lower())
        partes.append(funcion(*[entradas[e] for e in ENTRADAS_SENAL[senal]]))
    if not partes:
        return None, omitidas
    return reduce(lambda a, b: a.unionByName(b), partes), omitidas


def paso_senales(spark, args, entradas: dict | None = None) -> dict:
    """WR06: `fact_alerta` con las alertas de regla, por MERGE sobre `id_alerta`.

    El id es el SHA-256 determinista que arma `senales_spark._alertas`, asi que
    dos corridas sobre el mismo universo dejan una sola fila por alerta.

    `probabilidad` se escribe nula: la pone el modelo S12 en el WR11. La columna
    va aqui porque el DDL de la tabla la declara y el MERGE compara el esquema
    completo; el contrato `fact_alerta_base` sigue siendo el de las senales.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    alertas, omitidas = alertas_de_regla(entradas if entradas is not None
                                         else entradas_de_senales(spark, args))
    for senal, motivo in sorted(omitidas.items()):
        print(f"[evento] {senal} sin fuente: {motivo}")
    if alertas is None:
        return {"tabla": None, "senales": [], "omitidas": omitidas, "alertas_df": None}

    alertas = alertas.withColumn("probabilidad", F.lit(None).cast("double"))
    # El grano contractual de fact_alerta es id_alerta. Algunas fuentes pueden
    # producir el mismo evento más de una vez (p. ej. líneas repetidas de una
    # factura), lo que hace que Iceberg rechace el MERGE. Conservamos una sola
    # fila de forma determinista por id; ordenamos por todo el payload para que
    # reejecuciones con los mismos datos elijan siempre la misma representación.
    duplicadas = (alertas.groupBy("id_alerta").count()
                  .filter(F.col("count") > 1)
                  .agg(F.sum(F.col("count") - 1).alias("filas_excedentes"))
                  .first()["filas_excedentes"])
    if duplicadas:
        from pyspark.sql import Window  # noqa: PLC0415
        from pyspark.sql.functions import row_number  # noqa: PLC0415

        orden = Window.partitionBy("id_alerta").orderBy(
            *[F.col(c).cast("string").asc_nulls_first() for c in alertas.columns])
        alertas = (alertas.withColumn("_orden_alerta", row_number().over(orden))
                   .filter(F.col("_orden_alerta") == 1).drop("_orden_alerta"))
        print(f"[evento] fact_alerta: omitidas {duplicadas} filas excedentes por id_alerta repetido")
    tabla = iceberg.escribir_merge(spark, alertas, TABLA_ALERTA, LLAVE_ALERTA)
    return {"tabla": tabla, "senales": sorted(set(ENTRADAS_SENAL) - set(omitidas)),
            "omitidas": omitidas, "alertas_df": alertas}


def paso_unidad_mes(spark, unidad_mes_puntuado, alertas) -> str:
    """W07: añade señales y persiste el hecho unidad-mes en Iceberg."""
    puntuado = unidad_mes_puntuado
    if alertas is None:
        from pyspark.sql import functions as F  # noqa: PLC0415

        puntuado = (puntuado.withColumn("senales", F.array().cast("array<string>"))
                    .withColumn("n_senales", F.lit(0)))
    else:
        puntuado = senales_spark.agregar_senales(puntuado, alertas)
    # `log_combustible_por_t` es una columna de cálculo intermedio, no parte del
    # contrato Gold que consumen las vistas.
    puntuado = puntuado.drop("log_combustible_por_t")
    return iceberg.escribir_merge(spark, puntuado, "fact_unidad_mes",
                                  ("unidad_id", "anio", "mes"))


def estado_calidad_kpi4(spark, args) -> dict:
    """Estado de calidad de las fuentes de KPI 4, a partir de silver/_control/."""
    from src.quality import calidad_silver  # noqa: PLC0415

    ruta_control = f"{args.lake_uri.rstrip('/')}/silver/_control"
    filas = (calidad_silver.construir(spark, ruta_control=ruta_control)
             .select("tabla", "cumple", "metas_incumplidas")
             .take(1000))
    return calidad_silver.bloqueos([fila.asDict(recursive=True) for fila in filas])["kpi_4"]


def paso_dimensiones(spark, args) -> list[str]:
    """W08: las seis dimensiones del modelo estrella, en Iceberg."""
    return dimensiones.construir_y_escribir(spark, {
        "unidades": leer_silver(spark, "unidades"),
        "compras": leer_silver(spark, "compras_glp"),
        "ventas": leer_silver(spark, "ventas_detalle"),
    })


def tabla_de_modelado(spark, args, fecha_corte: str):
    """gold/modelo_factura a la fecha de corte, con las entradas del WP 0.8 (F07)."""
    from src.glue import modelo_factura  # noqa: PLC0415

    e = entradas_de_senales(spark, args)
    return modelo_factura.construir(e["compras"], e["tesoreria"], fecha_corte, tc=e.get("tc"),
                                    unidades=leer_silver(spark, "unidades"))


def paso_modelo_s12(spark, args) -> dict:
    """WR11: el modelo vigente puntua las facturas y las marcadas entran a fact_alerta por MERGE.

    Sin modelo vigente en el registro (todavia no hubo un `--modo entrenar` que lo
    promoviera) no se puntua y se dice: no hay probabilidad que escribir.
    """
    import datetime as dt  # noqa: PLC0415

    from pyspark.ml import PipelineModel  # noqa: PLC0415

    from src.models import mllib, registro  # noqa: PLC0415

    ficha = registro.vigente()
    if ficha is None:
        print("[evento] S12 sin modelo vigente: se puntua despues del primer --modo entrenar")
        return {"tabla": None, "version": None}
    facturas = tabla_de_modelado(spark, args, dt.date.today().isoformat())
    puntuadas = mllib.puntuar_s12(facturas, PipelineModel.load(ficha["ruta"]), ficha["umbral"],
                                  ficha["version"])
    alertas = mllib.alertas_s12(puntuadas, facturas)
    return {"tabla": iceberg.escribir_merge(spark, alertas, TABLA_ALERTA, LLAVE_ALERTA),
            "version": ficha["version"]}


def modo_evento(spark, args) -> dict:
    """Corrida normal por evento: Silver → hechos y dimensiones de Gold."""
    resumen = _pendiente("evento")
    resumen["escrito"].append(paso_mapreduce(spark, args))
    resumen["escrito"].extend(paso_dimensiones(spark, args))
    resumen["escrito"].append(paso_balance(spark, args))
    ventas = leer_silver(spark, "ventas_unidad_mes")
    gastos = leer_silver(spark, "gastos")
    unidades = leer_silver(spark, "unidades")
    unidad_mes_base = hecho_unidad_mes.construir(ventas, gastos, unidades)
    entradas = entradas_de_senales(spark, args)
    calidad_kpi4 = estado_calidad_kpi4(spark, args)
    if calidad_kpi4["publicable"]:
        unidad_mes_puntuado = senales_spark.kpi4(unidad_mes_base)
        entradas["unidad_mes"] = unidad_mes_puntuado
    else:
        from pyspark.sql import functions as F  # noqa: PLC0415

        print(f"[evento] KPI 4 bloqueado por calidad Silver: {calidad_kpi4['motivo']}")
        volumen = F.when(F.col("rol") == "reparto", F.col("kg_vendidos")) \
                   .otherwise(F.col("kg_transportados"))
        unidad_mes_puntuado = (unidad_mes_base
                               .withColumn("kg_base_rol", volumen.cast("double"))
                               .withColumn("soles_comb_por_t", F.lit(None).cast("double"))
                               .withColumn("z", F.lit(None).cast("double"))
                               .withColumn("puntaje", F.lit(None).cast("double"))
                               .withColumn("alerta_base", F.lit(False))
                               .withColumn("estado_puntaje", F.lit("calidad_fuente_bloqueada")))
    senales = paso_senales(spark, args, entradas)
    if senales["tabla"]:
        resumen["escrito"].append(senales["tabla"])
    resumen["senales"] = senales["senales"]
    resumen["senales_sin_fuente"] = senales["omitidas"]
    resumen["kpi_4_publicable"] = calidad_kpi4["publicable"]
    resumen["kpi_4_motivo"] = calidad_kpi4["motivo"]
    resumen["escrito"].append(paso_unidad_mes(spark, unidad_mes_puntuado,
                                               senales.pop("alertas_df")))
    modelo = paso_modelo_s12(spark, args)
    if modelo["tabla"]:
        resumen["escrito"].append(modelo["tabla"])
    resumen["modelo_s12"] = modelo["version"]
    return resumen


def modo_entrenar(spark, args) -> dict:
    """Reentrenamiento semanal del clasificador S12: entrena, registra y promueve si mejora."""
    import datetime as dt  # noqa: PLC0415

    from src.models import entrenamiento  # noqa: PLC0415

    resumen = _pendiente("entrenar")
    corte = dt.date.today().isoformat()
    r = entrenamiento.entrenar_y_registrar(tabla_de_modelado(spark, args, corte), corte)
    resumen.update({"estado": r["estado"], "promovido": r["promovido"]})
    if r.get("ficha"):
        resumen["escrito"].append(r["ficha"]["ruta"])
    return resumen


def leer_gold(spark, tabla: str):
    return spark.table(iceberg.nombre(tabla))


MESES_CON_VENTAS_POR_CLIENTE = ["2019-09", "2020-05", "2021-02", "2024-04"]   # catalogo, S5 y S10


def modo_operacion(spark, args) -> dict:
    """Tabla 4.8e mes a mes con las tablas de Gold, en gold/fact_operacion por MERGE."""
    import pandas as pd  # noqa: PLC0415

    from src.glue import operacion  # noqa: PLC0415

    resumen = _pendiente("operacion")
    tablas = {"fact_alerta": leer_gold(spark, TABLA_ALERTA),
              "modelo_factura": leer_gold(spark, "modelo_factura")}
    for opcional in ("fact_serie", "fact_balance_planta"):
        if iceberg.existe(spark, opcional):
            tablas[opcional] = leer_gold(spark, opcional)
    partes = [operacion.medir_tramo("facturas", tablas)]
    if "fact_serie" in tablas:
        partes.append(operacion.medir_tramo("unidades", tablas))
    else:
        print("[operacion] tramo de unidades sin fact_serie")
    partes.append(operacion.medir_tramo("clientes", tablas, meses=MESES_CON_VENTAS_POR_CLIENTE))
    medidas = pd.concat(partes, ignore_index=True)
    medidas = pd.concat([medidas, operacion.estabilidad_trimestral(medidas)], ignore_index=True)
    resumen["escrito"].append(iceberg.escribir_merge(spark, operacion.a_spark(spark, medidas),
                                                     TABLA_OPERACION, LLAVE_OPERACION))
    return resumen


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
