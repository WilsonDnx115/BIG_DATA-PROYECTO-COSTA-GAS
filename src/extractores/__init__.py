"""Extractores de las fuentes externas (W20, informe v16 seccion 2.4 y Tabla 2.5).

Cinco fuentes publicas, cada una en su Lambda y con su programa de EventBridge:

| modulo         | fuente                       | cadencia  | salida                        |
|----------------|------------------------------|-----------|-------------------------------|
| `bcrp`         | tipo de cambio oficial       | diaria    | `landing/externo/bcrp/`       |
| `facilito`     | precios de GLP de Osinergmin | semanal   | `landing/externo/facilito/`   |
| `youtube`      | YouTube Data API v3          | semanal   | `landing/externo/youtube/`    |
| `gdelt`        | eventos GDELT de 2020        | historica | `landing/externo/gdelt/`      |
| `resoluciones` | resoluciones en PDF          | mensual   | `landing/externo/resoluciones/` |

Todos dejan el dato **sin transformar** (ELT): lo que baja de la red se escribe
tal cual y el paso a Silver lo hace el job de externos (W21). `landing/externo/`
es justo el prefijo que la Lambda de ingesta de W02 ignora, porque estos
archivos no son la entrega interna de 35 archivos y no van a Bronze interno.

Las operaciones de red viven todas en `pedir()`, asi que las pruebas sustituyen
esa unica funcion y ningun extractor sale a internet al correr `pytest`.

Ninguna fuente externa trae datos personales: operan a nivel de marca, mes y
mercado. La clave de YouTube no se versiona: se lee de SSM en tiempo de
ejecucion (`/costagas/youtube/api_key`).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.common import rutas

PREFIJO = ("landing", "externo")
TIEMPO_ESPERA = int(os.environ.get("EXTRACTOR_TIMEOUT_S", "30"))
AGENTE = os.environ.get("EXTRACTOR_AGENTE", "costagas-extractor/1.0")
SSM_YOUTUBE = os.environ.get("SSM_PARAM_YOUTUBE", "/costagas/youtube/api_key")


class ClaveAusente(RuntimeError):
    """Falta la clave de la API en SSM: el extractor para con un mensaje claro."""


class RespuestaInvalida(RuntimeError):
    """La fuente respondio algo que no se puede guardar (vacio o con error)."""


def hoy() -> date:
    """Fecha de la corrida en UTC, que es la que usa EventBridge."""
    return datetime.now(timezone.utc).date()


def pedir(url: str, params: dict | None = None, cabeceras: dict | None = None) -> bytes:
    """GET y devuelve el cuerpo en bytes. Unico punto de red de los extractores."""
    completa = f"{url}?{urlencode(params)}" if params else url
    pedido = Request(completa, headers={"User-Agent": AGENTE, **(cabeceras or {})})  # noqa: S310
    with urlopen(pedido, timeout=TIEMPO_ESPERA) as r:  # noqa: S310
        cuerpo = r.read()
    if not cuerpo:
        raise RespuestaInvalida(f"{url} respondio un cuerpo vacio")
    return cuerpo


def clave_youtube(nombre: str | None = None) -> str:
    """Lee la clave de SSM. Nunca se escribe en el log ni en el repositorio."""
    directa = os.environ.get("YOUTUBE_API_KEY")
    if directa:
        return directa
    import boto3  # noqa: PLC0415

    try:
        p = boto3.client("ssm").get_parameter(Name=nombre or SSM_YOUTUBE, WithDecryption=True)
    except Exception as e:  # noqa: BLE001
        raise ClaveAusente(
            f"sin clave de YouTube en {nombre or SSM_YOUTUBE}: "
            "cargue el parametro en SSM antes de programar el extractor") from e
    return p["Parameter"]["Value"]


def destino(fuente: str, nombre: str, fecha: date | None = None) -> str:
    """`landing/externo/<fuente>/fecha_carga=AAAA-MM-DD/<nombre>`."""
    f = fecha or hoy()
    return rutas.ruta(*PREFIJO, fuente, f"fecha_carga={f.isoformat()}", nombre)


def escribir(contenido: bytes, fuente: str, nombre: str, fecha: date | None = None) -> str:
    """Guarda el objeto tal como bajo de la red y devuelve su ruta."""
    ruta = destino(fuente, nombre, fecha)
    if ruta.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, clave = ruta[5:].split("/", 1)
        boto3.client("s3").put_object(Bucket=bucket, Key=clave, Body=contenido,
                                      ServerSideEncryption="AES256")
    else:
        destino_local = Path(ruta)
        destino_local.parent.mkdir(parents=True, exist_ok=True)
        destino_local.write_bytes(contenido)
    return ruta
