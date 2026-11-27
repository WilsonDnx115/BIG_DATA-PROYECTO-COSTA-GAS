"""Tabla de modelado modelo_factura con la etiqueta S12 y su madurez (FR01; informe v16, 4.3 y Tabla 4.6).

Una fila por factura del cruce tesorería × logística (`senales_spark.cruce_s12`). Es la
entrada del clasificador (`src/models/mllib.py`) y de la vista `v_kpi_3`.

Etiqueta S12 (informe v16, Tabla 4.3: 36 solo en logística, 19 solo en tesorería y 22 con
kg distinto): 1 si la factura está solo en logística, solo en tesorería o con kg distinto;
0 si coincide; nula si los dos registros existen pero a uno le faltan los kg (no se afirma
nada).

Madurez: una factura reciente que figura solo en logística puede ser una que tesorería
todavía no paga. Por eso la etiqueta solo vale cuando pasaron MADUREZ_DIAS desde el
vencimiento. Si la factura no tiene vencimiento (no está en tesorería), se estima con el
plazo de pago **medido en los datos**: la mediana de (vencimiento − fecha de factura) de las
facturas del mismo proveedor que sí cruzaron; si el proveedor no tiene ninguna, la mediana
de todos. La marca `vence_estimado` lo deja dicho.

Variables, calculadas solo con lo disponible a la fecha de la factura (Tabla 4.6):
  * kg y mes;
  * usd_kg_vs_mediana: precio ÷ mediana de los VENTANA_MEDIANA_DIAS días previos del mismo
    proveedor − 1 (sin el mismo día ni los siguientes);
  * desvio_tc: |tipo de cambio − oficial del día| ÷ oficial (calendario del BCRP);
  * flag_scop_duplicado: el código SCOP aparece en más de una factura;
  * ratio_carga_capacidad: kg ÷ capacidad de GLP de la unidad (Silver `unidades`).
Lo que no se puede calcular queda nulo; el clasificador lo codifica con centinela y marca.
"""
from __future__ import annotations

from src.common import config
from src.glue import senales_spark

POSITIVAS = ("solo_logistica", "solo_tesoreria", "kg_distinto")


def _precio_usd_kg(tesoreria):
    """Precio de tesorería por factura (usd_por_kg), con la misma llave que logística."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    partes = F.split(F.col("documento"), "-")
    return tesoreria.select(
        senales_spark.llave_factura(F.col("proveedor"), partes.getItem(0), partes.getItem(1)).alias("factura_id"),
        F.regexp_replace(F.upper(F.trim(F.col("proveedor"))), r"\s+", " ").alias("_proveedor_t"),
        F.col("usd_por_kg").cast("double").alias("_usd_kg_t")).dropDuplicates(["factura_id"])


def construir(compras, tesoreria, fecha_corte: str, tc=None, unidades=None):
    """modelo_factura a la fecha de corte.

    compras: interfaz `compras` del WP 0.8 (`senales_spark.normalizar_compras`).
    tesoreria: Silver `pedidos_proveedor`. tc: interfaz `tc` (fecha, tc_oficial), opcional.
    unidades: Silver `unidades` (placa_norm, capacidad_glp_kg), opcional.
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cruce = senales_spark.cruce_s12(tesoreria, compras)
    log = compras.select("factura_id", F.col("proveedor_id").alias("_proveedor_l"),
                         F.col("precio_usd_kg").alias("_usd_kg_l"), "tipo_cambio")
    d = (cruce.join(log, "factura_id", "left")
         .join(_precio_usd_kg(tesoreria), "factura_id", "left")
         .withColumn("proveedor_id", F.coalesce("_proveedor_l", "_proveedor_t",
                                                F.split(F.col("factura_id"), r"\|").getItem(0)))
         .withColumn("kg", F.coalesce("kg_logistica", "kg_tesoreria"))
         .withColumn("precio_usd_kg", F.coalesce("_usd_kg_l", "_usd_kg_t"))
         .withColumn("mes", F.month("fecha")))

    # Etiqueta y madurez.
    etiqueta = (F.when(F.col("clase_s12").isin(*POSITIVAS), 1.0)
                .when(F.col("clase_s12") == "coincide", 0.0))
    d = d.withColumn("etiqueta_s12", etiqueta)
    plazo = F.datediff("fecha_vence", "fecha")
    plazo_prov = (d.filter(F.col("fecha_vence").isNotNull() & F.col("fecha").isNotNull())
                  .groupBy("proveedor_id").agg(F.expr("percentile(datediff(fecha_vence, fecha), 0.5)")
                                               .alias("_plazo_prov")))
    plazo_global = (d.filter(F.col("fecha_vence").isNotNull() & F.col("fecha").isNotNull())
                    .agg(F.expr("percentile(datediff(fecha_vence, fecha), 0.5)").alias("_plazo_global")))
    d = (d.join(broadcast(plazo_prov), "proveedor_id", "left").crossJoin(broadcast(plazo_global))
         .withColumn("vence_estimado", F.col("fecha_vence").isNull())
         .withColumn("fecha_vence", F.coalesce(
             F.col("fecha_vence"),
             F.date_add("fecha", F.coalesce("_plazo_prov", "_plazo_global").cast("int"))))
         .withColumn("fecha_madurez", F.date_add("fecha_vence", config.MADUREZ_DIAS))
         .withColumn("madura", F.coalesce(F.col("fecha_madurez") <= F.lit(fecha_corte).cast("date"),
                                          F.lit(False))))

    # Variables a la fecha de la factura.
    dia = F.datediff("fecha", F.lit("1970-01-01"))
    w = (Window.partitionBy("proveedor_id").orderBy(dia)
         .rangeBetween(-config.VENTANA_MEDIANA_DIAS, -1))
    d = d.withColumn("_mediana", F.expr("percentile(precio_usd_kg, 0.5)").over(w))
    d = d.withColumn("usd_kg_vs_mediana", F.when(F.col("_mediana") > 0,
                                                 F.col("precio_usd_kg") / F.col("_mediana") - 1))
    scop = Window.partitionBy("codigo_scop")
    d = d.withColumn("flag_scop_duplicado", F.when(
        F.col("codigo_scop").isNotNull(),
        (F.size(F.collect_set("factura_id").over(scop)) > 1).cast("int")).otherwise(0))
    if tc is not None:
        d = d.join(broadcast(senales_spark.calendario_tc(tc)), "fecha", "left")
        d = d.withColumn("desvio_tc", F.abs(F.col("tipo_cambio") - F.col("tc_oficial"))
                         / F.when(F.col("tc_oficial") > 0, F.col("tc_oficial")))
    else:
        d = d.withColumn("desvio_tc", F.lit(None).cast("double"))
    if unidades is not None:
        cap = unidades.select(F.col("placa_norm").alias("unidad_id"), "capacidad_glp_kg")
        d = d.join(broadcast(cap), "unidad_id", "left")
        d = d.withColumn("ratio_carga_capacidad", F.when(F.col("capacidad_glp_kg") > 0,
                                                         F.col("kg") / F.col("capacidad_glp_kg")))
    else:
        d = d.withColumn("ratio_carga_capacidad", F.lit(None).cast("double"))

    return d.select("factura_id", "proveedor_id", "unidad_id", "codigo_scop", "fecha", "anio", "mes",
                    "clase_s12", "etiqueta_s12", "kg", "precio_usd_kg", "usd_kg_vs_mediana", "desvio_tc",
                    "flag_scop_duplicado", "ratio_carga_capacidad", "fecha_vence", "vence_estimado",
                    "fecha_madurez", "madura")
