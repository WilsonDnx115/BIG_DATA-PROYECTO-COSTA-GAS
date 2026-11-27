"""Job de fuentes externas: `costagas-externos` (W21, informe seccion 3.3).

Lee lo que dejaron los extractores de W20 en `landing/externo/` y hace tres
cosas, en una sola corrida mensual en FLEX:

1. **Eventos de GDELT** con el patron MapReduce en DataFrames: cada evento del
   pais emite (anio, mes, codigo de evento) y el reduce los cuenta. Sale a
   `gold/mr/gdelt_eventos/`, al lado del balance de W05, para comparar los dos
   caminos del curso sobre el mismo universo.
2. **Texto**: las resoluciones en PDF se leen como binarios y se pasan a texto
   con pdfplumber dentro de cada particion (nunca en el driver), y a ese texto
   se suman los titulos y descripciones de YouTube. Sobre el texto consolidado
   corre un Pipeline de Spark MLlib (tokenizar, quitar palabras vacias en
   espanol, vectorizar) y LDA agrupa por temas.
3. **Contexto de mercado**: `gold.mercado_mes` junta por anio y mes el precio de
   la plaza (Facilito), el tipo de cambio oficial (BCRP), los eventos contados y
   los temas. Es la tabla de contexto que usa el tablero; **no es una medicion
   de la empresa** y no entra en ningun KPI de perdida.

Ninguna fuente externa trae personas: operan a nivel de marca, mes y mercado.
Lo que no tiene cobertura queda nulo, nunca en cero: un mes sin archivos de
Facilito no es un mes con precio cero.

Uso local (pruebas):
    python -m src.glue.externos_job --lake_uri file://data/lake --k 3
"""
from __future__ import annotations

import argparse
import os

from src.common import config, rutas
from src.glue import iceberg

FUENTES = ("bcrp", "facilito", "youtube", "gdelt", "resoluciones")
PAIS = "PE"
DESTINO_MR = ("gold", "mr", "gdelt_eventos")
DESTINO_TEXTO = ("silver", "entorno", "textos")
DESTINO_TEMAS = ("silver", "entorno", "temas")
DESTINO_EVENTOS = ("silver", "entorno", "gdelt")
# Destino y columnas que fija el ADR 0015 para la fuente NE-01/NE-02.
DESTINO_YOUTUBE = ("silver", "entorno", "youtube")
COLUMNAS_YOUTUBE = ("video_id", "publicado", "canal", "titulo",
                    "descripcion", "consulta")
TABLA_MERCADO = "mercado_mes"
LLAVE_MERCADO = ["anio", "mes"]
K_TEMAS = int(os.environ.get("LDA_K_TEMAS", "5"))
PALABRAS_MINIMAS = 2

# GDELT export v2.0: 61 campos separados por tabulador y sin encabezado. El
# esquema se declara (nunca inferSchema); Spark descarta los campos de mas.
CAMPOS_GDELT = (
    "global_event_id", "sqldate", "month_year", "anio_gdelt", "fraction_date",
    "actor1_code", "actor1_name", "actor1_country", "actor1_group", "actor1_etnia",
    "actor1_religion1", "actor1_religion2", "actor1_tipo1", "actor1_tipo2", "actor1_tipo3",
    "actor2_code", "actor2_name", "actor2_country", "actor2_group", "actor2_etnia",
    "actor2_religion1", "actor2_religion2", "actor2_tipo1", "actor2_tipo2", "actor2_tipo3",
    "is_root_event", "event_code", "event_base_code", "event_root_code", "quad_class",
    "goldstein", "n_menciones", "n_fuentes", "n_articulos", "tono_promedio",
    "actor1_geo_tipo", "actor1_geo_nombre", "actor1_geo_pais", "actor1_geo_adm1",
    "actor1_geo_adm2", "actor1_geo_lat", "actor1_geo_long", "actor1_geo_id",
    "actor2_geo_tipo", "actor2_geo_nombre", "actor2_geo_pais", "actor2_geo_adm1",
    "actor2_geo_adm2", "actor2_geo_lat", "actor2_geo_long", "actor2_geo_id",
    "accion_geo_tipo", "accion_geo_nombre", "accion_geo_pais", "accion_geo_adm1",
    "accion_geo_adm2", "accion_geo_lat", "accion_geo_long", "accion_geo_id",
    "fecha_agregado", "url_fuente",
)
NUMERICOS_GDELT = {"anio_gdelt": "int", "goldstein": "double", "n_menciones": "int",
                   "n_fuentes": "int", "n_articulos": "int", "tono_promedio": "double"}

