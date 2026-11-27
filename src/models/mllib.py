"""Clasificador S12 en Spark MLlib (FR06; informe v16, 4.3 y Tablas 4.6 y 4.6b).

Estima por factura la probabilidad de discrepancia documental entre tesorería y logística
(etiqueta S12, que viene de `modelo_factura`). Tres modelos, todos como Pipeline de MLlib
ajustado solo con el conjunto de entrenamiento:

* **Random Forest** (modelo principal): StringIndexer(proveedor_id), VectorAssembler y
  RandomForestClassifier con RF_ARBOLES, RF_PROFUNDIDAD, SEMILLA y `weightCol`. No necesita
  escalado (Breiman, 2001).
* **Regresión logística** (referencia): proveedor con OneHotEncoder, variables con
  RobustScaler (son asimétricas) y LogisticRegression, que MLlib optimiza con L-BFGS
  cuando no hay penalización L1.
* **Árbol de decisión** de ARBOL_PROFUNDIDAD niveles: reglas legibles para la gerencia.

Desbalance (7.4 % de facturas con discrepancia): peso de clase inverso a la frecuencia,
peso = total ÷ (2 × facturas de la clase), para que las dos clases pesen lo mismo.

Variables de la Tabla 4.6. Las que pueden faltar (`usd_kg_vs_mediana` sin facturas previas
del proveedor, `desvio_tc` sin tipo de cambio oficial, `ratio_carga_capacidad` sin capacidad
conocida) no se imputan con un valor plausible: se codifican con un centinela fuera de su
rango (−1) y una marca `<variable>_conocido`, así el modelo distingue «no se sabe» de un
valor real. Solo entrenan las etiquetas maduras (`madura`).
"""
from __future__ import annotations

from src.common import config

ETIQUETA = "etiqueta_s12"
PESO = "peso"
VARIABLES_CON_FALTANTES = ("usd_kg_vs_mediana", "desvio_tc", "ratio_carga_capacidad")
VARIABLES_NUMERICAS = ("kg", "usd_kg_vs_mediana", "desvio_tc", "flag_scop_duplicado",
                       "ratio_carga_capacidad", "mes")
CENTINELA = -1.0


def columnas_de_entrada() -> list[str]:
    """Columnas numéricas que entran al VectorAssembler, en orden (más el proveedor indexado)."""
    return list(VARIABLES_NUMERICAS) + [f"{v}_conocido" for v in VARIABLES_CON_FALTANTES]


def preparar_variables(df):
    """Codifica los faltantes con centinela y marca, y deja las variables en double."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    salida = df
    for v in VARIABLES_CON_FALTANTES:
        salida = salida.withColumn(f"{v}_conocido", F.col(v).isNotNull().cast("double"))
        salida = salida.withColumn(v, F.coalesce(F.col(v).cast("double"), F.lit(CENTINELA)))
    for v in ("kg", "flag_scop_duplicado", "mes"):
        salida = salida.withColumn(v, F.col(v).cast("double"))
    return salida.withColumn(ETIQUETA, F.col(ETIQUETA).cast("double"))


def pesos_clase(df):
    """Agrega `peso` = total ÷ (2 × facturas de su clase). Sin collect(): se une el conteo."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    conteo = df.groupBy(ETIQUETA).agg(F.count("*").alias("_n_clase"))
    total = conteo.agg(F.sum("_n_clase").alias("_n_total"))
    pesos = conteo.crossJoin(total).withColumn(
        PESO, F.col("_n_total") / (F.lit(2.0) * F.col("_n_clase"))).select(ETIQUETA, PESO)
    return df.join(broadcast(pesos), ETIQUETA, "left")


def _indexador():
    from pyspark.ml.feature import StringIndexer  # noqa: PLC0415

    # «keep»: un proveedor nuevo en la puntuación recibe su propio índice en vez de fallar.
    return StringIndexer(inputCol="proveedor_id", outputCol="proveedor_idx", handleInvalid="keep")


