"""Tabla `calidad_silver`: la calidad de cada corrida de Silver, lista para Gold (A10).

Cada vez que la Lambda de limpieza procesa una fuente deja un JSON en
`silver/_control/<tabla>/<fuente>.json` con lo que midio esa corrida. Este modulo los
junta en una sola tabla para que el tablero y el job de Gold puedan responder dos
preguntas sin abrir archivos sueltos: que tan completa quedo cada tabla y si cumple las
metas de la Tabla 3.7.

Importa porque `CLAUDE.md` prohibe publicar una metrica de Gold cuando sus fuentes Silver
incumplen las metas de su contrato: `cumple` es la columna que permite ver ese bloqueo.

Lo llama el job de Gold (W07) y se lee con un esquema declarado, nunca con inferSchema.

`bloqueos()` da el paso que falta (commit AR09): traduce esas filas a la pregunta que
de verdad se hace al publicar, que es por KPI y no por tabla. Un KPI se publica solo si
todas sus fuentes Silver cumplen; si alguna incumple o no se midio, el KPI sale bloqueado
con el nombre de la tabla y de la meta, para que el tablero muestre el motivo en lugar de
una cifra calculada sobre datos que no pasaron el contrato.

Uso local:
    python -m src.quality.calidad_silver
"""
from __future__ import annotations

from src.common import config, rutas

# Metas de la Tabla 3.7: metrica de calidad -> umbral minimo que debe alcanzar.
# Solo se evalua la meta cuya metrica esta presente en la corrida; una tabla que no
# declara placas no incumple META_PLACA_VALIDA, simplemente no se le aplica.
METAS: dict[str, tuple[str, float]] = {
    "placa_valida": ("META_PLACA_VALIDA", config.META_PLACA_VALIDA),
    "kg_con_placa_valida": ("META_PLACA_VALIDA", config.META_PLACA_VALIDA),
    "kg_positivo": ("META_KG_EN_RANGO", config.META_KG_EN_RANGO),
    "scop_presente": ("META_SCOP_COMPRAS", config.META_SCOP_COMPRAS),
}

# Metricas que cuentan filas corregidas, no rechazadas: la fila se conserva y se arregla.
# Crece a medida que las transformaciones registren mas correcciones.
CORRECCIONES = ("fechas_invertidas",)

# Tasas de validez que se publican como columna propia cuando la corrida las trae.
VALIDEZ = ("placa_valida", "kg_con_placa_valida", "kg_positivo", "scop_presente",
           "fecha_valida", "documento_presente", "mes_reconocido", "entidad_id_presente")

# Estos contratos declaran que la fuente no trae placa y que no se atribuye a una unidad.
# Un 0 en `placa_valida` es «no aplica», no un incumplimiento de META_PLACA_VALIDA.
FUENTES_SIN_PLACA = {
    "gastos": ("gastos_proyecto_2019", "otros_gastos_2020"),
}


# Fuentes Silver de cada KPI de la Tabla 4.10. Se deriva de la tabla de Gold que lee su
# vista (`sql/athena/vistas/v_kpi_*.sql`) y de los contratos de `contracts/` que la
# alimentan. `opcionales` son las fuentes cuya ausencia el KPI ya declara como supuesto
# en su propia vista, asi que no lo bloquean: el stock fisico no esta medido y el KPI 1
# publica `stock_es_supuesto` en lugar de callarlo.
KPI_FUENTES: dict[str, dict] = {
    "kpi_1": {"tabla_gold": "fact_balance_planta",
              "exigidas": ("compras_glp", "ventas_detalle"),
              "opcionales": ("produccion_diaria",)},
    "kpi_2": {"tabla_gold": "fact_balance_planta",
              "exigidas": ("compras_glp", "ventas_detalle"),
              "opcionales": ("produccion_diaria",)},
    "kpi_3": {"tabla_gold": "modelo_factura",
              "exigidas": ("compras_glp", "pedidos_proveedor"),
              "opcionales": ()},
    "kpi_4": {"tabla_gold": "fact_unidad_mes",
              "exigidas": ("ventas_unidad_mes", "unidades", "gastos"),
              "opcionales": ()},
    "kpi_5": {"tabla_gold": "v_alerta",
              "exigidas": ("compras_glp", "scop", "ventas_detalle", "unidades"),
              "opcionales": ()},
}

PUBLICADO = "publicado"
BLOQUEADO = "bloqueado"
SIN_MEDIR = "sin_medir"

# Tope de filas que se traen al driver: `calidad_silver` tiene una fila por tabla y
# fuente (decenas), no una por dato. Con `take` el limite es explicito; `collect()` esta
# prohibido en este proyecto justamente para que nadie lo descubra con una tabla grande.
LIMITE_FILAS = 500


