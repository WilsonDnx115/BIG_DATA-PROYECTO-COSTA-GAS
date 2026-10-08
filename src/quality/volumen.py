"""Medición de volumen por capa y fuente (pasos 1.7.1 y 3.3.12; V de volumen y variedad, S1).

Reporta tamaño y número de archivos por fuente y tipo (estructurado,
semiestructurado, no estructurado). Comparar Bronze contra Silver evidencia la
compactación de archivos pequeños (S2).
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from src.common import config, rutas

TIPO_POR_EXT = {".csv": "estructurado", ".xlsx": "estructurado", ".xls": "estructurado",
                ".parquet": "estructurado", ".json": "semiestructurado", ".html": "semiestructurado",
                ".vtt": "no_estructurado", ".pdf": "no_estructurado", ".txt": "no_estructurado"}


def _listar(prefijo: str):
    if prefijo.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = prefijo[5:].split("/", 1)
        pag = boto3.client("s3").get_paginator("list_objects_v2")
        for p in pag.paginate(Bucket=bucket, Prefix=key):
            for o in p.get("Contents", []):
                yield o["Key"], o["Size"]
    else:
        base = Path(prefijo)
        for f in base.rglob("*"):
            if f.is_file():
                yield f.relative_to(base.parent).as_posix(), f.stat().st_size


def _fuente(ruta: str, capa: str) -> str:
    if capa == "bronze":
        m = re.search(r"bronze/(?:interno/estructurado/[^/]+|externo/[^/]+)/([^/]+)/", ruta)
    else:
        m = re.search(rf"{capa}/([^/]+(?:/[^/=]+)?)/", ruta)
    return m.group(1) if m else "otros"


def medir(capas=("bronze", "silver", "gold")) -> list[dict]:
    filas = []
    for capa in capas:
        agg = defaultdict(lambda: {"archivos": 0, "bytes": 0})
        for ruta, tam in _listar(rutas.ruta(capa)):
            tipo = TIPO_POR_EXT.get(Path(ruta).suffix.lower(), "otro")
            k = (_fuente(ruta, capa), tipo)
            agg[k]["archivos"] += 1
            agg[k]["bytes"] += tam
        for (fuente, tipo), v in sorted(agg.items()):
            filas.append({"capa": capa, "fuente": fuente, "tipo": tipo, **v})
    return filas


def a_markdown(filas: list[dict]) -> str:
    lin = ["| Capa | Fuente | Tipo | Archivos | MB |", "|---|---|---|---:|---:|"]
    lin += [f"| {f['capa']} | {f['fuente']} | {f['tipo']} | {f['archivos']} | {f['bytes'] / 1e6:.2f} |"
            for f in filas]
    return "\n".join(lin)


if __name__ == "__main__":
    md = a_markdown(medir())
    destino = config.RAIZ_REPO / "docs" / "evidencias" / "volumen.md"
    destino.write_text("# Volumen por capa y fuente (1.7.1)\n\n" + md + "\n", encoding="utf-8")
    print(md)
