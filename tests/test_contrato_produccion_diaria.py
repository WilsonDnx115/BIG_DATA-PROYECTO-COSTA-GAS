"""Contrato de la tabla Silver produccion_diaria (commit AR27).

Es la fuente de la senal S11 y la unica forma de que el KPI 1 tenga una variacion de
stock medida en vez de supuesta. La hoja existe y esta localizada:
`Reporte de Produccion CGT 2018.xlsx`, hoja `ProduccionReal-Cap Efec (Octub)`, una fila
por dia y los 31 dias de octubre de 2018
(docs/evidencias/produccion_diaria_en_la_entrega.md).

Dos cosas que esta tabla tiene que dejar claras, porque son las que se malinterpretan:

1. **`stock_final_es_calculado` es verdadero siempre.** El informe lo dice: el inventario
   final de planta no se contabiliza fisicamente, se calcula para que el balance diario
   cuadre (`cierres_medidos_fisicamente: 0`). Declararlo nulo invitaria a leer ese stock
   como una medicion.
2. **La hoja es de 2018**, fuera del piloto 2020. Sirve para S11, no para el KPI 1 del
   piloto.
"""
from __future__ import annotations

import pandas as pd

from src.silver import contratos
from src.signals.contratos import ENTRADAS
from src.silver.transformar import TRANSFORMACIONES


def _entrada(filas: list[dict]) -> pd.DataFrame:
    columnas = ["fecha", "stock_inicial", "ventas", "bonificaciones", "stock_final",
                "produccion"]
    return pd.DataFrame([{c: f.get(c) for c in columnas} for f in filas])


# --- El contrato ---------------------------------------------------------------
def test_el_contrato_existe_con_su_grano_diario():
    c = contratos.cargar()["produccion_diaria"]
    assert c.dominio == "produccion" and c.llave == ("fecha",)
    assert "LOCATION '${LAKE}/silver/produccion/produccion_diaria/'" in c.ddl()


def test_declara_exactamente_lo_que_pide_la_interfaz_produccion_del_wp08():
    """Un solo esquema por tabla: las columnas las fija `src/signals/contratos.py`."""
    _, columnas_interfaz = ENTRADAS["produccion"]
    nombres = contratos.cargar()["produccion_diaria"].nombres()
    for columna in columnas_interfaz:
        assert columna in nombres, columna


def test_la_hoja_se_lee_por_posicion_tomando_el_total_de_cada_bloque():
    """El encabezado son dos filas y cada concepto se abre por marca; va el TOTAL."""
    f = contratos.cargar()["produccion_diaria"].fuentes[0]
    assert f.por_posicion and f.primera_fila == 3
    # A fecha · H stock inicial · O ventas · V bonificaciones · AC stock final · AJ produccion
    assert f.posiciones == {"fecha": 0, "stock_inicial": 7, "ventas": 14,
                            "bonificaciones": 21, "stock_final": 28, "produccion": 35}


# --- La transformacion ----------------------------------------------------------
def test_produce_todas_las_columnas_del_contrato():
    salida, _ = TRANSFORMACIONES["produccion_diaria"](
        _entrada([{"fecha": "2018-10-01", "stock_inicial": 1000.0, "ventas": 300.0,
                   "bonificaciones": 10.0, "stock_final": 890.0, "produccion": 200.0}]))
    del_contrato = set(contratos.cargar()["produccion_diaria"].nombres())
    linaje = {"origen", "hoja", "fila", "llave_repetida"}
    assert del_contrato - linaje <= set(salida.columns)


def test_el_stock_final_se_declara_calculado_y_no_medido():
    """La planta no cuenta su inventario fisico: lo calcula para que el balance cuadre."""
    salida, _ = TRANSFORMACIONES["produccion_diaria"](
        _entrada([{"fecha": "2018-10-01", "stock_final": 890.0}]))
    assert salida["stock_final_es_calculado"].tolist() == [True]


def test_un_valor_que_no_es_numero_pasa_a_nulo_y_se_cuenta():
    salida, calidad = TRANSFORMACIONES["produccion_diaria"](
        _entrada([{"fecha": "2018-10-01", "produccion": 200.0},
                  {"fecha": "2018-10-02", "produccion": "no es un numero"}]))
    assert salida["produccion"].notna().sum() == 1
    assert calidad["produccion_valida"] == 0.5


def test_la_fecha_que_no_se_puede_convertir_queda_nula():
    salida, calidad = TRANSFORMACIONES["produccion_diaria"](
        _entrada([{"fecha": "2018-10-01"}, {"fecha": "no es una fecha"}]))
    assert salida["fecha"].notna().sum() == 1
    assert calidad["fecha_valida"] == 0.5


def test_la_calidad_informa_el_residuo_que_mira_s11():
    """S11 busca los dias en que el residuo del balance es exactamente cero."""
    salida, calidad = TRANSFORMACIONES["produccion_diaria"](
        _entrada([{"fecha": "2018-10-01", "stock_inicial": 1000.0, "produccion": 200.0,
                   "ventas": 300.0, "bonificaciones": 10.0, "stock_final": 890.0},
                  {"fecha": "2018-10-02", "stock_inicial": 890.0, "produccion": 100.0,
                   "ventas": 200.0, "bonificaciones": 0.0, "stock_final": 700.0}]))
    # El primero cuadra exacto (1000 + 200 - 300 - 10 = 890); el segundo no (790 != 700).
    assert calidad["dias_con_residuo_cero"] == 1
    assert calidad["dias_completos"] == 2
    assert len(salida) == 2                      # los dos se conservan


def test_una_fila_sin_fecha_valida_no_cuenta_como_dia():
    """La hoja real trae una fila de cierre sin fecha: no es un dia del balance.

    Si contara, `dias_con_residuo_cero` diria 32 sobre un mes de 31 y la cifra que
    publica S11 saldria mal.
    """
    salida, calidad = TRANSFORMACIONES["produccion_diaria"](
        _entrada([{"fecha": "2018-10-01", "stock_inicial": 1000.0, "produccion": 200.0,
                   "ventas": 300.0, "bonificaciones": 10.0, "stock_final": 890.0},
                  {"fecha": "TOTAL", "stock_inicial": 1000.0, "produccion": 200.0,
                   "ventas": 300.0, "bonificaciones": 10.0, "stock_final": 890.0}]))
    assert calidad["dias_completos"] == 1
    assert calidad["dias_con_residuo_cero"] == 1
    assert len(salida) == 2                      # la fila se conserva, con su fecha nula
