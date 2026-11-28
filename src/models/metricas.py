"""Métricas del clasificador S12 (FR08; informe v16, 4.3 y Tablas 4.7 y 4.8e).

Con 77 discrepancias en 1 040 facturas, una precisión puntual engaña: con pocos casos
positivos puede variar mucho de una muestra a otra. Por eso se reporta con su intervalo
bootstrap (BOOTSTRAP_REMUESTREOS remuestreos, IC 95 %; la meta de la Tabla 4.7 pide un
límite inferior ≥ 0.50) y se agregan tres controles:

* **PR-AUC** con el evaluador de MLlib (principal, técnica del curso) y la precisión promedio
  de scikit-learn como control: resumen la curva de precisión y recall sin elegir umbral; con
  clases desbalanceadas son más honestas que el AUC ROC. Si difieren, se reporta cuál es la
  conservadora y por qué;
* **comparación con la regla simple S2 o S6**: si el modelo no supera a la regla, no se usa;
* **precision@k**, reutilizada del modelo base (`base_mad.precision_at_k`).

Todo corre en el driver sobre resúmenes pequeños (una fila por factura evaluada o la matriz
de cada mes de `mllib.evaluar_s12`), sin collect() de tablas grandes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config
from src.models.base_mad import precision_at_k  # noqa: F401  (se reexporta para el informe)


def precision_recall(tp: int, fp: int, fn: int) -> dict:
    """Precisión y recall de la clase positiva; None si el denominador es 0 (no se inventa un 0)."""
    marcadas, positivas = tp + fp, tp + fn
    return {"precision": tp / marcadas if marcadas else None,
            "recall": tp / positivas if positivas else None}


def matriz_confusion(y, pred) -> dict:
    """tp, fp, fn y tn a partir de etiquetas y predicciones 0/1."""
    y, pred = np.asarray(y, dtype=int), np.asarray(pred, dtype=int)
    return {"tp": int(((pred == 1) & (y == 1)).sum()), "fp": int(((pred == 1) & (y == 0)).sum()),
            "fn": int(((pred == 0) & (y == 1)).sum()), "tn": int(((pred == 0) & (y == 0)).sum())}


def pr_auc_mllib(puntuado, etiqueta: str = "etiqueta_s12", probabilidad: str = "probability") -> float:
    """PR-AUC principal: `BinaryClassificationEvaluator(metricName="areaUnderPR")` de MLlib.

    Es la técnica del curso (evaluadores de MLlib, S9 a S11) y corre repartida en el job de
    Glue sobre las facturas puntuadas. MLlib une los puntos de la curva de precisión y recall
    con rectas (regla trapezoidal); con clases desbalanceadas eso puede sobrestimar el área
    (Davis y Goadrich, 2006). Por eso se reporta junto a la precisión promedio como control.
    """
    from pyspark.ml.evaluation import BinaryClassificationEvaluator  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    evaluador = BinaryClassificationEvaluator(labelCol=etiqueta, rawPredictionCol=probabilidad,
                                              metricName="areaUnderPR")
    return float(evaluador.evaluate(puntuado.withColumn(etiqueta, F.col(etiqueta).cast("double"))))


def precision_promedio(y, prob) -> float | None:
    """Control de la PR-AUC: precisión promedio de scikit-learn (`average_precision_score`).

    Suma la precisión en cada umbral ponderada por el aumento de recall, sin interpolar, y es
    más conservadora que el área trapezoidal con clases desbalanceadas. scikit-learn ya está
    en el job de Glue (lo usan Isolation Forest y LOF). None si no hay positivos.
    """
    from sklearn.metrics import average_precision_score  # noqa: PLC0415

    y = np.asarray(y, dtype=int)
    if int(y.sum()) == 0:
        return None
    return float(average_precision_score(y, np.asarray(prob, dtype=float)))


def lectura_pr_auc(pr_auc_mllib_valor: float, precision_promedio_valor: float | None) -> dict:
    """Las dos medidas juntas, con cuál es la conservadora y cuánto difieren (para el informe)."""
    if precision_promedio_valor is None:
        return {"pr_auc_mllib": pr_auc_mllib_valor, "precision_promedio": None,
                "diferencia": None, "conservadora": None}
    diferencia = pr_auc_mllib_valor - precision_promedio_valor
    return {"pr_auc_mllib": pr_auc_mllib_valor, "precision_promedio": precision_promedio_valor,
            "diferencia": diferencia,
            "conservadora": "precision_promedio" if diferencia > 0 else "pr_auc_mllib"}


def bootstrap_precision(y, pred, n: int = config.BOOTSTRAP_REMUESTREOS,
                        semilla: int = config.SEMILLA) -> dict:
    """Precisión de la clase positiva con intervalo bootstrap percentil del 95 %.

    Se remuestrean facturas con reemplazo. Un remuestreo sin ninguna factura marcada no
    tiene precisión definida: no se cuenta y queda informado en `remuestreos_validos`.
    """
    y, pred = np.asarray(y, dtype=int), np.asarray(pred, dtype=int)
    punto = precision_recall(**{k: v for k, v in matriz_confusion(y, pred).items() if k != "tn"})["precision"]
    rng = np.random.default_rng(semilla)
    valores = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        marcadas = pred[i] == 1
        if marcadas.any():
            valores.append(float((y[i][marcadas] == 1).mean()))
    if not valores:
        return {"precision": punto, "li": None, "ls": None, "remuestreos_validos": 0}
    li, ls = np.percentile(valores, [2.5, 97.5])
    return {"precision": punto, "li": float(li), "ls": float(ls), "remuestreos_validos": len(valores)}


def pares_desde_matriz(tp: int, fp: int, fn: int, tn: int) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruye (etiqueta, predicción) por factura desde una matriz, para el bootstrap acumulado."""
    y = np.r_[np.ones(tp), np.zeros(fp), np.ones(fn), np.zeros(tn)].astype(int)
    pred = np.r_[np.ones(tp), np.ones(fp), np.zeros(fn), np.zeros(tn)].astype(int)
    return y, pred


