"""`fact_balance_planta`: el balance de planta por producto y mes (W06, KPI 1 y 2).

Es el primer nivel de conciliacion del informe (4.1): cuanto GLP entro por
compras, cuanto salio por ventas, y que parte de la diferencia queda **sin
explicar** despues de descontar lo que si tiene explicacion conocida.

    diferencia_bruta_kg = kg_comprados - kg_vendidos
    kg_no_explicados    = diferencia_bruta_kg - delta_stock_kg - merma_tecnica_kg

Las dos restas son opcionales a proposito, y cada una por un motivo distinto:

* **`delta_stock_kg` es nulo siempre, hoy.** La entrega de 35 archivos no trae
  stock de planta de ningun grano: lo verifique sobre las 199 hojas del
  inventario y quedo escrito en
  [`docs/evidencias/hojas_sin_encabezado.md`](../../docs/evidencias/hojas_sin_encabezado.md).
  Sin cierre fisico no se puede saber si el GLP que falta esta en el tanque o
  no esta, y por eso el informe v16 declara `cierres_medidos_fisicamente: 0`.
  La funcion acepta un DataFrame de produccion por si algun dia aparece; sin el,
  la columna queda nula, **no en cero**: un cero diria que el stock no se movio,
  y eso no lo sabemos.
* **`merma_tecnica_kg` es un supuesto declarado, no una medicion de la planta.**
  `config.MERMA_TECNICA_PCT` vale 0.5 %, que es la referencia de mercado para
  balances de masa de hidrocarburos con buena instrumentacion
  ([ADR 0027](../../docs/adr/0027-merma-tecnica-referencia-de-mercado.md));
  Osinergmin no publica una tolerancia para plantas envasadoras, y
  `MERMA_TECNICA_ES_SUPUESTO` hace que el tablero lo etiquete como supuesto.
  Pasando `merma_pct=None` la columna queda nula y el KPI se calcula sin
  descontar nada, que es la version que el tablero muestra al lado de la otra.

Sobre `valor_soles`: valoriza **los kg no explicados** al precio de compra del
propio mes, calculado de las facturas (`monto_usd * tipo_cambio / kg`), nunca
con un precio de referencia inventado. Si el mes no tiene facturas con tipo de
cambio valido, queda nulo. Y aun asi no es una perdida confirmada: es lo que
costo comprar el GLP que no se explica. La valorizacion de una alerta suelta,
en cambio, no existe: ver `senales_spark._alertas`.

El reparto por producto reutiliza `mapreduce_sql`, que ya implementa la regla
de clasificacion (envasado contra granel) una sola vez.
"""
from __future__ import annotations

from src.common import config
from src.glue import iceberg, mapreduce_sql

TABLA = "fact_balance_planta"
LLAVE = ("producto", "anio", "mes")

COLUMNAS = ("producto", "anio", "mes", "kg_comprados", "kg_vendidos",
            "diferencia_bruta_kg", "delta_stock_kg", "merma_tecnica_kg",
            "merma_es_supuesto", "kg_no_explicados", "pct_no_explicado",
            "valor_soles", "mes_completo")

# Columnas del contrato `compras_glp` con las que se arma el precio del mes.
SQL_PRECIO_MES = """
    SELECT CAST(anio AS int) AS anio, CAST(mes AS int) AS mes,
           SUM(monto_usd * tipo_cambio) / SUM(kg) AS precio_soles_kg
      FROM {compras}
     WHERE tc_valido AND monto_usd IS NOT NULL AND tipo_cambio IS NOT NULL
       AND kg IS NOT NULL AND kg > 0
     GROUP BY anio, mes
    HAVING SUM(kg) > 0
"""


def precio_mes(spark, compras):
    """Precio de compra del mes en S/ por kg, medido de las facturas.

    Por mes y no por producto: la factura trae un solo importe y los kg
    repartidos entre `kg_glp_e` y `kg_glp_g`, asi que el dato para separar el
    precio de cada producto no existe en la entrega. Es un promedio ponderado
    por kg, y los meses sin tipo de cambio valido no aparecen, de modo que su
    `valor_soles` queda nulo en vez de salir de un precio inventado.
    """
    compras.createOrReplaceTempView("bal_compras")
    return spark.sql(SQL_PRECIO_MES.format(compras="bal_compras"))


