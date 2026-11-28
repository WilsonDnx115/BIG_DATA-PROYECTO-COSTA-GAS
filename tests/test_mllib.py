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


# --- FR12 · puntuación al llegar la factura --------------------------------------------
class ModeloFijo:
    """Devuelve la probabilidad que trae la columna `_p`: así la prueba fija el resultado."""

    def transform(self, df):
        from pyspark.ml.functions import array_to_vector
        from pyspark.sql import functions as F

        return df.withColumn("probability", array_to_vector(F.array(1 - F.col("_p"), F.col("_p"))))


def test_puntuar_s12_con_el_umbral_del_vigente(spark, datos):
    nuevas = facturas(n=3).drop(columns=["etiqueta_s12", "madura"]).assign(_p=[0.4, 0.6, 0.5])
    p = mllib.puntuar_s12(spark.createDataFrame(nuevas), ModeloFijo(), umbral=0.5, version_modelo="s12-2023-01-01")
    filas = {r["factura_id"]: r for r in p.take(10)}
    assert set(p.columns) == {"factura_id", "probabilidad", "alerta_s12", "version_modelo"}
    assert (filas["F0"]["alerta_s12"], filas["F1"]["alerta_s12"], filas["F2"]["alerta_s12"]) == (0, 1, 1)
    assert filas["F1"]["version_modelo"] == "s12-2023-01-01"
    assert mllib.puntuar_s12(spark.createDataFrame(nuevas), ModeloFijo(), umbral=0.55,
                             version_modelo="v").filter("alerta_s12 = 1").count() == 1   # solo la de 0.6


def test_alertas_s12_con_el_contrato_de_fact_alerta(spark, datos):
    from src.common import schemas

    nuevas = facturas(n=2).drop(columns=["etiqueta_s12", "madura"]).assign(
        _p=[0.2, 0.9], fecha=pd.Timestamp("2023-03-10").date(), unidad_id="ABC123", codigo_scop="77")
    df = spark.createDataFrame(nuevas)
    a = mllib.alertas_s12(mllib.puntuar_s12(df, ModeloFijo(), 0.5, "s12-2023-03-01"), df)
    assert a.columns == schemas.CONTRATOS["fact_alerta_base"].columnas() + ["probabilidad"]
    (fila,) = a.take(5)
    assert (fila["factura_id"], fila["senal"], fila["tipo"]) == ("F1", "S12", "modelo")
    assert fila["puntaje"] == pytest.approx(0.9) and fila["probabilidad"] == pytest.approx(0.9)
    assert fila["motivo"] == "modelo_s12_s12-2023-03-01" and fila["valor_soles"] is None


def test_puntuar_s12_con_el_random_forest(spark, datos):
    modelo = mllib.entrenar_clasificador_s12(datos)
    nuevas = spark.createDataFrame(facturas(n=6, semilla=21).drop(columns=["etiqueta_s12", "madura"]))
    p = mllib.puntuar_s12(nuevas, modelo, umbral=0.5, version_modelo="v")
    assert p.count() == 6 and p.filter("probabilidad < 0 OR probabilidad > 1").count() == 0


# --- FR07 · evaluación hacia adelante -----------------------------------------------
def modelo_factura_sintetica(por_mes=40, semilla=4):
    """feb-2022 a jul-2023, como la ventana de S12; vence a los 30 días y madura a los 60."""
    rng = np.random.default_rng(semilla)
    filas = []
    for m in range(18):
        anio, mes = 2022 + (m + 1) // 12, (m + 1) % 12 + 1
        for i in range(por_mes):
            fecha = pd.Timestamp(anio, mes, 1) + pd.Timedelta(days=int(rng.integers(0, 28)))
            sobre = rng.normal(0, 0.04)
            filas.append({"factura_id": f"{anio}{mes:02d}-{i}", "proveedor_id": rng.choice(["P1", "P2", "P3"]),
                          "fecha": fecha.date(), "anio": anio, "mes": mes, "kg": float(rng.uniform(5e3, 3e4)),
                          "usd_kg_vs_mediana": sobre, "desvio_tc": abs(rng.normal(0, 0.005)),
                          "flag_scop_duplicado": int(rng.integers(0, 2)), "ratio_carga_capacidad": np.nan,
                          "etiqueta_s12": float(sobre > 0.04),
                          "fecha_madurez": (fecha + pd.Timedelta(days=60)).date(), "madura": True})
    return pd.DataFrame(filas)


@pytest.fixture()
def rapido(monkeypatch, spark):
    from src.common import config

    monkeypatch.setattr(config, "RF_ARBOLES", 10)   # solo para que la prueba corra rápido
    # Cada prueba activa Arrow por su cuenta: no depende de que otra lo haya hecho antes.
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")


def test_matriz_y_umbral():
    pares = [(0.9, 1), (0.8, 1), (0.7, 0), (0.3, 1), (0.2, 0), (0.1, 0)]
    assert mllib.matriz(pares, 0.75) == {"tp": 2, "fp": 0, "fn": 1, "tn": 3}
    # Precisión por umbral: 0.1 → 3/6, 0.2 → 3/5, 0.3 → 3/4 = 0.75, 0.7 → 2/3, 0.8 → 1, 0.9 → 1.
    # El menor umbral con precisión ≥ 0.70 es 0.3 (marca 4 facturas), no el más preciso.
    u = mllib.elegir_umbral(pares, meta=0.70)
    assert u["umbral"] == 0.3 and u["precision"] == 0.75 and u["recall"] == 1.0 and u["cumple_meta"]
    assert mllib.elegir_umbral(pares, meta=0.9)["umbral"] == 0.8
    # Si ningún umbral alcanza la meta, se toma el de mayor precisión y queda marcado.
    sin_meta = mllib.elegir_umbral([(0.9, 0), (0.5, 1), (0.1, 0)], meta=0.70)
    assert sin_meta["cumple_meta"] is False and sin_meta["umbral"] == 0.5 and sin_meta["precision"] == 0.5


