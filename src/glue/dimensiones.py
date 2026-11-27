"""Dimensiones del modelo estrella de Gold (W08, informe Tabla 4.9).

Seis dimensiones, todas en Iceberg y sin datos personales: de las personas y de
las contrapartes solo viaja el hash que ya trae Silver, nunca el nombre, el DNI
ni el RUC (`dim_contraparte` guarda si el RUC es valido, no el RUC).

Ninguna dimension se particiona: son tablas chicas y el particionado solo
tendria sentido en los hechos.
"""
from __future__ import annotations

from pathlib import Path

from src.common import config, limpieza
from src.glue import iceberg, senales_spark

# Unidad de transporte si su clase o su uso la nombran; si no, de reparto.
PATRON_TRANSPORTE = "CISTERNA|TRACTO|GRANELERO|REMOLQUE|SEMIRREMOLQUE"
PATRON_PRESENTACION = limpieza._RE_PRESENTACION.pattern   # noqa: SLF001
PATRON_DIGITOS = "([0-9]+)"

LLAVES: dict[str, list[str]] = {
    "dim_tiempo": ["id_tiempo"],
    "dim_unidad": ["placa_norm"],
    "dim_persona": ["persona_hash", "tipo"],
    "dim_producto": ["articulo_codigo"],
    "dim_contraparte": ["documento_hash"],
    "dim_senal": ["id_senal"],
}


def dim_tiempo(spark, anio_ini: int | None = None, anio_fin: int | None = None):
    """Generada, no leida: un mes por fila, con la ventana de analisis y 2020."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    ini, fin = anio_ini or config.ANIO_INI, anio_fin or config.ANIO_FIN
    anios = spark.range(ini, fin + 1).withColumnRenamed("id", "anio")
    meses = spark.range(1, 13).withColumnRenamed("id", "mes")
    return (anios.crossJoin(meses)
            .withColumn("anio", F.col("anio").cast("int"))
            .withColumn("mes", F.col("mes").cast("int"))
            .withColumn("id_tiempo", F.col("anio") * 100 + F.col("mes"))
            .withColumn("trimestre", ((F.col("mes") - 1) / 3 + 1).cast("int"))
            .withColumn("en_ventana_analisis",
                        (F.col("anio") >= config.ANIO_INI) & (F.col("anio") <= config.ANIO_FIN))
            .withColumn("pandemia_2020", F.col("anio") == F.lit(config.ANIO_PILOTO))
            .select("id_tiempo", "anio", "mes", "trimestre",
                    "en_ventana_analisis", "pandemia_2020")
            .orderBy("id_tiempo"))


def dim_unidad(unidades, compras=None, ventas=None):
    """Una fila por placa: rol, capacidad, habilitacion GLP, empresa y si esta en el maestro.

    El universo son las placas vistas en los movimientos mas las del maestro de
    vehiculos; `presente_en_maestro` dice si la placa figura en el maestro, que
    es justo lo que miran S4 y S7.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    texto = F.upper(F.concat_ws(" ", F.coalesce(F.col("clase"), F.lit("")),
                                F.coalesce(F.col("uso"), F.lit(""))))
    maestro = (unidades
               .filter(F.col("placa_norm").isNotNull())
               .withColumn("texto", texto)
               .withColumn("rol",
                           F.when(F.col("texto").rlike(PATRON_TRANSPORTE), F.lit("transporte"))
                           .when(F.length(F.trim(F.col("texto"))) > 0, F.lit("reparto")))
               .groupBy("placa_norm")
               .agg(F.max("empresa").alias("empresa"),
                    F.max("marca").alias("marca"),
                    F.max("clase").alias("clase"),
                    F.max("capacidad_glp_kg").alias("capacidad_kg"),
                    F.max(F.col("traslada_gas").cast("int")).cast("boolean").alias("habilitada_glp"),
                    F.max("rol").alias("rol"))
               .withColumn("presente_en_maestro", F.lit(True)))

    vistas = None
    for df in (compras, ventas):
        if df is None or "placa_norm" not in df.columns:
            continue
        placas = df.select("placa_norm").filter(F.col("placa_norm").isNotNull()).distinct()
        vistas = placas if vistas is None else vistas.unionByName(placas)
    if vistas is None:
        return maestro

    return (vistas.distinct()
            .join(F.broadcast(maestro), "placa_norm", "left_outer")   # el maestro es chico
            .withColumn("presente_en_maestro",
                        F.coalesce(F.col("presente_en_maestro"), F.lit(False)))
            .unionByName(maestro, allowMissingColumns=True)
            .dropDuplicates(["placa_norm"]))