def pipeline_s12():
    """Pipeline del Random Forest (Tabla 4.6)."""
    from pyspark.ml import Pipeline  # noqa: PLC0415
    from pyspark.ml.classification import RandomForestClassifier  # noqa: PLC0415
    from pyspark.ml.feature import VectorAssembler  # noqa: PLC0415

    ensamblador = VectorAssembler(inputCols=columnas_de_entrada() + ["proveedor_idx"], outputCol="features")
    bosque = RandomForestClassifier(labelCol=ETIQUETA, featuresCol="features", weightCol=PESO,
                                    numTrees=config.RF_ARBOLES, maxDepth=config.RF_PROFUNDIDAD,
                                    seed=config.SEMILLA)
    return Pipeline(stages=[_indexador(), ensamblador, bosque])


def pipeline_logistica():
    """Pipeline de la regresión logística de referencia, con escalado robusto."""
    from pyspark.ml import Pipeline  # noqa: PLC0415
    from pyspark.ml.classification import LogisticRegression  # noqa: PLC0415
    from pyspark.ml.feature import OneHotEncoder, RobustScaler, VectorAssembler  # noqa: PLC0415

    numericas = VectorAssembler(inputCols=columnas_de_entrada(), outputCol="numericas")
    escala = RobustScaler(inputCol="numericas", outputCol="numericas_escaladas")
    proveedor = OneHotEncoder(inputCols=["proveedor_idx"], outputCols=["proveedor_oh"], handleInvalid="keep")
    todas = VectorAssembler(inputCols=["numericas_escaladas", "proveedor_oh"], outputCol="features")
    # elasticNetParam = 0 (sin L1): MLlib optimiza con L-BFGS.
    modelo = LogisticRegression(labelCol=ETIQUETA, featuresCol="features", weightCol=PESO,
                                elasticNetParam=0.0)
    return Pipeline(stages=[_indexador(), numericas, escala, proveedor, todas, modelo])


def pipeline_arbol():
    """Pipeline del árbol de decisión que explica las reglas."""
    from pyspark.ml import Pipeline  # noqa: PLC0415
    from pyspark.ml.classification import DecisionTreeClassifier  # noqa: PLC0415
    from pyspark.ml.feature import VectorAssembler  # noqa: PLC0415

    ensamblador = VectorAssembler(inputCols=columnas_de_entrada() + ["proveedor_idx"], outputCol="features")
    arbol = DecisionTreeClassifier(labelCol=ETIQUETA, featuresCol="features", weightCol=PESO,
                                   maxDepth=config.ARBOL_PROFUNDIDAD, seed=config.SEMILLA)
    return Pipeline(stages=[_indexador(), ensamblador, arbol])


