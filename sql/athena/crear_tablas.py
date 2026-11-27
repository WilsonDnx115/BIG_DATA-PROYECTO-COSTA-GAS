"""Ejecuta los DDL de Silver y Gold y las vistas en el workgroup del proyecto (3.5).

Orden fijo, porque cada grupo depende del anterior: primero las tablas de Silver,
luego los hechos y dimensiones de Gold en Iceberg y al final las vistas que leen
de Gold. Dentro de cada grupo se ordena por nombre, para que la corrida sea
reproducible.

Uso:
  LAKE_URI=s3://costagas-trujillo-lake-<sufijo> python -m sql.athena.crear_tablas
  LAKE_URI=...                                   python -m sql.athena.crear_tablas --solo gold

Costo: los DDL no escanean datos (US$ 0.00).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import boto3

from src.common import config

DIR = Path(__file__).parent

# Grupo -> (subcarpeta, patron). El orden del diccionario es el orden de ejecucion.
GRUPOS: dict[str, tuple[str, str]] = {
    "silver": ("ddl", "silver_*.sql"),
    "gold": ("ddl", "gold_*.sql"),
    "vistas": ("vistas", "*.sql"),
}


def archivos_a_ejecutar(directorio: Path | str = DIR, solo: str | None = None) -> list[Path]:
    """Lista los .sql a ejecutar en orden: ddl/silver_*, ddl/gold_* y vistas/*.

    Los archivos que no siguen esa convencion de nombres quedan fuera: asi los
    DDL antiguos que no corresponden al informe no se ejecutan por descuido.
    """
    directorio = Path(directorio)
    if solo is not None and solo not in GRUPOS:
        raise ValueError(f"Grupo desconocido: {solo}. Use uno de {tuple(GRUPOS)}")
    grupos = (solo,) if solo else tuple(GRUPOS)
    archivos: list[Path] = []
    for grupo in grupos:
        subcarpeta, patron = GRUPOS[grupo]
        archivos.extend(sorted((directorio / subcarpeta).glob(patron)))
    return archivos


def ejecutar(sql: str, athena) -> str:
    q = athena.start_query_execution(QueryString=sql, WorkGroup=config.ATHENA_WORKGROUP)["QueryExecutionId"]
    while True:
        e = athena.get_query_execution(QueryExecutionId=q)["QueryExecution"]["Status"]
        if e["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if e["State"] != "SUCCEEDED":
                raise RuntimeError(e.get("StateChangeReason"))
            return q
        time.sleep(1)


def preparar(archivo: Path) -> str:
    """Resuelve ${LAKE} y quita los comentarios, que Athena no acepta en algunos DDL."""
    sql = archivo.read_text(encoding="utf-8").replace("${LAKE}", config.LAKE_URI.rstrip("/"))
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Crea las tablas y vistas de Athena del proyecto.")
    p.add_argument("--solo", choices=tuple(GRUPOS), help="ejecuta solo ese grupo")
    args = p.parse_args(argv)

    if not config.LAKE_URI.startswith("s3://"):
        raise SystemExit("LAKE_URI debe apuntar a S3")
    athena = boto3.client("athena", region_name=config.AWS_REGION)
    for f in archivos_a_ejecutar(DIR, args.solo):
        print(f.name, ejecutar(preparar(f), athena))


if __name__ == "__main__":
    main()
