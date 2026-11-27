"""Compensación de pares redigitados (commit A14).

La prueba que pide el A14: un par +500 y −500 se compensa; un +500 aislado no.
"""
import pandas as pd
import pytest

from src.quality.redigitados import TOLERANCIA_KG, compensar, resumen


def _mov(filas) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=["placa_norm", "periodo", "kg"])


def test_un_par_mas_y_menos_se_compensa():
    df = compensar(_mov([("T1A123", 1, 500.0), ("T1A123", 2, -500.0)]),
                   entidad="placa_norm", valor="kg")
    assert df["redigitado"].tolist() == [True, True]
    assert df["kg_compensado"].tolist() == [0.0, 0.0]
    assert df["kg"].tolist() == [500.0, -500.0]          # el dato original no se toca


def test_un_mas_aislado_no_se_toca():
    """Un error sin corregir es justo lo que el detector debe ver."""
    df = compensar(_mov([("T1A123", 1, 500.0), ("T1A123", 2, 10.0)]),
                   entidad="placa_norm", valor="kg")
    assert df["redigitado"].tolist() == [False, False]
    assert df["kg_compensado"].tolist() == [500.0, 10.0]


def test_la_correccion_tardia_queda_fuera_de_la_ventana():
    filas = [("T1A123", 1, 500.0), ("T1A123", 2, 0.0), ("T1A123", 3, 0.0), ("T1A123", 4, -500.0)]
    assert not compensar(_mov(filas), entidad="placa_norm", valor="kg")["redigitado"].any()
    # con una ventana mayor sí lo alcanza
    ancha = compensar(_mov(filas), entidad="placa_norm", valor="kg", ventana=3)
    assert ancha["redigitado"].tolist() == [True, False, False, True]


@pytest.mark.parametrize("correccion,compensa", [
    (-500.0, True), (-500.5, True), (-501.0, True), (-501.5, False), (-480.0, False)])
def test_la_tolerancia_es_de_un_kilo(correccion, compensa):
    df = compensar(_mov([("T1A123", 1, 500.0), ("T1A123", 2, correccion)]),
                   entidad="placa_norm", valor="kg")
    assert df["redigitado"].all() is compensa or df["redigitado"].any() == compensa
    assert abs(500.0 + correccion) <= TOLERANCIA_KG or not compensa


def test_cada_entidad_se_compensa_por_separado():
    """El −500 de otra placa no corrige el +500 de la primera."""
    df = compensar(_mov([("T1A123", 1, 500.0), ("B2E983", 2, -500.0)]),
                   entidad="placa_norm", valor="kg")
    assert not df["redigitado"].any()


def test_una_correccion_no_sirve_para_dos_errores():
    """Con dos errores y una sola correccion, uno queda sin compensar.

    La regla es «el error mas antiguo toma la primera correccion a su alcance», que es
    determinista y no depende del orden de las filas. Aqui el +500 del periodo 1 alcanza
    al -500 del periodo 3 y se lo queda; el del periodo 2 se queda expuesto, que es lo
    que debe ver el detector.
    """
    filas = [("T1A123", 1, 500.0), ("T1A123", 2, 500.0), ("T1A123", 3, -500.0)]
    df = compensar(_mov(filas), entidad="placa_norm", valor="kg")
    assert df["redigitado"].tolist() == [True, False, True]
    assert df["kg_compensado"].tolist() == [0.0, 500.0, 0.0]


def test_las_filas_desordenadas_se_emparejan_igual_y_no_se_reordenan():
    desordenado = _mov([("T1A123", 2, -500.0), ("T1A123", 1, 500.0)])
    df = compensar(desordenado, entidad="placa_norm", valor="kg")
    assert df["periodo"].tolist() == [2, 1]                   # se respeta el orden de entrada
    assert df["redigitado"].all()


def test_los_nulos_y_los_ceros_no_emparejan():
    df = compensar(_mov([("T1A123", 1, None), ("T1A123", 2, 0.0), ("T1A123", 3, 0.0)]),
                   entidad="placa_norm", valor="kg")
    assert not df["redigitado"].any()


def test_el_resumen_cuenta_pares_y_kilos():
    filas = [("T1A123", 1, 500.0), ("T1A123", 2, -500.0), ("B2E983", 1, 300.0)]
    r = resumen(compensar(_mov(filas), entidad="placa_norm", valor="kg"), "kg")
    assert r == {"filas_redigitadas": 2, "pares": 1, "valor_neutralizado": 1000.0,
                 "filas_sin_compensar": 1}


def test_una_columna_que_falta_avisa_claro():
    with pytest.raises(KeyError, match="periodo"):
        compensar(pd.DataFrame({"placa_norm": ["A"], "kg": [1.0]}), entidad="placa_norm", valor="kg")
