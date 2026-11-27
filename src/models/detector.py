"""Detector de desvíos persistentes: CUSUM y EWMA frente a los pares (informe v16, 4.3 y Figura 4.5).

Un faltante de 2 % en un periodo se confunde con el ruido; lo que lo delata es que se
repite hacia el mismo lado. Por eso se acumula:

1. **Valor esperado frente a los pares.** Cada entidad (unidad, vendedor, cliente o
   proveedor) se compara con el resto de su grupo en el mismo periodo, no con su propio
   pasado: una caída que afecta a todos (estacionalidad, cuarentena) no es un desvío.
   esperado = participación de la entidad × mediana de sus pares en ese periodo. La
   participación es la mediana de sus cocientes **anteriores** (sin mirar el futuro) y
   exige DETECTOR_PERIODOS_BASE periodos propios.
2. **Desvío estandarizado.** z = (real − esperado) ÷ esperado ÷ σ, con σ = 1.4826 × MAD de
   los desvíos relativos del grupo (escala robusta).
3. **CUSUM de un solo lado (faltante)** con k y h, y **EWMA** con λ y L (Montgomery;
   valores en config.py y ADR 0028). El CUSUM confirma (rojo); el EWMA avisa antes (ámbar).
4. **Punto de cambio:** el periodo siguiente al último en que el CUSUM estaba en 0.

Los errores de digitación corregidos se neutralizan antes con
`src/quality/redigitados.compensar` sobre el desvío con signo (`kg_error`), como pide su
autora: un par +X/−X no es un desvío; un error suelto sí se deja, porque puede ser lo que
hay que detectar.

Funciones puras en pandas; el job de Gold las aplica por entidad con applyInPandas
(`src/glue/fact_serie.py`). Una entidad o un grupo sin variación (MAD 0) queda
«no_evaluable»: no se inventa una escala.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config
from src.quality.redigitados import compensar

ESTADOS = ("verde", "ambar", "rojo", "no_evaluable")


# --- 1. Valor esperado ---------------------------------------------------------
def neutralizar_redigitados(df: pd.DataFrame, entidad: str, valor: str, periodo: str,
                            error: str = "kg_error") -> pd.DataFrame:
    """Quita del valor el efecto de los errores de digitación que alguien corrigió.

    Si la tabla trae la columna `error` (desvío de digitación con signo), los pares
    +X/−X que `compensar` empareja se restan del valor; los errores sueltos se quedan.
    Sin esa columna, el valor pasa tal cual (`<valor>_corregido` = `<valor>`).
    """
    salida = df.copy()
    corregido = f"{valor}_corregido"
    if error not in salida.columns:
        salida[corregido] = pd.to_numeric(salida[valor], errors="coerce")
        salida["redigitado"] = False
        return salida
    salida = compensar(salida, entidad=entidad, valor=error, periodo=periodo)
    quitar = salida[error].fillna(0) - salida[f"{error}_compensado"].fillna(0)
    salida[corregido] = pd.to_numeric(salida[valor], errors="coerce") - quitar
    return salida


def esperado_por_pares(df: pd.DataFrame, entidad: str, valor: str, periodo: str, grupo: str,
                       periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> pd.DataFrame:
    """Agrega `mediana_pares`, `participacion`, `valor_esperado` y `desvio_rel`.

    mediana_pares: mediana del grupo en el periodo, sin la propia entidad.
    participacion: mediana de los cocientes valor ÷ mediana_pares de los periodos
    ANTERIORES de la entidad; nula hasta tener `periodos_base` de ellos.
    desvio_rel = (valor − esperado) ÷ esperado.
    """
    d = df.copy()
    d["_v"] = pd.to_numeric(d[valor], errors="coerce").astype(float)

    def _pares(g):
        v = g["_v"].to_numpy()
        med = np.full(len(v), np.nan)
        for i in range(len(v)):
            otros = np.delete(v, i)
            otros = otros[np.isfinite(otros)]
            if otros.size:
                med[i] = np.median(otros)
        return pd.Series(med, index=g.index)

    d["mediana_pares"] = d.groupby([grupo, periodo], group_keys=False)[["_v"]].apply(_pares)
    cociente = d["_v"] / d["mediana_pares"].where(d["mediana_pares"] > 0)
    d["_cociente"] = cociente
    d = d.sort_values([entidad, periodo], kind="stable")
    previo = d.groupby(entidad)["_cociente"].transform(
        lambda s: s.shift(1).expanding(min_periods=periodos_base).median())
    d["participacion"] = previo
    d["valor_esperado"] = d["participacion"] * d["mediana_pares"]
    d["desvio_rel"] = (d["_v"] - d["valor_esperado"]) / d["valor_esperado"].where(d["valor_esperado"] > 0)
    return d.drop(columns=["_v", "_cociente"]).sort_index()


def escala_robusta(desvios: pd.Series) -> float | None:
    """σ robusta = 1.4826 × MAD. None si no hay datos o el MAD es 0 (no evaluable)."""
    x = pd.to_numeric(desvios, errors="coerce").dropna()
    if x.empty:
        return None
    mad = float((x - x.median()).abs().median())
    return 1.4826 * mad if mad > 0 else None


# --- 2. CUSUM, EWMA y punto de cambio -------------------------------------------
def cusum(x, k: float = config.DETECTOR_K) -> np.ndarray:
    """CUSUM tabular de un solo lado: S_t = max(0, S_{t−1} + x_t − k). Un nulo no suma."""
    s, salida = 0.0, []
    for v in np.asarray(x, dtype=float):
        if np.isfinite(v):
            s = max(0.0, s + v - k)
        salida.append(s)
    return np.array(salida)


def ewma(x, lam: float = config.DETECTOR_LAMBDA) -> np.ndarray:
    """E_t = λ x_t + (1 − λ) E_{t−1}, con E_0 = 0 (la media en control del desvío estandarizado)."""
    e, salida = 0.0, []
    for v in np.asarray(x, dtype=float):
        if np.isfinite(v):
            e = lam * v + (1 - lam) * e
        salida.append(e)
    return np.array(salida)


def limite_ewma(lam: float = config.DETECTOR_LAMBDA, L: float = config.DETECTOR_L) -> float:
    """Límite asintótico del EWMA para desvíos con σ = 1: L × √(λ ÷ (2 − λ))."""
    return L * float(np.sqrt(lam / (2 - lam)))


def punto_cambio(s, h: float = config.DETECTOR_H) -> int | None:
    """Posición donde empezó el desvío: la siguiente al último 0 del CUSUM antes de cruzar h."""
    s = np.asarray(s, dtype=float)
    cruces = np.flatnonzero(s > h)
    if not cruces.size:
        return None
    primero = int(cruces[0])
    ceros = np.flatnonzero(s[: primero + 1] == 0)
    return int(ceros[-1]) + 1 if ceros.size else 0


# --- 3. Detector completo por entidad ---------------------------------------------
def detectar(df: pd.DataFrame, entidad: str, valor: str, periodo: str, grupo: str = "rol",
             k: float = config.DETECTOR_K, h: float = config.DETECTOR_H,
             lam: float = config.DETECTOR_LAMBDA, L: float = config.DETECTOR_L,
             sigma: dict | None = None, precio: float = config.PRECIO_REF_KG,
             periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> pd.DataFrame:
    """Serie del detector por entidad y periodo.

    Columnas que agrega: `valor_esperado`, `residuo` (real − esperado, en kg), `z`,
    `cusum`, `ewma`, `estado` (verde, ambar, rojo o no_evaluable), `periodo_inicio`,
    `kg_acumulados` y `soles_acumulados` (faltante neto desde el inicio estimado).
    `sigma` permite usar la escala fijada en la calibración (por grupo); si no se da,
    se estima con los datos recibidos.
    """
    d = neutralizar_redigitados(df, entidad, valor, periodo)
    d = esperado_por_pares(d, entidad, f"{valor}_corregido", periodo, grupo, periodos_base)
    escalas = dict(sigma or {})
    for g, desv in d.groupby(grupo)["desvio_rel"]:
        escalas.setdefault(g, escala_robusta(desv))
    d["_sigma"] = d[grupo].map(escalas)
    d["residuo"] = d[f"{valor}_corregido"] - d["valor_esperado"]
    d["z"] = d["desvio_rel"] / d["_sigma"]
    limite = limite_ewma(lam, L)

    partes = []
    for _, g in d.sort_values([entidad, periodo], kind="stable").groupby(entidad, sort=False):
        g = g.copy()
        faltante = -g["z"].to_numpy(dtype=float)          # un faltante es un desvío negativo
        s, e = cusum(faltante, k), ewma(faltante, lam)
        g["cusum"], g["ewma"] = s, e
        evaluable = g["_sigma"].notna().to_numpy() & np.isfinite(g["z"].to_numpy(dtype=float))
        estado = np.where(s > h, "rojo", np.where(e > limite, "ambar", "verde"))
        g["estado"] = np.where(evaluable, estado, "no_evaluable")
        inicio = punto_cambio(s, h)
        g["periodo_inicio"] = None
        g["kg_acumulados"] = 0.0
        if inicio is not None:
            g["periodo_inicio"] = g[periodo].iloc[inicio]
            desde = np.arange(len(g)) >= inicio
            faltante_kg = (-g["residuo"]).where(desde, 0.0).fillna(0.0)
            g["kg_acumulados"] = faltante_kg.cumsum().where(desde, 0.0)
        g["soles_acumulados"] = g["kg_acumulados"] * precio
        partes.append(g)
    salida = pd.concat(partes).sort_index() if partes else d
    return salida.drop(columns=["_sigma"])


def alarmas(serie: pd.DataFrame, entidad: str, periodo: str) -> pd.DataFrame:
    """Primer periodo en rojo de cada entidad, con su inicio estimado. Lo usa calibrar_h."""
    rojas = serie[serie["estado"] == "rojo"].sort_values([entidad, periodo])
    return rojas.groupby(entidad, as_index=False).first()[[entidad, periodo, "periodo_inicio"]]
