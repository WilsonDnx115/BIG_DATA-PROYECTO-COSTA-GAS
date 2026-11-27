"""Precios de GLP publicados en Facilito (Osinergmin), semanal (W20).

Facilito es el comparador publico de precios de combustibles de Osinergmin.
Da el contexto de mercado de la senal S10 (precio bajo la mediana del canal):
sin el, un precio atipico de la empresa no se puede contrastar con el de la
plaza. Opera a nivel de establecimiento, distrito y producto; no trae personas.

El endpoint se declara aqui y se puede sustituir por variable de entorno
(`FACILITO_URL`), porque es un servicio publico sin contrato de API estable:
antes de programar la funcion hay que confirmarlo contra el servicio real y
dejar la evidencia de la primera corrida en `docs/evidencias/`.
"""
from __future__ import annotations

import json
import os

from src.extractores import RespuestaInvalida, escribir, hoy, pedir

URL = os.environ.get("FACILITO_URL",
                     "https://www.facilito.gob.pe/facilito/rest/consulta/precios")
FUENTE = "facilito"
DEPARTAMENTO = os.environ.get("FACILITO_DEPARTAMENTO", "LA LIBERTAD")
PRODUCTOS = ("GLP ENVASADO", "GLP GRANEL")


def descargar(producto: str, departamento: str = DEPARTAMENTO) -> list:
    """Precios de un producto en un departamento, como los devuelve el servicio."""
    crudo = pedir(URL, params={"producto": producto, "departamento": departamento})
    datos = json.loads(crudo)
    registros = datos.get("data", datos) if isinstance(datos, dict) else datos
    if not registros:
        raise RespuestaInvalida(f"Facilito no devolvio precios de {producto} en {departamento}")
    return registros


def extraer(productos=PRODUCTOS, departamento: str = DEPARTAMENTO) -> list[str]:
    """Un archivo JSON por producto, sin consolidar: el crudo se guarda tal cual."""
    fecha = hoy()
    rutas_escritas = []
    for producto in productos:
        registros = descargar(producto, departamento)
        nombre = f"{producto.lower().replace(' ', '_')}__{fecha.isoformat()}.json"
        cuerpo = json.dumps({"producto": producto, "departamento": departamento,
                             "consultado": fecha.isoformat(), "registros": registros},
                            ensure_ascii=False).encode("utf-8")
        rutas_escritas.append(escribir(cuerpo, FUENTE, nombre, fecha))
    return rutas_escritas


def lambda_handler(event: dict | None = None, context=None) -> dict:  # noqa: ARG001
    """Programa `costagas-facilito-semanal`."""
    evento = event or {}
    productos = tuple(evento.get("productos") or PRODUCTOS)
    return {"fuente": FUENTE, "rutas": extraer(productos,
                                               evento.get("departamento", DEPARTAMENTO))}
