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


def elegir_umbral(pares, meta: float = config.META_PRECISION) -> dict:
    """Umbral de decisión como dice el informe (sección 4.3, «Desbalance de clases»).

    Es el MENOR valor de probabilidad con el que la precisión de la clase positiva alcanza
    la meta (META_PRECISION = 0.70) en los meses de validación. Así se marca el mayor número
    de facturas posible sin bajar de la precisión exigida: el falso positivo recae en un
    trabajador. El recall mínimo de 0.50 no se usa aquí: es la regla para reemplazar el
    modelo vigente (`registro.promover_si_mejora`).

    Los candidatos son las probabilidades observadas en la validación, no una rejilla
    arbitraria. Si ningún umbral alcanza la meta, se toma el de mayor precisión (y, entre
    iguales, el menor) y `cumple_meta` queda en False, para que se vea en la evaluación.
    """
    positivos = sum(1 for _, y in pares if y == 1)
    candidatos = []
    for u in sorted({p for p, _ in pares}):
        m = matriz(pares, u)
        marcadas = m["tp"] + m["fp"]
        precision = m["tp"] / marcadas if marcadas else 0.0
        recall = m["tp"] / positivos if positivos else 0.0
        candidatos.append({"umbral": u, "precision": precision, "recall": recall,
                           "cumple_meta": marcadas > 0 and precision >= meta})
    if not candidatos:
        return {"umbral": None, "precision": None, "recall": None, "cumple_meta": False}
    cumplen = [c for c in candidatos if c["cumple_meta"]]
    if cumplen:
        return cumplen[0]                                  # el menor umbral que alcanza la meta
    return max(candidatos, key=lambda c: (c["precision"], -c["umbral"]))


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
            "cumple_meta": umbral["cumple_meta"], **m}


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


# --- Puntuación al llegar la factura a logística (FR12; informe v17, 4.3 «Cómo se usa») -----
def puntuar_s12(df_nuevas, modelo, umbral: float, version_modelo: str):
    """Probabilidad de descuadre de cada factura nueva con el modelo vigente.

    `umbral` y `version_modelo` salen de la ficha del vigente (`registro.vigente()`): el
    umbral es el que se eligió en la validación y no se recalcula al puntuar. Devuelve
    factura_id, probabilidad, alerta_s12 (1 si probabilidad ≥ umbral) y version_modelo. No
    hace falta la etiqueta: la factura acaba de llegar y todavía no se sabe si descuadra.
    """
    from pyspark.ml.functions import vector_to_array  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    datos = df_nuevas if ETIQUETA in df_nuevas.columns else df_nuevas.withColumn(ETIQUETA, F.lit(None))
    prob = vector_to_array("probability").getItem(1)
    return (modelo.transform(preparar_variables(datos))
            .select("factura_id", prob.alias("probabilidad"))
            .withColumn("alerta_s12", (F.col("probabilidad") >= F.lit(float(umbral))).cast("int"))
            .withColumn("version_modelo", F.lit(version_modelo)))


def alertas_s12(puntuadas, facturas):
    """Facturas con alerta_s12 = 1 → filas de fact_alerta (contrato fact_alerta_base + probabilidad).

    `facturas`: las mismas facturas con fecha, unidad_id, codigo_scop y kg. tipo = «modelo»,
    puntaje = probabilidad y el motivo lleva la versión del modelo que la marcó. Las facturas
    bajo el umbral no son alertas y no entran a la bandeja; su probabilidad queda en
    `puntuadas` para el semáforo de pago.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    from src.glue import senales_spark  # noqa: PLC0415

    marcadas = (puntuadas.filter(F.col("alerta_s12") == 1)
                .join(facturas.select("factura_id", "fecha", "unidad_id", "codigo_scop", "kg"),
                      "factura_id", "inner"))
    filas = senales_spark._alertas(  # noqa: SLF001
        marcadas, "S12", F.concat(F.lit("modelo_s12_"), F.col("version_modelo")), kg=F.col("kg"),
        puntaje=F.col("probabilidad"), tipo="modelo", unidad=F.col("unidad_id"),
        factura=F.col("factura_id"), scop=F.col("codigo_scop"))
    return (filas.join(marcadas.select("factura_id", "probabilidad"), "factura_id", "left")
            .select(*senales_spark.COLUMNAS_ALERTA, "probabilidad"))


# --- Regresión del combustible esperado (FR09; informe v16, 4.3 y Tablas 4.6b y 4.7) ---------
def _volumen_del_rol(unidad_mes):
    """kg_movidos: kg vendidos en reparto y transportados en transporte (igual que el modelo base)."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    return unidad_mes.withColumn(
        "kg_movidos", F.when(F.col("rol") == "reparto", F.col("kg_vendidos"))
                       .otherwise(F.col("kg_transportados")).cast("double"))