def conjunto_de_entrenamiento(modelo_factura):
    """Facturas con etiqueta madura, variables preparadas y peso de clase."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    maduras = modelo_factura.filter(F.coalesce(F.col("madura"), F.lit(False)) & F.col(ETIQUETA).isNotNull())
    return pesos_clase(preparar_variables(maduras))


def entrenar_clasificador_s12(modelo_factura):
    """Random Forest ajustado solo con las etiquetas maduras. Devuelve el PipelineModel."""
    return pipeline_s12().fit(conjunto_de_entrenamiento(modelo_factura))


def entrenar_referencias(modelo_factura) -> dict:
    """Regresión logística y árbol de reglas, con el mismo conjunto que el Random Forest."""
    datos = conjunto_de_entrenamiento(modelo_factura)
    return {"logistica": pipeline_logistica().fit(datos), "arbol": pipeline_arbol().fit(datos)}


def importancias(modelo) -> dict[str, float]:
    """featureImportances del Random Forest o del árbol, con el nombre de cada variable."""
    nombres = columnas_de_entrada() + ["proveedor_idx"]
    valores = modelo.stages[-1].featureImportances.toArray()
    return dict(sorted(zip(nombres, (float(v) for v in valores)), key=lambda kv: -kv[1]))


def reglas(modelo_arbol) -> str:
    """Reglas del árbol con el nombre de cada variable en vez de «feature N»."""
    texto = modelo_arbol.stages[-1].toDebugString
    for i, nombre in sorted(enumerate(columnas_de_entrada() + ["proveedor_idx"]), reverse=True):
        texto = texto.replace(f"feature {i} ", f"{nombre} ")
    return texto


# --- Evaluación hacia adelante (FR07; informe v16, 4.3 y Tabla 4.7) -------------------
def _primer_dia(anio: int, mes: int):
    import datetime as dt  # noqa: PLC0415

    return dt.date(int(anio), int(mes), 1)


def _sumar_meses(fecha, n: int):
    total = fecha.year * 12 + fecha.month - 1 + n
    return _primer_dia(total // 12, total % 12 + 1)


def _probabilidades(modelo, df, limite: int = 100_000) -> list[tuple[float, float]]:
    """(probabilidad de la clase 1, etiqueta) de cada factura; take() acotado, nunca collect()."""
    from pyspark.ml.functions import vector_to_array  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    p = modelo.transform(preparar_variables(df)).select(
        vector_to_array("probability").getItem(1).alias("prob"), F.col(ETIQUETA).alias("y"))
    return [(float(r["prob"]), float(r["y"])) for r in p.take(limite)]


def matriz(pares, umbral: float) -> dict:
    """Matriz de confusión con la regla «alerta si probabilidad ≥ umbral»."""
    tp = sum(1 for p, y in pares if p >= umbral and y == 1)
    fp = sum(1 for p, y in pares if p >= umbral and y == 0)
    fn = sum(1 for p, y in pares if p < umbral and y == 1)
    tn = sum(1 for p, y in pares if p < umbral and y == 0)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def elegir_umbral(pares, recall_min: float = config.RECALL_MIN_RETADOR) -> dict:
    """Umbral con la mayor precisión de la clase positiva entre los que dejan recall ≥ recall_min.

    Los candidatos son las probabilidades observadas en la validación (no una rejilla
    arbitraria). Si ninguno alcanza el recall mínimo, se toma el de mayor recall y
    `cumple_recall` queda en False, para que se vea en la evaluación.
    """
    positivos = sum(1 for _, y in pares if y == 1)
    mejor = None
    for u in sorted({p for p, _ in pares}):
        m = matriz(pares, u)
        marcadas = m["tp"] + m["fp"]
        precision = m["tp"] / marcadas if marcadas else 0.0
        recall = m["tp"] / positivos if positivos else 0.0
        cand = {"umbral": u, "precision": precision, "recall": recall, "cumple_recall": recall >= recall_min}
        clave = (cand["cumple_recall"], precision if cand["cumple_recall"] else recall, -u if not cand["cumple_recall"] else u)
        if mejor is None or clave > mejor[0]:
            mejor = (clave, cand)
    return mejor[1] if mejor else {"umbral": None, "precision": None, "recall": None, "cumple_recall": False}


def evaluar_corte(modelo_factura, corte, prueba, meses_validacion: int = config.MESES_VALIDACION) -> dict:
    """Entrena, elige el umbral y puntúa la prueba con lo que se sabía el día `corte`.

    Solo se usan etiquetas maduras antes del corte (fecha_madurez < corte). De ellas, los
    `meses_validacion` meses más recientes eligen el umbral y los anteriores entrenan.
    `prueba` son las facturas a evaluar, con su etiqueta madura final.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    corte_col = F.lit(str(corte)).cast("date")
    conocidas = modelo_factura.filter((F.col("fecha_madurez") < corte_col) & F.col(ETIQUETA).isNotNull())
    meses = sorted({(r["anio"], r["mes"]) for r in conocidas.select("anio", "mes").distinct().take(1000)})
    resultado = {"corte": str(corte), "n_maduras": conocidas.count(), "n_prueba": prueba.count()}
    if len(meses) <= meses_validacion:
        return {**resultado, "estado": "no_evaluable_sin_meses_suficientes"}
    inicio_val = _primer_dia(*meses[-meses_validacion])
    entrenamiento = conocidas.filter(F.col("fecha") < F.lit(str(inicio_val)).cast("date"))
    validacion = conocidas.filter(F.col("fecha") >= F.lit(str(inicio_val)).cast("date"))
    return {**resultado, **entrenar_validar_probar(entrenamiento, validacion, prueba)}


