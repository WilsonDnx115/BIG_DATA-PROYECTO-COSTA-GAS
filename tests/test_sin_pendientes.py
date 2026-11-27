"""El repositorio no deja ningun valor «por confirmar» (commit AR12).

Es la regla 2 del equipo: todo parametro, umbral o cifra lleva su fuente, y lo que no
existe en la entrega se escribe como **no cubierto** con la evidencia de la busqueda. Un
«por confirmar» en la sustentacion se lee como trabajo inacabado, y un hueco en un
tablero se lee como un cero.

La diferencia que hace esta prueba:

* «no cubierto: el inventario no publica los nombres de esas 25 columnas» es un
  resultado, con su evidencia. Pasa.
* «por confirmar con el DDL de W09» es una tarea que alguien tiene que recordar. Falla.

Lo que recorre: `docs/`, `sql/`, `dashboards/`, `contracts/` y `src/common/config.py`,
que es donde viven los valores que se publican. No recorre `tests/`, porque una prueba
que busca estas formulas tiene que poder escribirlas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.common import config

# Las formulas prohibidas. Se buscan con limites de palabra: «para definir las fuentes»
# es prosa normal y no debe fallar, mientras que «a definir» si es una tarea pendiente.
PROHIBIDAS = (
    r"\bpor\s+confirmar\b",
    r"\bpor\s+fijar\b",
    r"\ba\s+definir\b",
    r"\bpendiente\s+de\s+la\s+empresa\b",
    r"\bTBD\b",
    r"_{4,}",
)
RE_PROHIBIDAS = [re.compile(p, re.IGNORECASE) for p in PROHIBIDAS]

CARPETAS = ("docs", "sql", "dashboards", "contracts")
ARCHIVOS = ("src/common/config.py",)

# Solo lo que se lee o se publica. Un .parquet o un .png no se revisan por texto.
EXTENSIONES = {".md", ".yaml", ".yml", ".sql", ".json", ".py", ".txt", ".csv", ".cfg", ".ini"}

# `docs/guias/` guarda los PDF y documentos que entrego el curso y la empresa: son
# fuentes, no texto nuestro, y no se corrigen. `docs/evidencias/capturas/` son imagenes.
EXCLUIDOS = ("docs/guias/", "docs/evidencias/capturas/")


def _revisables() -> list[Path]:
    raiz = config.RAIZ_REPO
    encontrados: list[Path] = []
    for carpeta in CARPETAS:
        base = raiz / carpeta
        if not base.exists():
            continue
        encontrados += [p for p in sorted(base.rglob("*"))
                        if p.is_file() and p.suffix.lower() in EXTENSIONES]
    encontrados += [raiz / a for a in ARCHIVOS if (raiz / a).exists()]
    return [p for p in encontrados
            if not any(e in p.relative_to(raiz).as_posix() for e in EXCLUIDOS)]


def _hallazgos() -> list[tuple[str, int, str]]:
    raiz = config.RAIZ_REPO
    salida = []
    for archivo in _revisables():
        try:
            texto = archivo.read_text(encoding="utf-8")
        except UnicodeDecodeError:                      # un binario con extension de texto
            continue
        for numero, linea in enumerate(texto.splitlines(), start=1):
            for patron in RE_PROHIBIDAS:
                if patron.search(linea):
                    salida.append((archivo.relative_to(raiz).as_posix(), numero,
                                   linea.strip()[:120]))
                    break
    return salida


def test_el_repositorio_no_tiene_valores_por_confirmar():
    hallazgos = _hallazgos()
    detalle = "\n".join(f"  {a}:{n}  {t}" for a, n, t in hallazgos)
    assert not hallazgos, (
        f"{len(hallazgos)} valor(es) sin resolver. Cada uno lleva su fuente, o se "
        f"escribe como «no cubierto» con la evidencia de la busqueda:\n{detalle}")


def test_la_busqueda_llega_a_los_sitios_que_importan():
    """Si la prueba dejara de encontrar archivos, pasaria en vacio sin avisar."""
    revisables = {p.relative_to(config.RAIZ_REPO).as_posix() for p in _revisables()}
    assert len(revisables) > 50
    for imprescindible in ("docs/bitacora.md",
                           "contracts/pedidos_proveedor.yaml",
                           "sql/athena/vistas/v_kpi_1.sql",
                           "src/common/config.py"):
        assert imprescindible in revisables, imprescindible
    assert any(p.startswith("dashboards/") for p in revisables)


@pytest.mark.parametrize("linea", [
    "| B02 | Base del tablero | hecho | Columnas por confirmar con el DDL de W09 |",
    "MERMA_TECNICA_PCT = por fijar",
    "umbral: a definir",
    "El dato lo trae la empresa: pendiente de la empresa",
    "precio_ref_kg = TBD",
    "| Umbral | ____ |",
])
def test_las_formulas_prohibidas_se_detectan(linea):
    """Que la prueba sepa fallar es parte de la prueba."""
    assert any(p.search(linea) for p in RE_PROHIBIDAS), linea


@pytest.mark.parametrize("linea", [
    "no cubierto: el inventario no publica los nombres de esas 25 columnas",
    "El documento fue consultado para definir las metas de calidad",
    "La merma de 0.5 % se apoya en Emerson (2019), ADR 0027",
    "stock_es_supuesto marca que la variacion de stock se toma como 0",
    "Las columnas las fija el DDL de W09; el tablero las toma de COLUMNAS_GOLD",
])
def test_lo_que_si_esta_resuelto_no_se_marca(linea):
    """«No cubierto con su evidencia» es un resultado, no un pendiente."""
    assert not any(p.search(linea) for p in RE_PROHIBIDAS), linea
