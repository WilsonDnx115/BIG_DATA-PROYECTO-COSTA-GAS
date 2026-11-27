"""Eventos de GDELT de 2020, carga historica (W20, informe seccion 3.5).

GDELT publica un archivo cada 15 minutos: unos 35 000 zip al ano, de pocos
kilobytes cada uno. Leidos tal cual generan un mapper por archivo y el arranque
de cada tarea supera al trabajo util (Tabla 3.10, «Bloques de ~128 MB»). Por eso
este extractor no guarda los zip: los descomprime y concatena en bloques gzip de
~128 MB, que es el tamano de bloque de referencia del proyecto
(`config.TAMANO_OBJETIVO_MB`).

El zip original se descarta en memoria y no se versiona: la regla del proyecto
es comprimir GDELT y borrarlo despues del filtrado. Lo que queda en el lago son
los bloques `.csv.gz`, que es lo que lee el job de externos (W21).
"""
from __future__ import annotations

import gzip
import io
import zipfile
from datetime import date

from src.common import config
from src.extractores import RespuestaInvalida, escribir, pedir

BASE = "http://data.gdeltproject.org/gdeltv2"
LISTA_MAESTRA = f"{BASE}/masterfilelist.txt"
FUENTE = "gdelt"
TIPO = "export"
BYTES_POR_BLOQUE = config.TAMANO_OBJETIVO_MB * 1024 * 1024


def urls_del_anio(anio: int, lista: str, tipo: str = TIPO) -> list[str]:
    """Las URL del ano pedido, sacadas de la lista maestra (una por linea)."""
    marca = f"/{anio}"
    urls = []
    for linea in lista.splitlines():
        partes = linea.split()
        if len(partes) == 3 and partes[2].endswith(f".{tipo}.CSV.zip"):
            nombre = partes[2].rsplit("/", 1)[-1]
            if nombre.startswith(str(anio)) or marca in partes[2]:
                urls.append(partes[2])
    if not urls:
        raise RespuestaInvalida(f"la lista maestra no trae archivos {tipo} de {anio}")
    return urls


def descomprimir(contenido: bytes) -> bytes:
    """Saca el unico CSV del zip. El zip no se guarda en ningun momento."""
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        nombres = z.namelist()
        if len(nombres) != 1:
            raise RespuestaInvalida(f"se esperaba un CSV por zip, llegaron {nombres}")
        return z.read(nombres[0])


def _guardar_bloque(partes: list[bytes], anio: int, numero: int) -> str:
    bloque = gzip.compress(b"".join(partes))
    nombre = f"anio={anio}/{TIPO}-{numero:04d}.csv.gz"
    return escribir(bloque, FUENTE, nombre, date(anio, 1, 1))


def cargar_anio(anio: int, limite: int | None = None,
                bytes_por_bloque: int = BYTES_POR_BLOQUE) -> list[str]:
    """Baja el ano completo y lo deja en bloques gzip de ~128 MB."""
    urls = urls_del_anio(anio, pedir(LISTA_MAESTRA).decode("utf-8", "replace"))
    if limite:
        urls = urls[:limite]
    partes: list[bytes] = []
    acumulado = 0
    escritas: list[str] = []
    for u in urls:
        csv = descomprimir(pedir(u))
        partes.append(csv)
        acumulado += len(csv)
        if acumulado >= bytes_por_bloque:
            escritas.append(_guardar_bloque(partes, anio, len(escritas) + 1))
            partes, acumulado = [], 0
    if partes:                                   # la cola, aunque no llegue al bloque
        escritas.append(_guardar_bloque(partes, anio, len(escritas) + 1))
    return escritas


def lambda_handler(event: dict | None = None, context=None) -> dict:  # noqa: ARG001
    """Carga historica: se invoca a mano por ano, no tiene programa."""
    evento = event or {}
    anio = int(evento.get("anio", config.ANIO_PILOTO))
    limite = evento.get("limite")
    rutas_escritas = cargar_anio(anio, int(limite) if limite else None)
    return {"fuente": FUENTE, "anio": anio, "bloques": len(rutas_escritas),
            "rutas": rutas_escritas}