def acumular(evaluacion_mensual: pd.DataFrame, n: int = config.BOOTSTRAP_REMUESTREOS) -> dict:
    """Suma las matrices de los meses evaluados de `mllib.evaluar_s12` (Tabla 4.7, hacia adelante).

    Solo cuentan los meses con estado «evaluado»; los demás se informan aparte con su motivo.
    """
    evaluados = evaluacion_mensual[evaluacion_mensual["estado"] == "evaluado"]
    total = {k: int(evaluados[k].sum()) for k in ("tp", "fp", "fn", "tn")}
    y, pred = pares_desde_matriz(**total)
    no_evaluados = (evaluacion_mensual.loc[evaluacion_mensual["estado"] != "evaluado", ["mes", "estado"]]
                    .to_dict("records"))
    return {**total, **precision_recall(total["tp"], total["fp"], total["fn"]),
            "bootstrap": bootstrap_precision(y, pred, n=n), "meses_evaluados": len(evaluados),
            "meses_no_evaluados": no_evaluados,
            "cumple_meta_precision": (lambda p: None if p is None else p >= config.META_PRECISION)(
                precision_recall(total["tp"], total["fp"], total["fn"])["precision"])}


def comparar_con_regla(y, pred_modelo, pred_regla) -> dict:
    """Modelo frente a la regla simple «S2 o S6» sobre las mismas facturas (Tabla 4.7).

    `pred_regla` es 1 si la factura disparó S2 o S6. Si el modelo no supera a la regla en
    precisión con un recall comparable, la regla es suficiente y así se reporta.
    """
    salida = {}
    for nombre, pred in (("modelo", pred_modelo), ("regla_s2_s6", pred_regla)):
        m = matriz_confusion(y, pred)
        salida[nombre] = {**m, **precision_recall(m["tp"], m["fp"], m["fn"])}
    pm, pr_ = salida["modelo"]["precision"], salida["regla_s2_s6"]["precision"]
    salida["modelo_supera_a_la_regla"] = None if pm is None or pr_ is None else pm > pr_
    return salida


def regla_s2_s6(facturas: pd.Series, alertas: pd.DataFrame) -> np.ndarray:
    """1 si la factura tiene una alerta S2 o S6 en `fact_alerta_base` (columna factura_id)."""
    marcadas = set(alertas.loc[alertas["senal"].isin(["S2", "S6"]), "factura_id"].astype(str))
    return facturas.astype(str).isin(marcadas).astype(int).to_numpy()