SQL_MAPA_GDELT = """
    SELECT CAST(substring(sqldate, 1, 4) AS int) AS anio,
           CAST(substring(sqldate, 5, 2) AS int) AS mes,
           event_root_code AS codigo_evento,
           CAST(n_articulos AS double) AS n_articulos,
           CAST(tono_promedio AS double) AS tono_promedio,
           1 AS uno
      FROM {eventos}
     WHERE sqldate IS NOT NULL AND length(sqldate) = 8
       AND accion_geo_pais = '{pais}'
"""

SQL_REDUCE_GDELT = """
    SELECT anio, mes, codigo_evento,
           SUM(uno) AS n_eventos,
           SUM(n_articulos) AS n_articulos,
           AVG(tono_promedio) AS tono_promedio
      FROM {pares}
     GROUP BY anio, mes, codigo_evento
"""


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Argumentos del job. Ignora los que agrega Glue (--JOB_NAME y demas)."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--lake_uri", default=config.LAKE_URI)
    p.add_argument("--catalogo", default=iceberg.CATALOGO)
    p.add_argument("--k", type=int, default=K_TEMAS, help="numero de temas de LDA")
    args, _ = p.parse_known_args(argv)
    return args


def ruta_fuente(fuente: str, lake_uri: str | None = None) -> str:
    """`landing/externo/<fuente>/`, en el esquema que entiende Spark."""
    if fuente not in FUENTES:
        raise ValueError(f"Fuente externa desconocida: {fuente}. Use una de {FUENTES}")
    return rutas.ruta_spark("landing", "externo", fuente, lake_uri=lake_uri)


def esquema_gdelt() -> str:
    """Esquema declarado del export de GDELT: todo string salvo los numericos."""
    return ", ".join(f"{c} {NUMERICOS_GDELT.get(c, 'string')}" for c in CAMPOS_GDELT)


# --- 1. Eventos de GDELT con el patron MapReduce ------------------------------

def leer_gdelt(spark, lake_uri: str | None = None):
    """Los bloques `.csv.gz` de W20, con esquema declarado y separador tabulador."""
    return (spark.read
            .option("sep", "\t")
            .option("header", "false")
            .option("mode", "PERMISSIVE")
            .schema(esquema_gdelt())
            .csv(f"{ruta_fuente('gdelt', lake_uri)}/*/*/*.csv.gz"))


def mapear_eventos(spark, eventos, pais: str = PAIS):
    """Map: una fila por evento del pais, con su mes y su codigo."""
    eventos.createOrReplaceTempView("gdelt_eventos_crudos")
    return spark.sql(SQL_MAPA_GDELT.format(eventos="gdelt_eventos_crudos", pais=pais))


def contar_eventos(spark, eventos, pais: str = PAIS):
    """Reduce: eventos, articulos y tono por anio, mes y codigo de evento."""
    pares = mapear_eventos(spark, eventos, pais)
    pares.createOrReplaceTempView("gdelt_pares")
    return spark.sql(SQL_REDUCE_GDELT.format(pares="gdelt_pares"))


def escribir_eventos(conteo, lake_uri: str | None = None) -> str:
    """Parquet en `gold/mr/gdelt_eventos/`, particionado solo por anio y mes."""
    destino = rutas.ruta_spark(*DESTINO_MR, lake_uri=lake_uri)
    (conteo.repartition(*config.PARTICIONES)
           .write.mode("overwrite").partitionBy(*config.PARTICIONES)
           .parquet(destino))
    return destino


# --- 2. Texto: resoluciones en PDF y texto de YouTube -------------------------

