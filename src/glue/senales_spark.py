"""Señales determinísticas en Spark para el job de Gold (informe v16, 4.2 y Tabla 4.3).

Son funciones puras: reciben DataFrames de Silver y devuelven alertas con el
contrato `fact_alerta`. El job `src/glue/gold_job.py` (Wilson) las llama; este
módulo no lee ni escribe en el lago.

Esta versión porta a Spark las señales de `src/signals/senales.py` (pandas) con la
misma lógica, para que la conciliación por evento corra repartida en el clúster:

  S1  placa cargada distinta de la facturada            filtro
  S4  carga superior a la capacidad autorizada           join con broadcast(flota)
  S5  volumen a un cliente superior a su capacidad       join con broadcast(maestro)
  S7  operación de una unidad no habilitada para GLP     left_anti con broadcast(flota habilitada)
  S8  venta sin compra que la respalde (circuito SCOP)   left_anti por codigo_scop
  S10 precio de venta bajo la mediana de su canal        ventana con percentile exacto

S2, S3, S6, S9, S11 y S12 se agregan en los commits F03 y F04. Sin collect().
"""
from __future__ import annotations

from src.common import config, schemas

# Tabla 4.3 del informe: descripción y grado de evidencia de cada señal.
# S1, S4 y S7 son indicios porque la muestra es mínima (2 a 9 casos; Tabla 5.3).
CATALOGO: dict[str, tuple[str, str]] = {
    "S1": ("Placa cargada distinta de la facturada", "indicio"),
    "S2": ("Compra sin SCOP o SCOP repetido", "alta"),
    "S3": ("Precio de compra fuera de lo pactado o de la mediana", "media"),
    "S4": ("Carga superior a la capacidad autorizada", "indicio"),
    "S5": ("Volumen a un distribuidor superior a su capacidad", "media"),
    "S6": ("Tipo de cambio distinto del oficial", "alta"),
    "S7": ("Operación de una unidad no habilitada para GLP", "indicio"),
    "S8": ("Venta sin compra que la respalde (circuito SCOP)", "alta"),
    "S9": ("Combustible sin venta o carga proporcional", "media"),
    "S10": ("Precio de venta bajo la mediana de su canal", "media"),
    "S11": ("Cierre de planta sin medición física", "alta"),
    "S12": ("Factura sin segundo registro o con kg distinto entre tesorería y logística", "alta"),
}

COLUMNAS_ALERTA = schemas.CONTRATOS["fact_alerta"].columnas()


def _alertas(df, senal: str, placa: str, kg: str = "kg", puntaje=None):
    """Lleva las filas que disparan una señal al contrato `fact_alerta`."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    puntaje = F.lit(1.0) if puntaje is None else puntaje
    out = df.select(
        F.lit(senal).alias("senal"),
        F.lit("regla").alias("tipo"),
        F.col("fecha").cast("date").alias("fecha"),
        F.col(placa).cast("string").alias("placa_norm"),
        F.col("documento").cast("string").alias("documento"),
        F.col(kg).cast("double").alias("kg"),
        (F.col(kg).cast("double") * F.lit(config.PRECIO_REF_KG)).alias("valor_soles"),
        puntaje.cast("double").alias("puntaje"),
        F.lit(CATALOGO[senal][1]).alias("grado_evidencia"),
        F.lit("pendiente").alias("estado_revision"),
        F.col("anio").cast("int").alias("anio"),
        F.col("mes").cast("int").alias("mes"),
    )
    # Identificador determinístico: la misma alerta en otra corrida tiene el mismo id (MERGE idempotente).
    clave = F.concat_ws("|", F.col("senal"), F.coalesce(F.col("documento"), F.lit("")),
                        F.coalesce(F.col("placa_norm"), F.lit("")))
    out = out.withColumn("id_alerta", F.substring(F.md5(clave), 1, 12))
    return out.select(*COLUMNAS_ALERTA)


def s1(compras):
    """Placa cargada distinta de la facturada en la misma orden."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    d = compras.filter(F.coalesce(F.col("flag_placa_divergente"), F.lit(False)))
    return _alertas(d, "S1", "placa_cargada")


def s4(compras, flota):
    """Carga mayor que la capacidad autorizada del vehículo que la llevó."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cap = flota.select(F.col("placa_norm").alias("_placa_flota"), "capacidad_kg")
    d = (compras.join(broadcast(cap), compras["placa_cargada"] == cap["_placa_flota"], "inner")
         .filter(F.col("kg") > F.col("capacidad_kg")))
    return _alertas(d, "S4", "placa_cargada", puntaje=F.col("kg") / F.col("capacidad_kg"))


def s5(ventas, maestro):
    """Venta a un cliente mayor que la capacidad de almacenamiento de su local."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cap = maestro.select("card_code", F.col("capacidad_kg").alias("cap_local"))
    d = (ventas.join(broadcast(cap), "card_code", "inner")
         .filter(F.col("cap_local").isNotNull() & (F.col("kg") > F.col("cap_local"))))
    return _alertas(d, "S5", "placa_norm", puntaje=F.col("kg") / F.col("cap_local"))


def s7(compras, flota):
    """Compras cargadas en una unidad que no está habilitada para trasladar GLP."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    habilitadas = (flota.filter(F.coalesce(F.col("habilitada"), F.lit(False)))
                   .select(F.col("placa_norm").alias("_placa_hab")).dropna().distinct())
    c = compras.withColumn("_placa", F.col("placa_cargada"))
    d = c.join(broadcast(habilitadas), c["_placa"] == habilitadas["_placa_hab"], "left_anti")
    return _alertas(d, "S7", "_placa")


def s8(ventas, compras):
    """Venta con código SCOP que no cierra con ninguna compra."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    con_scop = ventas.filter(F.col("codigo_scop").isNotNull())
    claves = compras.select("codigo_scop").dropna().distinct()
    d = con_scop.join(claves, "codigo_scop", "left_anti")
    return _alertas(d, "S8", "placa_norm")


def s10(ventas):
    """Precio más de TOL_PRECIO_S10 bajo la mediana de su canal, producto y mes."""
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    w = Window.partitionBy("canal", "id_producto", "anio", "mes")
    # percentile(…, 0.5) es la mediana exacta con interpolación (igual que pandas), no la aproximada.
    v = (ventas.filter(F.col("precio").isNotNull())
         .withColumn("mediana", F.expr("percentile(precio, 0.5)").over(w)))
    d = v.filter(F.col("precio") < F.col("mediana") * F.lit(1 - config.TOL_PRECIO_S10))
    return _alertas(d, "S10", "placa_norm", puntaje=F.lit(1.0) - F.col("precio") / F.col("mediana"))


def calcular(compras, ventas, flota, maestro):
    """Une las alertas de las señales de esta versión en un solo DataFrame."""
    from functools import reduce  # noqa: PLC0415

    partes = [s1(compras), s4(compras, flota), s5(ventas, maestro),
              s7(compras, flota), s8(ventas, compras), s10(ventas)]
    return reduce(lambda a, b: a.unionByName(b), partes)
