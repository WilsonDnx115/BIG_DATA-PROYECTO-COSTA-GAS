"""Patron MapReduce resuelto con Spark SQL, hacia `gold/mr/` (W05, informe 3.3).

Es el mismo Map -> Shuffle -> Reduce de `src/silver_to_gold/mapreduce.py`, pero
escrito en SQL para que Catalyst lo optimice (column pruning, partition pruning
y agregacion parcial antes del shuffle, que hace el papel del Combiner):

  Map      cada linea de compra o de venta emite (producto, anio, mes, kg con signo)
           compras en positivo, ventas en negativo
  Reduce   GROUP BY producto, anio, mes

La version con RDD se mantiene para la comparacion del curso; `mapear_reducir_rdd`
hace aqui el mismo calculo con `reduceByKey` para poder comprobar que los dos
caminos dan los mismos totales.

El producto de una linea de venta sale de la descripcion del articulo con la
MISMA regla que `limpieza.presentacion_kg`: si nombra una presentacion (5, 10,
15 o 45 kg, o BL10) es GLP envasado; si no, granel.
"""
from __future__ import annotations

from src.common import config, limpieza, rutas

DESTINO = ("gold", "mr", "balance")
LLAVE = ("producto", "anio", "mes")
# Fuente unica de la regla: el patron es el de limpieza.presentacion_kg.
PATRON_PRESENTACION = limpieza._RE_PRESENTACION.pattern   # noqa: SLF001
# Dentro de una cadena de Spark SQL la barra invertida es escape: se duplica.
PATRON_SQL = PATRON_PRESENTACION.replace(chr(92), chr(92) * 2)

SQL_MAPA_COMPRAS = """
    SELECT 'GLP-E' AS producto, anio, mes, CAST(kg_glp_e AS double) AS kg_firmado
      FROM {compras} WHERE kg_glp_e IS NOT NULL AND kg_glp_e <> 0
    UNION ALL
    SELECT 'GLP-G' AS producto, anio, mes, CAST(kg_glp_g AS double) AS kg_firmado
      FROM {compras} WHERE kg_glp_g IS NOT NULL AND kg_glp_g <> 0
    UNION ALL
    -- 2020 trae el total en `kg` y el producto en `tipo` (contrato compras_glp).
    SELECT COALESCE(tipo, 'SIN_CLASIFICAR') AS producto, anio, mes, CAST(kg AS double)
      FROM {compras}
     WHERE kg_glp_e IS NULL AND kg_glp_g IS NULL AND kg IS NOT NULL AND kg <> 0
"""

SQL_MAPA_VENTAS = """
    SELECT CASE WHEN regexp_extract(upper(articulo), '{patron}', 0) <> ''
                THEN 'GLP-E' ELSE 'GLP-G' END AS producto,
           anio, mes, -CAST(kg AS double) AS kg_firmado
      FROM {ventas}
     WHERE es_glp AND kg IS NOT NULL AND kg <> 0
"""

SQL_REDUCE = """
    SELECT producto, anio, mes,
           SUM(CASE WHEN kg_firmado > 0 THEN kg_firmado ELSE 0 END) AS kg_comprados,
           SUM(CASE WHEN kg_firmado < 0 THEN -kg_firmado ELSE 0 END) AS kg_vendidos,
           SUM(kg_firmado) AS kg_neto,
           COUNT(*) AS n_lineas
      FROM {pares}
     GROUP BY producto, anio, mes
"""


def mapear(spark, compras, ventas):
    """Fase de mapeo: una fila por (producto, anio, mes, kg con signo)."""
    compras.createOrReplaceTempView("mr_compras")
    ventas.createOrReplaceTempView("mr_ventas")
    sql = (SQL_MAPA_COMPRAS.format(compras="mr_compras") + " UNION ALL "
           + SQL_MAPA_VENTAS.format(ventas="mr_ventas", patron=PATRON_SQL))
    return spark.sql(sql)


def reducir(spark, pares):
    """Fase de reduccion: GROUP BY producto, anio, mes."""
    pares.createOrReplaceTempView("mr_pares")
    return spark.sql(SQL_REDUCE.format(pares="mr_pares")).orderBy(*LLAVE)


def construir(spark, compras, ventas):
    """Map + Reduce en Spark SQL. Devuelve el balance por producto y mes."""
    return reducir(spark, mapear(spark, compras, ventas))


def mapear_reducir_rdd(spark, compras, ventas):
    """El mismo calculo con RDD y `reduceByKey`, para comparar con la version SQL."""
    pares = mapear(spark, compras, ventas)
    return (pares.rdd
            .map(lambda f: ((f.producto, f.anio, f.mes), float(f.kg_firmado)))
            .reduceByKey(lambda a, b: a + b))


def escribir(df, lake_uri: str | None = None) -> str:
    """Parquet en `gold/mr/balance/`, particionado solo por anio y mes."""
    destino = rutas.ruta_spark(*DESTINO, lake_uri=lake_uri)
    (df.repartition(*config.PARTICIONES)
       .write.mode("overwrite").partitionBy(*config.PARTICIONES)
       .parquet(destino))
    return destino
