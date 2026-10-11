"""Bronze → Silver guiado por contratos (WP 0.2). Corre igual en AWS Lambda y en local.

Para cada archivo que llega a Bronze:
  1. Busca en `contracts/` las fuentes cuyo patrón coincide con el nombre del archivo.
  2. Lee solo las hojas y columnas declaradas (esquema declarado, S5) con corte de
     filas vacías (hallazgo C6).
  3. Aplica la limpieza de la tabla y valida el resultado contra el contrato.
  4. Escribe UN Parquet por fuente: `silver/<dominio>/<tabla>/<fuente>.parquet`.
     Reprocesar el mismo archivo reemplaza ese Parquet y no toca los demás, así que
     la corrida es idempotente (hallazgo C4, S3: tareas re-ejecutables). Las tablas
     Silver son pequeñas y no se particionan (hallazgo C2).
  5. Deja las métricas de la corrida en `silver/_control/<tabla>/<fuente>.json`.

Los datos personales (conductor, vendedor, cliente) se seudonimizan aquí y el
valor original no llega a Silver (Ley 29733).
"""
from __future__ import annotations

import json
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.common import limpieza as L
from src.common import rutas
from src.silver import contratos, lector
from src.silver.transformar import TRANSFORMACIONES

_COLUMNAS_DE_TOTAL = ("proveedor", "tipo", "numero", "proyecto", "articulo", "mes_texto", "placa")


# --- Entrada y salida (local o S3) -------------------------------------------
def _a_local(ruta: str) -> tuple[str, bool]:
    if not ruta.startswith("s3://"):
        return ruta, False
    import boto3  # noqa: PLC0415

    bucket, key = ruta[5:].split("/", 1)
    destino = Path(tempfile.gettempdir()) / Path(key).name
    boto3.client("s3").download_file(bucket, key, str(destino))
    return str(destino), True


