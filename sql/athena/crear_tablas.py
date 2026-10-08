"""Ejecuta los DDL y vistas de KPIs en el workgroup del proyecto (paso 3.5.2).

Uso:  LAKE_URI=s3://costagas-trujillo-lake-<sufijo> python -m sql.athena.crear_tablas
Costo: los DDL no escanean datos (US$ 0.00).
"""
from __future__ import annotations

import time
from pathlib import Path

import boto3

from src.common import config

DIR = Path(__file__).parent


def ejecutar(sql: str, athena) -> str:
    q = athena.start_query_execution(QueryString=sql, WorkGroup=config.ATHENA_WORKGROUP)["QueryExecutionId"]
    while True:
        e = athena.get_query_execution(QueryExecutionId=q)["QueryExecution"]["Status"]
        if e["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if e["State"] != "SUCCEEDED":
                raise RuntimeError(e.get("StateChangeReason"))
            return q
        time.sleep(1)


def main() -> None:
    if not config.LAKE_URI.startswith("s3://"):
        raise SystemExit("LAKE_URI debe apuntar a S3")
    athena = boto3.client("athena", region_name=config.AWS_REGION)
    for f in sorted((DIR / "ddl").glob("*.sql")) + sorted((DIR / "kpis").glob("*.sql")):
        sql = f.read_text(encoding="utf-8").replace("${LAKE}", config.LAKE_URI.rstrip("/"))
        sql = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
        print(f.name, ejecutar(sql, athena))


if __name__ == "__main__":
    main()
