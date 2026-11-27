"""Métricas del clasificador S12 (FR08; informe v16, 4.3 y Tablas 4.7 y 4.8e).

Con 77 discrepancias en 1 040 facturas, una precisión puntual engaña: con pocos casos
positivos puede variar mucho de una muestra a otra. Por eso se reporta con su intervalo
bootstrap (BOOTSTRAP_REMUESTREOS remuestreos, IC 95 %; la meta de la Tabla 4.7 pide un
límite inferior ≥ 0.50) y se agregan tres controles:

* **PR-AUC** (precisión promedio): resume la curva de precisión y recall sin elegir umbral;
  con clases desbalanceadas es más honesta que el AUC ROC;
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


def pr_auc(y, prob) -> float | None:
    """Precisión promedio: Σ (Rₙ − Rₙ₋₁) · Pₙ recorriendo los umbrales de mayor a menor.

    Es la definición de precisión promedio (la misma que average_precision_score de
    scikit-learn), escrita aquí para no depender de la versión instalada en Glue.
    """
    y, prob = np.asarray(y, dtype=int), np.asarray(prob, dtype=float)
    positivas = int(y.sum())
    if positivas == 0:
        return None
    orden = np.argsort(-prob, kind="stable")
    y_ord, p_ord = y[orden], prob[orden]
    tp = np.cumsum(y_ord)
    ultimos = np.r_[np.flatnonzero(np.diff(p_ord) != 0), len(p_ord) - 1]  # un punto por umbral distinto
    precision = tp[ultimos] / (ultimos + 1)
    recall = tp[ultimos] / positivas
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


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