def pipeline_combustible(reg_param: float = 0.0):
    """StringIndexer y OneHotEncoder del rol, VectorAssembler y LinearRegression, sin escalar.

    Sin escalado el coeficiente de kg_movidos queda en soles por kg (× 1 000 = S/ por t).
    """
    from pyspark.ml import Pipeline  # noqa: PLC0415
    from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler  # noqa: PLC0415
    from pyspark.ml.regression import LinearRegression  # noqa: PLC0415

    return Pipeline(stages=[
        StringIndexer(inputCol="rol", outputCol="rol_idx", handleInvalid="keep"),
        OneHotEncoder(inputCols=["rol_idx"], outputCols=["rol_vec"], handleInvalid="keep"),
        VectorAssembler(inputCols=["kg_movidos", "rol_vec"], outputCol="features_comb"),
        LinearRegression(featuresCol="features_comb", labelCol="gasto_combustible",
                         predictionCol="combustible_esperado", regParam=reg_param,
                         standardization=False),
    ])


def _fuera_de_pliegue(datos, reg_param: float):
    """Predicciones por exclusión mensual: cada mes se predice con un modelo que no lo vio.

    Para el mismo mes, el modelo trivial predice la mediana del gasto en los demás meses.
    """
    from functools import reduce  # noqa: PLC0415

    from pyspark.sql import functions as F  # noqa: PLC0415

    periodos = sorted({(r["anio"], r["mes"]) for r in datos.select("anio", "mes").distinct().take(1000)})
    partes = []
    for anio, mes in periodos:
        es_mes = (F.col("anio") == anio) & (F.col("mes") == mes)
        entrenamiento, prueba = datos.filter(~es_mes), datos.filter(es_mes)
        mediana = entrenamiento.agg(F.expr("percentile(gasto_combustible, 0.5)")).take(1)[0][0]
        pred = (pipeline_combustible(reg_param).fit(entrenamiento).transform(prueba)
                .withColumn("combustible_trivial", F.lit(mediana).cast("double")))
        partes.append(pred.select("unidad_id", "rol", "anio", "mes", "kg_movidos", "gasto_combustible",
                                  "combustible_esperado", "combustible_trivial"))
    return reduce(lambda a, b: a.unionByName(b), partes), len(periodos)


def regresion_combustible(unidad_mes, rejilla=config.REGRESION_REGPARAM) -> dict:
    """Combustible esperado por unidad-mes con validación por exclusión mensual.

    Entrada: interfaz `unidad_mes` del WP 0.8. Solo entran las unidades-mes con volumen y
    gasto de combustible positivos (las demás no son evaluables y se cuentan).
    Elige el regParam de la rejilla con menor RMSE fuera de pliegue y devuelve:
      * `rmse`, `r2` y `rmse_trivial` (mediana del gasto de los otros meses) del elegido;
      * `soles_por_t`: el coeficiente de kg_movidos × 1 000, ajustado con todos los meses;
      * `residuos`: DataFrame con el residuo (real − esperado) por unidad-mes, que alimenta S9.
    """
    from pyspark.ml.evaluation import RegressionEvaluator  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    base = _volumen_del_rol(unidad_mes)
    evaluables = base.filter((F.col("kg_movidos") > 0) & (F.col("gasto_combustible") > 0))
    datos = evaluables.withColumn("gasto_combustible", F.col("gasto_combustible").cast("double"))
    rmse_de = lambda df, col: RegressionEvaluator(  # noqa: E731
        labelCol="gasto_combustible", predictionCol=col, metricName="rmse").evaluate(df)

    candidatos = []
    for reg in rejilla:
        pred, pliegues = _fuera_de_pliegue(datos, float(reg))
        candidatos.append((rmse_de(pred, "combustible_esperado"), float(reg), pred, pliegues))
    rmse, reg_elegido, pred, pliegues = min(candidatos, key=lambda c: c[0])

    final = pipeline_combustible(reg_elegido).fit(datos).stages[-1]
    r2 = RegressionEvaluator(labelCol="gasto_combustible", predictionCol="combustible_esperado",
                             metricName="r2").evaluate(pred)
    residuos = pred.withColumn("residuo_combustible", F.col("gasto_combustible") - F.col("combustible_esperado"))
    rmse_trivial = rmse_de(pred, "combustible_trivial")
    return {"reg_param": reg_elegido, "rmse": rmse, "r2": r2, "rmse_trivial": rmse_trivial,
            "mejor_que_trivial": rmse < rmse_trivial, "pliegues": pliegues,
            "soles_por_t": float(final.coefficients[0]) * 1000.0, "intercepto": float(final.intercept),
            "n_evaluables": datos.count(), "n_no_evaluables": base.count() - datos.count(),
            "rmse_por_regparam": {c[1]: c[0] for c in candidatos}, "residuos": residuos}
