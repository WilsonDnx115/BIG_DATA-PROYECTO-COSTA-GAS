"""Lectura y escritura del lago con pandas/pyarrow (Lambda y local).

En S3 se usa awswrangler (capa gestionada «AWS SDK for pandas», paso 2.4.2);
en local, pyarrow directamente. Parquet + Snappy particionado por anio/mes
(S5: column pruning y partition pruning).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.common import config, rutas, schemas


def escribir_parquet(df: pd.DataFrame, destino: str, contrato: str | None = None,
                     modo: str = "overwrite_partitions") -> None:
    """Escribe Parquet Snappy; particiona por anio/mes si el contrato lo indica.

    modo = "overwrite_partitions" reemplaza solo las particiones presentes en df
    (idempotente: reprocesar una carga no duplica filas).
    """
    particionar = True
    if contrato:
        errores = schemas.validar(df, contrato)
        if errores:
            raise ValueError(f"{contrato} no cumple su contrato: {errores}")
        c = schemas.CONTRATOS[contrato]
        particionar = c.particionada
        tabla = pa.Table.from_pandas(df[c.columnas()], schema=c.pyarrow(), preserve_index=False)
    else:
        tabla = pa.Table.from_pandas(df, preserve_index=False)
    cols = list(config.PARTICIONES) if particionar and "anio" in df.columns else None

    if destino.startswith("s3://"):
        import awswrangler as wr  # noqa: PLC0415

        wr.s3.to_parquet(df=tabla.to_pandas(), path=destino, dataset=True,
                         partition_cols=cols, mode=modo if cols else "overwrite",
                         compression="snappy")
        return

    Path(destino).mkdir(parents=True, exist_ok=True)
    if cols is None:
        for f in Path(destino).glob("*.parquet"):
            f.unlink()
        pq.write_table(tabla, f"{destino}/part-00000.snappy.parquet", compression="snappy")
        return
    # Una sola escritura por partición → evita el problema de archivos pequeños (S2)
    pq.write_to_dataset(
        tabla, root_path=destino, partition_cols=cols, compression="snappy",
        existing_data_behavior="delete_matching",
        basename_template="part-{i}.snappy.parquet",
    )


def leer_parquet(origen: str, filtros: list | None = None, columnas: list[str] | None = None) -> pd.DataFrame:
    """Lee con partition pruning (`filtros`) y column pruning (`columnas`)."""
    if origen.startswith("s3://"):
        import awswrangler as wr  # noqa: PLC0415

        part_filter = None
        if filtros:
            def part_filter(p):  # noqa: E306
                return all(str(p.get(c)) == str(v) for c, _, v in filtros)
        return wr.s3.read_parquet(origen, dataset=True, columns=columnas,
                                  partition_filter=part_filter)
    if not Path(origen).exists():
        return pd.DataFrame(columns=columnas or [])
    df = pq.read_table(origen, filters=filtros, columns=columnas,
                       partitioning="hive").to_pandas()
    for c in config.PARTICIONES:
        if c in df.columns:
            df[c] = df[c].astype("int32")
    return df


def escribir_json(obj, destino: str) -> None:
    texto = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if destino.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = destino[5:].split("/", 1)
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=texto.encode("utf-8"),
                                      ServerSideEncryption="AES256")
        return
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    Path(destino).write_text(texto, encoding="utf-8")


def borrar(destino: str) -> None:
    """Borra una tabla o partición (usado por la prueba de reproceso 2.2.1)."""
    if destino.startswith("s3://"):
        import awswrangler as wr  # noqa: PLC0415

        wr.s3.delete_objects(destino)
    elif Path(destino).exists():
        shutil.rmtree(destino)


def tabla(capa: str, *partes: str) -> str:
    return rutas.ruta(capa, *partes)
