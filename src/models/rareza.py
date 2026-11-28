"""Detectores de rareza: Isolation Forest y LOF (FR10; informe v17, 4.3 y Tablas 4.5 y 4.6b).

Isolation Forest aísla las observaciones raras sin necesidad de etiquetas (Liu et al., 2008)
y Local Outlier Factor las detecta respecto de su vecindario (Breunig et al., 2000). MLlib no
los incluye, así que se ajustan con scikit-learn en el driver sobre el extracto de Gold
(1 541 facturas y 146 unidades-mes) y puntúan en paralelo en los executors con mapInPandas.

Dos modelos independientes, sin imputar (informe, «Preparación de datos»):
  * por factura (modelo_factura): kg, USD/kg frente a la mediana, desvío del tipo de cambio
    y SCOP repetido. Se ajusta con 2020 y 2022 y se evalúa con 2023 (estabilidad);
  * por unidad-mes (fact_unidad_mes): kg del rol, S/ por tonelada, señales disparadas,
    pandemia y, si existen, eventos de mercado. Se valida por exclusión mensual.
Las filas con alguna variable faltante no se puntúan y se cuentan. Escalado robusto
(mediana e IQR), por el mismo motivo que el MAD del modelo base.

Elección de hiperparámetros (Tabla 4.6b): mayor precision@20 en la ventana de validación.
precision@20 necesita etiquetas: por factura, la etiqueta S12 madura; por unidad-mes, las
alertas confirmadas por la revisión documental. Si la ventana no tiene al menos 20 filas
etiquetadas, no hay con qué elegir y se usan los valores que recomiendan los autores del
método: 100 árboles y submuestras de 256 (Liu et al., 2008) y 20 vecinos para LOF (Breunig
et al., 2000, recomiendan al menos 10). `criterio` lo deja dicho.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from src.common import config
from src.models.base_mad import precision_at_k

REJILLA = {
    "isolation_forest": {"n_estimators": [100, 300], "max_samples": [256, "auto"],
                         "contamination": [0.01, 0.02, 0.05]},
    "lof": {"n_neighbors": [10, 20, 35]},
}
POR_DEFECTO = {"isolation_forest": {"n_estimators": 100, "max_samples": 256, "contamination": 0.02}}
# contamination solo fija el corte de predict(); el puntaje (score_samples) y precision@20 no
# dependen de ella. 0.02 es el valor central de la rejilla de la Tabla 4.6b.

VARIABLES_FACTURA = ["kg", "usd_kg_vs_mediana", "desvio_tc", "flag_scop_duplicado"]
VARIABLES_UNIDAD_MES = ["kg_base_rol", "soles_comb_por_t", "n_senales", "pandemia"]


def _modelo(nombre: str, params: dict, filas: int | None = None):
    from sklearn.ensemble import IsolationForest  # noqa: PLC0415
    from sklearn.neighbors import LocalOutlierFactor  # noqa: PLC0415
    from sklearn.pipeline import make_pipeline  # noqa: PLC0415
    from sklearn.preprocessing import RobustScaler  # noqa: PLC0415

    if nombre == "isolation_forest":
        params = dict(params)
        # Con menos filas que la submuestra (la unidad-mes tiene 146), se usan todas: es lo que
        # scikit-learn haría por su cuenta, dicho aquí para que no quede como un aviso.
        if isinstance(params.get("max_samples"), int) and filas is not None and filas < params["max_samples"]:
            params["max_samples"] = filas
        est = IsolationForest(random_state=config.SEMILLA, **params)
    else:
        est = LocalOutlierFactor(novelty=True, **params)
    return make_pipeline(RobustScaler(), est)


def puntuar_pandas(modelo, pdf: pd.DataFrame, columnas: list[str]) -> pd.Series:
    """Puntaje de rareza: mayor = más raro (se invierte score_samples). Nulo si falta una variable."""
    completas = pdf[columnas].notna().all(axis=1)
    puntaje = pd.Series(np.nan, index=pdf.index, dtype=float)
    if completas.any():
        puntaje[completas] = -modelo.score_samples(pdf.loc[completas, columnas].astype(float))
    return puntaje


def _etiquetadas(pdf: pd.DataFrame, etiqueta: str | None) -> int:
    return 0 if etiqueta is None or etiqueta not in pdf.columns else int(pdf[etiqueta].notna().sum())


def ajustar(entreno: pd.DataFrame, validacion: pd.DataFrame, columnas: list[str],
            etiqueta: str | None = None, k: int = config.TOP_K) -> dict:
    """Elige modelo e hiperparámetros por precision@k en la validación y ajusta el final.

    Devuelve: `nombre`, `params`, `modelo` (ajustado con `entreno`), `tabla` (rejilla con su
    precision@k) y `criterio` («precision@k en la validación» o «valores de los autores»).
    """
    ent = entreno.dropna(subset=columnas)
    val = validacion.dropna(subset=columnas)
    filas = []
    if _etiquetadas(val, etiqueta) >= k:
        y = val[etiqueta]
        for nombre, rejilla in REJILLA.items():
            for combo in itertools.product(*rejilla.values()):
                params = dict(zip(rejilla.keys(), combo))
                m = _modelo(nombre, params, len(ent)).fit(ent[columnas].astype(float))
                filas.append({"modelo": nombre, **params,
                              f"precision@{k}": precision_at_k(puntuar_pandas(m, val, columnas), y, k)})
        tabla = pd.DataFrame(filas)
        valida = tabla[tabla[f"precision@{k}"].notna()]
        if not valida.empty:
            mejor = valida.sort_values(f"precision@{k}", ascending=False, kind="stable").iloc[0]
            nombre = mejor["modelo"]
            params = {c: mejor[c] for c in REJILLA[nombre]}
            params = {c: (int(v) if isinstance(v, (int, float, np.integer, np.floating)) and float(v).is_integer()
                          else v) for c, v in params.items()}
            return {"nombre": nombre, "params": params, "tabla": tabla,
                    "modelo": _modelo(nombre, params, len(ent)).fit(ent[columnas].astype(float)),
                    "criterio": f"precision@{k} en la validación"}
    nombre, params = "isolation_forest", POR_DEFECTO["isolation_forest"]
    return {"nombre": nombre, "params": params, "tabla": pd.DataFrame(filas),
            "modelo": _modelo(nombre, params, len(ent)).fit(ent[columnas].astype(float)),
            "criterio": "valores de los autores (Liu et al., 2008): validación sin etiquetas suficientes"}


# --- Particiones del informe ------------------------------------------------------------
def particion_factura(modelo_factura: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ajuste con las compras de 2020 y 2022; evaluación con 2023 (informe, «Partición»)."""
    anio = modelo_factura["anio"]
    return modelo_factura[anio.isin([2020, 2022])], modelo_factura[anio == 2023]


