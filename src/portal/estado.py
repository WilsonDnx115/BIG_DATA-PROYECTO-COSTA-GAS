"""Estado del lago para el portal (W22, M9).

Responde lo que el operador necesita ver despues de una carga, sin abrir la
consola de AWS:

* cuantas entradas de manifiesto hay por fecha de carga (`_manifests/`), que es
  el recuento de archivos que de verdad entraron a Bronze;
* el ultimo control de calidad por tabla (`silver/_control/`), con su fecha.

No lee Bronze ni los archivos crudos: solo manifiestos y control de calidad, que
no llevan datos personales. Los conteos salen de listar claves, asi que la
funcion no descarga ningun objeto del lago.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from src.common import config, rutas
from src.portal import manejar

PREFIJO_MANIFIESTOS = "_manifests/"
PREFIJO_CONTROL = "silver/_control/"
MAXIMO_CLAVES = 10_000


def _bucket() -> str:
    return os.environ.get("LAKE_BUCKET", config.BUCKET)


def claves(prefijo: str, cliente=None) -> list[str]:
    """Claves bajo un prefijo, en S3 o en el lago local de las pruebas."""
    if rutas.es_s3():
        import boto3  # noqa: PLC0415

        s3 = cliente or boto3.client("s3")
        pag = s3.get_paginator("list_objects_v2")
        salida = []
        for pagina in pag.paginate(Bucket=_bucket(), Prefix=prefijo):
            salida.extend(o["Key"] for o in pagina.get("Contents", []))
            if len(salida) >= MAXIMO_CLAVES:
                break
        return salida[:MAXIMO_CLAVES]
    raiz = Path(rutas.base())
    carpeta = raiz / prefijo
    if not carpeta.exists():
        return []
    return sorted(p.relative_to(raiz).as_posix() for p in carpeta.rglob("*") if p.is_file())


def cargas_por_fecha(cliente=None) -> dict[str, int]:
    """`{fecha_carga: archivos}` leyendo solo los nombres de los manifiestos."""
    cuenta: Counter[str] = Counter()
    for k in claves(PREFIJO_MANIFIESTOS, cliente):
        partes = [p for p in k.split("/") if p.startswith("fecha_carga=")]
        if partes and k.endswith(".json"):
            cuenta[partes[0].split("=", 1)[1]] += 1
    return dict(sorted(cuenta.items()))


def calidad_por_tabla(cliente=None) -> dict[str, dict]:
    """Ultimo control de calidad de cada tabla de Silver, con su fecha."""
    salida: dict[str, dict] = {}
    for k in sorted(claves(PREFIJO_CONTROL, cliente)):
        if not k.endswith(".json"):
            continue
        tabla = Path(k).stem
        try:
            if rutas.es_s3():
                import boto3  # noqa: PLC0415

                s3 = cliente or boto3.client("s3")
                crudo = s3.get_object(Bucket=_bucket(), Key=k)["Body"].read()
            else:
                crudo = (Path(rutas.base()) / k).read_bytes()
            salida[tabla] = json.loads(crudo.decode("utf-8"))
        except Exception as e:                  # noqa: BLE001, PERF203
            # Un control ilegible no tumba el portal: se informa y se sigue.
            print(f"[portal] control de calidad ilegible en {k}: {type(e).__name__}")
            salida[tabla] = {"error": "no se pudo leer el control de calidad"}
    return salida


def accion(cuerpo: dict, claims: dict) -> dict:  # noqa: ARG001
    cargas = cargas_por_fecha()
    return {"cargas_por_fecha": cargas,
            "archivos_en_manifiesto": sum(cargas.values()),
            "calidad_silver": calidad_por_tabla()}


def lambda_handler(event: dict, context=None) -> dict:  # noqa: ARG001
    return manejar(event, accion)
