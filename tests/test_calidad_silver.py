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


# --- Bloqueo de metricas de Gold (commit AR09) --------------------------------
# Estas no necesitan Spark: `bloqueos` trabaja sobre las filas, asi que la regla de
# CLAUDE.md queda probada tambien donde Spark no corre.
def _fila(tabla, fuente="f1", cumple=True, metas=()):
    return {"tabla": tabla, "fuente": fuente, "cumple": cumple,
            "metas_incumplidas": list(metas)}


def _todas_cumplen():
    tablas = {t for cfg in cs.KPI_FUENTES.values() for t in cfg["exigidas"]}
    return [_fila(t) for t in sorted(tablas)]


def test_con_todo_en_regla_los_cinco_kpi_se_publican():
    resultado = cs.bloqueos(_todas_cumplen())
    assert set(resultado) == {"kpi_1", "kpi_2", "kpi_3", "kpi_4", "kpi_5"}
    assert all(v["publicable"] for v in resultado.values())
    assert cs.kpi_bloqueados(_todas_cumplen()) == []


def test_una_meta_incumplida_bloquea_su_kpi_y_lo_informa():
    """La prueba que pide el AR09: bloquea y dice qué tabla y qué meta."""
    filas = [f for f in _todas_cumplen() if f["tabla"] != "compras_glp"]
    filas.append(_fila("compras_glp", cumple=False, metas=["META_SCOP_COMPRAS"]))

    resultado = cs.bloqueos(filas)
    kpi1 = resultado["kpi_1"]
    assert kpi1["estado"] == cs.BLOQUEADO and kpi1["publicable"] is False
    assert kpi1["tablas_que_incumplen"] == ["compras_glp"]
    assert kpi1["metas_incumplidas"] == ["META_SCOP_COMPRAS"]
    assert "META_SCOP_COMPRAS" in kpi1["motivo"] and "Tabla 3.7" in kpi1["motivo"]
    # El KPI 4 no lee compras_glp: no tiene por qué caerse con él.
    assert resultado["kpi_4"]["publicable"] is True


def test_el_kpi_que_no_usa_esa_tabla_sigue_publicandose():
    filas = [f for f in _todas_cumplen() if f["tabla"] != "gastos"]
    filas.append(_fila("gastos", cumple=False, metas=["META_KG_EN_RANGO"]))

    resultado = cs.bloqueos(filas)
    assert resultado["kpi_4"]["publicable"] is False
    assert [k for k, v in resultado.items() if not v["publicable"]] == ["kpi_4"]


def test_una_tabla_sin_corrida_no_es_lo_mismo_que_una_que_incumple():
    """Sin medicion no hay cifra; con medicion mala hay cifra y no se publica."""
    sin_gastos = [f for f in _todas_cumplen() if f["tabla"] != "gastos"]
    resultado = cs.bloqueos(sin_gastos)["kpi_4"]
    assert resultado["estado"] == cs.SIN_MEDIR and resultado["publicable"] is False
    assert resultado["tablas_sin_medir"] == ["gastos"]
    assert resultado["metas_incumplidas"] == []
    assert "no hay nada medido que publicar" in resultado["motivo"]


def test_una_sola_fuente_que_incumple_arrastra_a_su_tabla():
    """La metrica se calcula sobre la tabla entera, no sobre la hoja que sí pasó."""
    filas = _todas_cumplen() + [_fila("compras_glp", fuente="f2", cumple=False,
                                      metas=["META_PLACA_VALIDA"])]
    assert cs.bloqueos(filas)["kpi_1"]["tablas_que_incumplen"] == ["compras_glp"]


def test_una_fuente_opcional_no_bloquea_pero_se_informa():
    """El stock físico no está medido: el KPI 1 lo declara como supuesto, no se calla."""
    resultado = cs.bloqueos(_todas_cumplen())["kpi_1"]
    assert resultado["publicable"] is True
    assert resultado["fuentes_opcionales_ausentes_o_incumplidas"] == ["produccion_diaria"]


def test_el_estado_sin_datos_bloquea_todo_y_no_falla():
    resultado = cs.bloqueos([])
    assert all(v["estado"] == cs.SIN_MEDIR for v in resultado.values())
    assert cs.kpi_bloqueados([]) == ["kpi_1", "kpi_2", "kpi_3", "kpi_4", "kpi_5"]


def test_cada_kpi_declara_la_tabla_de_gold_que_lee_su_vista():
    """Si una vista cambia de tabla, el mapa de fuentes tiene que cambiar con ella."""
    for kpi, info in cs.bloqueos(_todas_cumplen()).items():
        vista = Path("sql/athena/vistas") / f"v_{kpi}.sql"
        assert vista.exists(), vista
        assert info["tabla_gold"] in vista.read_text(encoding="utf-8")