def _filas(calidad) -> list[dict]:
    """Acepta un DataFrame de `construir()` o cualquier iterable de diccionarios."""
    if hasattr(calidad, "take"):
        return [fila.asDict() for fila in calidad.take(LIMITE_FILAS)]
    return [dict(fila) for fila in calidad]


def _estado_por_tabla(calidad) -> dict[str, dict]:
    """Resume las corridas de cada tabla: una sola fuente que incumple basta.

    Una tabla Silver se arma de varias fuentes (varias hojas o varios libros). Si una
    de esas corridas no cumple, la tabla no cumple: la metrica de Gold se calcula sobre
    la tabla completa, no sobre la fuente que si paso.
    """
    resumen: dict[str, dict] = {}
    for fila in _filas(calidad):
        tabla = fila.get("tabla")
        if not tabla:
            continue
        info = resumen.setdefault(tabla, {"cumple": True, "metas_incumplidas": [],
                                          "fuentes": [], "fuentes_que_incumplen": []})
        info["fuentes"].append(fila.get("fuente"))
        metas = list(fila.get("metas_incumplidas") or [])
        if not fila.get("cumple", True) or metas:
            info["cumple"] = False
            info["fuentes_que_incumplen"].append(fila.get("fuente"))
            for meta in metas:
                if meta not in info["metas_incumplidas"]:
                    info["metas_incumplidas"].append(meta)
    return resumen


def bloqueos(calidad, kpi_fuentes: dict | None = None) -> dict[str, dict]:
    """Que KPI se puede publicar con esta calidad de Silver, y si no, por que.

    `CLAUDE.md` («Contratos y capas») prohibe publicar una metrica de Gold cuando sus
    fuentes Silver incumplen las metas de su contrato, y pide informar el bloqueo. Esto
    es ese informe: por cada KPI, su estado y la lista de tablas con la meta que falló.

    Tres estados, y la diferencia entre los dos ultimos importa:

    * `publicado`: todas sus fuentes exigidas se midieron y cumplen.
    * `bloqueado`: alguna fuente incumple una meta de la Tabla 3.7. Hay un dato y es malo.
    * `sin_medir`: alguna fuente no tiene corrida en `silver/_control/`. No hay dato.
      Publicar un KPI en este estado seria presentar como medicion algo que nadie midio.
    """
    kpi_fuentes = kpi_fuentes or KPI_FUENTES
    por_tabla = _estado_por_tabla(calidad)

    salida: dict[str, dict] = {}
    for kpi, cfg in kpi_fuentes.items():
        incumplen, sin_medir, metas = [], [], []
        for tabla in cfg["exigidas"]:
            info = por_tabla.get(tabla)
            if info is None:
                sin_medir.append(tabla)
                continue
            if not info["cumple"]:
                incumplen.append(tabla)
                metas += [m for m in info["metas_incumplidas"] if m not in metas]

        # Una fuente opcional que incumple no bloquea, pero se informa: el KPI ya declara
        # ese supuesto en su vista y el tablero lo etiqueta.
        opcionales = [t for t in cfg["opcionales"]
                      if t in por_tabla and not por_tabla[t]["cumple"]]
        opcionales += [t for t in cfg["opcionales"] if t not in por_tabla]

        if incumplen:
            estado = BLOQUEADO
            motivo = (f"{', '.join(sorted(incumplen))} incumple "
                      f"{', '.join(sorted(metas))} (Tabla 3.7)")
        elif sin_medir:
            estado = SIN_MEDIR
            motivo = (f"sin corrida en silver/_control/ de {', '.join(sorted(sin_medir))}: "
                      "no hay nada medido que publicar")
        else:
            estado = PUBLICADO
            motivo = "todas sus fuentes Silver cumplen las metas de la Tabla 3.7"

        salida[kpi] = {
            "estado": estado,
            "publicable": estado == PUBLICADO,
            "tabla_gold": cfg["tabla_gold"],
            "tablas_que_incumplen": sorted(incumplen),
            "tablas_sin_medir": sorted(sin_medir),
            "metas_incumplidas": sorted(metas),
            "fuentes_opcionales_ausentes_o_incumplidas": sorted(set(opcionales)),
            "motivo": motivo,
        }
    return salida


def kpi_bloqueados(calidad, kpi_fuentes: dict | None = None) -> list[str]:
    """Solo los nombres de los KPI que no se pueden publicar. Util para el tablero."""
    return sorted(k for k, v in bloqueos(calidad, kpi_fuentes).items() if not v["publicable"])


