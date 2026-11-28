"""Convergencia de señales y riesgo de sustracción (FR11; informe v17, 4.3 y Figura 4.4).

La empresa no ha confirmado ningún robo, así que no hay una etiqueta que lo nombre. El
sistema se acerca combinando señales independientes, y solo donde sus ventanas se cruzan:

  * proveedor × mes, feb-2022 a jul-2023: S12, S2, S3, S6 y S1;
  * unidad × mes, ene-2020 a feb-2021: S9, S7, el CUSUM del detector y el Isolation Forest;
  * cliente de granel o mostrador × mes, en los meses con ventas por cliente: S5 y S10.

Cuando dos o más fuentes coinciden sobre la misma entidad y el mismo periodo, el caso recibe
una etiqueta probable y un puntaje de convergencia: la suma de las fuentes ponderada por su
grado de evidencia (`PESO_GRADO`: alto 3, medio 2, indicio 1). El CUSUM en rojo y el
Isolation Forest sobre su corte son evidencia estadística sin segundo registro, como S9, y
pesan como grado medio.

Con esas etiquetas se entrena un Random Forest de riesgo (MLlib) que NO usa las señales que
definen la etiqueta sino el contexto de la entidad (volumen, actividad en documentos y
clientes, proveedor y mes), para anticipar la convergencia en vez de repetir la regla. Es
supervisión débil: el puntaje se lee como riesgo, no como prueba (Tabla 4.8f, nivel 1).
"""
from __future__ import annotations

import pandas as pd

from src.common import config
from src.signals.common import PESO_GRADO

# Ventanas donde las fuentes de cada grupo se cruzan (informe v17, 4.3).
GRUPOS = {
    "proveedor": {"fuentes": ("S12", "S2", "S3", "S6", "S1"), "ventana": ("2022-02-01", "2023-07-31")},
    "unidad": {"fuentes": ("S9", "S7", "CUSUM", "IF"), "ventana": ("2020-01-01", "2021-02-28")},
    "cliente": {"fuentes": ("S5", "S10"), "ventana": None},   # los meses con ventas por cliente
}
GRADO_ESTADISTICO = "medio"   # CUSUM en rojo e Isolation Forest: sin segundo registro, como S9
COLUMNAS_EVENTO = ["grupo", "entidad_id", "anio", "mes", "fuente", "grado_evidencia"]


# --- Eventos: una fila por fuente que marcó una entidad en un mes -----------------------
def desde_alertas(alertas: pd.DataFrame) -> pd.DataFrame:
    """fact_alerta_base → eventos de proveedor (S12, S2, S3, S6, S1) y de unidad (S9, S7).

    El proveedor es la primera parte de factura_id («PROVEEDOR|SERIE|NUMERO»).
    """
    a = alertas.copy()
    prov = a[a["senal"].isin(GRUPOS["proveedor"]["fuentes"]) & a["factura_id"].notna()]
    unid = a[a["senal"].isin(("S9", "S7")) & a["unidad_id"].notna()]
    partes = [
        pd.DataFrame({"grupo": "proveedor", "entidad_id": prov["factura_id"].astype(str).str.split("|").str[0],
                      "anio": prov["anio"], "mes": prov["mes"], "fuente": prov["senal"],
                      "grado_evidencia": prov["grado_evidencia"]}),
        pd.DataFrame({"grupo": "unidad", "entidad_id": unid["unidad_id"].astype(str), "anio": unid["anio"],
                      "mes": unid["mes"], "fuente": unid["senal"], "grado_evidencia": unid["grado_evidencia"]}),
    ]
    return pd.concat(partes, ignore_index=True)[COLUMNAS_EVENTO]


def desde_detector(fact_serie: pd.DataFrame) -> pd.DataFrame:
    """Unidades en rojo del CUSUM (fact_serie) → eventos «CUSUM» por unidad y mes."""
    rojas = fact_serie[(fact_serie["entidad_tipo"] == "unidad") & (fact_serie["estado"] == "rojo")]
    return pd.DataFrame({"grupo": "unidad", "entidad_id": rojas["entidad_id"].astype(str),
                         "anio": rojas["anio"], "mes": rojas["mes"], "fuente": "CUSUM",
                         "grado_evidencia": GRADO_ESTADISTICO})[COLUMNAS_EVENTO]


def desde_rareza(unidad_mes: pd.DataFrame, puntaje: str = "puntaje_rareza",
                 contaminacion: float = 0.02) -> pd.DataFrame:
    """Unidades-mes con puntaje de Isolation Forest en el `contaminacion` superior → eventos «IF».

    0.02 es la contaminación del modelo por defecto (`rareza.POR_DEFECTO`): la misma
    proporción que el modelo declara como rara.
    """
    p = unidad_mes[puntaje]
    corte = p.quantile(1 - contaminacion)
    raras = unidad_mes[p >= corte]
    return pd.DataFrame({"grupo": "unidad", "entidad_id": raras["unidad_id"].astype(str),
                         "anio": raras["anio"], "mes": raras["mes"], "fuente": "IF",
                         "grado_evidencia": GRADO_ESTADISTICO})[COLUMNAS_EVENTO]


