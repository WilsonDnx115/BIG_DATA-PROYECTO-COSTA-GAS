"""URL prefirmada para cargar la entrega desde el portal (W22, M9).

El portal no sube el archivo por la Lambda: pide una URL prefirmada y el
navegador escribe directo en S3. Asi un Excel de 62 MB no pasa por la funcion.

Dos limites que no se negocian:

* la URL vale **5 minutos** y es de un solo `PUT`;
* la clave esta siempre bajo `landing/interno/`, con el nombre normalizado, y
  solo con una extension que admita `contracts/_archivos.yaml`.

Ese prefijo es el que dispara la Lambda de ingesta (W02), asi que un archivo
subido desde el portal recorre el mismo camino que uno cargado a mano: huella
SHA-256, manifiesto y Bronze inmutable.
"""
from __future__ import annotations

import os
import re
from pathlib import PurePosixPath

from src.common import config
from src.ingest.entrega import _reglas
from src.portal import manejar, usuario

PREFIJO = "landing/interno/"
VIGENCIA_S = 300
METODO = "put_object"
NOMBRE_SEGURO = re.compile(r"^[A-Za-z0-9 ()._-]{1,120}$")


def extensiones() -> tuple[str, ...]:
    """Las que declara el contrato de archivos; no hay una lista aparte aqui."""
    return tuple(_reglas().get("extensiones", ()))


def clave(nombre: str) -> str:
    """Valida el nombre y devuelve la clave de S3. No acepta rutas, solo nombres."""
    limpio = PurePosixPath(nombre.replace("\\", "/")).name
    if limpio != nombre or not NOMBRE_SEGURO.match(limpio):
        raise ValueError(f"nombre de archivo no admitido: {nombre}")
    admitidas = extensiones()
    if admitidas and not limpio.lower().endswith(tuple(e.lower() for e in admitidas)):
        raise ValueError(f"extension fuera de _archivos.yaml (admite {', '.join(admitidas)})")
    return f"{PREFIJO}{limpio}"


def firmar(nombre: str, bucket: str | None = None, cliente=None) -> dict:
    """Devuelve la URL prefirmada y su vigencia; no escribe nada en S3."""
    import boto3  # noqa: PLC0415

    destino = clave(nombre)
    s3 = cliente or boto3.client("s3")
    url = s3.generate_presigned_url(
        METODO,
        Params={"Bucket": bucket or os.environ.get("LAKE_BUCKET", config.BUCKET),
                "Key": destino, "ServerSideEncryption": "AES256"},
        ExpiresIn=VIGENCIA_S)
    return {"url": url, "clave": destino, "vigencia_s": VIGENCIA_S}


def accion(cuerpo: dict, claims: dict) -> dict:
    datos = firmar(cuerpo["nombre"])
    # Queda en el log quien pidio la carga; el nombre sale del token, no del cuerpo.
    print(f"[portal] URL de carga para {datos['clave']} pedida por {usuario(claims)}")
    return datos


def lambda_handler(event: dict, context=None) -> dict:  # noqa: ARG001
    return manejar(event, accion)
