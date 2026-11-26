"""Funciones del portal web (W22, informe v16 seccion 2.4, M9 y M10).

Cuatro Lambdas con URL de funcion, una por accion del portal:

| modulo    | funcion AWS                | que hace                                  |
|-----------|----------------------------|-------------------------------------------|
| `firmar`  | costagas-portal-firmar     | URL prefirmada de 5 min hacia landing/interno/ |
| `estado`  | costagas-portal-estado     | conteos por capa desde _manifests y silver/_control |
| `kpis`    | costagas-portal-kpis       | lee las vistas de KPI por Athena          |
| `revision`| costagas-portal-revision   | INSERT en revision_alerta (solo inserciones) |

Las cuatro comparten este modulo: el CORS va limitado al dominio de CloudFront
y toda peticion pasa por `src/controles/jwt.py` antes de hacer nada, porque la
URL de funcion es publica (`AuthType: NONE`). Sin token valido se responde 401 y
no se toca el lago.

Nada de lo que devuelven lleva nombres, DNI ni RUC: el portal muestra conteos,
KPI y estados de revision, y el revisor viaja seudonimizado como el usuario del
token.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from src.controles.jwt import TokenInvalido, usuario, verificar

ORIGEN = os.environ.get("PORTAL_ORIGEN", "")
METODOS = "OPTIONS,POST"
CABECERAS_PERMITIDAS = "Authorization,Content-Type"
MAX_EDAD_CORS_S = 600


def cors(origen: str | None = None) -> dict:
    """CORS solo para el dominio de CloudFront. Sin dominio configurado, nada de CORS."""
    permitido = origen if origen is not None else ORIGEN
    if not permitido:
        return {}
    return {"Access-Control-Allow-Origin": permitido,
            "Access-Control-Allow-Methods": METODOS,
            "Access-Control-Allow-Headers": CABECERAS_PERMITIDAS,
            "Access-Control-Max-Age": str(MAX_EDAD_CORS_S)}


def respuesta(estado: int, cuerpo: dict, origen: str | None = None) -> dict:
    return {"statusCode": estado,
            "headers": {"Content-Type": "application/json", **cors(origen)},
            "body": json.dumps(cuerpo, ensure_ascii=False, default=str)}


def token_del_evento(event: dict) -> str:
    """El token va en Authorization: Bearer <token>, nunca en el cuerpo ni en la URL."""
    cabeceras = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    bruto = cabeceras.get("authorization", "")
    if not bruto.lower().startswith("bearer "):
        raise TokenInvalido("falta la cabecera Authorization: Bearer")
    return bruto.split(" ", 1)[1].strip()


def cuerpo_del_evento(event: dict) -> dict:
    """El cuerpo JSON de la peticion; vacio si no trae ninguno."""
    crudo = event.get("body")
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError as e:
        raise ValueError("el cuerpo no es JSON valido") from e
    if not isinstance(datos, dict):
        raise ValueError("el cuerpo debe ser un objeto JSON")
    return datos


def manejar(event: dict, accion: Callable[[dict, dict], dict]) -> dict:
    """Preflight, token y errores en un solo lugar; `accion(cuerpo, claims)`.

    Un error de dominio sale como 400 con su motivo, y uno inesperado como 500
    sin detalle: el mensaje interno queda en el log de la funcion, no en la
    respuesta del portal.
    """
    metodo = ((event.get("requestContext") or {}).get("http") or {}).get("method", "POST")
    if metodo == "OPTIONS":
        return respuesta(204, {})
    try:
        claims = verificar(token_del_evento(event))
    except TokenInvalido as e:
        return respuesta(401, {"error": str(e)})
    try:
        return respuesta(200, accion(cuerpo_del_evento(event), claims))
    except (ValueError, KeyError) as e:
        return respuesta(400, {"error": str(e)})
    except Exception as e:                      # noqa: BLE001
        print(f"[portal] error inesperado: {type(e).__name__}: {e}")
        return respuesta(500, {"error": "error interno"})


__all__ = ["cors", "cuerpo_del_evento", "manejar", "respuesta", "token_del_evento", "usuario"]
