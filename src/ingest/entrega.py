"""Ingesta a Bronze de la entrega de la empresa (WP 0.2, informe v6, Tabla 3.4b) — ELT.

Recibe la carpeta con los Excel tal como los entregó la empresa (sin subcarpetas
obligatorias) y copia cada archivo SIN transformar a

    bronze/interno/estructurado/<dominio>/<codigo>/fecha_carga=AAAA-MM-DD/<nombre original>

El dominio sale de `contracts/_archivos.yaml`. Cada archivo queda en el manifiesto
con su tamaño y su SHA-256. Un archivo cuyo contenido ya se cargó con otro nombre
(mismo hash) se rechaza y se anota: evita contar dos veces la misma fuente.

En S3 la llegada de cada archivo dispara la Lambda que escribe Silver.

Uso:
  python -m src.ingest.entrega --origen "C:/ruta/a/los/archivos" --simular   # no copia nada
  python -m src.ingest.entrega --origen "C:/ruta/a/los/archivos"
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import yaml

from src.common import config, rutas
from src.ingest.internos import subir
from src.ingest.manifest import Manifiesto, sha256

MAPA = config.RAIZ_REPO / "contracts" / "_archivos.yaml"


def _reglas() -> dict:
    return yaml.safe_load(MAPA.read_text(encoding="utf-8"))


def codigo(nombre: str) -> str:
    """'COMPRAS MENSUALES (1).xlsx' → 'compras_mensuales_1'."""
    base = unicodedata.normalize("NFKD", Path(nombre).stem)
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_")


def dominio(nombre: str, reglas: dict | None = None) -> str:
    reglas = reglas or _reglas()
    for r in reglas["reglas"]:
        if re.search(r["patron"], nombre):
            return r["dominio"]
    return reglas["por_defecto"]


def destino_bronze(nombre: str, fecha_carga: str, reglas: dict | None = None) -> str:
    return rutas.ruta("bronze", "interno", "estructurado", dominio(nombre, reglas), codigo(nombre),
                      f"fecha_carga={fecha_carga}", nombre)


def ingerir(origen: Path, fecha_carga: str | None = None, simular: bool = False) -> list[dict]:
    origen = Path(origen)
    if not origen.is_dir():
        raise NotADirectoryError(f"La ruta de origen '{origen}' no es una carpeta.")
    reglas = _reglas()
    man = Manifiesto(fecha_carga)
    vistos: dict[str, str] = {}
    resultado = []
    # Primero los nombres sin marca de copia '(1)': ante dos archivos idénticos se conserva el original.
    es_copia = lambda p: bool(re.search(r"\(\d+\)\.[A-Za-z]+$", p.name))  # noqa: E731
    for f in sorted((p for p in origen.rglob("*") if p.is_file()), key=lambda p: (es_copia(p), p.name)):
        if f.suffix.lower() not in reglas["extensiones"] or f.name.startswith("~$"):
            continue
        huella = sha256(f)
        destino = destino_bronze(f.name, man.fecha_carga, reglas)
        if huella in vistos:
            resultado.append({"archivo": f.name, "estado": "duplicado_rechazado", "igual_a": vistos[huella]})
            continue
        vistos[huella] = f.name
        if not simular:
            subir(f, destino)
            man.agregar(f, codigo(f.name), destino)
        resultado.append({"archivo": f.name, "estado": "simulado" if simular else "cargado",
                          "dominio": dominio(f.name, reglas), "destino": destino})
    if not simular:
        man.guardar()
    return resultado


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--origen", type=Path, required=True)
    ap.add_argument("--fecha-carga", default=None)
    ap.add_argument("--simular", action="store_true", help="muestra a dónde iría cada archivo sin copiar nada")
    a = ap.parse_args()
    filas = ingerir(a.origen, a.fecha_carga, a.simular)
    for r in filas:
        print(f"{r['estado']:<20} {r['archivo']:<62} {r.get('dominio', 'igual a ' + r.get('igual_a', ''))}")
    cargados = sum(r["estado"] != "duplicado_rechazado" for r in filas)
    print(f"\n{cargados} archivo(s) {'por cargar' if a.simular else 'cargados'} · "
          f"{len(filas) - cargados} duplicado(s) rechazado(s) · destino {rutas.base()}")
