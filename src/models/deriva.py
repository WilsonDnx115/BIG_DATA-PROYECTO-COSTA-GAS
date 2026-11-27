"""Deriva de las variables del modelo S12, medida con PSI (commit A15).

El modelo se entrena con un periodo y después puntúa facturas que no se parecen a
las de entonces. El PSI (Population Stability Index) compara, variable por variable,
cómo se repartían los valores en el entrenamiento y cómo se reparten ahora:

    PSI = Σ (p_obs − p_esp) · ln(p_obs / p_esp)

La lectura habitual es < 0.1 estable, 0.1 a 0.2 vigilar y > 0.2 reentrenar; el umbral
vive en `PSI_UMBRAL` y no se escribe aquí.

Dos cuidados que cambian el resultado:

* **Los cortes son los del entrenamiento.** Si se recalculan con los datos nuevos,
  cada muestra queda repartida en deciles por construcción y el PSI sale casi cero
  siempre: no mediría nada. Por eso `deciles_entrenamiento()` se guarda junto al modelo.
* **Con pocas facturas el PSI salta por ruido.** Debajo de `PSI_MIN_OBS` no se informa
  un número que invitaría a reentrenar sin motivo: se devuelve «insuficiente».

Uso:
    cortes = deciles_entrenamiento(pdf_entrenamiento, VARIABLES)   # se guarda con el modelo
    resultado = evaluar(pdf_nuevas, cortes)
    if requiere_reentreno(resultado): ...
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config

# Evita dividir entre cero y log(0) cuando un decil se queda sin observaciones.
# Es el convenio habitual: se cuenta como si hubiera una fracción mínima, no como cero.
EPSILON = 1e-6

ESTADO_OK = "ok"
ESTADO_INSUFICIENTE = "insuficiente"


def _limpiar(valores) -> np.ndarray:
    v = pd.to_numeric(pd.Series(valores), errors="coerce").to_numpy(dtype="float64")
    return v[np.isfinite(v)]


def deciles_entrenamiento(pdf: pd.DataFrame, variables, bins: int | None = None) -> dict:
    """Cortes y reparto esperado de cada variable, tal como estaban al entrenar.

    Se guarda junto al modelo. Los extremos quedan abiertos (−inf, +inf) para que un
    valor nuevo fuera del rango del entrenamiento caiga en el primer o el último tramo
    en vez de quedarse fuera y desaparecer del cálculo.
    """
    bins = config.PSI_BINS if bins is None else bins
    cortes = {}
    for var in variables:
        v = _limpiar(pdf[var])
        if v.size == 0:
            cortes[var] = {"cortes": [], "esperado": [], "n": 0}
            continue
        bordes = np.unique(np.quantile(v, np.linspace(0, 1, bins + 1)))
        bordes = np.concatenate(([-np.inf], bordes[1:-1], [np.inf])) if bordes.size > 2 \
            else np.array([-np.inf, np.inf])
        cortes[var] = {"cortes": bordes.tolist(),
                       "esperado": _proporciones(v, bordes).tolist(),
                       "n": int(v.size)}
    return cortes


def _proporciones(valores, cortes) -> np.ndarray:
    """Fracción de los valores que cae en cada tramo. Suma 1."""
    v = _limpiar(valores)
    bordes = np.asarray(cortes, dtype="float64")
    if v.size == 0 or bordes.size < 2:
        return np.zeros(max(bordes.size - 1, 1))
    conteo = np.histogram(v, bins=bordes)[0].astype("float64")
    return conteo / conteo.sum()


def psi(esperado, observado, cortes) -> float:
    """PSI entre dos muestras de valores crudos, usando los cortes del entrenamiento."""
    p_esp = np.clip(_proporciones(esperado, cortes), EPSILON, None)
    p_obs = np.clip(_proporciones(observado, cortes), EPSILON, None)
    if p_esp.size != p_obs.size:
        raise ValueError("el esperado y el observado no tienen el mismo número de tramos")
    return float(np.sum((p_obs - p_esp) * np.log(p_obs / p_esp)))


def _psi_contra_esperado(info: dict, observado) -> float:
    p_esp = np.clip(np.asarray(info["esperado"], dtype="float64"), EPSILON, None)
    p_obs = np.clip(_proporciones(observado, info["cortes"]), EPSILON, None)
    return float(np.sum((p_obs - p_esp) * np.log(p_obs / p_esp)))


def evaluar(df_nuevas: pd.DataFrame, cortes: dict, minimo: int | None = None) -> dict:
    """PSI de cada variable contra el entrenamiento, o «insuficiente» si hay pocas filas.

    No se informa un PSI calculado sobre menos de `PSI_MIN_OBS` facturas: con esa
    cantidad el índice se mueve por el azar del muestreo y no por una deriva real.
    """
    minimo = config.PSI_MIN_OBS if minimo is None else minimo
    n = int(len(df_nuevas))
    if n < minimo:
        return {"estado": ESTADO_INSUFICIENTE, "n": n, "minimo": minimo,
                "motivo": f"{n} facturas nuevas, se necesitan {minimo}"}

    valores, faltantes = {}, []
    for var, info in cortes.items():
        if var not in df_nuevas.columns or not info["cortes"]:
            faltantes.append(var)
            continue
        valores[var] = round(_psi_contra_esperado(info, df_nuevas[var]), 6)

    con_deriva = sorted(v for v, p in valores.items() if p > config.PSI_UMBRAL)
    return {"estado": ESTADO_OK, "n": n, "minimo": minimo, "umbral": config.PSI_UMBRAL,
            "psi": valores, "variables_con_deriva": con_deriva,
            "variables_sin_cortes": faltantes}


def requiere_reentreno(resultado: dict) -> bool:
    """True solo si se pudo medir y alguna variable pasó el umbral.

    «Insuficiente» no es motivo para reentrenar: significa que todavía no se sabe.
    """
    return resultado.get("estado") == ESTADO_OK and bool(resultado.get("variables_con_deriva"))