def esquema():
    """Esquema declarado del JSON de control (`src/silver/procesar.py`)."""
    from pyspark.sql import types as T  # noqa: PLC0415

    hoja = T.StructType([
        T.StructField("hoja", T.StringType()),
        T.StructField("estado", T.StringType()),
        T.StructField("filas_leidas", T.LongType()),
        T.StructField("filas_efectivas", T.LongType()),
        T.StructField("cortada_por_filas_vacias", T.BooleanType()),
        T.StructField("motivo", T.StringType()),
    ])
    return T.StructType([
        T.StructField("tabla", T.StringType()),
        T.StructField("fuente", T.StringType()),
        T.StructField("familia", T.StringType()),
        T.StructField("generado_utc", T.StringType()),
        T.StructField("estado", T.StringType()),
        T.StructField("filas_leidas", T.LongType()),
        T.StructField("filas_efectivas", T.LongType()),
        T.StructField("filas_salida", T.LongType()),
        T.StructField("filas_con_llave_repetida", T.LongType()),
        T.StructField("celdas_con_dato", T.MapType(T.StringType(), T.LongType())),
        T.StructField("descartes", T.MapType(T.StringType(), T.LongType())),
        T.StructField("calidad", T.MapType(T.StringType(), T.DoubleType())),
        T.StructField("hojas", T.ArrayType(hoja)),
    ])


def _suma_mapa(columna):
    """Suma los valores de un MapType sin traer nada al driver."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    return F.aggregate(F.map_values(columna), F.lit(0).cast("long"),
                       lambda acumulado, v: acumulado + F.coalesce(v, F.lit(0).cast("long")))


def construir(spark, ruta_control: str | None = None):
    """Una fila por tabla y corrida con su completitud, validez, unicidad y si cumple.

    `ruta_control` apunta a `silver/_control/`; por defecto sale de `LAKE_URI`.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    base = ruta_control or rutas.ruta_spark("silver", "_control")
    crudo = (spark.read.schema(esquema())
             .option("multiLine", "true")          # procesar.py escribe el JSON con indent=2
             .json(f"{base.rstrip('/')}/*/*.json"))

    columnas = F.size(F.map_keys(F.col("celdas_con_dato")))
    celdas_posibles = F.col("filas_efectivas") * columnas
    completitud = F.when(celdas_posibles > 0,
                         _suma_mapa(F.col("celdas_con_dato")) / celdas_posibles)
    repetidas = F.coalesce(F.col("filas_con_llave_repetida"), F.lit(0).cast("long"))
    unicidad = F.when(F.col("filas_salida") > 0, 1 - repetidas / F.col("filas_salida"))

    df = (crudo
          .withColumn("columnas_declaradas", columnas)
          .withColumn("completitud", completitud)
          .withColumn("unicidad", unicidad)
          .withColumn("filas_con_llave_repetida", repetidas)
          .withColumn("filas_descartadas", _suma_mapa(F.col("descartes")))
          .withColumn("filas_corregidas",
                      sum((F.coalesce(F.col("calidad").getItem(m), F.lit(0.0)) for m in CORRECCIONES),
                          F.lit(0.0)).cast("long")))

    sin_placa = F.coalesce(
        (F.col("fuente").isin(*FUENTES_SIN_PLACA["gastos"]) & (F.col("tabla") == "gastos")),
        F.lit(False))
    for metrica in VALIDEZ:                        # nula si la corrida no mide esa tasa
        valor = F.col("calidad").getItem(metrica)
        if metrica == "placa_valida":
            valor = F.when(sin_placa, F.lit(None).cast("double")).otherwise(valor)
        df = df.withColumn(metrica, valor)

    # Una meta solo se evalua si su metrica esta presente; si falta, no se incumple.
    incumplidas = F.array_compact(F.array(*[
        F.when(F.col("calidad").getItem(m).isNotNull()
               & (F.col("calidad").getItem(m) < F.lit(umbral))
               & (F.lit(m != "placa_valida") | ~sin_placa), F.lit(nombre))
        for m, (nombre, umbral) in METAS.items()]))

    return (df
            .withColumn("metas_incumplidas", F.array_distinct(incumplidas))
            .withColumn("cumple", F.size(F.col("metas_incumplidas")) == 0)
            .drop("celdas_con_dato", "descartes", "calidad", "hojas"))


if __name__ == "__main__":                         # pragma: no cover - utilidad local
    from src.common.spark import obtener_spark

    sesion = obtener_spark("calidad_silver")
    construir(sesion).show(truncate=False)
    sesion.stop()
