"""Prueba de disponibilidad (paso 2.2.1).

Borra una partición de Silver y la regenera desde Bronze (inmutable), como la
replicación de HDFS garantiza recuperar un bloque perdido (S2). Acepta si la
partición regenerada tiene el mismo número de filas y la misma suma de kg.

Uso:  python -m src.common.reproceso --fuente aba_02 --anio 2020 --mes 7
"""
from __future__ import annotations

import argparse
import glob
import json

from src.bronze_to_silver import handler
from src.common import lake_io, rutas, schemas


def huella(fuente: str, anio: int, mes: int) -> dict:
    df = lake_io.leer_parquet(handler.destino_silver(fuente), filtros=[("anio", "=", anio), ("mes", "=", mes)])
    return {"filas": len(df), "kg": round(float(df["kg"].sum()), 3)}


def regenerar(fuente: str, anio: int, mes: int) -> dict:
    antes = huella(fuente, anio, mes)
    lake_io.borrar(f"{handler.destino_silver(fuente)}/anio={anio}/mes={mes}")
    borrada = huella(fuente, anio, mes)
    f = schemas.FUENTES[fuente]
    patron = rutas.ruta("bronze", "interno", "estructurado", f.proceso, fuente, "fecha_carga=*", "*")
    for archivo in sorted(glob.glob(patron)):
        handler.procesar_archivo(archivo, fuente)
    despues = huella(fuente, anio, mes)
    return {"antes": antes, "tras_borrar": borrada, "despues": despues, "identica": antes == despues}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuente", default="aba_02")
    ap.add_argument("--anio", type=int, default=2020)
    ap.add_argument("--mes", type=int, default=7)
    a = ap.parse_args()
    print(json.dumps(regenerar(a.fuente, a.anio, a.mes), indent=2))