def entrenar_validar_probar(entrenamiento, validacion, prueba) -> dict:
    """Entrena con `entrenamiento`, elige el umbral en `validacion` y puntúa `prueba` sin tocarlo."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    clases = {r[ETIQUETA] for r in entrenamiento.select(ETIQUETA).distinct().take(3)}
    if clases != {0.0, 1.0}:
        return {"estado": "no_evaluable_entrenamiento_sin_dos_clases"}
    modelo = entrenar_clasificador_s12(entrenamiento.withColumn("madura", F.lit(True)))
    umbral = elegir_umbral(_probabilidades(modelo, validacion))
    m = matriz(_probabilidades(modelo, prueba), umbral["umbral"]) if umbral["umbral"] is not None else {}
    return {"estado": "evaluado", "umbral": umbral["umbral"],
            "precision_validacion": umbral["precision"], "recall_validacion": umbral["recall"],
            "cumple_recall": umbral["cumple_recall"], **m}


def evaluar_s12(modelo_factura, inicio: str = config.INICIO_EVAL_ADELANTE, fin: str | None = None):
    """Evaluación hacia adelante, mes a mes desde `inicio` (Tabla 4.7).

    Para cada mes M: corte = primer día de M; se entrena y se elige el umbral con lo
    conocido antes del corte, y se puntúan las facturas de M que tienen etiqueta madura.
    Devuelve un DataFrame de pandas pequeño (una fila por mes) para acumular métricas (FR08).
    """
    import pandas as pd  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    anio, mes = (int(x) for x in inicio.split("-"))
    mes_actual = _primer_dia(anio, mes)
    ultimo = modelo_factura.agg(F.max("fecha")).take(1)[0][0]
    fin_fecha = _primer_dia(*(int(x) for x in fin.split("-"))) if fin else _primer_dia(ultimo.year, ultimo.month)
    filas = []
    while mes_actual <= fin_fecha:
        prueba = modelo_factura.filter(
            (F.col("anio") == mes_actual.year) & (F.col("mes") == mes_actual.month)
            & F.coalesce(F.col("madura"), F.lit(False)) & F.col(ETIQUETA).isNotNull())
        filas.append({"mes": f"{mes_actual:%Y-%m}", **evaluar_corte(modelo_factura, mes_actual, prueba)})
        mes_actual = _sumar_meses(mes_actual, 1)
    return pd.DataFrame(filas)


def evaluar_2022_2023(modelo_factura) -> dict:
    """Evaluación inicial de la Tabla 4.7: entrena con feb-ago 2022, valida con set-dic 2022 y prueba con 2023.

    Es retrospectiva: usa las etiquetas ya maduras. Los meses de validación son los de la
    Tabla 4.6b (set-dic 2022); el umbral elegido ahí no se toca al puntuar 2023.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    maduras = modelo_factura.filter(F.coalesce(F.col("madura"), F.lit(False)) & F.col(ETIQUETA).isNotNull())
    fecha = F.col("fecha")
    entrenamiento = maduras.filter(fecha < F.lit("2022-09-01").cast("date"))
    validacion = maduras.filter((fecha >= F.lit("2022-09-01").cast("date")) & (fecha < F.lit("2023-01-01").cast("date")))
    prueba = maduras.filter(F.col("anio") == 2023)
    return {"evaluacion": "2022 frente a 2023", "n_entrenamiento": entrenamiento.count(),
            "n_validacion": validacion.count(), "n_prueba": prueba.count(),
            **entrenar_validar_probar(entrenamiento, validacion, prueba)}
