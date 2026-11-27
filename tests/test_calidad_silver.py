"""Tabla calidad_silver (commit A10).

La prueba que pide el A10 arma dos JSON de control y comprueba dos cosas: que la
completitud sale bien y que una meta incumplida deja la corrida en `cumple=False`.
Las pruebas con Spark se omiten donde Spark no puede acceder al disco (Windows sin
winutils); la integración continua las corre en Ubuntu.
"""
import json
from pathlib import Path

import pytest

from src.common import config
from src.quality import calidad_silver as cs

# Dos corridas: compras_glp cumple sus metas y scop incumple la de placa.
CONTROL_COMPRAS = {
    "tabla": "compras_glp", "fuente": "compras_mensuales_2022_2023", "familia": "F06",
    "generado_utc": "2026-11-26T12:00:00+00:00", "estado": "ok",
    "filas_leidas": 120, "filas_efectivas": 100, "filas_salida": 100,
    "filas_con_llave_repetida": 0,
    # 4 columnas x 100 filas = 400 celdas posibles; con dato: 100+100+80+120 = 400 -> hay
    # una columna con mas dato que filas? no: 100+100+80+20 = 300 -> completitud 0.75
    "celdas_con_dato": {"proveedor": 100, "numero": 100, "placa": 80, "guia": 20},
    "descartes": {"filas_de_total": 3, "encabezados_repetidos": 1, "sin_campos_exigidos": 6},
    "calidad": {"placa_valida": 0.99, "scop_presente": 0.97, "kg_positivo": 1.0,
                "fechas_invertidas": 7.0},
    "hojas": [{"hoja": "ENERO 2022", "estado": "leida", "filas_leidas": 120,
               "filas_efectivas": 100, "cortada_por_filas_vacias": False}],
}
CONTROL_SCOP = {
    "tabla": "scop", "fuente": "scops_generados", "familia": "F05",
    "generado_utc": "2026-11-26T12:00:00+00:00", "estado": "ok",
    "filas_leidas": 30, "filas_efectivas": 20, "filas_salida": 20,
    "filas_con_llave_repetida": 4,
    "celdas_con_dato": {"nro_scop": 20, "placa_cargada": 10},   # 2 x 20 = 40; 30/40 = 0.75
    "descartes": {"filas_de_total": 0, "encabezados_repetidos": 0, "sin_campos_exigidos": 10},
    "calidad": {"placa_valida": 0.50, "fecha_valida": 1.0},     # 0.50 < META_PLACA_VALIDA
    "hojas": [{"hoja": "SCOPS GENERADOS", "estado": "leida", "filas_leidas": 30,
               "filas_efectivas": 20, "cortada_por_filas_vacias": False}],
}


@pytest.fixture()
def control(tmp_path) -> str:
    for ctl in (CONTROL_COMPRAS, CONTROL_SCOP):
        destino = tmp_path / "_control" / ctl["tabla"]
        destino.mkdir(parents=True, exist_ok=True)
        (destino / f"{ctl['fuente']}.json").write_text(
            json.dumps(ctl, ensure_ascii=False, indent=2), encoding="utf-8")
    return "file:///" + (tmp_path / "_control").as_posix().lstrip("/")


# --- Sin Spark ----------------------------------------------------------------
def test_las_metas_salen_de_config_y_no_de_numeros_sueltos():
    assert cs.METAS["placa_valida"] == ("META_PLACA_VALIDA", config.META_PLACA_VALIDA)
    assert cs.METAS["kg_positivo"] == ("META_KG_EN_RANGO", config.META_KG_EN_RANGO)
    assert cs.METAS["scop_presente"] == ("META_SCOP_COMPRAS", config.META_SCOP_COMPRAS)


def test_el_esquema_declara_lo_que_escribe_procesar():
    campos = {c.name: c.dataType.simpleString() for c in cs.esquema()}
    assert campos["tabla"] == "string" and campos["filas_salida"] == "bigint"
    assert campos["celdas_con_dato"] == "map<string,bigint>"
    assert campos["calidad"] == "map<string,double>"
    # el contrato de procesar.py: todas estas claves existen en el JSON de control
    for clave in CONTROL_COMPRAS:
        assert clave in campos, clave


def test_los_datos_de_prueba_son_los_que_escribe_el_pipeline():
    """Si procesar.py cambia de forma, esta prueba avisa antes que la de Spark."""
    from src.silver import procesar  # noqa: PLC0415

    fuente = Path(procesar.__file__).read_text(encoding="utf-8")
    for clave in ("filas_con_llave_repetida", "celdas_con_dato", "descartes", "calidad"):
        assert f'"{clave}"' in fuente or f"{clave}=" in fuente, clave


# --- Con Spark ----------------------------------------------------------------
def test_completitud_y_meta_incumplida(spark, control):
    """La prueba del A10: la completitud se calcula bien y la meta incumplida marca cumple=False."""
    df = cs.construir(spark, control).orderBy("tabla")
    filas = {f["tabla"]: f for f in df.take(5)}
    assert set(filas) == {"compras_glp", "scop"}

    compras = filas["compras_glp"]
    assert compras["columnas_declaradas"] == 4
    assert compras["completitud"] == pytest.approx(300 / 400)      # 100+100+80+20 sobre 4x100
    assert compras["unicidad"] == 1.0 and compras["filas_con_llave_repetida"] == 0
    assert compras["filas_descartadas"] == 10                      # 3 + 1 + 6
    assert compras["filas_corregidas"] == 7                        # fechas_invertidas
    assert compras["cumple"] is True and compras["metas_incumplidas"] == []

    scop = filas["scop"]
    assert scop["completitud"] == pytest.approx(30 / 40)           # 20+10 sobre 2x20
    assert scop["unicidad"] == pytest.approx(1 - 4 / 20)
    assert scop["cumple"] is False
    assert scop["metas_incumplidas"] == ["META_PLACA_VALIDA"]      # 0.50 < 0.98
    assert scop["filas_corregidas"] == 0                           # no registra correcciones


def test_una_meta_sin_su_metrica_no_se_incumple(spark, control):
    """scop no mide kg ni SCOP: esas metas no se le aplican, no las incumple."""
    df = cs.construir(spark, control).filter("tabla = 'scop'")
    fila = df.take(1)[0]
    assert "META_KG_EN_RANGO" not in fila["metas_incumplidas"]
    assert "META_SCOP_COMPRAS" not in fila["metas_incumplidas"]
    assert fila["kg_positivo"] is None and fila["scop_presente"] is None
    assert fila["fecha_valida"] == 1.0
