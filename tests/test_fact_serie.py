"""fact_serie (FR05): el detector llevado a Gold, por entidad y periodo.

Datos de prueba sintéticos (no son de la empresa): 8 unidades de reparto y 4 cisternas
con 18 meses, y una unidad con un faltante de 3 % desde el mes 8.
"""
import sys

import numpy as np
import pandas as pd
import pytest

from src.glue import fact_serie

UMBRAL = {"h": 8.0}   # umbral de prueba; en producción sale de detector.calibrar_con_escenario_a()


def unidad_mes(faltante=0.03, desde=8, meses=18, semilla=3):
    rng = np.random.default_rng(semilla)
    filas = []
    for rol, n in (("reparto", 8), ("transporte", 4)):
        for u in range(n):
            for m in range(meses):
                anio, mes = 2020 + m // 12, m % 12 + 1
                kg = 10_000 * (1 + u / 4) * (1 + 0.1 * np.sin(m / 2)) * (1 + rng.normal(0, 0.005))
                if faltante and rol == "reparto" and u == 0 and m >= desde:
                    kg *= 1 - faltante
                vendidos, transportados = (kg, 0.0) if rol == "reparto" else (0.0, kg * 5)
                filas.append((f"{rol[:3].upper()}{u}", rol, anio, mes, vendidos, transportados, 500.0, 900.0))
    return pd.DataFrame(filas, columns=["unidad_id", "rol", "anio", "mes", "kg_vendidos", "kg_transportados",
                                        "gasto_combustible", "gasto_total"])


def test_entrada_mensual_usa_el_kg_de_cada_rol():
    e = fact_serie.unidades_mes_pandas(unidad_mes(faltante=0))
    rep = e[e.entidad_id == "REP0"].valor
    tra = e[e.entidad_id == "TRA0"].valor
    assert (rep > 0).all() and (tra > 40_000).all()            # transporte usa kg transportados
    assert set(e.granularidad) == {"mes"} and set(e.grupo) == {"reparto", "transporte"}


def test_serie_mensual_marca_el_faltante_y_tiene_las_columnas_de_gold():
    serie = fact_serie.serie_pandas(fact_serie.unidades_mes_pandas(unidad_mes()), UMBRAL)
    assert list(serie.columns) == fact_serie.COLUMNAS
    rojas = serie[serie.estado == "rojo"]
    assert set(rojas.entidad_id) == {"REP0"}
    inicio = rojas.periodo_inicio.dropna().iloc[0]
    assert pd.Timestamp(inicio) >= pd.Timestamp("2020-07-01")    # el faltante empieza en el mes 9 (set-2020)
    assert serie.loc[serie.entidad_id == "REP0", "kg_acumulados"].max() > 0


def test_cada_entidad_tiene_su_serie_completa_y_ordenada():
    serie = fact_serie.serie_pandas(fact_serie.unidades_mes_pandas(unidad_mes(faltante=0)), UMBRAL)
    for _, g in serie.groupby("entidad_id"):
        meses = pd.to_datetime(g.sort_values("periodo").periodo)
        assert len(meses) == 18 and (meses.diff().dropna().dt.days.between(28, 31)).all()


def test_contiene_las_columnas_que_lee_el_semaforo():
    from tests.test_vistas_sql import COLUMNAS_GOLD

    assert set(COLUMNAS_GOLD["fact_serie"]) <= set(fact_serie.COLUMNAS)


def _ventas():
    filas = []
    for semana in range(10):
        for placa, vendedor, cliente in (("ABC123", "v1", "c1"), ("XYZ789", "v2", "c2"), ("ABC123", "v3", "c3")):
            fecha = pd.Timestamp("2020-01-06") + pd.Timedelta(weeks=semana, days=2)
            filas.append((fecha, placa, True, 100.0, cliente, vendedor))
        filas.append((pd.Timestamp("2020-01-07") + pd.Timedelta(weeks=semana), "ABC123", False, 999.0, "c1", "v1"))
    return pd.DataFrame(filas, columns=["fecha", "placa_norm", "es_glp", "kg", "cliente_id", "vendedor_hash"])


def test_serie_semanal_solo_glp_y_por_lunes():
    e = fact_serie.unidades_semana_pandas(_ventas())
    abc = e[e.entidad_id == "ABC123"]
    assert (abc.valor == 200.0).all()                           # el artículo que no es GLP no suma
    assert (pd.to_datetime(abc.periodo).dt.dayofweek == 0).all() and len(abc) == 10


def test_baja_a_vendedor_y_cliente_solo_en_unidades_marcadas():
    marcadas = pd.DataFrame({"entidad_id": ["ABC123", "XYZ789"], "estado": ["ambar", "verde"]})
    e = fact_serie.bajar_a_vendedor_y_cliente(_ventas(), marcadas)
    assert set(e[e.entidad_tipo == "vendedor"].entidad_id) == {"v1", "v3"}
    assert set(e[e.entidad_tipo == "cliente"].entidad_id) == {"c1", "c3"}
    assert fact_serie.bajar_a_vendedor_y_cliente(_ventas(), marcadas.assign(estado="verde")).empty


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Spark local en Windows no levanta los workers de Python (lo arregla WR19)")
def test_construir_en_spark_igual_que_en_pandas(spark):
    entrada = fact_serie.unidades_mes_pandas(unidad_mes())
    esperado = fact_serie.serie_pandas(entrada, UMBRAL)
    obtenido = fact_serie.construir(spark.createDataFrame(entrada), UMBRAL)
    rojas = {r["entidad_id"] for r in obtenido.filter(obtenido.estado == "rojo").select("entidad_id").take(100)}
    assert rojas == set(esperado.loc[esperado.estado == "rojo", "entidad_id"])
    assert obtenido.count() == len(esperado)
