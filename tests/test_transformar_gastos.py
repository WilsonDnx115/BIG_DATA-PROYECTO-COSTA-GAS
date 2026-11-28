"""Transformacion de la tabla Silver gastos (commit AR25).

`gasto_combustible` de `fact_unidad_mes` se arma agregando estas filas por placa, anio
y mes, quedandose con las de combustible. Lo que esta transformacion tiene que resolver:

1. **`es_combustible` sale de la categoria**, y queda **nulo** cuando la fuente no trae
   categoria. Un falso por defecto diria que ningun gasto es combustible, que es
   justamente la cifra que el KPI 4 necesita.
2. **El RUC del proveedor no se publica**, aunque venga pegado a la razon social.
3. **La placa se normaliza**, porque es la llave contra `dim_unidad`.

Todos los datos de estas pruebas son sinteticos.
"""
from __future__ import annotations

import pandas as pd

from src.silver import contratos
from src.silver.transformar import TRANSFORMACIONES


def _entrada(filas: list[dict]) -> pd.DataFrame:
    columnas = ["mes_texto", "fecha", "placa_norm", "unidad_codigo", "area", "categoria",
                "descripcion", "comentarios", "monto_soles", "proveedor", "planta"]
    return pd.DataFrame([{c: f.get(c) for c in columnas} for f in filas])


def _salida(filas: list[dict]) -> pd.DataFrame:
    salida, _ = TRANSFORMACIONES["gastos"](_entrada(filas))
    return salida


# --- La transformacion existe y cumple el contrato -----------------------------
def test_la_tabla_gastos_tiene_su_transformacion():
    assert "gastos" in TRANSFORMACIONES


def test_produce_todas_las_columnas_que_el_contrato_declara():
    """`procesar` falla si falta una: el contrato y la transformacion van juntos."""
    salida = _salida([{"mes_texto": "ENERO", "monto_soles": 10.0}])
    del_contrato = set(contratos.cargar()["gastos"].nombres())
    linaje = {"origen", "hoja", "fila", "llave_repetida"}     # las agrega `procesar`
    assert del_contrato - linaje <= set(salida.columns)


# --- es_combustible ------------------------------------------------------------
def test_la_categoria_de_combustible_marca_es_combustible():
    salida = _salida([{"categoria": "COMBUSTIBLE", "monto_soles": 50.0},
                      {"categoria": "PETROLEO D2", "monto_soles": 60.0}])
    assert salida["es_combustible"].tolist() == [True, True]


def test_una_categoria_que_no_es_combustible_queda_en_falso():
    salida = _salida([{"categoria": "PEAJES", "monto_soles": 50.0},
                      {"categoria": "MANTENIMIENTO", "monto_soles": 60.0}])
    assert salida["es_combustible"].tolist() == [False, False]


def test_sin_categoria_es_combustible_queda_nulo_y_no_en_falso():
    """Un falso diria que ese gasto no es combustible. No se sabe."""
    salida = _salida([{"mes_texto": "ENERO", "monto_soles": 50.0}])
    assert salida["es_combustible"].isna().all()


# --- Privacidad ----------------------------------------------------------------
def test_el_ruc_pegado_al_proveedor_no_llega_a_silver():
    """La razon social se conserva; el RUC, no, aunque venga en la misma celda."""
    salida = _salida([{"proveedor": "20123456786 PROVEEDOR FICTICIO S.A.C.", "monto_soles": 10.0}])
    proveedor = salida["proveedor"].iloc[0]
    assert "20123456786" not in proveedor
    assert "PROVEEDOR FICTICIO" in proveedor


def test_un_documento_de_persona_natural_tampoco_llega():
    salida = _salida([{"proveedor": "10456789019 PERSONA FICTICIA", "monto_soles": 10.0}])
    assert "10456789019" not in salida["proveedor"].iloc[0]


# --- Llave y medidas -----------------------------------------------------------
def test_la_placa_se_normaliza_para_cruzar_con_dim_unidad():
    salida = _salida([{"placa_norm": "T1A-111", "monto_soles": 10.0}])
    assert salida["placa_norm"].iloc[0] == "T1A111"


def test_una_placa_que_no_lo_es_queda_nula_y_no_se_inventa():
    salida = _salida([{"placa_norm": "U-07", "monto_soles": 10.0}])
    assert pd.isna(salida["placa_norm"].iloc[0])


def test_un_monto_que_no_es_numero_pasa_a_nulo_y_se_cuenta():
    salida, calidad = TRANSFORMACIONES["gastos"](
        _entrada([{"monto_soles": 125.5}, {"monto_soles": "no es un numero"}]))
    assert salida["monto_soles"].notna().sum() == 1
    assert calidad["monto_valido"] == 0.5


def test_el_anio_y_el_mes_salen_de_la_fecha():
    salida = _salida([{"fecha": "2020-05-17", "monto_soles": 10.0}])
    assert salida["anio"].iloc[0] == 2020 and salida["mes"].iloc[0] == 5


def test_sin_fecha_el_mes_sale_del_texto_del_mes():
    """La hoja de flota trae el mes como texto aunque falte la fecha."""
    salida = _salida([{"mes_texto": "MARZO", "monto_soles": 10.0}])
    assert salida["mes"].iloc[0] == 3
    assert pd.isna(salida["fecha"].iloc[0])


def test_la_calidad_informa_lo_que_el_bloqueo_de_gold_necesita():
    _, calidad = TRANSFORMACIONES["gastos"](
        _entrada([{"placa_norm": "T1A-111", "categoria": "COMBUSTIBLE", "monto_soles": 10.0},
                  {"placa_norm": None, "categoria": "PEAJES", "monto_soles": 20.0}]))
    assert calidad["placa_valida"] == 0.5
    assert calidad["monto_valido"] == 1.0
    assert calidad["filas_de_combustible"] == 1
