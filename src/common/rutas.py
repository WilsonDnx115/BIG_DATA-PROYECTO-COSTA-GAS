"""Construcción de rutas del lago a partir de LAKE_URI (paso 2.3.1).

`ruta("silver", "movimientos")` devuelve `s3://bucket/silver/movimientos` en la
nube o una ruta absoluta local en desarrollo. Así el mismo job corre en local,
en Lambda y en Glue cambiando solo la variable de entorno: «HDFS (o S3) es una
implementación, no la arquitectura» (S2).
"""
from __future__ import annotations

from pathlib import Path

from src.common import config

CAPAS = ("bronze", "silver", "gold", "_manifests", "scaletest", "athena-results")


def base(lake_uri: str | None = None) -> str:
    uri = lake_uri or config.LAKE_URI
    if uri.startswith("file://"):
        local = Path(uri[len("file://"):])
        if not local.is_absolute():
            local = config.RAIZ_REPO / local
        return local.as_posix()
    return uri.rstrip("/")


def es_s3(uri: str | None = None) -> bool:
    return base(uri).startswith("s3://")


def ruta(*partes: str, lake_uri: str | None = None) -> str:
    if partes and partes[0] not in CAPAS:
        raise ValueError(f"Capa desconocida: {partes[0]}. Use una de {CAPAS}")
    limpio = [p.strip("/") for p in partes if p]
    return "/".join([base(lake_uri), *limpio])


def ruta_spark(*partes: str, lake_uri: str | None = None) -> str:
    """En Spark local se usa el esquema file://; en S3 (Glue) s3:// funciona tal cual."""
    r = ruta(*partes, lake_uri=lake_uri)
    return r if es_s3(lake_uri) else "file:///" + r.lstrip("/")


def asegurar_local(*partes: str, lake_uri: str | None = None) -> str:
    r = ruta(*partes, lake_uri=lake_uri)
    if not es_s3(lake_uri):
        Path(r).mkdir(parents=True, exist_ok=True)
    return r