def _delta_stock(spark, produccion):
    """Variacion de stock fisico por producto y mes, si existe la fuente.

    Devuelve None cuando no hay produccion: quien llama deja la columna nula.
    Se espera un DataFrame con `producto`, `anio`, `mes` y `delta_stock_kg`, o
    con `stock_inicial_kg` y `stock_final_kg` para calcularlo.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    if produccion is None:
        return None
    cols = set(produccion.columns)
    if "delta_stock_kg" in cols:
        return produccion.select("producto", "anio", "mes",
                                 F.col("delta_stock_kg").cast("double").alias("delta_stock_kg"))
    if {"stock_inicial_kg", "stock_final_kg"} <= cols:
        return produccion.select(
            "producto", "anio", "mes",
            (F.col("stock_final_kg").cast("double")
             - F.col("stock_inicial_kg").cast("double")).alias("delta_stock_kg"))
    raise ValueError(
        "produccion debe traer delta_stock_kg, o stock_inicial_kg y stock_final_kg; "
        f"trae {sorted(cols)}"
    )


def construir(spark, compras, ventas, produccion=None,
              merma_pct: float | None = config.MERMA_TECNICA_PCT):
    """Balance por producto y mes, con la diferencia no explicada y su valor.

    `produccion` es opcional y hoy no existe: ver el encabezado del modulo.
    `merma_pct=None` deja `merma_tecnica_kg` nula y no la descuenta.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    # anio y mes llegan de Silver como bigint; el DDL de Gold los declara int,
    # igual que `dim_tiempo`, para que el join del modelo estrella no castee.
    base = (mapreduce_sql.construir(spark, compras, ventas)
            .withColumn("anio", F.col("anio").cast("int"))
            .withColumn("mes", F.col("mes").cast("int")))

    stock = _delta_stock(spark, produccion)
    if stock is None:
        base = base.withColumn("delta_stock_kg", F.lit(None).cast("double"))
    else:
        base = base.join(F.broadcast(stock), list(LLAVE), "left")

    # `merma_es_supuesto` la consume `v_kpi_1` de F06 para etiquetar el KPI: es
    # nula cuando no se descuenta merma, porque entonces no hay supuesto que
    # declarar.
    if merma_pct is None:
        base = (base.withColumn("merma_tecnica_kg", F.lit(None).cast("double"))
                    .withColumn("merma_es_supuesto", F.lit(None).cast("boolean")))
    else:
        base = (base.withColumn("merma_tecnica_kg",
                                F.col("kg_comprados") * F.lit(float(merma_pct)))
                    .withColumn("merma_es_supuesto",
                                F.lit(bool(config.MERMA_TECNICA_ES_SUPUESTO))))

    base = (base
            .withColumn("diferencia_bruta_kg", F.col("kg_comprados") - F.col("kg_vendidos"))
            .withColumn("kg_no_explicados",
                        F.col("diferencia_bruta_kg")
                        - F.coalesce(F.col("delta_stock_kg"), F.lit(0.0))
                        - F.coalesce(F.col("merma_tecnica_kg"), F.lit(0.0)))
            .withColumn("pct_no_explicado",
                        F.when(F.col("kg_comprados") > 0,
                               F.col("kg_no_explicados") / F.col("kg_comprados")))
            # Un mes con compras y sin ventas, o al reves, es un mes con una
            # fuente incompleta: el KPI se calcula igual, pero marcado.
            .withColumn("mes_completo",
                        (F.col("kg_comprados") > 0) & (F.col("kg_vendidos") > 0)))

    precios = precio_mes(spark, compras)
    base = (base.join(F.broadcast(precios), ["anio", "mes"], "left")
                .withColumn("valor_soles",
                            F.col("kg_no_explicados") * F.col("precio_soles_kg")))

    return base.select(*COLUMNAS)


def escribir(spark, df, catalogo: str = iceberg.CATALOGO, base: str = iceberg.BASE_GOLD) -> str:
    """MERGE INTO `fact_balance_planta` por producto, anio y mes."""
    return iceberg.escribir_merge(spark, df, TABLA, list(LLAVE), catalogo=catalogo, base=base)


def construir_y_escribir(spark, compras, ventas, produccion=None,
                         merma_pct: float | None = config.MERMA_TECNICA_PCT,
                         catalogo: str = iceberg.CATALOGO,
                         base: str = iceberg.BASE_GOLD) -> str:
    return escribir(spark, construir(spark, compras, ventas, produccion, merma_pct),
                    catalogo=catalogo, base=base)