def _texto_de_pdf(contenido: bytes) -> str:
    """pdfplumber sobre los bytes del PDF. Corre en el executor, no en el driver."""
    import io  # noqa: PLC0415

    import pdfplumber  # noqa: PLC0415

    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def texto_de_resoluciones(spark, lake_uri: str | None = None, extractor=None):
    """Lee los PDF como binarios y los pasa a texto dentro de cada particion."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.types import StringType  # noqa: PLC0415

    binarios = (spark.read.format("binaryFile")
                .option("pathGlobFilter", "*.pdf")
                .load(ruta_fuente("resoluciones", lake_uri)))
    a_texto = F.udf(extractor or _texto_de_pdf, StringType())
    return (binarios
            .withColumn("texto", a_texto(F.col("content")))
            .withColumn("fuente", F.lit("resoluciones"))
            .select(F.col("path").alias("origen"), "fuente", "texto"))


def tabla_youtube(spark, lake_uri: str | None = None):
    """Silver de YouTube con las columnas del ADR 0015, una fila por video.

    `id del video, fecha, canal, titulo y descripcion`. Nada de quien comenta:
    la fuente externa opera a nivel de marca, mes y mercado.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    esquema = ("consulta string, canal string, consultado string, "
               "items array<struct<title:string, description:string, "
               "channelTitle:string, publishedAt:string, video_id:string>>")
    crudo = (spark.read.option("multiLine", "true").schema(esquema)
             .json(f"{ruta_fuente('youtube', lake_uri)}/*/*.json"))
    item = F.explode("items").alias("item")
    return (crudo.select("consulta", item)
            .select(F.col("item.video_id").alias("video_id"),
                    F.to_date(F.col("item.publishedAt")).alias("publicado"),
                    F.col("item.channelTitle").alias("canal"),
                    F.col("item.title").alias("titulo"),
                    F.col("item.description").alias("descripcion"),
                    "consulta")
            .dropDuplicates(["video_id"]))


def texto_de_youtube(spark, lake_uri: str | None = None):
    """El mismo Silver de YouTube, visto como texto para el pipeline de temas."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    return (tabla_youtube(spark, lake_uri)
            .select(F.col("video_id").alias("origen"),
                    F.lit("youtube").alias("fuente"),
                    F.concat_ws(". ", "titulo", "descripcion").alias("texto")))


def consolidar_texto(spark, lake_uri: str | None = None, extractor=None):
    """Un solo DataFrame `origen, fuente, texto` con lo que haya disponible."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    partes = []
    for leer in (lambda: texto_de_resoluciones(spark, lake_uri, extractor),
                 lambda: texto_de_youtube(spark, lake_uri)):
        try:
            partes.append(leer())
        except Exception as e:                      # noqa: BLE001, PERF203
            # Sin archivos de esa fuente el job sigue: lo que falta queda fuera,
            # no se rellena. El motivo se imprime en el log de la corrida.
            print(f"[externos] sin texto de una fuente: {type(e).__name__}: {e}")
    if not partes:
        return None
    union = partes[0]
    for p in partes[1:]:
        union = union.unionByName(p)
    return union.filter(F.col("texto").isNotNull() & (F.length(F.trim("texto")) > 0))


def pipeline_temas(k: int = K_TEMAS, vocabulario: int = 5000, semilla: int = 42):
    """Pipeline de MLlib: tokenizar, quitar palabras vacias en espanol, vectorizar, LDA."""
    from pyspark.ml import Pipeline  # noqa: PLC0415
    from pyspark.ml.clustering import LDA  # noqa: PLC0415
    from pyspark.ml.feature import CountVectorizer, RegexTokenizer, StopWordsRemover  # noqa: PLC0415

    return Pipeline(stages=[
        RegexTokenizer(inputCol="texto", outputCol="palabras",
                       pattern=r"[^\p{L}]+", minTokenLength=3, toLowercase=True),
        StopWordsRemover(inputCol="palabras", outputCol="utiles",
                         stopWords=StopWordsRemover.loadDefaultStopWords("spanish")),
        CountVectorizer(inputCol="utiles", outputCol="vector",
                        vocabSize=vocabulario, minDF=1.0),
        LDA(featuresCol="vector", k=k, seed=semilla, maxIter=10),
    ])


