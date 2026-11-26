"""Los cinco KPI del tablero, leidos por Athena (W22, Tabla 4.10).

El portal pide un KPI por nombre y la funcion consulta su vista en
`costagas_gold`. **El cliente no manda SQL**: manda el nombre de una vista de
una lista cerrada y aqui se arma la consulta. Una vista que no este en la lista
se rechaza con 400, asi que el portal no puede leer otra tabla ni colar una
subconsulta.

Las vistas `v_kpi_1` a `v_kpi_5` son las de F06; hasta que esten desplegadas, la
funcion responde `sin_vista` para la que falte en lugar de inventar un valor. Un
KPI sin su vista no es un KPI en cero.

| KPI | Que mide (Tabla 4.10)                        | Tabla de Gold        |
|-----|----------------------------------------------|----------------------|
| 1   | diferencia no explicada de planta (%)        | fact_balance_planta  |
| 2   | valor de la diferencia (S/)                  | fact_balance_planta  |
| 3   | compras con segundo registro coincidente (%) | modelo_factura       |
| 4   | combustible por tonelada (S/ por t)          | fact_unidad_mes      |
| 5   | confirmacion documental de alertas (%)       | fact_alerta          |
"""
from __future__ import annotations

import os
import time

from src.common import config
from src.portal import manejar

BASE = os.environ.get("BASE_GOLD", "costagas_gold")
VISTAS = {f"kpi_{n}": f"v_kpi_{n}" for n in range(1, 6)}
VISTAS.update({"cubo_unidad": "v_cubo_unidad", "semaforo": "v_semaforo_unidades",
               "alertas": "v_alerta"})
FILAS_MAXIMAS = 500
ESPERA_MAXIMA_S = 20
PASO_ESPERA_S = 0.5
ESTADOS_FINALES = ("SUCCEEDED", "FAILED", "CANCELLED")


class VistaDesconocida(ValueError):
    """Nombre fuera de `VISTAS`: nunca se concatena en la consulta."""


def consulta(nombre: str, limite: int = FILAS_MAXIMAS) -> str:
    """SQL de solo lectura sobre una vista de la lista cerrada."""
    if nombre not in VISTAS:
        raise VistaDesconocida(
            f"indicador desconocido: {nombre}. Use uno de {', '.join(sorted(VISTAS))}")
    tope = min(int(limite), FILAS_MAXIMAS)
    return f"SELECT * FROM {BASE}.{VISTAS[nombre]} LIMIT {tope}"


def _filas(resultado: dict) -> list[dict]:
    """Pasa la respuesta de Athena a filas; la primera trae los encabezados."""
    crudas = resultado.get("ResultSet", {}).get("Rows", [])
    if not crudas:
        return []
    columnas = [c.get("VarCharValue") for c in crudas[0].get("Data", [])]
    return [{c: d.get("VarCharValue") for c, d in zip(columnas, f.get("Data", []), strict=False)}
            for f in crudas[1:]]


def leer(nombre: str, limite: int = FILAS_MAXIMAS, cliente=None,
         espera_maxima: float = ESPERA_MAXIMA_S, dormir=time.sleep) -> dict:
    """Corre la consulta en el workgroup del proyecto y devuelve sus filas."""
    import boto3  # noqa: PLC0415

    sql = consulta(nombre, limite)
    athena = cliente or boto3.client("athena")
    id_consulta = athena.start_query_execution(
        QueryString=sql,
        WorkGroup=os.environ.get("ATHENA_WORKGROUP", config.ATHENA_WORKGROUP),
        QueryExecutionContext={"Database": BASE})["QueryExecutionId"]

    limite_tiempo = time.monotonic() + espera_maxima
    estado = "QUEUED"
    motivo = None
    while time.monotonic() < limite_tiempo:
        ejecucion = athena.get_query_execution(QueryExecutionId=id_consulta)["QueryExecution"]
        estado = ejecucion["Status"]["State"]
        motivo = ejecucion["Status"].get("StateChangeReason")
        if estado in ESTADOS_FINALES:
            break
        dormir(PASO_ESPERA_S)

    if estado != "SUCCEEDED":
        # Mientras la vista no exista, se dice que falta; no se devuelve un cero.
        falta = motivo and "does not exist" in motivo.lower()
        return {"indicador": nombre, "vista": VISTAS[nombre],
                "estado": "sin_vista" if falta else estado.lower(),
                "motivo": motivo, "filas": []}
    filas = _filas(athena.get_query_results(QueryExecutionId=id_consulta,
                                            MaxResults=min(limite + 1, 1000)))
    return {"indicador": nombre, "vista": VISTAS[nombre], "estado": "ok",
            "n_filas": len(filas), "filas": filas}


def accion(cuerpo: dict, claims: dict) -> dict:  # noqa: ARG001
    return leer(cuerpo.get("indicador", "kpi_1"), cuerpo.get("limite", FILAS_MAXIMAS))


def lambda_handler(event: dict, context=None) -> dict:  # noqa: ARG001
    return manejar(event, accion)
