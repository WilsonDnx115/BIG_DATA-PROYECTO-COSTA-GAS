"""Modelo definitivo: Isolation Forest frente a LOF (pasos 4.3.2 a 4.3.5).

* Partición temporal: ajuste 2016–2019, evaluación 2020 (piloto), estabilidad 2021–2024.
* RobustScaler (mediana/IQR) por el mismo motivo que el MAD del modelo base.
* Rejilla de la Tabla 4.6; elección por precision@20 en 2020; semilla fija.
* scikit-learn y no MLlib: la tabla unidad-mes es pequeña y MLlib no trae
  Isolation Forest (decisión en PLAN.md, sección B).
"""
from __future__ import annotations

import itertools

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler

from src.common import config
from src.models.base_mad import precision_at_k

REJILLA = {
    "isolation_forest": {"n_estimators": [100, 300], "max_samples": [64, 256],
                         "contamination": [0.02, 0.05]},
    "lof": {"n_neighbors": [10, 20, 35], "contamination": [0.02, 0.05]},
}


def particion_temporal(um: pd.DataFrame):
    p = config.ANIO_PILOTO
    return (um[um["anio"] < p], um[um["anio"] == p], um[um["anio"] > p])


def _modelo(nombre: str, params: dict):
    if nombre == "isolation_forest":
        est = IsolationForest(random_state=config.SEMILLA, **params)
    else:
        est = LocalOutlierFactor(novelty=True, **params)
    return make_pipeline(RobustScaler(), est)


def puntaje(modelo, X: pd.DataFrame) -> pd.Series:
    """Mayor = más anómalo (se invierte score_samples)."""
    return pd.Series(-modelo.score_samples(X), index=X.index)


def ajustar(um: pd.DataFrame, y: pd.Series, features: list[str], k: int = config.TOP_K) -> dict:
    um = um.dropna(subset=features)
    y = y.loc[um.index]
    entreno, piloto, estab = particion_temporal(um)
    resultados = []
    for nombre, rejilla in REJILLA.items():
        for combo in itertools.product(*rejilla.values()):
            params = dict(zip(rejilla.keys(), combo))
            m = _modelo(nombre, params).fit(entreno[features])
            p_piloto = puntaje(m, piloto[features])
            p_estab = puntaje(m, estab[features]) if len(estab) else pd.Series(dtype=float)
            resultados.append({
                "modelo": nombre, **params,
                f"precision@{k}_piloto": precision_at_k(p_piloto, y, k),
                f"precision@{k}_estabilidad": precision_at_k(p_estab, y, k) if len(estab) else None,
            })
    tabla = pd.DataFrame(resultados).sort_values(f"precision@{k}_piloto", ascending=False)
    mejor = {c: v for c, v in tabla.iloc[0].to_dict().items() if v == v}   # sin NaN de la otra rejilla
    params = {c: mejor[c] for c in REJILLA[mejor["modelo"]]}
    params = {c: (int(v) if float(v).is_integer() else float(v)) for c, v in params.items()}
    final = _modelo(mejor["modelo"], params).fit(entreno[features])
    um = um.assign(puntaje_modelo=puntaje(final, um[features]))
    return {"tabla": tabla, "mejor": mejor, "modelo": final, "puntuado": um}