def _subir(local: Path, destino: str) -> None:
    if destino.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = destino[5:].split("/", 1)
        boto3.client("s3").upload_file(str(local), bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    else:
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        Path(destino).write_bytes(local.read_bytes())


def _escribir_parquet(tabla: pa.Table, destino: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "datos.parquet"
        pq.write_table(tabla, f, compression="snappy")
        _subir(f, destino)


def _escribir_json(obj: dict, destino: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "control.json"
        f.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        _subir(f, destino)


def ruta_tabla(c: contratos.Contrato) -> str:
    return rutas.ruta("silver", c.dominio, c.tabla)


# --- Procesamiento -----------------------------------------------------------
def _leer_fuente(local: str, hojas: list[str], f: contratos.Fuente) -> tuple[pd.DataFrame, list[dict]]:
    partes, detalle = [], []
    for hoja in hojas:
        m = f.hojas.search(hoja)
        if not m:
            continue
        grupos = m.groupdict()
        try:
            lec = lector.leer_hoja(local, hoja, f)
        except lector.HojaRechazada as e:
            detalle.append({"hoja": hoja, "estado": "rechazada", "motivo": str(e)})
            continue
        d = lec.datos
        d["hoja"] = hoja
        d["_anio"] = int(grupos["anio"]) if grupos.get("anio") else f.anio
        d["_mes"] = L.mes_a_numero(grupos.get("mes"))
        d["_empresa"] = (grupos.get("empresa") or "").upper() or None
        partes.append(d)
        detalle.append({"hoja": hoja, "estado": "leida", "filas_leidas": lec.leidas,
                        "filas_efectivas": lec.efectivas, "cortada_por_filas_vacias": lec.cortada})
    datos = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    return datos, detalle


def _filtrar(df: pd.DataFrame, f: contratos.Fuente) -> tuple[pd.DataFrame, dict]:
    """Quita filas de total y filas sin los campos exigidos por el contrato."""
    presentes = [c for c in _COLUMNAS_DE_TOTAL if c in df.columns]
    es_total = df[presentes].apply(lambda fila: L.es_fila_total(*fila), axis=1) if presentes else pd.Series(False, index=df.index)
    df = df[~es_total]
    incompleta = pd.Series(False, index=df.index)
    for c in f.exigir:
        incompleta |= df[c].map(lambda v: lector.a_texto(v) is None)
    return df[~incompleta].reset_index(drop=True), {"filas_de_total": int(es_total.sum()),
                                                    "sin_campos_exigidos": int(incompleta.sum())}


def procesar_fuente(local: str, hojas: list[str], c: contratos.Contrato, f: contratos.Fuente,
                    escribir: bool = True) -> dict:
    crudo, detalle = _leer_fuente(local, hojas, f)
    control = {"tabla": c.tabla, "fuente": f.id, "familia": f.familia, "hojas": detalle,
               "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if crudo.empty:
        return {**control, "estado": "sin_filas", "filas_salida": 0}
    filtrado, descartes = _filtrar(crudo, f)
    salida, calidad = TRANSFORMACIONES[c.tabla](filtrado)
    salida = salida.assign(origen=f.id, hoja=filtrado.loc[salida.index, "hoja"],
                           fila=filtrado.loc[salida.index, "fila"].astype("Int64"))
    duplicada = salida.duplicated(subset=list(c.llave), keep="first")
    salida = salida[~duplicada]
    faltan = [n for n in c.nombres() if n not in salida.columns]
    if faltan:
        raise ValueError(f"{c.tabla}: la transformación no produjo las columnas {faltan}")
    tabla = pa.Table.from_pandas(salida[c.nombres()], schema=c.esquema(), preserve_index=False, safe=False)
    control.update(estado="ok", filas_leidas=sum(h.get("filas_leidas", 0) for h in detalle),
                   filas_efectivas=len(crudo), filas_salida=tabla.num_rows, duplicadas_por_llave=int(duplicada.sum()),
                   descartes=descartes, calidad=calidad)
    if escribir:
        _escribir_parquet(tabla, f"{ruta_tabla(c)}/{f.id}.parquet")
        _escribir_json(control, rutas.ruta("silver", "_control", c.tabla, f"{f.id}.json"))
    return control


def procesar_archivo(ruta: str, nombre: str | None = None, escribir: bool = True) -> list[dict]:
    """Procesa un archivo de Bronze. Devuelve un control por cada fuente que lo usa."""
    nombre = nombre or Path(ruta.replace("\\", "/")).name
    pares = contratos.fuentes_para(nombre)
    if not pares:
        return [{"archivo": nombre, "estado": "sin_contrato"}]
    local, temporal = _a_local(ruta)
    try:
        hojas = lector.nombres_hojas(local)
        return [{"archivo": nombre, **procesar_fuente(local, hojas, c, f, escribir)} for c, f in pares]
    finally:
        if temporal:
            Path(local).unlink(missing_ok=True)


def leer_tabla(tabla: str) -> pd.DataFrame:
    """Une los Parquet de todas las fuentes de una tabla Silver (solo en local; en AWS se usa Athena)."""
    c = contratos.cargar()[tabla]
    archivos = sorted(Path(ruta_tabla(c)).glob("*.parquet"))
    if not archivos:
        return c.esquema().empty_table().to_pandas()
    return pa.concat_tables([pq.read_table(a) for a in archivos]).to_pandas()


def lambda_handler(event, context):  # pragma: no cover - se prueba en AWS
    resultados = []
    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        if key.endswith("/"):
            continue
        resultados += procesar_archivo(f"s3://{bucket}/{key}")
    resumen = [{k: r.get(k) for k in ("archivo", "tabla", "fuente", "estado", "filas_salida")} for r in resultados]
    print(json.dumps(resumen, ensure_ascii=False))       # solo conteos: ningún dato llega a los logs
    return {"procesados": len(resultados), "resultados": resumen}
