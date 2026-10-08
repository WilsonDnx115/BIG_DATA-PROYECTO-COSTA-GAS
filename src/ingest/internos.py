"""Ingesta de fuentes internas a Bronze (pasos 3.2.2 y 3.2.5) — ELT.

Copia los archivos SIN transformar a
  bronze/interno/estructurado/<proceso>/<codigo>/fecha_carga=YYYY-MM-DD/<nombre original>
y registra cada uno en el manifiesto. Bronze es inmutable: una nueva entrega
crea una nueva partición fecha_carga, nunca sobrescribe.

Uso:
  python -m src.ingest.internos --origen data/sample/entrega
  python -m src.ingest.internos --origen data/raw   # datos reales (nunca se versionan)
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from src.common import rutas
from src.ingest.manifest import Manifiesto

EXTENSIONES = {".csv", ".xlsx", ".xls", ".json"}


def destino_bronze(proceso: str, codigo: str, fecha_carga: str, nombre: str) -> str:
    if proceso == "externo":
        return rutas.ruta("bronze", "externo", "publico", codigo, f"fecha_carga={fecha_carga}", nombre)
    return rutas.ruta("bronze", "interno", "estructurado", proceso, codigo,
                      f"fecha_carga={fecha_carga}", nombre)


def subir(local: Path, destino: str) -> None:
    if destino.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = destino[5:].split("/", 1)
        boto3.client("s3").upload_file(str(local), bucket, key,
                                       ExtraArgs={"ServerSideEncryption": "AES256"})
        return
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    if Path(destino).exists():
        return                                    # inmutable: no se sobrescribe
    shutil.copy2(local, destino)


def ingerir(origen: Path, fecha_carga: str | None = None) -> list[str]:
    """Recorre <origen>/<proceso>/<codigo>/<archivo> y sube cada archivo a Bronze."""
    man = Manifiesto(fecha_carga)
    destinos = []
    for f in sorted(Path(origen).rglob("*")):
        if f.suffix.lower() not in EXTENSIONES or f.name.startswith("_"):
            continue
        rel = f.relative_to(origen).parts
        if len(rel) < 3:
            continue
        proceso, codigo = rel[0], rel[1]
        destino = destino_bronze(proceso, codigo, man.fecha_carga, f.name)
        subir(f, destino)
        man.agregar(f, codigo, destino)
        destinos.append(destino)
    man.guardar()
    return destinos


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--origen", type=Path, required=True)
    ap.add_argument("--fecha-carga", default=None)
    a = ap.parse_args()
    for d in ingerir(a.origen, a.fecha_carga):
        print(d)