# --- Regla de convergencia ----------------------------------------------------------------
def _en_ventana(ev: pd.DataFrame) -> pd.Series:
    fecha = pd.to_datetime(dict(year=ev["anio"], month=ev["mes"], day=1))
    dentro = pd.Series(True, index=ev.index)
    for grupo, regla in GRUPOS.items():
        if regla["ventana"] is None:
            continue
        ini, fin = (pd.Timestamp(x) for x in regla["ventana"])
        es = ev["grupo"] == grupo
        dentro &= ~es | fecha.between(ini, fin)
    validas = ev.apply(lambda r: r["fuente"] in GRUPOS[r["grupo"]]["fuentes"], axis=1) if len(ev) else dentro
    return dentro & validas


def puntaje_convergencia(eventos: pd.DataFrame, minimo: int = 2) -> pd.DataFrame:
    """Puntaje y etiqueta probable por grupo, entidad y mes.

    Cada fuente cuenta una vez por entidad y mes, con su grado más alto. puntaje = Σ pesos;
    etiqueta_probable = 1 si coinciden `minimo` fuentes o más (informe: «dos o más»).
    """
    ev = eventos[_en_ventana(eventos)].copy()
    ev["peso"] = ev["grado_evidencia"].map(PESO_GRADO)
    por_fuente = ev.groupby(["grupo", "entidad_id", "anio", "mes", "fuente"], as_index=False)["peso"].max()
    salida = (por_fuente.groupby(["grupo", "entidad_id", "anio", "mes"])
              .agg(puntaje_convergencia=("peso", "sum"), n_fuentes=("fuente", "nunique"),
                   fuentes=("fuente", lambda s: ",".join(sorted(s)))).reset_index())
    salida["etiqueta_probable"] = (salida["n_fuentes"] >= minimo).astype(int)
    return salida


# --- Random Forest de riesgo con variables de contexto -------------------------------------
PROHIBIDAS = ("senal", "fuente", "puntaje", "cusum", "ewma", "alerta", "etiqueta", "convergencia")
SENALES = {f"S{i}" for i in range(1, 13)}


def validar_contexto(columnas: list[str]) -> None:
    """Las variables del modelo de riesgo no pueden ser las señales que definen la etiqueta."""
    malas = [c for c in columnas
             if any(p in c.lower() for p in PROHIBIDAS) or c.upper() in SENALES
             or c.lower() == "z" or c.lower().startswith("z_")]
    if malas:
        raise ValueError(f"el modelo de riesgo no puede usar señales como variables: {malas}")


def riesgo_rf(datos, contexto: list[str], etiqueta: str = "etiqueta_probable"):
    """Random Forest de riesgo (MLlib) entrenado con variables de contexto y peso de clase.

    `datos`: DataFrame de Spark con la etiqueta probable de `puntaje_convergencia` unida al
    contexto de cada entidad y mes. Variables de texto (por ejemplo, el proveedor) se indexan.
    """
    from pyspark.ml import Pipeline  # noqa: PLC0415
    from pyspark.ml.classification import RandomForestClassifier  # noqa: PLC0415
    from pyspark.ml.feature import StringIndexer, VectorAssembler  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    validar_contexto(contexto)
    tipos = dict(datos.dtypes)
    texto = [c for c in contexto if tipos[c] == "string"]
    numericas = [c for c in contexto if c not in texto]
    d = datos.withColumn(etiqueta, F.col(etiqueta).cast("double"))
    for c in numericas:
        d = d.withColumn(c, F.col(c).cast("double"))
    conteo = d.groupBy(etiqueta).agg(F.count("*").alias("_n"))
    total = conteo.agg(F.sum("_n").alias("_t"))
    pesos = conteo.crossJoin(total).withColumn("_peso", F.col("_t") / (F.lit(2.0) * F.col("_n")))
    d = d.join(broadcast(pesos.select(etiqueta, "_peso")), etiqueta, "left")
    etapas = [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep") for c in texto]
    etapas += [VectorAssembler(inputCols=numericas + [f"{c}_idx" for c in texto], outputCol="_x",
                               handleInvalid="keep"),
               RandomForestClassifier(labelCol=etiqueta, featuresCol="_x", weightCol="_peso",
                                      numTrees=config.RF_ARBOLES, maxDepth=config.RF_PROFUNDIDAD,
                                      seed=config.SEMILLA, probabilityCol="probabilidad_riesgo")]
    return Pipeline(stages=etapas).fit(d)
