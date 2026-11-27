"""Resoluciones de Osinergmin en PDF, mensual (W20, informe seccion 3.3).

Son el unico insumo no estructurado del proyecto junto con el texto de las
fuentes publicas: el job de externos (W21) las lee como binarios y las pasa a
texto con pdfplumber dentro de cada particion. Aqui solo se bajan y se guardan
tal cual, con su nombre de origen, para que el PDF original quede trazable.

La lista de URL se pasa en el evento o se toma de `RESOLUCIONES_URLS`
(separadas por coma), porque el buscador de Osinergmin no expone una API
estable: antes de programar la funcion hay que fijar la lista y dejar la
evidencia de la primera corrida en `docs/evidencias/`.
"""
from __future__ import annotations

import os

from src.extractores import RespuestaInvalida, escribir, hoy

CABECERA_PDF = b"%PDF-"
FUENTE = "resoluciones"
URLS = tuple(u for u in os.environ.get("RESOLUCIONES_URLS", "").split(",") if u.strip())


def nombre_de(url: str) -> str:
    """El nombre del archivo en el origen; si la URL no lo trae, se arma uno."""
    cola = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return cola if cola.lower().endswith(".pdf") else f"{cola or 'resolucion'}.pdf"


def descargar(url: str, descargador=None) -> bytes:
    """Baja un PDF y comprueba que de verdad sea un PDF antes de guardarlo."""
    from src.extractores import pedir  # noqa: PLC0415

    contenido = (descargador or pedir)(url)
    if not contenido.startswith(CABECERA_PDF):
        raise RespuestaInvalida(f"{url} no devolvio un PDF")
    return contenido


def extraer(urls=None, descargador=None) -> list[str]:
    """Un objeto por resolucion. Sin URL que bajar, no escribe nada."""
    lista = tuple(urls) if urls is not None else URLS
    if not lista:
        raise RespuestaInvalida(
            "sin URL de resoluciones: pase «urls» en el evento o defina RESOLUCIONES_URLS")
    fecha = hoy()
    return [escribir(descargar(u, descargador), FUENTE, nombre_de(u), fecha) for u in lista]


def lambda_handler(event: dict | None = None, context=None) -> dict:  # noqa: ARG001
    """Programa `costagas-resoluciones-mensual`."""
    evento = event or {}
    return {"fuente": FUENTE, "rutas": extraer(evento.get("urls"))}
