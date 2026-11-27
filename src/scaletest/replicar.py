"""Prueba de escalabilidad de la Tabla 3.11 (W24, informe v16 seccion 3.7).

Replica la muestra 1x, 10x y 100x en `sim/escala/xN/` y mide la misma
agregacion con los dos escalados:

* **vertical** (pandas, una sola maquina): es lo que hace Lambda. Se registra la
  duracion y la memoria pico, que es donde se ve el punto de quiebre.
* **horizontal** (Spark, Driver + Executors): es lo que hace Glue. Se registra
  la duracion, las particiones de entrada y los executors.

Las replicas son **datos sinteticos para medir**: desplazan las placas y los
documentos en cada copia para que las uniones sigan siendo validas, no entran a
Silver ni a Gold, no se publican como cifras del negocio y se borran al
terminar. Lo que se mide es el motor, no la operacion.

Las filas de la Tabla 3.11 que corresponden a AWS (Lambda de 3 y 10 GB, Glue con
2 y 5 trabajadores) no se pueden llenar desde aqui: salen de la linea REPORT de
CloudWatch y del historial del job, y las recoge `src/scaletest/aws.py` despues
de la corrida real. Este modulo mide el motor local y deja la tabla lista.

Uso:
    python -m src.scaletest.replicar --factores 1 10 --motores pandas
    python -m src.scaletest.replicar --factores 1 10 100 --motores pandas spark
"""
from __future__ import annotations

import argparse
import json
import os
import time
import tracemalloc
from pathlib import Path

import pandas as pd

from src.common import config, lake_io, rutas

MUESTRA = config.RAIZ_REPO / "data" / "sample" / "entrega"
CAPA = "sim"
PREFIJO = "escala"
FACTORES = (1, 10, 100)
MOTORES = ("pandas", "spark")
# Columnas de identidad: se desplazan en cada copia para no inventar cruces.
IDENTIDADES = ("placa", "placa_norm", "documento", "ruc", "comprobante", "nro_scop")
LLAVE_AGRUPACION = ("anio", "mes")


def archivos_muestra(origen: Path | None = None) -> list[Path]:
    """Los CSV de la muestra sintetica, en orden estable."""
    origen = Path(origen) if origen is not None else MUESTRA
    if not origen.exists():
        raise FileNotFoundError(
            f"no hay muestra en {origen}: genere una con "
            "`python -m src.common.muestra --unidades 25 --semilla 42`")
    return sorted(p for p in origen.rglob("*.csv") if p.is_file())


def destino(factor: int, nombre: str = "") -> str:
    return rutas.ruta(CAPA, PREFIJO, f"x{factor}", nombre) if nombre else \
        rutas.ruta(CAPA, PREFIJO, f"x{factor}")


def _desplazar(df: pd.DataFrame, copia: int) -> pd.DataFrame:
    """Nueva identidad por copia: la copia 0 es la original, intacta."""
    if copia == 0:
        return df
    salida = df.copy()
    for columna in IDENTIDADES:
        if columna in salida.columns:
            salida[columna] = salida[columna].astype("string") + f"_r{copia}"
    return salida


def replicar_archivo(archivo: Path, factor: int) -> dict:
    """Escribe `factor` copias del archivo en `sim/escala/xN/` y devuelve su tamano."""
    base = pd.read_csv(archivo, dtype="string", keep_default_na=False)
    copias = pd.concat([_desplazar(base, i) for i in range(factor)], ignore_index=True)
    salida = Path(destino(factor, archivo.name))
    salida.parent.mkdir(parents=True, exist_ok=True)
    copias.to_csv(salida, index=False, encoding="utf-8")
    return {"archivo": archivo.name, "filas": len(copias),
            "bytes": salida.stat().st_size}


def replicar(factor: int, origen: Path | None = None) -> dict:
    """Replica la muestra completa. Devuelve el conteo de filas y los bytes."""
    partes = [replicar_archivo(a, factor) for a in archivos_muestra(origen)]
    return {"factor": factor, "archivos": len(partes),
            "filas": sum(p["filas"] for p in partes),
            "mb": round(sum(p["bytes"] for p in partes) / 1e6, 2),
            "ruta": destino(factor)}


def _csv_del_factor(factor: int) -> list[Path]:
    return sorted(Path(destino(factor)).rglob("*.csv"))


