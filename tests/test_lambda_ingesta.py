"""W02: la Lambda de ingesta copia a Bronze una vez y rechaza el duplicado."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common import rutas
from src.ingest import lambda_ingesta as li

FECHA = "2026-11-26"
NOMBRE = "COMPRAS MENSUALES.xlsx"


def evento(*claves: str) -> dict:
    return {"Records": [{"s3": {"bucket": {"name": "costagas-trujillo-lake-dev"},
                                "object": {"key": c}}} for c in claves]}


def _poner(lago, clave: str, contenido: bytes = b"contenido de prueba") -> Path:
    destino = Path(rutas.base()) / clave
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return destino


def test_archivo_nuevo_se_copia_y_se_registra(lago):
    clave = f"landing/interno/{NOMBRE}"
    _poner(lago, clave)

    r = li.procesar(clave, FECHA)

    assert r["estado"] == "cargado"
    assert r["dominio"] == "compras"
    assert Path(r["destino"]).exists()
    assert r["destino"].endswith(
        f"bronze/interno/estructurado/compras/compras_mensuales/fecha_carga={FECHA}/{NOMBRE}"
    )
    manifiesto = Path(li.ruta_manifiesto(NOMBRE, FECHA, r["sha256"]))
    fila = json.loads(manifiesto.read_text(encoding="utf-8"))
    assert fila["sha256"] == r["sha256"]
    assert fila["fuente"] == "compras_mensuales"
    assert fila["bytes"] == len(b"contenido de prueba")
    assert fila["fecha_carga"] == FECHA


def test_el_mismo_contenido_queda_duplicado(lago):
    _poner(lago, f"landing/interno/{NOMBRE}")
    primera = li.procesar(f"landing/interno/{NOMBRE}", FECHA)

    # El mismo contenido con otro nombre y en otra fecha: no se vuelve a copiar.
    _poner(lago, "landing/interno/COMPRAS MENSUALES (1).xlsx")
    segunda = li.procesar("landing/interno/COMPRAS MENSUALES (1).xlsx", "2026-12-01")

    assert primera["estado"] == "cargado"
    assert segunda["estado"] == "duplicado"
    assert segunda["igual_a"].endswith(f"__{primera['sha256']}.json")
    copias = list((Path(rutas.base()) / "bronze").rglob("*.xlsx"))
    assert len(copias) == 1


def test_op_landing_va_al_lago_de_operacion(lago):
    clave = f"op/landing/{NOMBRE}"
    _poner(lago, clave, b"entrega mensual de operacion")

    r = li.procesar(clave, FECHA)

    assert "/op/bronze/interno/estructurado/compras/" in r["destino"]
    assert Path(r["destino"]).exists()


def test_extension_no_admitida_levanta_error(lago):
    clave = "landing/interno/notas.txt"
    _poner(lago, clave)

    with pytest.raises(li.ExtensionNoAdmitida):
        li.procesar(clave, FECHA)


def test_externo_se_ignora(lago):
    clave = "landing/externo/bcrp/tc_2026-11-26.json"
    _poner(lago, clave, b"{}")

    assert li.procesar(clave, FECHA)["estado"] == "externo_ignorado"


def test_fuera_de_landing_no_se_toca(lago):
    assert li.procesar("silver/compras_glp/part-0.parquet", FECHA)["estado"] == "fuera_de_landing"


def test_handler_procesa_todas_las_claves_del_evento(lago):
    _poner(lago, f"landing/interno/{NOMBRE}", b"uno")
    _poner(lago, "landing/interno/VENTAS 2020.xlsx", b"dos")

    r = li.lambda_handler(evento(f"landing/interno/{NOMBRE}", "landing/interno/VENTAS 2020.xlsx"))

    assert r["procesados"] == 2
    assert [x["estado"] for x in r["resultados"]] == ["cargado", "cargado"]
    assert {x["dominio"] for x in r["resultados"]} == {"compras", "ventas"}


def test_claves_del_evento_desescapa_el_nombre():
    assert li.claves_del_evento(evento("landing/interno/COMPRAS+MENSUALES.xlsx")) == [
        "landing/interno/COMPRAS MENSUALES.xlsx"
    ]
