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