def medir_pandas(factor: int) -> dict:
    """Escalado vertical: todo en una maquina, como en Lambda."""
    tracemalloc.start()
    inicio = time.perf_counter()
    filas = 0
    grupos = 0
    for archivo in _csv_del_factor(factor):
        df = pd.read_csv(archivo, dtype="string", keep_default_na=False)
        filas += len(df)
        llaves = [c for c in LLAVE_AGRUPACION if c in df.columns] or list(df.columns[:1])
        grupos += len(df.groupby(llaves, dropna=False).size())
    segundos = time.perf_counter() - inicio
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"factor": factor, "motor": "pandas (vertical)", "filas": filas,
            "grupos": grupos, "segundos": round(segundos, 2),
            "memoria_pico_mb": round(pico / 1e6, 1),
            "nucleos": os.cpu_count()}


def medir_spark(factor: int, spark=None) -> dict:
    """Escalado horizontal: el mismo calculo en Spark, como en Glue."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    sesion = spark
    if sesion is None:
        from src.glue.gold_job import crear_sesion  # noqa: PLC0415

        sesion = crear_sesion(config.LAKE_URI, app="costagas-escala")
    inicio = time.perf_counter()
    ruta = rutas.ruta_spark(CAPA, PREFIJO, f"x{factor}")
    # Esquema declarado (todo texto, como el CSV crudo): nunca inferSchema.
    cabecera = _csv_del_factor(factor)[0].read_text(encoding="utf-8").splitlines()[0]
    esquema = ", ".join(f"`{c.strip()}` string" for c in cabecera.split(","))
    df = (sesion.read.option("header", "true").option("recursiveFileLookup", "true")
          .schema(esquema).csv(f"{ruta}/*.csv"))
    particiones = df.rdd.getNumPartitions()
    columna = df.columns[0]
    grupos = df.groupBy(columna).agg(F.count("*").alias("n")).count()
    return {"factor": factor, "motor": "spark (horizontal)", "grupos": grupos,
            "particiones_entrada": particiones,
            "executors": len(sesion.sparkContext._jsc.sc().statusTracker()
                             .getExecutorInfos()),
            "segundos": round(time.perf_counter() - inicio, 2)}


def ejecutar(factores=FACTORES, motores=("pandas",), origen: Path | None = None,
             spark=None) -> list[dict]:
    """Replica y mide cada combinacion. Imprime cada medida en cuanto sale."""
    medidas = []
    for factor in factores:
        replica = replicar(factor, origen)
        print(json.dumps(replica, ensure_ascii=False))
        for motor in motores:
            if motor not in MOTORES:
                raise ValueError(f"motor desconocido: {motor}. Use {MOTORES}")
            medida = medir_pandas(factor) if motor == "pandas" else medir_spark(factor, spark)
            medida["mb_entrada"] = replica["mb"]
            medidas.append(medida)
            print(json.dumps(medida, ensure_ascii=False))
    return medidas


COLUMNAS = ("factor", "motor", "mb_entrada", "filas", "grupos", "segundos",
            "memoria_pico_mb", "particiones_entrada", "executors")


def a_markdown(medidas: list[dict]) -> str:
    lineas = ["| " + " | ".join(COLUMNAS) + " |", "|" + "---|" * len(COLUMNAS)]
    lineas += ["| " + " | ".join(str(m.get(c, "")) for c in COLUMNAS) + " |"
               for m in medidas]
    return "\n".join(lineas)


def limpiar() -> None:
    """Las replicas se borran al terminar (informe 3.7): no quedan en el lago."""
    lake_io.borrar(rutas.ruta(CAPA, PREFIJO))


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--factores", type=int, nargs="+", default=[1, 10])
    p.add_argument("--motores", nargs="+", default=["pandas"], choices=list(MOTORES))
    p.add_argument("--conservar", action="store_true",
                   help="no borrar sim/escala/ al terminar (para medir en AWS)")
    p.add_argument("--salida", default=None,
                   help="archivo Markdown donde anotar las medidas locales")
    p.add_argument("--muestra", default=None,
                   help=f"carpeta de la muestra a replicar (por defecto {MUESTRA})")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> list[dict]:
    args = argumentos(argv)
    medidas = ejecutar(args.factores, args.motores, args.muestra)
    if args.salida:
        Path(args.salida).write_text(a_markdown(medidas) + "\n", encoding="utf-8")
        print(f"medidas en {args.salida}")
    if not args.conservar:
        limpiar()
    return medidas


if __name__ == "__main__":
    main()
