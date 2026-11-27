"""WR03: las interfaces del WP 0.8 armadas en Spark.

La prueba que pide el commit: cada interfaz pasa `src.signals.contratos.validar`
en pandas sobre una muestra. Eso es lo que cierra el circulo, porque `validar` es
el mismo juez que usan las senales cuando leen el lago en pandas: si Spark
entrega una columna con otro nombre, otro grano o una fecha invalida, falla aqui
y no en la corrida de Glue.

La muestra se saca con `take()`, nunca con `collect()`.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.glue import interfaces
from src.signals import contratos


def muestra(df, n: int = 20) -> pd.DataFrame:
    """Las primeras n filas en pandas, sin traer la tabla entera al driver."""
    return pd.DataFrame([f.asDict() for f in df.take(n)])


# --- lo que se puede comprobar sin Spark --------------------------------------

def test_las_columnas_salen_del_contrato_y_no_de_una_lista_a_mano():
    for nombre in interfaces.DISPONIBLES:
        assert interfaces.columnas(nombre) == list(contratos.ENTRADAS[nombre][1])


def test_solo_se_declaran_disponibles_las_interfaces_que_tienen_fuente():
    """`unidad_mes` espera el contrato de gastos y `produccion` no esta cubierta."""
    assert set(interfaces.DISPONIBLES) < set(contratos.ENTRADAS)
    assert set(contratos.ENTRADAS) - set(interfaces.DISPONIBLES) == {"unidad_mes", "produccion"}


def test_la_fuente_del_tipo_de_cambio_es_la_del_extractor():
    from src.glue import externos_job

    assert "bcrp" in externos_job.FUENTES
    assert interfaces.FORMATO_FECHA_BCRP == "dd.MMM.yy"


# --- las interfaces armadas de verdad (necesitan Spark) -----------------------

FILAS_COMPRAS = [
    # proveedor, serie, numero, fecha, scop, kg, usd, tc, placa
    ("PETROPERU SA", "F001", "0000123", "2020-03-02", "SCOP-1", 9000.0, 4500.0, 3.45, "T1A111"),
    ("petroperu  sa", "f001", "124", "2020-03-09", "", 8000.0, 4000.0, 3.47, "T2B222"),
    ("ZETA GAS", "E002", "7", "2020-04-01", "SCOP-2", 0.0, 10.0, 3.50, None),
]
ESQUEMA_COMPRAS = ("proveedor string, serie string, numero string, fecha_factura date, "
                   "nro_scop string, kg double, monto_usd double, tipo_cambio double, "
                   "placa_norm string")

FILAS_UNIDADES = [
    ("T1A111", "CAMION CISTERNA", "TRANSPORTE DE GLP", "COSTA GAS", "VOLVO", 9000.0, True),
    ("T1A111", "CAMION CISTERNA", "TRANSPORTE DE GLP", "COSTA GAS", "VOLVO", 9000.0, True),
    ("T2B222", "CAMIONETA", "REPARTO", "COSTA GAS", "TOYOTA", 1000.0, False),
    (None, "CAMIONETA", "REPARTO", "COSTA GAS", "TOYOTA", 1000.0, False),
]
ESQUEMA_UNIDADES = ("placa_norm string, clase string, uso string, empresa string, "
                    "marca string, capacidad_glp_kg double, traslada_gas boolean")


@pytest.fixture()
def compras_silver(spark):
    filas = [(p, s, n, pd.Timestamp(f).date(), sc, kg, usd, tc, pl)
             for p, s, n, f, sc, kg, usd, tc, pl in FILAS_COMPRAS]
    return spark.createDataFrame(filas, ESQUEMA_COMPRAS)


@pytest.fixture()
def unidades_silver(spark):
    return spark.createDataFrame(FILAS_UNIDADES, ESQUEMA_UNIDADES)


def test_la_interfaz_de_compras_pasa_el_contrato(compras_silver):
    df = interfaces.compras(compras_silver)

    validada = contratos.validar(muestra(df), "compras")
    assert set(interfaces.columnas("compras")) <= set(validada.columns)


def test_dos_facturas_del_mismo_proveedor_no_colapsan_en_una_llave(compras_silver):
    """`F001-123` y `f001-124` son dos documentos; el grano del contrato lo exige."""
    df = muestra(interfaces.compras(compras_silver))

    assert df.factura_id.nunique() == len(df) == 3


def test_el_precio_queda_nulo_cuando_los_kg_no_son_positivos(compras_silver):
    """Dividir por cero daria un precio infinito; el contrato prefiere el nulo."""
    df = muestra(interfaces.compras(compras_silver)).set_index("factura_id")
    sin_kg = df[df.kg == 0]

    assert len(sin_kg) == 1
    assert sin_kg.precio_usd_kg.isna().all()


def test_la_interfaz_de_unidades_pasa_el_contrato_y_tiene_una_fila_por_placa(unidades_silver):
    df = muestra(interfaces.unidades(unidades_silver))

    contratos.validar(df, "unidades")
    assert sorted(df.unidad_id) == ["T1A111", "T2B222"]       # la placa nula se descarta


def test_la_habilitacion_es_la_misma_que_la_de_dim_unidad(unidades_silver):
    """Si discrepan, la dimension y S7 contarian universos distintos."""
    from src.glue import dimensiones

    interfaz = muestra(interfaces.unidades(unidades_silver)).set_index("unidad_id")
    dim = muestra(dimensiones.dim_unidad(unidades_silver)).set_index("placa_norm")

    for placa in interfaz.index:
        assert bool(interfaz.habilitada[placa]) == bool(dim.habilitada_glp[placa])


def test_el_tipo_de_cambio_queda_a_un_valor_por_dia(spark, lago):
    """La extraccion baja ventanas que se solapan: la misma fecha llega dos veces."""
    from pathlib import Path

    from src.common import rutas

    destino = Path(rutas.asegurar_local("landing", "externo", "bcrp", "2020"))
    for nombre, periodos in (("a.json", ["02.Mar.20", "03.Mar.20"]),
                             ("b.json", ["03.Mar.20", "04.Mar.20"])):
        contenido = {"periods": [{"name": p, "values": ["3.45"]} for p in periodos]}
        (destino / nombre).write_text(json.dumps(contenido), encoding="utf-8")

    df = interfaces.tipo_cambio(spark)
    fechas = muestra(df)

    contratos.validar(fechas, "tc")
    assert len(fechas) == 3                                    # no 4: el 03 venia dos veces


def test_sin_extraccion_del_bcrp_la_interfaz_se_omite_en_vez_de_quedar_vacia(spark, lago,
                                                                             unidades_silver):
    """Un DataFrame vacio pasaria por una medicion de cero facturas fuera de tipo."""
    armadas = interfaces.construir(spark, {"unidades": unidades_silver})

    assert "tc" not in armadas
    assert set(armadas) == {"unidades"}
