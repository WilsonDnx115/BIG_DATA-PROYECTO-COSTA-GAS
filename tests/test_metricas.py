"""Métricas del clasificador S12 (FR08). Datos de prueba sintéticos."""
import numpy as np
import pandas as pd
import pytest

from src.models import metricas


def test_precision_y_recall_sin_dividir_por_cero():
    assert metricas.precision_recall(8, 2, 4) == {"precision": 0.8, "recall": pytest.approx(8 / 12)}
    assert metricas.precision_recall(0, 0, 3)["precision"] is None


def test_matriz_igual_a_la_de_la_evaluacion():
    from src.models import mllib

    prob = [0.9, 0.8, 0.7, 0.3, 0.2]
    y = [1, 1, 0, 1, 0]
    pred = [int(p >= 0.75) for p in prob]
    assert metricas.matriz_confusion(y, pred) == mllib.matriz(list(zip(prob, y)), 0.75)


def test_precision_promedio_de_control():
    assert metricas.precision_promedio([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)
    # orden: 1, 0, 1 → (0.5 − 0)·1 + (1 − 0.5)·(2/3)
    assert metricas.precision_promedio([1, 0, 1], [0.9, 0.5, 0.1]) == pytest.approx(0.5 + 0.5 * 2 / 3)
    assert metricas.precision_promedio([0, 0], [0.4, 0.1]) is None


def _puntuado(spark, y, prob):
    """DataFrame como el que deja el clasificador: etiqueta y vector de probabilidades."""
    from pyspark.ml.functions import array_to_vector
    from pyspark.sql import functions as F

    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    pdf = pd.DataFrame({"etiqueta_s12": np.asarray(y, dtype=float), "p": np.asarray(prob, dtype=float)})
    df = spark.createDataFrame(pdf)
    return df.withColumn("probability", array_to_vector(F.array(F.lit(1.0) - F.col("p"), F.col("p"))))


def test_pr_auc_de_mllib(spark):
    assert metricas.pr_auc_mllib(_puntuado(spark, [1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1])) == pytest.approx(1.0)
    rng = np.random.default_rng(2)
    y = (rng.random(300) < 0.074).astype(int)            # 7.4 % de positivos, como S12
    prob = np.clip(0.3 * y + rng.random(300) * 0.7, 0, 1)
    valor = metricas.pr_auc_mllib(_puntuado(spark, y, prob))
    assert 0 < valor <= 1


def test_lectura_de_las_dos_medidas():
    r = metricas.lectura_pr_auc(0.62, 0.55)
    assert r["conservadora"] == "precision_promedio" and r["diferencia"] == pytest.approx(0.07)
    assert metricas.lectura_pr_auc(0.5, None)["conservadora"] is None


def test_bootstrap_intervalo():
    perfecto = metricas.bootstrap_precision([1] * 10 + [0] * 10, [1] * 10 + [0] * 10, n=200)
    assert (perfecto["precision"], perfecto["li"], perfecto["ls"]) == (1.0, 1.0, 1.0)
    y, pred = metricas.pares_desde_matriz(tp=21, fp=9, fn=10, tn=200)
    b = metricas.bootstrap_precision(y, pred, n=500)
    assert b["precision"] == pytest.approx(0.7) and b["li"] < 0.7 < b["ls"]
    assert b["remuestreos_validos"] == 500


def test_acumular_meses_de_la_evaluacion_hacia_adelante():
    ev = pd.DataFrame([
        {"mes": "2022-08", "estado": "evaluado", "tp": 3, "fp": 1, "fn": 1, "tn": 40},
        {"mes": "2022-09", "estado": "evaluado", "tp": 4, "fp": 2, "fn": 2, "tn": 38},
        {"mes": "2022-10", "estado": "no_evaluable_entrenamiento_sin_dos_clases"},
    ])
    r = metricas.acumular(ev, n=300)
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (7, 3, 3, 78)
    assert r["precision"] == pytest.approx(0.7) and r["cumple_meta_precision"] is True
    assert r["meses_evaluados"] == 2 and r["meses_no_evaluados"][0]["mes"] == "2022-10"


def test_comparacion_con_la_regla_s2_s6():
    alertas = pd.DataFrame({"senal": ["S2", "S6", "S9"], "factura_id": ["A", "B", "C"]})
    facturas = pd.Series(["A", "B", "C", "D"])
    regla = metricas.regla_s2_s6(facturas, alertas)
    assert regla.tolist() == [1, 1, 0, 0]
    c = metricas.comparar_con_regla(y=[1, 0, 1, 0], pred_modelo=[1, 0, 1, 0], pred_regla=regla)
    assert c["modelo"]["precision"] == 1.0 and c["regla_s2_s6"]["precision"] == 0.5
    assert c["modelo_supera_a_la_regla"] is True
