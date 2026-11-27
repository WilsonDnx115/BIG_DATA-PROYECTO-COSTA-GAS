"""Tipo de cambio oficial del BCRP, diario (W20).

La regla de calidad de la Tabla 3.7 exige comparar el tipo de cambio registrado
en las facturas con el oficial del BCRP (desvio <= 1 %), y 514 de 942 facturas
traen T.C. = 1. Este extractor baja la serie oficial para esa comparacion; el
T.C. registrado no se pisa nunca, el oficial va en una columna aparte.

Serie PD04640PD: tipo de cambio bancario, venta, en soles por dolar.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from src.extractores import RespuestaInvalida, escribir, hoy, pedir

API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SERIE = "PD04640PD"
FUENTE = "bcrp"
DIAS_ATRAS = 7          # ventana corta: el BCRP publica con rezago de un dia


def url(serie: str, desde: date, hasta: date) -> str:
    return f"{API}/{serie}/json/{desde.isoformat()}/{hasta.isoformat()}"


def descargar(desde: date, hasta: date, serie: str = SERIE) -> dict:
    """Devuelve el JSON de la serie. Levanta si no trae periodos."""
    datos = json.loads(pedir(url(serie, desde, hasta)))
    if not datos.get("periods"):
        raise RespuestaInvalida(f"la serie {serie} no trajo periodos entre {desde} y {hasta}")
    return datos


def extraer(desde: date | None = None, hasta: date | None = None) -> str:
    """Baja la ventana pedida y la guarda tal cual en `landing/externo/bcrp/`."""
    fin = hasta or hoy()
    ini = desde or fin - timedelta(days=DIAS_ATRAS)
    datos = descargar(ini, fin)
    nombre = f"{SERIE}__{ini.isoformat()}__{fin.isoformat()}.json"
    return escribir(json.dumps(datos, ensure_ascii=False).encode("utf-8"), FUENTE, nombre, fin)


def lambda_handler(event: dict | None = None, context=None) -> dict:  # noqa: ARG001
    """Programa `costagas-bcrp-diario`."""
    evento = event or {}
    desde = date.fromisoformat(evento["desde"]) if evento.get("desde") else None
    hasta = date.fromisoformat(evento["hasta"]) if evento.get("hasta") else None
    return {"fuente": FUENTE, "ruta": extraer(desde, hasta)}