def preparar_unidad_mes(unidad_mes: pd.DataFrame) -> pd.DataFrame:
    """Agrega la marca de pandemia por mes (PANDEMIA_INICIO a PANDEMIA_FIN) a fact_unidad_mes."""
    um = unidad_mes.copy()
    mes = pd.to_datetime(dict(year=um["anio"], month=um["mes"], day=1))
    inicio = pd.Timestamp(config.PANDEMIA_INICIO).to_period("M").to_timestamp()
    um["pandemia"] = ((mes >= inicio) & (mes <= pd.Timestamp(config.PANDEMIA_FIN))).astype(float)
    return um


def fuera_de_pliegue_mensual(unidad_mes: pd.DataFrame, nombre: str, params: dict,
                             columnas: list[str]) -> pd.Series:
    """Puntaje por exclusión mensual: cada mes se puntúa con un modelo que no lo vio."""
    puntaje = pd.Series(np.nan, index=unidad_mes.index, dtype=float)
    for (anio, mes), g in unidad_mes.groupby(["anio", "mes"]):
        resto = unidad_mes.drop(g.index).dropna(subset=columnas)
        if len(resto) < 2:
            continue
        m = _modelo(nombre, params, len(resto)).fit(resto[columnas].astype(float))
        puntaje.loc[g.index] = puntuar_pandas(m, g, columnas)
    return puntaje


# --- Puntuación repartida en los executors ----------------------------------------------
def puntuar_spark(df, modelo, columnas: list[str], salida: str = "puntaje_rareza"):
    """Puntúa un DataFrame de Spark con el modelo ajustado en el driver, partición por partición.

    El modelo viaja serializado a cada tarea (es pequeño) y mapInPandas aplica
    puntuar_pandas a cada lote; ningún dato vuelve al driver.
    """
    from pyspark.sql.types import DoubleType, StructField, StructType  # noqa: PLC0415

    esquema = StructType(df.schema.fields + [StructField(salida, DoubleType(), True)])

    def _lotes(iterador):
        for pdf in iterador:
            yield pdf.assign(**{salida: puntuar_pandas(modelo, pdf, columnas).to_numpy()})

    return df.mapInPandas(_lotes, schema=esquema)
