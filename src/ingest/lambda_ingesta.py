"""Lambda de ingesta: de `landing/` a Bronze con huella SHA-256 (W02, Tabla 2.7c).

Cada objeto que llega a `landing/` o a `op/landing/` dispara esta funcion. El
flujo es siempre el mismo:

1. se calcula el SHA-256 del objeto por bloques (sin cargarlo entero en memoria);
2. si esa huella ya figura en `_manifests/`, el archivo se anota como duplicado
   y no se copia: Bronze no cuenta dos veces la misma fuente;
3. si no, se copia SIN transformar (ELT) a
   `bronze/interno/estructurado/<dominio>/<codigo>/fecha_carga=AAAA-MM-DD/<nombre>`,
   con el dominio que resuelve `contracts/_archivos.yaml`;
4. se escribe su entrada de manifiesto (fuente, fecha, huella y tamano).

Lo que llega a `op/landing/` va a `op/bronze/`: es el lago de la operacion
mensual (W18), con la misma estructura.

Cada invocacion escribe su propia entrada de manifiesto
(`_manifests/fecha_carga=<fecha>/<codigo>__<huella>.json`) en lugar de reescribir
un `manifest.json` comun: varias invocaciones corren a la vez y una escritura
compartida perderia entradas. La huella va en el nombre, asi que comprobar si un
contenido ya se cargo es listar claves, sin leer ningun archivo.

Un archivo con una extension que `_archivos.yaml` no admite levanta excepcion: la
`EventInvokeConfig` de la funcion la deriva a la cola `costagas-eventos-fallidos`
(W03).
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import unquote_plus

from src.common import lake_io, rutas
from src.ingest.entrega import _reglas, codigo, dominio
from src.ingest.manifest import entrada, sha256

PREFIJOS = ("landing/", "op/landing/")
PREFIJO_EXTERNO = "landing/externo/"
TMP = Path(os.environ.get("CARPETA_TMP", "/tmp"))


class ExtensionNoAdmitida(ValueError):
    """Extension fuera de `_archivos.yaml`: el evento va a la cola de fallas."""


def claves_del_evento(event: dict) -> list[str]:
    """Claves de S3 del evento de notificacion, ya sin el escape de la URL."""
    claves = []
    for r in event.get("Records", []):
        clave = r.get("s3", {}).get("object", {}).get("key")
        if clave:
            claves.append(unquote_plus(clave))
    return claves


def es_operacion(clave: str) -> bool:
    return clave.startswith("op/landing/")


def ruta_origen(clave: str) -> str:
    return f"{rutas.base()}/{clave}"


def ruta_destino(nombre: str, fecha_carga: str, reglas: dict, operacion: bool = False) -> str:
    partes = ("interno", "estructurado", dominio(nombre, reglas), codigo(nombre),
              f"fecha_carga={fecha_carga}", nombre)
    return rutas.ruta("op", "bronze", *partes) if operacion else rutas.ruta("bronze", *partes)


def ruta_manifiesto(nombre: str, fecha_carga: str, huella: str) -> str:
    return rutas.ruta("_manifests", f"fecha_carga={fecha_carga}",
                      f"{codigo(nombre)}__{huella}.json")


def _listar(prefijo: str) -> list[str]:
    """Claves (o rutas) bajo un prefijo del lago, en S3 y en el lago local."""
    if rutas.es_s3():
        import boto3  # noqa: PLC0415

        bucket, raiz = rutas.base()[5:].split("/", 1) if "/" in rutas.base()[5:] else (rutas.base()[5:], "")
        inicio = f"{raiz}/{prefijo}".lstrip("/")
        pag = boto3.client("s3").get_paginator("list_objects_v2")
        return [o["Key"] for p in pag.paginate(Bucket=bucket, Prefix=inicio)
                for o in p.get("Contents", [])]
    base = Path(rutas.base()) / prefijo
    return [p.as_posix() for p in base.rglob("*.json")] if base.exists() else []


def huella_registrada(huella: str) -> str | None:
    """Clave del manifiesto que ya registro esa huella, o None si es contenido nuevo."""
    for clave in _listar("_manifests/"):
        if clave.endswith(f"__{huella}.json"):
            return clave
    return None


def descargar(origen: str) -> Path:
    """Copia local del objeto para calcular su huella por bloques."""
    if not origen.startswith("s3://"):
        return Path(origen)
    import boto3  # noqa: PLC0415

    bucket, key = origen[5:].split("/", 1)
    local = TMP / Path(key).name
    local.parent.mkdir(parents=True, exist_ok=True)
    boto3.client("s3").download_file(bucket, key, str(local))
    return local


def copiar(local: Path, destino: str) -> None:
    """Copia a Bronze sin transformar. Bronze es inmutable: no se sobrescribe."""
    if destino.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = destino[5:].split("/", 1)
        boto3.client("s3").upload_file(str(local), bucket, key,
                                       ExtraArgs={"ServerSideEncryption": "AES256"})
        return
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    if not Path(destino).exists():
        shutil.copy2(local, destino)


def procesar(clave: str, fecha_carga: str | None = None, reglas: dict | None = None) -> dict:
    """Ingiere un objeto de `landing/` y devuelve lo que paso con el."""
    reglas = reglas or _reglas()
    fecha_carga = fecha_carga or date.today().isoformat()
    nombre = Path(clave).name

    if not clave.startswith(PREFIJOS):
        return {"clave": clave, "estado": "fuera_de_landing"}
    if clave.startswith(PREFIJO_EXTERNO):
        # Las fuentes externas (W20) traen JSON, PDF y zip: las procesa el job de
        # externos (W21), no esta funcion.
        return {"clave": clave, "estado": "externo_ignorado"}
    if Path(nombre).suffix.lower() not in reglas["extensiones"]:
        raise ExtensionNoAdmitida(
            f"{nombre}: extension no admitida. _archivos.yaml acepta {reglas['extensiones']}"
        )

    local = descargar(ruta_origen(clave))
    huella = sha256(local)
    ya = huella_registrada(huella)
    if ya:
        return {"clave": clave, "estado": "duplicado", "igual_a": ya, "sha256": huella}

    operacion = es_operacion(clave)
    destino = ruta_destino(nombre, fecha_carga, reglas, operacion)
    copiar(local, destino)
    fila = entrada(local, codigo(nombre), destino, fecha_carga)
    lake_io.escribir_json(fila, ruta_manifiesto(nombre, fecha_carga, huella))
    return {"clave": clave, "estado": "cargado", "destino": destino,
            "dominio": dominio(nombre, reglas), "sha256": huella}


def lambda_handler(event, context=None) -> dict:
    reglas = _reglas()
    fecha_carga = date.today().isoformat()
    resultados = [procesar(c, fecha_carga, reglas) for c in claves_del_evento(event)]
    print(json.dumps(resultados, ensure_ascii=False, default=str))
    return {"procesados": len(resultados), "resultados": resultados}
