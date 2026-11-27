"""Ficha de cada version del modelo, generada desde el registro (commit AR07).

La prueba que pide el AR07: la ficha contiene el umbral y la precision. Alrededor de
eso, lo que importa es que ningun dato que falte salga en blanco ni como
«por confirmar»: sale como «no cubierto» con su motivo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.models import ficha, registro


class ModeloFalso:
    def __init__(self, nombre: str = "rf"):
        self.nombre = nombre


METRICAS = {
    "precision": 0.72, "recall": 0.61, "pr_auc": 0.55, "f1": 0.66, "umbral": 0.38,
    "ic": {"precision": [0.65, 0.79], "recall": [0.52, 0.70],
           "pr_auc": [0.47, 0.63], "f1": [0.59, 0.73]},
    "remuestreos": 1000,
    "datos": {"filas_entrenamiento": 3200, "filas_validacion": 800,
              "periodo": "2022-02 a 2023-08", "positivos": 96},
    "variables": ["kg", "usd_por_kg", "dias_hasta_pago"],
    "psi": {"estado": "ok", "n": 800, "psi": {"kg": 0.04, "usd_por_kg": 0.11},
            "variables_con_deriva": []},
    "sesgos": {"por_rol": {"reparto": 0.71, "planta": 0.74},
               "por_producto": {"GLP envasado": 0.72, "GLP granel": 0.70},
               "por_canal": {"directo": 0.73, "distribuidor": 0.69}},
}


@pytest.fixture()
def vigente(lago) -> dict:
    """Un modelo promovido de verdad, con el registro de W13."""
    retador = registro.guardar(ModeloFalso(), METRICAS, fecha="2026-11-26", umbral=0.38)
    assert registro.promover_si_mejora(retador) is True
    return retador


# --- Lo que pide el AR07 ------------------------------------------------------
def test_la_ficha_contiene_umbral_y_precision(vigente):
    texto = ficha.a_markdown(ficha.construir())
    assert "0.3800" in texto                        # el umbral del registro
    assert "0.7200" in texto                        # la precision
    assert "s12-2026-11-26" in texto


def test_sale_del_vigente_y_no_de_la_ultima_corrida(lago):
    """Una corrida guardada sin promover no describe al modelo que esta puntuando."""
    promovido = registro.guardar(ModeloFalso(), METRICAS, fecha="2026-11-26", umbral=0.38)
    registro.promover_si_mejora(promovido)
    # Retador peor: se guarda, no se promueve, y la ficha no debe cambiar de umbral.
    peor = dict(METRICAS, precision=0.40, recall=0.62, umbral=0.9)
    registro.guardar(ModeloFalso("peor"), peor, fecha="2026-11-27", umbral=0.9)

    f = ficha.construir()
    assert f["corrida"] == "2026-11-26" and f["umbral"] == 0.38


def test_las_metricas_llevan_su_intervalo(vigente):
    f = ficha.construir()
    assert f["metricas"]["precision"]["ic95"] == [0.65, 0.79]
    assert "0.6500 a 0.7900" in ficha.a_markdown(f)


def test_trae_datos_variables_psi_y_los_tres_sesgos(vigente):
    f = ficha.construir()
    assert f["datos"]["filas_entrenamiento"] == 3200
    assert f["variables"] == ["kg", "usd_por_kg", "dias_hasta_pago"]
    assert f["psi"]["variables_con_deriva"] == []
    texto = ficha.a_markdown(f)
    for etiqueta in ("Por tipo de unidad (rol)", "Por producto", "Por canal"):
        assert etiqueta in texto


# --- Lo que falta se dice ------------------------------------------------------
def test_sin_modelo_vigente_lo_dice_y_no_falla(lago):
    f = ficha.construir()
    assert f["estado"] == "sin_vigente"
    texto = ficha.a_markdown(f)
    assert "Sin modelo vigente" in texto and ficha.FALTA in texto


def test_un_dato_que_falta_sale_como_no_cubierto_con_motivo(lago):
    """Un hueco en los sesgos se leeria como «no tiene sesgos», que no es lo mismo."""
    minimas = {"precision": 0.72, "recall": 0.61, "umbral": 0.38}
    retador = registro.guardar(ModeloFalso(), minimas, fecha="2026-11-26", umbral=0.38)
    registro.promover_si_mejora(retador)

    f = ficha.construir()
    assert f["sesgos"]["por_rol"].startswith(ficha.FALTA)
    assert "paso 5.3 del PLAN" in f["sesgos"]["por_rol"]
    assert f["psi"].startswith(ficha.FALTA)
    assert f["metricas"]["pr_auc"]["valor"] is None
    assert f["metricas"]["precision"]["ic95"] is None      # no hay bootstrap


def test_la_ficha_no_usa_ninguna_formula_prohibida(vigente):
    """Regla 2 del equipo: ni «por confirmar» ni «____» en lo que se publica."""
    texto = ficha.a_markdown(ficha.construir()).lower()
    for prohibida in ("por confirmar", "por fijar", "a definir", "tbd", "____"):
        assert prohibida not in texto


def test_ninguna_celda_de_la_tabla_queda_vacia(lago):
    minimas = {"precision": 0.72, "recall": 0.61, "umbral": 0.38}
    registro.promover_si_mejora(
        registro.guardar(ModeloFalso(), minimas, fecha="2026-11-26", umbral=0.38))
    for linea in ficha.a_markdown(ficha.construir()).splitlines():
        if linea.startswith("|") and "---" not in linea:
            assert all(celda.strip() for celda in linea.strip("|").split("|")), linea


# --- La interfaz de linea de comandos -----------------------------------------
def test_escribe_el_archivo_que_se_le_pide(vigente, tmp_path, capsys):
    destino = tmp_path / "modelos" / "ficha_s12.md"
    assert ficha.main(["--destino", str(destino)]) == 0
    capsys.readouterr()
    texto = Path(destino).read_text(encoding="utf-8")
    assert texto.startswith("# Ficha del modelo s12-2026-11-26")
    assert "0.3800" in texto


def test_sin_vigente_la_cli_no_es_un_error(lago, capsys):
    """El registro vacio es un estado, no un fallo del programa."""
    assert ficha.main([]) == 0
    assert "Sin modelo vigente" in capsys.readouterr().out
