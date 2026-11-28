"""Construcción del hecho Gold `fact_unidad_mes` (W07).

Las ventas por unidad y los gastos se agregan al grano placa-mes. El volumen
transportado no se deriva de ventas ni de compras: ninguna fuente declarada
ofrece ese dato por unidad. Por eso permanece nulo hasta que exista una fuente
que lo mida.
"""
from __future__ import annotations


LLAVE = ("unidad_id", "anio", "mes")


def construir(ventas, gastos, unidades):
    """Agrega Silver `ventas_unidad_mes` y `gastos` al grano de `fact_unidad_mes`.

    Solo suma kg GLP identificados por el contrato de ventas. Los gastos por
    placa se conservan; los gastos sin placa no se atribuyen a una unidad.
    Categorías de combustible desconocidas no se convierten en cero.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    periodo = (F.col("anio").isNotNull() & F.col("mes").between(1, 12))

    kg_vendidos = (ventas
                   .filter(F.col("placa_norm").isNotNull() & periodo
                           & F.col("articulo").rlike(r"(?i)\bGLP\b")
                           & F.col("kg").isNotNull())
                   .groupBy(F.col("placa_norm").alias("unidad_id"), "anio", "mes")
                   .agg(F.sum(F.col("kg").cast("double")).alias("kg_vendidos")))

    gasto_filas = gastos.filter(F.col("placa_norm").isNotNull() & periodo
                                & F.col("monto_soles").isNotNull())
    gastos_mes = (gasto_filas
                  .groupBy(F.col("placa_norm").alias("unidad_id"), "anio", "mes")
                  .agg(F.sum(F.col("monto_soles").cast("double")).alias("gasto_total"),
                       F.sum(F.when(F.col("es_combustible") == F.lit(True),
                                    F.col("monto_soles").cast("double")))
                        .alias("combustible_conocido"),
                       F.max(F.when(F.col("es_combustible").isNull(), 1).otherwise(0))
                        .alias("categoria_desconocida"))
                  .withColumn("gasto_combustible",
                              F.when(F.col("categoria_desconocida") == 1, F.lit(None).cast("double"))
                               .when(F.col("combustible_conocido").isNotNull(),
                                     F.col("combustible_conocido"))
                               .otherwise(F.lit(0.0)))
                  .drop("combustible_conocido", "categoria_desconocida"))

    hechos = kg_vendidos.join(gastos_mes, list(LLAVE), "full_outer")
    from src.glue import dimensiones  # noqa: PLC0415

    roles = (dimensiones.dim_unidad(unidades, ventas=ventas)
             .select(F.col("placa_norm").alias("unidad_id"), "rol"))
    hechos = (hechos.join(roles, "unidad_id", "left")
              # `ventas_unidad_mes` es explícitamente la fuente de reparto; usarlo
              # como respaldo solo aplica a filas que sí tienen ventas registradas.
              .withColumn("rol", F.coalesce("rol",
                                             F.when(F.col("kg_vendidos").isNotNull(), "reparto")))
              .withColumn("kg_transportados", F.lit(None).cast("double"))
              .select("unidad_id", "rol", F.col("anio").cast("int"), F.col("mes").cast("int"),
                      F.col("kg_vendidos").cast("double"), "kg_transportados",
                      F.col("gasto_combustible").cast("double"),
                      F.col("gasto_total").cast("double")))
    sin_rol = F.col("rol").isNull() | ~F.col("rol").isin("reparto", "transporte")
    if hechos.filter(sin_rol).limit(1).count():
        raise ValueError("fact_unidad_mes: hay placas sin rol en dim_unidad; se cancela para no inventar el rol")
    return hechos
