"""Formulario de revision ciega: INSERT en `revision_alerta` (W22, M10).

`revision_alerta` es una tabla **de solo inserciones**: cada revision deja una
fila nueva y la vista `v_alerta` muestra la ultima de cada alerta. Esta funcion
es la unica que escribe ahi, y solo puede insertar: no construye `UPDATE`, ni
`DELETE`, ni `MERGE`. Por eso la historia de una revision no se puede corregir
borrandola, solo agregando la siguiente, y el job de Gold y el portal nunca
escriben la misma tabla (informe v16, seccion 4.3).

Tres cosas que la funcion no deja pasar:

* una **causa** fuera de las seis del informe;
* un **nivel de evidencia** fuera de 1 a 3 (Tabla 4.8f). El nivel 3, que es el
  unico donde puede figurar «sustraccion», lo pone el control interno con la
  verificacion en campo, no el modelo;
* un **revisor** puesto en el cuerpo de la peticion: el revisor sale del token
  de Cognito, asi que la revision es atribuible y el formulario no puede firmar
  por otra persona.

La fila no lleva el puntaje del modelo: la revision es ciega y el panel no
muestra la probabilidad.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone

from src.common import config
from src.portal import manejar, usuario

BASE = os.environ.get("BASE_GOLD", "costagas_gold")
TABLA = "revision_alerta"
# Las seis causas del informe v16 (seccion 4.3): no hay una septima opcion.
CAUSAS = ("digitacion", "pago_tardio", "entrega_parcial", "nota_credito",
          "sustraccion_confirmada", "sin_explicar")
ESTADOS = ("confirmada", "descartada")
EVIDENCIAS = (1, 2, 3)
EVIDENCIA_SUSTRACCION = 3
ID_ALERTA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
NOTA_MAXIMA = 500


class CausaNoValida(ValueError):
    """Causa fuera de las seis del informe."""


class EvidenciaNoValida(ValueError):
    """Nivel de evidencia fuera de 1 a 3, o incoherente con la causa."""


def revisor_hash(nombre: str, sal: str | None = None) -> str:
    """El revisor se guarda seudonimizado, igual que las personas de Silver."""
    semilla = sal if sal is not None else os.environ.get("SEUDONIMO_SAL", "")
    if not semilla:
        raise ValueError("falta SEUDONIMO_SAL: el revisor no se guarda en claro")
    return hashlib.sha256(f"{semilla}|{nombre}".encode()).hexdigest()[:32]


def _texto(valor, nombre: str, maximo: int) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"falta {nombre}")
    limpio = valor.strip()
    if len(limpio) > maximo or "'" in limpio or "--" in limpio:
        raise ValueError(f"{nombre} no admitido")
    return limpio


def validar(cuerpo: dict, revisor: str) -> dict:
    """Devuelve la fila a insertar, ya validada. Levanta si algo no cuadra."""
    id_alerta = _texto(cuerpo.get("id_alerta"), "id_alerta", 64)
    if not ID_ALERTA.match(id_alerta):
        raise ValueError(f"id_alerta no admitido: {id_alerta}")

    causa = cuerpo.get("causa")
    if causa not in CAUSAS:
        raise CausaNoValida(f"causa no valida: {causa}. Use una de {', '.join(CAUSAS)}")

    estado = cuerpo.get("estado")
    if estado not in ESTADOS:
        raise ValueError(f"estado no valido: {estado}. Use uno de {', '.join(ESTADOS)}")

    try:
        evidencia = int(cuerpo.get("nivel_evidencia"))
    except (TypeError, ValueError) as e:
        raise EvidenciaNoValida("nivel_evidencia debe ser 1, 2 o 3") from e
    if evidencia not in EVIDENCIAS:
        raise EvidenciaNoValida(f"nivel_evidencia fuera de rango: {evidencia}")
    if causa == "sustraccion_confirmada" and evidencia != EVIDENCIA_SUSTRACCION:
        raise EvidenciaNoValida(
            "«sustraccion_confirmada» solo existe en el nivel 3, verificado en campo")

    nota = cuerpo.get("nota")
    return {"id_alerta": id_alerta, "estado": estado, "causa": causa,
            "nivel_evidencia": evidencia,
            "nota": _texto(nota, "nota", NOTA_MAXIMA) if nota else None,
            "revisor_hash": revisor_hash(revisor),
            "revisado_en": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def sentencia(fila: dict, base: str = BASE, tabla: str = TABLA) -> str:
    """El unico SQL que esta funcion sabe escribir: un INSERT de una fila."""
    nota = "NULL" if fila["nota"] is None else f"'{fila['nota']}'"
    return (f"INSERT INTO {base}.{tabla} "
            "(id_alerta, estado, causa, nivel_evidencia, nota, revisor_hash, revisado_en) "
            f"VALUES ('{fila['id_alerta']}', '{fila['estado']}', '{fila['causa']}', "
            f"{fila['nivel_evidencia']}, {nota}, '{fila['revisor_hash']}', "
            f"from_iso8601_timestamp('{fila['revisado_en']}'))")


def insertar(fila: dict, cliente=None) -> str:
    """Lanza el INSERT en Athena y devuelve el id de la ejecucion."""
    import boto3  # noqa: PLC0415

    athena = cliente or boto3.client("athena")
    return athena.start_query_execution(
        QueryString=sentencia(fila),
        WorkGroup=os.environ.get("ATHENA_WORKGROUP", config.ATHENA_WORKGROUP),
        QueryExecutionContext={"Database": BASE})["QueryExecutionId"]


def accion(cuerpo: dict, claims: dict) -> dict:
    fila = validar(cuerpo, usuario(claims))
    return {"registrado": True, "id_alerta": fila["id_alerta"],
            "estado": fila["estado"], "causa": fila["causa"],
            "nivel_evidencia": fila["nivel_evidencia"],
            "consulta": insertar(fila)}


def lambda_handler(event: dict, context=None) -> dict:  # noqa: ARG001
    return manejar(event, accion)