def test_el_umbral_no_usa_etiquetas_que_no_se_conocian(spark, rapido):
    from pyspark.sql import functions as F

    mf = spark.createDataFrame(modelo_factura_sintetica())
    corte = mllib._primer_dia(2022, 10)
    prueba = mf.filter((F.col("anio") == 2022) & (F.col("mes") == 10))
    base = mllib.evaluar_corte(mf, corte, prueba)
    # Se invierten las etiquetas que maduran después del corte: el umbral no debe cambiar.
    invertidas = mf.withColumn("etiqueta_s12", F.when(F.col("fecha_madurez") >= F.lit(str(corte)).cast("date"),
                                                      1.0 - F.col("etiqueta_s12")).otherwise(F.col("etiqueta_s12")))
    otra = mllib.evaluar_corte(invertidas, corte, prueba)
    assert base["estado"] == "evaluado" and base["umbral"] == otra["umbral"]


def test_evaluacion_hacia_adelante_mes_a_mes(spark, rapido):
    mf = spark.createDataFrame(modelo_factura_sintetica())
    r = mllib.evaluar_s12(mf, inicio="2022-08", fin="2022-10")
    assert list(r["mes"]) == ["2022-08", "2022-09", "2022-10"]
    evaluados = r[r["estado"] == "evaluado"]
    assert len(evaluados) >= 2
    assert ((evaluados.tp + evaluados.fp + evaluados.fn + evaluados.tn) == evaluados.n_prueba).all()


def test_sin_meses_suficientes_no_se_evalua(spark, rapido):
    from pyspark.sql import functions as F

    mf = spark.createDataFrame(modelo_factura_sintetica())
    r = mllib.evaluar_corte(mf, mllib._primer_dia(2022, 4), mf.filter(F.col("mes") == 4))
    assert r["estado"] == "no_evaluable_sin_meses_suficientes"


def test_evaluacion_inicial_2022_frente_a_2023(spark, rapido):
    r = mllib.evaluar_2022_2023(spark.createDataFrame(modelo_factura_sintetica()))
    assert (r["n_entrenamiento"], r["n_validacion"], r["n_prueba"]) == (280, 160, 280)
    assert r["estado"] == "evaluado" and r["tp"] + r["fp"] + r["fn"] + r["tn"] == 280


# --- FR09 · regresión del combustible -----------------------------------------------
def unidad_mes_combustible(meses=12, semilla=6):
    """2020 sintético: 50 S/ por t en los dos roles, con un fijo distinto por rol y ruido de 3 %."""
    rng = np.random.default_rng(semilla)
    filas = []
    for rol, n, fijo in (("reparto", 10, 200.0), ("transporte", 4, 800.0)):
        for u in range(n):
            for mes in range(1, meses + 1):
                kg = float(rng.uniform(8_000, 40_000) * (5 if rol == "transporte" else 1))
                gasto = (fijo + 50.0 * kg / 1000) * (1 + rng.normal(0, 0.03))
                vend, trans = (kg, 0.0) if rol == "reparto" else (0.0, kg)
                filas.append((f"{rol[:3]}{u}", rol, 2020, mes, vend, trans, gasto, gasto * 1.5))
    filas.append(("rep_parada", "reparto", 2020, 5, 0.0, 0.0, 0.0, 0.0))          # sin volumen ni gasto
    filas.append(("rep_sin_venta", "reparto", 2020, 6, 0.0, 0.0, 300.0, 400.0))   # combustible sin volumen
    return pd.DataFrame(filas, columns=["unidad_id", "rol", "anio", "mes", "kg_vendidos", "kg_transportados",
                                        "gasto_combustible", "gasto_total"])


def test_regresion_recupera_los_soles_por_tonelada(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    r = mllib.regresion_combustible(spark.createDataFrame(unidad_mes_combustible()), rejilla=(0.0,))
    assert r["pliegues"] == 12                                    # exclusión mensual
    assert r["soles_por_t"] == pytest.approx(50.0, rel=0.05)      # coeficiente en S/ por t, sin escalar
    assert r["rmse"] < r["rmse_trivial"] and r["mejor_que_trivial"] is True
    assert r["n_no_evaluables"] == 2 and r["residuos"].count() == r["n_evaluables"] == 14 * 12
    assert "residuo_combustible" in r["residuos"].columns


def test_regresion_elige_el_regparam_de_menor_rmse(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    datos = spark.createDataFrame(unidad_mes_combustible(meses=4))
    r = mllib.regresion_combustible(datos, rejilla=(0.0, 50_000.0))   # un regParam enorme aplasta la pendiente
    assert r["reg_param"] == 0.0 and r["rmse_por_regparam"][0.0] < r["rmse_por_regparam"][50_000.0]


def test_la_rejilla_por_defecto_es_la_de_la_tabla_4_6b():
    from src.common import config

    assert config.REGRESION_REGPARAM == (0.0, 0.1, 0.3)