def dim_persona(compras=None, ventas=None):
    """Solo el hash y el tipo. Ninguna columna de nombre ni de documento."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    partes = []
    if compras is not None and "conductor_hash" in compras.columns:
        partes.append(compras.select(F.col("conductor_hash").alias("persona_hash"))
                      .withColumn("tipo", F.lit("conductor")))
    if ventas is not None and "vendedor_hash" in ventas.columns:
        partes.append(ventas.select(F.col("vendedor_hash").alias("persona_hash"))
                      .withColumn("tipo", F.lit("vendedor")))
    if not partes:
        return None
    df = partes[0]
    for otro in partes[1:]:
        df = df.unionByName(otro)
    return df.filter(F.col("persona_hash").isNotNull()).distinct()


def dim_producto(ventas):
    """Presentacion en kg, GLP-E o GLP-G y marca (sin fuente todavia: queda nula)."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    presentacion = F.regexp_extract(F.upper(F.col("articulo")), PATRON_PRESENTACION, 0)
    return (ventas.filter(F.col("es_glp"))
            .select("articulo_codigo", "articulo")
            .distinct()
            .withColumn("coincidencia", presentacion)
            .withColumn("presentacion_kg",
                        F.when(F.col("coincidencia") != "",
                               F.regexp_extract(F.col("coincidencia"),
                                                PATRON_DIGITOS, 1).cast("double")))
            .withColumn("producto", F.when(F.col("presentacion_kg").isNotNull(), F.lit("GLP-E"))
                        .otherwise(F.lit("GLP-G")))
            # La entrega no trae marca comercial por articulo: se declara nula,
            # no se inventa. Se llena cuando la empresa entregue ese maestro.
            .withColumn("marca", F.lit(None).cast("string"))
            .drop("coincidencia"))


def dim_contraparte(maestro):
    """Hash, tipo, si el RUC es valido y capacidad. El RUC no se publica."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    if maestro is None:
        return None
    columnas = [F.col("documento_hash"),
                F.col("clase_documento").alias("tipo"),
                F.col("ruc_valido"),
                F.col("capacidad_kg")]
    for opcional in ("estado", "canal"):
        if opcional in maestro.columns:
            columnas.append(F.col(opcional))
    return maestro.select(*columnas).filter(F.col("documento_hash").isNotNull()).distinct()


CATALOGO_YAML = Path(__file__).resolve().parents[1] / "signals" / "catalogo.yaml"
ESQUEMA_SENAL = ("id_senal string, descripcion string, resolucion string, "
                 "ventana string, estado string, grado_evidencia string")


def _catalogo_yaml(ruta: Path | None = None) -> dict:
    """Resolucion, ventana y estado de cada senal, del catalogo S1-S12.

    La Tabla 4.9 pide esos tres campos en `dim_senal` y solo viven en el
    catalogo YAML; si falta el archivo quedan nulos, nunca inventados.
    """
    import yaml  # noqa: PLC0415

    archivo = ruta or CATALOGO_YAML
    if not archivo.exists():
        return {}
    datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
    return datos.get("senales", {})


def dim_senal(spark, ruta_catalogo: Path | None = None):
    """Catalogo S1-S12: descripcion, resolucion, ventana, estado y evidencia (Tabla 4.9).

    La descripcion y el grado de evidencia salen del catalogo de Frank
    (`senales_spark.CATALOGO`), que es el que usa el detector; la resolucion, la
    ventana y el estado salen del YAML, que es donde se declaran.
    """
    detalle = _catalogo_yaml(ruta_catalogo)
    filas = []
    for codigo, (descripcion, grado) in sorted(senales_spark.CATALOGO.items(),
                                               key=lambda kv: int(kv[0][1:])):
        d = detalle.get(codigo, {})
        filas.append((codigo, descripcion, d.get("resolucion"), d.get("ventana"),
                      d.get("estado"), grado))
    return spark.createDataFrame(filas, ESQUEMA_SENAL)


def construir(spark, fuentes: dict) -> dict:
    """Las seis dimensiones. Las que todavia no tienen fuente no se devuelven."""
    salida = {
        "dim_tiempo": dim_tiempo(spark),
        "dim_senal": dim_senal(spark),
        "dim_persona": dim_persona(fuentes.get("compras"), fuentes.get("ventas")),
        "dim_contraparte": dim_contraparte(fuentes.get("maestro")),
    }
    if fuentes.get("unidades") is not None:
        salida["dim_unidad"] = dim_unidad(fuentes["unidades"], fuentes.get("compras"),
                                          fuentes.get("ventas"))
    if fuentes.get("ventas") is not None:
        salida["dim_producto"] = dim_producto(fuentes["ventas"])
    return {k: v for k, v in salida.items() if v is not None}


def construir_y_escribir(spark, fuentes: dict, base: str = iceberg.BASE_GOLD) -> list[str]:
    """MERGE de cada dimension en su tabla Iceberg, sin particionar."""
    escritas = []
    for tabla, df in construir(spark, fuentes).items():
        iceberg.crear_si_no_existe(spark, df, tabla, particiones=(), base=base)
        escritas.append(iceberg.escribir_merge(spark, df, tabla, LLAVES[tabla], base=base))
    return escritas
