"""Clasificador S12 en MLlib (FR06).

Facturas sintéticas de prueba (no son de la empresa): la discrepancia aparece sobre todo
cuando el precio por kg se aleja de la mediana del proveedor, para comprobar que el modelo
aprende esa relación. Spark recibe los datos por Arrow; MLlib corre en la JVM.
"""
import numpy as np
import pandas as pd
import pytest

from src.models import mllib


def facturas(n=300, semilla=8):
    rng = np.random.default_rng(semilla)
    sobreprecio = rng.normal(0, 0.04, n)
    etiqueta = (sobreprecio > 0.05).astype(float)
    etiqueta[rng.random(n) < 0.03] = 1.0                      # algo de ruido en la etiqueta
    df = pd.DataFrame({
        "factura_id": [f"F{i}" for i in range(n)],
        "proveedor_id": rng.choice(["PETROPERU", "SOLGAS", "PLUSPETROL"], n),
        "mes": rng.integers(1, 13, n),
        "kg": rng.uniform(5_000, 30_000, n),
        "usd_kg_vs_mediana": sobreprecio,
        "desvio_tc": np.abs(rng.normal(0, 0.005, n)),
        "flag_scop_duplicado": rng.integers(0, 2, n),
        "ratio_carga_capacidad": np.nan,
        "etiqueta_s12": etiqueta,
        "madura": True,
    })
    df.loc[: n // 10, "usd_kg_vs_mediana"] = np.nan             # primeras facturas sin mediana previa
    df.loc[: 5, "ratio_carga_capacidad"] = 0.9                  # capacidad conocida en pocas
    df.loc[n - 20:, "madura"] = False                           # recientes: no entrenan
    return df


@pytest.fixture()
def datos(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return spark.createDataFrame(facturas())


def test_faltantes_con_centinela_y_marca(datos):
    p = mllib.preparar_variables(datos)
    fila = p.filter(p.factura_id == "F0").take(1)[0]
    assert fila["usd_kg_vs_mediana"] == mllib.CENTINELA and fila["usd_kg_vs_mediana_conocido"] == 0.0
    otra = p.filter(p.factura_id == "F200").take(1)[0]
    assert otra["usd_kg_vs_mediana_conocido"] == 1.0
    assert p.filter(p.usd_kg_vs_mediana.isNull()).count() == 0


def test_peso_de_clase_equilibra_las_dos_clases(datos):
    p = mllib.pesos_clase(mllib.preparar_variables(datos))
    suma = {r["etiqueta_s12"]: r["s"] for r in p.groupBy("etiqueta_s12").sum("peso")
            .withColumnRenamed("sum(peso)", "s").take(2)}
    assert suma[0.0] == pytest.approx(suma[1.0])                # cada clase pesa la mitad del total


def test_solo_entrenan_las_etiquetas_maduras(datos):
    assert mllib.conjunto_de_entrenamiento(datos).count() == 280


def test_random_forest_aprende_el_sobreprecio(datos):
    modelo = mllib.entrenar_clasificador_s12(datos)
    bosque = modelo.stages[-1]
    assert bosque.getNumTrees == 100 and bosque.getOrDefault("maxDepth") == 6
    imp = mllib.importancias(modelo)
    assert len(imp) == len(mllib.columnas_de_entrada()) + 1
    assert next(iter(imp)) == "usd_kg_vs_mediana"              # la variable que manda en estos datos
    puntuado = modelo.transform(mllib.preparar_variables(datos))
    assert {"probability", "prediction"} <= set(puntuado.columns)


def test_referencias_logistica_y_arbol(datos):
    ref = mllib.entrenar_referencias(datos)
    assert ref["logistica"].stages[-1].getOrDefault("elasticNetParam") == 0.0   # L-BFGS
    texto = mllib.reglas(ref["arbol"])
    assert "usd_kg_vs_mediana" in texto and "feature " not in texto
    assert ref["arbol"].stages[-1].depth <= 3


def test_proveedor_nuevo_no_rompe_la_puntuacion(spark, datos):
    modelo = mllib.entrenar_clasificador_s12(datos)
    nueva = facturas(n=5).assign(proveedor_id="PROVEEDOR_NUEVO")
    puntuado = modelo.transform(mllib.preparar_variables(spark.createDataFrame(nueva)))
    assert puntuado.count() == 5
