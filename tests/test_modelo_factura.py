"""modelo_factura (FR01): etiqueta S12, madurez y variables a la fecha de la factura.

Facturas sintéticas de prueba (no son de la empresa). Spark recibe los datos por Arrow.
"""
import pandas as pd
import pytest

from src.glue import modelo_factura, senales_spark
from src.models import mllib


@pytest.fixture()
def sp(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return lambda pdf: spark.createDataFrame(pdf)


def _fechas(serie):
    return pd.to_datetime(serie).dt.date


def logistica():
    df = pd.DataFrame([
        # proveedor, serie, numero, scop, fecha, kg, monto_usd, tc, placa
        ("PETROPERU", "F001", "1", "111", "2022-03-01", 10_000.0, 6_000.0, 3.80, "ABC123"),   # coincide
        ("PETROPERU", "F001", "2", "111", "2022-03-05", 10_000.0, 6_000.0, 3.80, "ABC123"),   # kg distinto; SCOP repetido
        ("PETROPERU", "F001", "3", "333", "2022-03-10", 10_000.0, 6_600.0, 3.95, "ABC123"),   # solo logística; +10 % y T.C. alto
        ("SOLGAS", "F002", "7", "777", "2022-06-20", 8_000.0, 4_800.0, 3.80, "XYZ789"),       # coincide, vence hace poco
        ("SOLGAS", "F002", "8", "888", "2022-03-02", 8_000.0, 4_800.0, 3.80, "XYZ789"),       # kg desconocido
    ], columns=["proveedor", "serie", "numero", "nro_scop", "fecha_factura", "kg", "monto_usd",
                "tipo_cambio", "placa_norm"])
    df["fecha_factura"] = _fechas(df["fecha_factura"])
    return df


def tesoreria():
    df = pd.DataFrame([
        ("PETROPERU", "F001-1", 10_000.0, 0.60, "2022-03-20", "2022-03-31"),
        ("PETROPERU", "F001-2", 12_000.0, 0.60, "2022-03-25", "2022-04-04"),
        ("SOLGAS", "F002-7", 8_000.0, 0.60, None, "2022-07-20"),
        ("SOLGAS", "F002-8", None, 0.60, None, "2022-04-01"),
        ("SOLGAS", "F002-99", 5_000.0, 0.62, "2022-04-10", "2022-04-30"),               # solo tesorería
    ], columns=["proveedor", "documento", "kg", "usd_por_kg", "fecha_pago", "fecha_vence"])
    for c in ("fecha_pago", "fecha_vence"):
        df[c] = _fechas(df[c])
    return df


def _tabla(sp, fecha_corte="2022-07-31", con_tc=True, con_unidades=True):
    compras = senales_spark.normalizar_compras(sp(logistica()))
    tc = sp(pd.DataFrame({"fecha": _fechas(pd.Series(["2022-03-01", "2022-06-30"])), "tc_oficial": [3.80, 3.82]}))
    unidades = sp(pd.DataFrame({"placa_norm": ["ABC123", "XYZ789"], "capacidad_glp_kg": [12_500.0, 0.0]}))
    t = modelo_factura.construir(compras, sp(tesoreria()), fecha_corte,
                                 tc=tc if con_tc else None, unidades=unidades if con_unidades else None)
    return {r["factura_id"]: r for r in t.take(100)}


def test_clase_y_etiqueta_s12(sp):
    r = _tabla(sp)
    esperado = {"PETROPERU|F001|1": ("coincide", 0.0), "PETROPERU|F001|2": ("kg_distinto", 1.0),
                "PETROPERU|F001|3": ("solo_logistica", 1.0), "SOLGAS|F002|7": ("coincide", 0.0),
                "SOLGAS|F002|8": ("kg_desconocido", None), "SOLGAS|F002|99": ("solo_tesoreria", 1.0)}
    assert {k: (v["clase_s12"], v["etiqueta_s12"]) for k, v in r.items()} == esperado


def test_madurez_con_vencimiento_real_y_estimado(sp):
    r = _tabla(sp, fecha_corte="2022-07-31")
    assert r["PETROPERU|F001|1"]["madura"] is True                       # venció el 31/03 + 30 días
    assert r["SOLGAS|F002|7"]["madura"] is False                         # venció el 20/07: aún no maduró
    solo_log = r["PETROPERU|F001|3"]
    assert solo_log["vence_estimado"] is True
    # plazo medido de PETROPERU: mediana de 30 y 30 días → vence el 09/04
    assert str(solo_log["fecha_vence"]) == "2022-04-09" and solo_log["madura"] is True


def test_variables_a_la_fecha_de_la_factura(sp):
    r = _tabla(sp)
    assert r["PETROPERU|F001|1"]["usd_kg_vs_mediana"] is None            # primera factura del proveedor
    assert r["PETROPERU|F001|3"]["usd_kg_vs_mediana"] == pytest.approx(0.10)
    assert r["PETROPERU|F001|1"]["flag_scop_duplicado"] == 1 and r["PETROPERU|F001|3"]["flag_scop_duplicado"] == 0
    assert r["PETROPERU|F001|3"]["desvio_tc"] == pytest.approx(abs(3.95 - 3.80) / 3.80)   # último hábil anterior
    assert r["PETROPERU|F001|1"]["ratio_carga_capacidad"] == pytest.approx(0.8)
    assert r["SOLGAS|F002|7"]["ratio_carga_capacidad"] is None           # capacidad 0: no se divide


def test_sin_tc_ni_unidades_quedan_nulos(sp):
    r = _tabla(sp, con_tc=False, con_unidades=False)
    assert all(v["desvio_tc"] is None and v["ratio_carga_capacidad"] is None for v in r.values())


def test_sirve_al_clasificador_y_a_la_vista_del_kpi3(sp):
    from tests.test_vistas_sql import COLUMNAS_GOLD

    compras = senales_spark.normalizar_compras(sp(logistica()))
    t = modelo_factura.construir(compras, sp(tesoreria()), "2022-07-31")
    assert set(COLUMNAS_GOLD["modelo_factura"]) <= set(t.columns)
    necesarias = set(mllib.VARIABLES_NUMERICAS) | {"proveedor_id", "etiqueta_s12", "madura"}
    assert necesarias <= set(t.columns)
    entrenamiento = mllib.conjunto_de_entrenamiento(t)
    assert entrenamiento.count() == 4                                     # maduras y con etiqueta