def temas(textos, k: int = K_TEMAS):
    """Ajusta el pipeline y devuelve (modelo, temas, documentos puntuados).

    `temas` trae una fila por tema con sus palabras; `documentos`, la mezcla de
    temas de cada texto. Con menos de `k` documentos LDA no tiene de donde
    estimar: se devuelve `(None, None, None)` en lugar de un modelo que no
    significa nada.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    utiles = textos.filter(F.size(F.split(F.col("texto"), r"\s+")) >= PALABRAS_MINIMAS)
    if utiles.limit(k).count() < k:
        print(f"[externos] menos de {k} textos utiles: LDA no corre")
        return None, None, None
    modelo = pipeline_temas(k).fit(utiles)
    lda = modelo.stages[-1]
    # El UDF se queda con el vocabulario (una lista de str), nunca con el modelo
    # del vectorizador: ese lleva un candado y Spark no lo puede serializar.
    vocabulario = list(modelo.stages[-2].vocabulary)
    palabras = F.udf(lambda idx: [vocabulario[i] for i in idx], "array<string>")
    descripcion = (lda.describeTopics(10)
                   .withColumn("palabras", palabras(F.col("termIndices")))
                   .select(F.col("topic").alias("tema"), "palabras",
                           F.col("termWeights").alias("pesos")))
    return modelo, descripcion, modelo.transform(utiles)


def escribir_texto(textos, temas_df, lake_uri: str | None = None) -> list[str]:
    """Silver del entorno: el texto consolidado y los temas, sin particionar."""
    escritas = []
    for df, destino in ((textos, DESTINO_TEXTO), (temas_df, DESTINO_TEMAS)):
        if df is None:
            continue
        ruta = rutas.ruta_spark(*destino, lake_uri=lake_uri)
        df.write.mode("overwrite").parquet(ruta)
        escritas.append(ruta)
    return escritas


# --- 3. Contexto de mercado: gold.mercado_mes ---------------------------------

def precios_mes(spark, lake_uri: str | None = None):
    """Precio mediano de la plaza por anio, mes y producto, desde Facilito."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    esquema = ("producto string, departamento string, consultado string, "
               "registros array<struct<establecimiento:string, distrito:string, "
               "producto:string, precio:double>>")
    crudo = (spark.read.option("multiLine", "true").schema(esquema)
             .json(f"{ruta_fuente('facilito', lake_uri)}/*/*.json"))
    return (crudo
            .withColumn("fecha", F.to_date("consultado"))
            .withColumn("registro", F.explode("registros"))
            .groupBy(F.year("fecha").alias("anio"), F.month("fecha").alias("mes"),
                     F.col("producto"))
            .agg(F.expr("percentile_approx(registro.precio, 0.5)").alias("precio_mediano"),
                 F.countDistinct("registro.establecimiento").alias("n_establecimientos")))


def tipo_cambio_mes(spark, lake_uri: str | None = None):
    """Tipo de cambio oficial promedio por mes, desde el JSON del BCRP."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    esquema = "periods array<struct<name:string, values:array<string>>>"
    crudo = (spark.read.option("multiLine", "true").schema(esquema)
             .json(f"{ruta_fuente('bcrp', lake_uri)}/*/*.json"))
    periodo = F.explode("periods").alias("p")
    return (crudo.select(periodo)
            .withColumn("fecha", F.to_date("p.name", "dd.MMM.yy"))
            .withColumn("tc", F.col("p.values")[0].cast("double"))
            .filter(F.col("fecha").isNotNull() & F.col("tc").isNotNull())
            .groupBy(F.year("fecha").alias("anio"), F.month("fecha").alias("mes"))
            .agg(F.avg("tc").alias("tipo_cambio_promedio"),
                 F.count("tc").alias("n_dias_tc")))


def mercado_mes(spark, conteo=None, precios=None, tc=None, temas_df=None):
    """Tabla de contexto por anio y mes. Lo que no tiene fuente queda nulo.

    No es una medicion de la empresa: son precios de la plaza, tipo de cambio y
    volumen de noticias. Sirve para leer un KPI en su contexto, no para
    imputarle perdidas a nadie.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    base = None
    for df in (conteo, precios, tc):
        if df is None:
            continue
        llaves = df.select("anio", "mes").distinct()
        base = llaves if base is None else base.unionByName(llaves).distinct()
    if base is None:
        return None

    salida = base
    if conteo is not None:
        eventos = conteo.groupBy("anio", "mes").agg(
            F.sum("n_eventos").cast("long").alias("n_eventos_gdelt"),
            F.avg("tono_promedio").alias("tono_promedio"))
        salida = salida.join(F.broadcast(eventos), LLAVE_MERCADO, "left")
    else:
        salida = (salida.withColumn("n_eventos_gdelt", F.lit(None).cast("long"))
                        .withColumn("tono_promedio", F.lit(None).cast("double")))
    if precios is not None:
        plaza = precios.groupBy("anio", "mes").agg(
            F.avg("precio_mediano").alias("precio_mediano_plaza"),
            F.sum("n_establecimientos").cast("long").alias("n_establecimientos"))
        salida = salida.join(F.broadcast(plaza), LLAVE_MERCADO, "left")
    else:
        salida = (salida.withColumn("precio_mediano_plaza", F.lit(None).cast("double"))
                        .withColumn("n_establecimientos", F.lit(None).cast("long")))
    if tc is not None:
        salida = salida.join(F.broadcast(tc.select("anio", "mes", "tipo_cambio_promedio")),
                             LLAVE_MERCADO, "left")
    else:
        salida = salida.withColumn("tipo_cambio_promedio", F.lit(None).cast("double"))
    n_temas = temas_df.count() if temas_df is not None else None
    salida = salida.withColumn("n_temas", F.lit(n_temas).cast("int"))
    return salida.select("anio", "mes", "n_eventos_gdelt", "tono_promedio",
                         "precio_mediano_plaza", "n_establecimientos",
                         "tipo_cambio_promedio", "n_temas")


