"""Entrenamiento completo del clasificador S12 con registro y cortes de deriva (FR13).

Informe v17, 4.3 («Cómo se usa») y Tabla 4.8b. Cada reentrenamiento hace, en este orden:

  1. separa las etiquetas maduras antes del corte: los MESES_VALIDACION meses más recientes
     validan y los anteriores entrenan (la misma partición que la evaluación hacia adelante);
  2. entrena el Random Forest (`mllib.entrenar_clasificador_s12`) y elige el umbral en la
     validación (`mllib.elegir_umbral`: el menor con precisión ≥ META_PRECISION);
  3. mide en la validación la precisión y el recall con ese umbral y la PR-AUC de MLlib;
  4. guarda los cortes de deciles de cada variable del entrenamiento (`deriva`), que el
     PSI necesita: si se recalculan con los datos nuevos, el PSI sale casi cero siempre;
  5. registra la corrida (`registro.guardar`) y la promueve solo si mejora al vigente
     (`registro.promover_si_mejora`: sube la precisión y el recall alcanza 0.50).

Los cortes viajan dentro de la ficha (`metricas["cortes_deriva"]`), así el vigente.json que
lee la puntuación ya trae lo necesario para medir la deriva de las facturas nuevas.
"""
from __future__ import annotations

import pandas as pd

from src.common import config
from src.models import deriva, metricas, mllib, registro

# Variables cuya deriva se vigila: las numéricas de la Tabla 4.6, en su escala original
# (sin el centinela −1, que movería los deciles).
VARIABLES_DERIVA = ("kg", "usd_kg_vs_mediana", "desvio_tc", "ratio_carga_capacidad")


def particion(modelo_factura, corte: str, meses_validacion: int = config.MESES_VALIDACION):
    """(entrenamiento, validación) con las etiquetas maduras antes de `corte`, o None si no alcanza."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    corte_col = F.lit(str(corte)).cast("date")
    conocidas = modelo_factura.filter((F.col("fecha_madurez") < corte_col) & F.col(mllib.ETIQUETA).isNotNull())
    meses = sorted({(r["anio"], r["mes"]) for r in conocidas.select("anio", "mes").distinct().take(1000)})
    if len(meses) <= meses_validacion:
        return None
    inicio = F.lit(str(mllib._primer_dia(*meses[-meses_validacion]))).cast("date")  # noqa: SLF001
    return conocidas.filter(F.col("fecha") < inicio), conocidas.filter(F.col("fecha") >= inicio)


def _pandas(df, columnas, limite: int = 100_000) -> pd.DataFrame:
    """Muestra acotada con take(), nunca collect(): el entrenamiento son unos cientos de facturas."""
    filas = df.select(*columnas).take(limite)
    return pd.DataFrame([r.asDict() for r in filas], columns=list(columnas))


def entrenar(modelo_factura, corte: str) -> dict:
    """Pasos 1 a 4. Devuelve el modelo, el umbral, las métricas de validación y los cortes."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    partes = particion(modelo_factura, corte)
    if partes is None:
        return {"estado": "no_evaluable_sin_meses_suficientes", "corte": str(corte)}
    entrenamiento, validacion = partes
    clases = {r[mllib.ETIQUETA] for r in entrenamiento.select(mllib.ETIQUETA).distinct().take(3)}
    if clases != {0.0, 1.0}:
        return {"estado": "no_evaluable_entrenamiento_sin_dos_clases", "corte": str(corte)}

    modelo = mllib.entrenar_clasificador_s12(entrenamiento.withColumn("madura", F.lit(True)))
    pares = mllib._probabilidades(modelo, validacion)  # noqa: SLF001
    umbral = mllib.elegir_umbral(pares)
    pr_auc = metricas.pr_auc_mllib(modelo.transform(mllib.preparar_variables(validacion)))
    cortes = deriva.deciles_entrenamiento(_pandas(entrenamiento, VARIABLES_DERIVA), VARIABLES_DERIVA)
    return {"estado": "entrenado", "corte": str(corte), "modelo": modelo, "umbral": umbral["umbral"],
            "metricas": {"precision": umbral["precision"], "recall": umbral["recall"],
                         "cumple_meta": umbral["cumple_meta"], "pr_auc": pr_auc,
                         "umbral": umbral["umbral"], "n_entrenamiento": entrenamiento.count(),
                         "n_validacion": validacion.count(), "cortes_deriva": cortes}}


def entrenar_y_registrar(modelo_factura, corte: str, base: str | None = None,
                         actual: dict | None = None) -> dict:
    """Pasos 1 a 5: entrena, registra la corrida con fecha `corte` y decide la promoción."""
    resultado = entrenar(modelo_factura, corte)
    if resultado["estado"] != "entrenado":
        return {**resultado, "promovido": False}
    ficha = registro.guardar(resultado["modelo"], resultado["metricas"], base=base, fecha=str(corte),
                             umbral=resultado["umbral"])
    promovido = registro.promover_si_mejora(ficha, actual=actual, base=base)
    return {"estado": "registrado", "ficha": ficha, "promovido": promovido}


def deriva_de_nuevas(pdf_nuevas: pd.DataFrame, ficha: dict) -> dict:
    """PSI de las facturas nuevas contra los cortes que guardó el modelo vigente."""
    resultado = deriva.evaluar(pdf_nuevas, ficha["metricas"]["cortes_deriva"])
    return {**resultado, "requiere_reentreno": deriva.requiere_reentreno(resultado)}
