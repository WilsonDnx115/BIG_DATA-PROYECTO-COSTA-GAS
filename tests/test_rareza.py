"""Detectores de rareza (FR10): Isolation Forest y LOF. Datos de prueba sintéticos."""
import sys

import numpy as np
import pandas as pd
import pytest

from src.models import rareza

COLS = ["kg", "usd_kg_vs_mediana", "desvio_tc", "flag_scop_duplicado"]


def facturas(n=300, raras=25, semilla=9):
    rng = np.random.default_rng(semilla)
    df = pd.DataFrame({"kg": rng.normal(20_000, 2_000, n), "usd_kg_vs_mediana": rng.normal(0, 0.02, n),
                       "desvio_tc": np.abs(rng.normal(0, 0.003, n)), "flag_scop_duplicado": 0.0,
                       "anio": rng.choice([2020, 2022, 2023], n), "etiqueta_s12": 0.0})
    idx = df.index[:raras]
    df.loc[idx, "usd_kg_vs_mediana"] = rng.normal(0.25, 0.03, raras)        # sobreprecio marcado
    df.loc[idx, "etiqueta_s12"] = 1.0
    return df.sample(frac=1, random_state=1).reset_index(drop=True)


def test_con_etiquetas_elige_por_precision_at_20():
    df = facturas()
    entreno, validacion = rareza.particion_factura(df)
    r = rareza.ajustar(entreno, validacion, COLS, etiqueta="etiqueta_s12")
    assert r["criterio"] == "precision@20 en la validación"
    assert len(r["tabla"]) == 2 * 2 * 3 + 3                    # rejilla de la Tabla 4.6b
    # En 2023 hay pocas raras: precision@20 no puede pasar de raras ÷ 20. La mejor se acerca a ese tope.
    tope = min(1.0, validacion["etiqueta_s12"].sum() / 20)
    assert r["tabla"]["precision@20"].max() >= 0.75 * tope
    assert r["nombre"] in ("isolation_forest", "lof")


def test_sin_etiquetas_usa_los_valores_de_los_autores():
    df = facturas()
    r = rareza.ajustar(df, df.drop(columns="etiqueta_s12"), COLS)
    assert r["nombre"] == "isolation_forest" and r["params"]["n_estimators"] == 100
    assert r["params"]["max_samples"] == 256 and "Liu" in r["criterio"]


def test_puntaje_alto_para_lo_raro_y_nulo_sin_variables():
    df = facturas(raras=10)
    r = rareza.ajustar(df, df, COLS)
    sin_kg = df.index[df.etiqueta_s12 == 0][0]
    df.loc[sin_kg, "kg"] = np.nan
    p = rareza.puntuar_pandas(r["modelo"], df, COLS)
    assert np.isnan(p.loc[sin_kg])
    top = df.assign(p=p).dropna(subset=["p"]).nlargest(20, "p")
    assert top["etiqueta_s12"].sum() >= 8                       # 8 de las 10 raras entre las 20 más raras


def test_particion_de_facturas():
    entreno, prueba = rareza.particion_factura(facturas())
    assert set(entreno.anio) == {2020, 2022} and set(prueba.anio) == {2023}


def test_pandemia_por_mes_y_exclusion_mensual():
    filas = [(f"U{u}", 2020, m, 10_000.0 * (1 + u / 10), 50.0 + u, u % 3) for u in range(8) for m in range(1, 13)]
    um = pd.DataFrame(filas, columns=["unidad_id", "anio", "mes", "kg_base_rol", "soles_comb_por_t", "n_senales"])
    um = rareza.preparar_unidad_mes(um)
    assert um.loc[um.mes == 2, "pandemia"].eq(0).all() and um.loc[um.mes.between(3, 12), "pandemia"].eq(1).all()
    p = rareza.fuera_de_pliegue_mensual(um, "isolation_forest", rareza.POR_DEFECTO["isolation_forest"],
                                        rareza.VARIABLES_UNIDAD_MES)
    assert p.notna().all() and len(p) == len(um)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Spark local en Windows no levanta los workers de Python (lo arregla WR19)")
def test_puntuar_en_spark_igual_que_en_pandas(spark):
    df = facturas()
    r = rareza.ajustar(df, df, COLS)
    esperado = rareza.puntuar_pandas(r["modelo"], df, COLS)
    obtenido = rareza.puntuar_spark(spark.createDataFrame(df), r["modelo"], COLS)
    valores = sorted(f["puntaje_rareza"] for f in obtenido.select("puntaje_rareza").take(1000))
    assert np.allclose(valores, sorted(esperado))