def escribir_mercado(spark, df, catalogo: str = iceberg.CATALOGO) -> str | None:
    """MERGE por anio y mes: una corrida mensual no duplica el mes anterior."""
    if df is None:
        return None
    iceberg.crear_si_no_existe(spark, df, TABLA_MERCADO, catalogo=catalogo)
    return iceberg.escribir_merge(spark, df, TABLA_MERCADO, LLAVE_MERCADO, catalogo=catalogo)


# --- Orquestacion -------------------------------------------------------------

def ejecutar(spark, args, extractor=None) -> dict:
    """Las tres partes del job. Una fuente ausente no tumba la corrida."""
    resumen: dict = {"escrito": [], "sin_cobertura": []}

    conteo = None
    try:
        conteo = contar_eventos(spark, leer_gdelt(spark, args.lake_uri))
        resumen["escrito"].append(escribir_eventos(conteo, args.lake_uri))
    except Exception as e:                          # noqa: BLE001
        print(f"[externos] sin eventos de GDELT: {type(e).__name__}: {e}")
        resumen["sin_cobertura"].append("gdelt")

    try:
        youtube = tabla_youtube(spark, args.lake_uri)
        youtube.take(1)                         # fuerza la lectura: take(), no collect()
        destino_yt = rutas.ruta_spark(*DESTINO_YOUTUBE, lake_uri=args.lake_uri)
        youtube.write.mode("overwrite").parquet(destino_yt)
        resumen["escrito"].append(destino_yt)
    except Exception as e:                      # noqa: BLE001
        print(f"[externos] sin videos de YouTube: {type(e).__name__}: {e}")
        resumen["sin_cobertura"].append("youtube")

    textos = consolidar_texto(spark, args.lake_uri, extractor)
    _, descripcion, _ = temas(textos, args.k) if textos is not None else (None, None, None)
    if textos is None:
        resumen["sin_cobertura"].append("texto")
    resumen["escrito"].extend(escribir_texto(textos, descripcion, args.lake_uri))

    precios = tc = None
    for nombre_fuente, leer in (("facilito", lambda: precios_mes(spark, args.lake_uri)),
                                ("bcrp", lambda: tipo_cambio_mes(spark, args.lake_uri))):
        try:
            df = leer()
            df.take(1)                              # fuerza la lectura: take(), no collect()
        except Exception as e:                      # noqa: BLE001, PERF203
            print(f"[externos] sin {nombre_fuente}: {type(e).__name__}: {e}")
            resumen["sin_cobertura"].append(nombre_fuente)
            continue
        if nombre_fuente == "facilito":
            precios = df
        else:
            tc = df
    escrita = escribir_mercado(spark, mercado_mes(spark, conteo, precios, tc, descripcion),
                               args.catalogo)
    if escrita:
        resumen["escrito"].append(escrita)
    return resumen


def main(argv: list[str] | None = None) -> dict:
    from src.glue.gold_job import crear_sesion  # noqa: PLC0415

    args = argumentos(argv)
    spark = crear_sesion(args.lake_uri, args.catalogo, app="costagas-externos")
    try:
        resumen = ejecutar(spark, args)
    finally:
        if not args.lake_uri.startswith("s3://"):
            spark.stop()                 # en Glue la sesion la cierra el servicio
    print(resumen)
    return resumen


if __name__ == "__main__":
    main()
