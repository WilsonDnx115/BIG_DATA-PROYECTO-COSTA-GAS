"""Recoge las medidas reales de la Tabla 3.11 desde AWS (W24).

No mide nada por si mismo: **lee** lo que ya quedo registrado en la corrida.

* De Lambda toma la linea `REPORT` que CloudWatch escribe al final de cada
  invocacion, con la duracion facturada y la memoria maxima usada. Es la unica
  fuente de la memoria pico: no se estima.
* De Glue toma el historial del job (`get_job_runs`), con la duracion, el tipo y
  el numero de trabajadores y la clase de ejecucion.

Si una corrida no existe todavia, la fila sale como `None` con su motivo, nunca
con un numero inventado. Asi la evidencia distingue lo medido de lo pendiente.

Uso (despues de la corrida real, con el perfil costagas):
    python -m src.scaletest.aws --lambda costagas-bronze-to-silver --job costagas-gold-conciliacion
"""
from __future__ import annotations

import argparse
import json
import re

GRUPO_LOG = "/aws/lambda/{funcion}"
PATRON_REPORT = re.compile(
    r"Duration: (?P<duracion_ms>[\d.]+) ms.*?"
    r"Billed Duration: (?P<facturado_ms>\d+) ms.*?"
    r"Memory Size: (?P<memoria_mb>\d+) MB.*?"
    r"Max Memory Used: (?P<memoria_usada_mb>\d+) MB", re.S)
PATRON_TIMEOUT = re.compile(r"Task timed out after ([\d.]+) seconds")


def reportes_lambda(funcion: str, maximo: int = 5, cliente=None) -> list[dict]:
    """Las ultimas lineas REPORT de la funcion, ya parseadas."""
    import boto3  # noqa: PLC0415

    logs = cliente or boto3.client("logs")
    eventos = logs.filter_log_events(
        logGroupName=GRUPO_LOG.format(funcion=funcion),
        filterPattern="REPORT", limit=maximo)["events"]
    salida = []
    for e in eventos:
        m = PATRON_REPORT.search(e.get("message", ""))
        if not m:
            continue
        fila = {k: float(v) for k, v in m.groupdict().items()}
        fila["funcion"] = funcion
        fila["agotado"] = bool(PATRON_TIMEOUT.search(e.get("message", "")))
        salida.append(fila)
    return salida


def corridas_glue(job: str, maximo: int = 5, cliente=None) -> list[dict]:
    """Duracion, trabajadores y clase de las ultimas corridas del job."""
    import boto3  # noqa: PLC0415

    glue = cliente or boto3.client("glue")
    corridas = glue.get_job_runs(JobName=job, MaxResults=maximo).get("JobRuns", [])
    return [{"job": job, "id": c.get("Id"), "estado": c.get("JobRunState"),
             "segundos": c.get("ExecutionTime"),
             "trabajadores": c.get("NumberOfWorkers"),
             "tipo_trabajador": c.get("WorkerType"),
             "clase": c.get("ExecutionClass"),
             "iniciada": c.get("StartedOn")} for c in corridas]


def fila_pendiente(que: str, motivo: str) -> dict:
    """Una fila de la Tabla 3.11 que todavia no se corrio."""
    return {"medida": que, "valor": None, "estado": "pendiente", "motivo": motivo}


def recoger(funcion: str | None = None, job: str | None = None,
            logs=None, glue=None) -> dict:
    """Lo que haya: lo que falte queda declarado como pendiente, no en cero."""
    salida: dict = {"lambda": [], "glue": []}
    if funcion:
        try:
            salida["lambda"] = reportes_lambda(funcion, cliente=logs)
        except Exception as e:                  # noqa: BLE001
            salida["lambda"] = [fila_pendiente(f"lambda {funcion}",
                                               f"{type(e).__name__}: {e}")]
    if job:
        try:
            salida["glue"] = corridas_glue(job, cliente=glue)
        except Exception as e:                  # noqa: BLE001
            salida["glue"] = [fila_pendiente(f"glue {job}", f"{type(e).__name__}: {e}")]
    return salida


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--lambda", dest="funcion", default=None)
    p.add_argument("--job", default=None)
    args = p.parse_args(argv)
    datos = recoger(args.funcion, args.job)
    print(json.dumps(datos, ensure_ascii=False, indent=2, default=str))
    return datos


if __name__ == "__main__":
    main()
