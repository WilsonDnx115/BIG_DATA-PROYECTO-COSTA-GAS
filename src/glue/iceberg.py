"""Escritura en tablas Iceberg del catalogo de Gold (W04, informe 3.5).

Gold se escribe siempre con `MERGE INTO` sobre las llaves del grano, nunca con
`append`: una corrida que vuelve a procesar un mes actualiza sus filas en vez de
duplicarlas. Esa es la propiedad que el job necesita para poder reintentarse.

`escribir_merge` crea la tabla la primera vez con el esquema del DataFrame; a
partir de ahi los DDL de W09 son la fuente de verdad y esta funcion solo
actualiza datos.
"""
from __future__ import annotations

from src.common import config

CATALOGO = "glue_catalog"
BASE_GOLD = "costagas_gold"
VERSION_ICEBERG = "1.6.1"          # runtime para Spark 3.5 (Glue 5.0)
PAQUETE = f"org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:{VERSION_ICEBERG}"


def configurar(builder, catalogo: str = CATALOGO, almacen: str | None = None,
               tipo: str = "glue"):
    """Agrega a un builder de Spark el catalogo Iceberg.

    tipo="glue" en AWS (el catalogo de datos de Glue) y tipo="hadoop" en las
    pruebas locales, con `almacen` apuntando a una carpeta temporal.
    """
    b = (builder
         .config("spark.sql.extensions",
                 "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
         .config(f"spark.sql.catalog.{catalogo}", "org.apache.iceberg.spark.SparkCatalog"))
    if tipo == "hadoop":
        b = (b.config(f"spark.sql.catalog.{catalogo}.type", "hadoop")
              .config(f"spark.sql.catalog.{catalogo}.warehouse", almacen)
              .config("spark.jars.packages", PAQUETE))
    else:
        b = (b.config(f"spark.sql.catalog.{catalogo}.catalog-impl",
                      "org.apache.iceberg.aws.glue.GlueCatalog")
              .config(f"spark.sql.catalog.{catalogo}.warehouse", almacen or config.LAKE_URI)
              .config(f"spark.sql.catalog.{catalogo}.io-impl",
                      "org.apache.iceberg.aws.s3.S3FileIO"))
    return b


def nombre(tabla: str, catalogo: str = CATALOGO, base: str = BASE_GOLD) -> str:
    """`fact_alerta` -> `glue_catalog.costagas_gold.fact_alerta` (ya calificado se respeta)."""
    return tabla if tabla.count(".") >= 2 else f"{catalogo}.{base}.{tabla}"


def existe(spark, tabla: str, catalogo: str = CATALOGO, base: str = BASE_GOLD) -> bool:
    return spark.catalog.tableExists(nombre(tabla, catalogo, base))


def crear_si_no_existe(spark, df, tabla: str, particiones=config.PARTICIONES,
                       catalogo: str = CATALOGO, base: str = BASE_GOLD) -> str:
    """Crea la tabla Iceberg con el esquema del DataFrame. Particiona solo por anio/mes."""
    completo = nombre(tabla, catalogo, base)
    if existe(spark, tabla, catalogo, base):
        return completo
    cols = [c for c in particiones if c in df.columns]
    escritor = df.limit(0).writeTo(completo).using("iceberg")
    if cols:
        from pyspark.sql.functions import col  # noqa: PLC0415

        escritor = escritor.partitionedBy(*[col(c) for c in cols])
    escritor.create()
    return completo


def escribir_merge(spark, df, tabla: str, llaves: list[str] | tuple[str, ...],
                   catalogo: str = CATALOGO, base: str = BASE_GOLD) -> str:
    """MERGE INTO por `llaves`: actualiza lo que ya estaba e inserta lo nuevo.

    Correr dos veces con las mismas llaves deja una sola fila por llave.
    """
    if not llaves:
        raise ValueError("escribir_merge necesita al menos una llave del grano")
    faltan = [k for k in llaves if k not in df.columns]
    if faltan:
        raise ValueError(f"{tabla}: el DataFrame no trae las llaves {faltan}")

    completo = crear_si_no_existe(spark, df, tabla, catalogo=catalogo, base=base)
    vista = f"nuevos_{tabla.split('.')[-1]}"
    df.createOrReplaceTempView(vista)
    condicion = " AND ".join(f"d.{k} = n.{k}" for k in llaves)
    spark.sql(f"""
        MERGE INTO {completo} AS d
        USING {vista} AS n
        ON {condicion}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    spark.catalog.dropTempView(vista)
    return completo


def instantanea_actual(spark, tabla: str, catalogo: str = CATALOGO,
                       base: str = BASE_GOLD) -> int | None:
    """Id de la ultima instantanea, que W14 usa para leer solo lo nuevo."""
    completo = nombre(tabla, catalogo, base)
    if not existe(spark, tabla, catalogo, base):
        return None
    filas = (spark.sql(f"SELECT snapshot_id, committed_at FROM {completo}.snapshots")
             .orderBy("committed_at", ascending=False)
             .take(1))                      # take(), nunca collect()
    return filas[0]["snapshot_id"] if filas else None
