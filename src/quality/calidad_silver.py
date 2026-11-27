"""Tabla `calidad_silver`: la calidad de cada corrida de Silver, lista para Gold (A10).

Cada vez que la Lambda de limpieza procesa una fuente deja un JSON en
`silver/_control/<tabla>/<fuente>.json` con lo que midio esa corrida. Este modulo los
junta en una sola tabla para que el tablero y el job de Gold puedan responder dos
preguntas sin abrir archivos sueltos: que tan completa quedo cada tabla y si cumple las
metas de la Tabla 3.7.

Importa porque `CLAUDE.md` prohibe publicar una metrica de Gold cuando sus fuentes Silver
incumplen las metas de su contrato: `cumple` es la columna que permite ver ese bloqueo.

Lo llama el job de Gold (W07) y se lee con un esquema declarado, nunca con inferSchema.

Uso local:
    python -m src.quality.calidad_silver
"""
from __future__ import annotations

from src.common import config, rutas

# Metas de la Tabla 3.7: metrica de calidad -> umbral minimo que debe alcanzar.
# Solo se evalua la meta cuya metrica esta presente en la corrida; una tabla que no
# declara placas no incumple META_PLACA_VALIDA, simplemente no se le aplica.
METAS: dict[str, tuple[str, float]] = {
    "placa_valida": ("META_PLACA_VALIDA", config.META_PLACA_VALIDA),
    "kg_con_placa_valida": ("META_PLACA_VALIDA", config.META_PLACA_VALIDA),
    "kg_positivo": ("META_KG_EN_RANGO", config.META_KG_EN_RANGO),
    "scop_presente": ("META_SCOP_COMPRAS", config.META_SCOP_COMPRAS),
}

# Metricas que cuentan filas corregidas, no rechazadas: la fila se conserva y se arregla.
# Crece a medida que las transformaciones registren mas correcciones.
CORRECCIONES = ("fechas_invertidas",)

# Tasas de validez que se publican como columna propia cuando la corrida las trae.
VALIDEZ = ("placa_valida", "kg_con_placa_valida", "kg_positivo", "scop_presente",
           "fecha_valida", "documento_presente", "mes_reconocido", "entidad_id_presente")


def esquema():
    """Esquema declarado del JSON de control (`src/silver/procesar.py`)."""
    from pyspark.sql import types as T  # noqa: PLC0415

    hoja = T.StructType([
        T.StructField("hoja", T.StringType()),
        T.StructField("estado", T.StringType()),
        T.StructField("filas_leidas", T.LongType()),
        T.StructField("filas_efectivas", T.LongType()),
        T.StructField("cortada_por_filas_vacias", T.BooleanType()),
        T.StructField("motivo", T.StringType()),
    ])
    return T.StructType([
        T.StructField("tabla", T.StringType()),
        T.StructField("fuente", T.StringType()),
        T.StructField("familia", T.StringType()),
        T.StructField("generado_utc", T.StringType()),
        T.StructField("estado", T.StringType()),
        T.StructField("filas_leidas", T.LongType()),
        T.StructField("filas_efectivas", T.LongType()),
        T.StructField("filas_salida", T.LongType()),
        T.StructField("filas_con_llave_repetida", T.LongType()),
        T.StructField("celdas_con_dato", T.MapType(T.StringType(), T.LongType())),
        T.StructField("descartes", T.MapType(T.StringType(), T.LongType())),
        T.StructField("calidad", T.MapType(T.StringType(), T.DoubleType())),
        T.StructField("hojas", T.ArrayType(hoja)),
    ])


def _suma_mapa(columna):
    """Suma los valores de un MapType sin traer nada al driver."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    return F.aggregate(F.map_values(columna), F.lit(0).cast("long"),
                       lambda acumulado, v: acumulado + F.coalesce(v, F.lit(0).cast("long")))


def construir(spark, ruta_control: str | None = None):
    """Una fila por tabla y corrida con su completitud, validez, unicidad y si cumple.

    `ruta_control` apunta a `silver/_control/`; por defecto sale de `LAKE_URI`.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    base = ruta_control or rutas.ruta_spark("silver", "_control")
    crudo = (spark.read.schema(esquema())
             .option("multiLine", "true")          # procesar.py escribe el JSON con indent=2
             .json(f"{base.rstrip('/')}/*/*.json"))

    columnas = F.size(F.map_keys(F.col("celdas_con_dato")))
    celdas_posibles = F.col("filas_efectivas") * columnas
    completitud = F.when(celdas_posibles > 0,
                         _suma_mapa(F.col("celdas_con_dato")) / celdas_posibles)
    repetidas = F.coalesce(F.col("filas_con_llave_repetida"), F.lit(0).cast("long"))
    unicidad = F.when(F.col("filas_salida") > 0, 1 - repetidas / F.col("filas_salida"))

    df = (crudo
          .withColumn("columnas_declaradas", columnas)
          .withColumn("completitud", completitud)
          .withColumn("unicidad", unicidad)
          .withColumn("filas_con_llave_repetida", repetidas)
          .withColumn("filas_descartadas", _suma_mapa(F.col("descartes")))
          .withColumn("filas_corregidas",
                      sum((F.coalesce(F.col("calidad").getItem(m), F.lit(0.0)) for m in CORRECCIONES),
                          F.lit(0.0)).cast("long")))

    for metrica in VALIDEZ:                        # nula si la corrida no mide esa tasa
        df = df.withColumn(metrica, F.col("calidad").getItem(metrica))

    # Una meta solo se evalua si su metrica esta presente; si falta, no se incumple.
    incumplidas = F.array_compact(F.array(*[
        F.when(F.col("calidad").getItem(m).isNotNull() & (F.col("calidad").getItem(m) < F.lit(umbral)),
               F.lit(nombre))
        for m, (nombre, umbral) in METAS.items()]))

    return (df
            .withColumn("metas_incumplidas", F.array_distinct(incumplidas))
            .withColumn("cumple", F.size(F.col("metas_incumplidas")) == 0)
            .drop("celdas_con_dato", "descartes", "calidad", "hojas"))


if __name__ == "__main__":                         # pragma: no cover - utilidad local
    from src.common.spark import obtener_spark

    sesion = obtener_spark("calidad_silver")
    construir(sesion).show(truncate=False)
    sesion.stop()
