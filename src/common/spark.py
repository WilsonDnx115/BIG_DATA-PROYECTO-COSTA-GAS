"""Sesión de Spark común a local y Glue (S4, S5).

* AQE activado (coalesce de particiones y skew join) — tratamiento del data skew (S3).
* `spark.sql.shuffle.partitions` parametrizable: con 124 MB, 200 particiones
  por defecto generarían tareas vacías.
* En Glue, `getOrCreate()` reutiliza la sesión que crea el servicio.
"""
from __future__ import annotations

from src.common import config


def obtener_spark(app: str = "costagas"):
    from pyspark.sql import SparkSession  # noqa: PLC0415

    b = (SparkSession.builder.appName(app)
         .config("spark.sql.adaptive.enabled", "true")
         .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
         .config("spark.sql.adaptive.skewJoin.enabled", "true")
         .config("spark.sql.shuffle.partitions", str(config.SPARK_SHUFFLE_PARTITIONS))
         .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
         .config("spark.sql.parquet.compression.codec", "snappy")
         .config("spark.sql.session.timeZone", "America/Lima"))
    if not config.LAKE_URI.startswith("s3://"):
        b = b.master("local[*]")
    return b.getOrCreate()


def guardar_plan(df, nombre: str) -> str:
    """Guarda la salida de explain() como evidencia (3.6). Sin collect()."""
    from pathlib import Path  # noqa: PLC0415

    plan = df._jdf.queryExecution().toString()  # mismo texto que explain(True)
    destino = config.RAIZ_REPO / "docs" / "evidencias" / f"explain_{nombre}.txt"
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    Path(destino).write_text(plan, encoding="utf-8")
    return str(destino)
