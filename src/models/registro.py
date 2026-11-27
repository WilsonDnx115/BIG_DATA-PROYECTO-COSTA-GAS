"""Registro de modelos del clasificador S12 en S3 (W13, informe 4.3, Tabla 4.8b).

Cada entrenamiento deja su corrida completa en

    gold/_modelos/s12/corrida=<AAAA-MM-DD>/   (modelo y metricas.json)

y `gold/_modelos/s12/vigente.json` apunta a la corrida que esta puntuando hoy,
con su umbral, su version y sus metricas. Asi la puntuacion no depende de la
ultima carpeta escrita, sino de una promocion explicita.

Un retador solo reemplaza al vigente si **sube la precision** y ademas alcanza
`RECALL_MIN_RETADOR`: un modelo muy preciso que deja pasar casi todo no sirve
para una bandeja de revision.
"""
from __future__ import annotations

import json
import pickle
from datetime import date
from pathlib import Path

from src.common import config, lake_io, rutas

MODELO = "s12"
VIGENTE = "vigente.json"


def ruta_base(modelo: str = MODELO) -> str:
    return rutas.ruta("gold", "_modelos", modelo)


def ruta_corrida(fecha: str, modelo: str = MODELO) -> str:
    return f"{ruta_base(modelo)}/corrida={fecha}"


def ruta_vigente(modelo: str = MODELO) -> str:
    return f"{ruta_base(modelo)}/{VIGENTE}"


def _leer_json(ruta: str) -> dict | None:
    if ruta.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = ruta[5:].split("/", 1)
        cliente = boto3.client("s3")
        try:
            cuerpo = cliente.get_object(Bucket=bucket, Key=key)["Body"].read()
        except cliente.exceptions.NoSuchKey:
            return None
        return json.loads(cuerpo.decode("utf-8"))
    archivo = Path(ruta)
    return json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else None


def _guardar_modelo(modelo, destino: str) -> str:
    """Spark MLlib guarda con `save()`; scikit-learn se serializa con pickle."""
    if hasattr(modelo, "save"):
        modelo.save(destino)
        return destino
    ruta = f"{destino}.pkl"
    datos = pickle.dumps(modelo)
    if ruta.startswith("s3://"):
        import boto3  # noqa: PLC0415

        bucket, key = ruta[5:].split("/", 1)
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=datos,
                                      ServerSideEncryption="AES256")
    else:
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        Path(ruta).write_bytes(datos)
    return ruta


def guardar(modelo, metricas: dict, base: str | None = None, fecha: str | None = None,
            umbral: float | None = None, modelo_nombre: str = MODELO) -> dict:
    """Guarda una corrida y devuelve su ficha, sin promoverla todavia."""
    fecha = fecha or date.today().isoformat()
    base = base or ruta_base(modelo_nombre)
    destino = f"{base}/corrida={fecha}"
    ruta_modelo = _guardar_modelo(modelo, f"{destino}/modelo")
    ficha = {
        "ruta": ruta_modelo,
        "corrida": fecha,
        "version": f"{modelo_nombre}-{fecha}",
        "umbral": umbral if umbral is not None else metricas.get("umbral"),
        "metricas": metricas,
    }
    lake_io.escribir_json(ficha, f"{destino}/metricas.json")
    return ficha


def vigente(base: str | None = None, modelo_nombre: str = MODELO) -> dict | None:
    """Ficha del modelo que esta puntuando, o None si todavia no hay ninguno."""
    base = base or ruta_base(modelo_nombre)
    return _leer_json(f"{base}/{VIGENTE}")


def promover_si_mejora(retador: dict, actual: dict | None = None, base: str | None = None,
                       modelo_nombre: str = MODELO) -> bool:
    """Deja al retador como vigente solo si sube la precision y su recall alcanza el minimo.

    Devuelve True si hubo promocion. Sin vigente previo, el retador entra igual:
    tiene que cumplir el recall minimo.
    """
    base = base or ruta_base(modelo_nombre)
    if actual is None:
        actual = vigente(base, modelo_nombre)

    recall = retador["metricas"].get("recall")
    if recall is None or recall < config.RECALL_MIN_RETADOR:
        return False
    if actual is not None:
        precision_actual = actual["metricas"].get("precision")
        if precision_actual is not None and retador["metricas"].get("precision", 0) <= precision_actual:
            return False

    lake_io.escribir_json(retador, f"{base}/{VIGENTE}")
    return True
