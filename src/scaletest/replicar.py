"""Prueba de escalabilidad (pasos 3.7.1 a 3.7.3).

Replica `silver/movimientos/` N veces en `scaletest/xN/`, desplazando placas y
documentos en cada copia para que las uniones sigan siendo válidas, y mide la
conciliación con el motor pandas (una máquina = escalado vertical, como Lambda)
y, si hay pyspark, con Spark (Driver + Executors = escalado horizontal).

Los datos replicados NO entran al análisis y se borran al terminar (3.7.4).

Uso:  python -m src.scaletest.replicar --factores 1 10 --motores pandas
"""
from __future__ import annotations

import argparse
import json
import os
import time
import tracemalloc

import pandas as pd

from src.common import config, lake_io, rutas, schemas


def replicar(factor: int) -> str:
    base = lake_io.leer_parquet(rutas.ruta("silver", "movimientos"))
    copias = []
    for i in range(factor):
        c = base.copy()
        if i:
            c["placa_norm"] = c["placa_norm"].str[:5] + f"{i:03d}"[-1] + "_" + str(i)  # nueva identidad
            c["documento"] = c["documento"] + f"_r{i}"
        copias.append(c)
    df = pd.concat(copias, ignore_index=True)
    destino = rutas.ruta("scaletest", f"x{factor}", "movimientos")
    lake_io.escribir_parquet(df, destino, contrato="movimientos")
    return destino


def medir_pandas(origen: str) -> dict:
    tracemalloc.start()
    t0 = time.perf_counter()
    movs = lake_io.leer_parquet(origen)
    conc = (movs.groupby(["placa_norm", "fecha", "id_producto"], as_index=False)
            .agg(kg_comprados=("kg_comprados", "sum"), kg_vendidos=("kg_vendidos", "sum")))
    seg = time.perf_counter() - t0
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"motor": "pandas (vertical)", "filas_entrada": len(movs), "filas_salida": len(conc),
            "segundos": round(seg, 2), "memoria_pico_mb": round(pico / 1e6, 1)}


def medir_spark(origen: str, executors: str = "local[*]") -> dict:
    from pyspark.sql import functions as F  # noqa: PLC0415

    from src.common.spark import obtener_spark  # noqa: PLC0415

    spark = obtener_spark("scaletest")
    t0 = time.perf_counter()
    ruta = origen if origen.startswith("s3://") else "file:///" + origen.lstrip("/")
    movs = spark.read.schema(schemas.CONTRATOS["movimientos"].spark()).parquet(ruta)
    conc = (movs.groupBy("placa_norm", "fecha", "id_producto")
            .agg(F.sum("kg_comprados").alias("kg_comprados"), F.sum("kg_vendidos").alias("kg_vendidos")))
    n = conc.count()
    return {"motor": f"spark {executors} (horizontal)", "filas_salida": n,
            "particiones_entrada": movs.rdd.getNumPartitions(),
            "segundos": round(time.perf_counter() - t0, 2)}


def ejecutar(factores, motores) -> list[dict]:
    res = []
    for f in factores:
        origen = replicar(f)
        for m in motores:
            r = medir_pandas(origen) if m == "pandas" else medir_spark(origen)
            res.append({"factor": f, **r})
            print(json.dumps(res[-1]))
    return res


def a_markdown(res: list[dict]) -> str:
    cab = ["factor", "motor", "filas_salida", "segundos", "memoria_pico_mb", "particiones_entrada"]
    lin = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    lin += ["| " + " | ".join(str(r.get(c, "")) for c in cab) + " |" for r in res]
    return "\n".join(lin)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--factores", type=int, nargs="+", default=[1, 10])
    ap.add_argument("--motores", nargs="+", default=["pandas"])
    ap.add_argument("--conservar", action="store_true", help="no borrar scaletest/ al terminar")
    a = ap.parse_args()
    res = ejecutar(a.factores, a.motores)
    destino = config.RAIZ_REPO / "docs" / "evidencias" / "escalabilidad.md"
    destino.write_text("# Prueba de escalabilidad (3.7)\n\n" + a_markdown(res) + "\n\n"
                       f"Máquina local: {os.cpu_count()} núcleos. Reemplazar con las corridas en Lambda/Glue.\n",
                       encoding="utf-8")
    if not a.conservar:
        lake_io.borrar(rutas.ruta("scaletest"))
