"""Medición de la operación con entregas mensuales (FR14; informe v17, 4.3 y Tabla 4.8e).

La corrida `--modo operacion` recorre los dos tramos mes a mes y en cada mes mide con lo que
había hasta el último día de ese mes: todas las tablas se filtran por fecha ≤ fin de mes
antes de medir, así una medida no cambia cuando llegan meses posteriores. La verdad contra
la que se compara (la etiqueta S12 madura de cada factura) es la final: eso es lo que se mide.

Grano de gold/fact_operacion: mes × tramo × medida (Tabla 4.9). Tramos:
  * unidades, ene-2020 a feb-2021: unidades en rojo, kg en rojo y kg bajo control;
  * facturas, feb-2022 a jul-2023: descuadres marcados en la misma carga, precisión de las
    alertas (acumulada, con intervalo bootstrap), pagos retenidos a tiempo, monto retenido y
    retenciones innecesarias;
  * clientes, en los meses con ventas por cliente: ventas revisadas por S5 o S10;
  * los dos primeros, además, el tiempo hasta la alerta; la estabilidad por trimestre se
    calcula al final sobre la serie (`estabilidad_trimestral`).
Lo que la entrada no permite medir queda con valor nulo y su causa en `nota` (CLAUDE.md).

Rojo el día del pago (Tabla 4.8i): la factura no tiene su pareja en logística a esa fecha
(solo está en tesorería, o logística la registró después del pago) o sus kilos no coinciden.
El día del pago es fecha_pago y, para los proveedores que no la registran, fecha_vence.
"""
from __future__ import annotations

import calendar

import pandas as pd

from src.common import config
from src.models import metricas

TRAMOS = {"unidades": ("2020-01-01", "2021-02-28"), "facturas": ("2022-02-01", "2023-07-31"),
          "clientes": None}
COLUMNAS = ["anio", "mes", "tramo", "medida", "valor", "numerador", "denominador", "ic_inferior",
            "ic_superior", "nota"]
ESQUEMA = ("anio int, mes int, tramo string, medida string, valor double, numerador double, "
           "denominador double, ic_inferior double, ic_superior double, nota string")
METAS = {"descuadres_misma_carga": 0.50, "precision_alertas": config.META_PRECISION,
         "pagos_retenidos_a_tiempo": 0.50, "retenciones_innecesarias": 0.30,
         "tiempo_hasta_alerta_min": 5.0, "estabilidad_trimestral": 0.10}


def _fin_de_mes(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}-{calendar.monthrange(anio, mes)[1]:02d}"


def _fila(anio, mes, tramo, medida, valor=None, num=None, den=None, nota=None, ic=(None, None)) -> dict:
    return {"anio": anio, "mes": mes, "tramo": tramo, "medida": medida,
            "valor": None if valor is None else float(valor), "numerador": None if num is None else float(num),
            "denominador": None if den is None else float(den), "ic_inferior": ic[0], "ic_superior": ic[1],
            "nota": nota}


def _razon(anio, mes, tramo, medida, num, den, nota_sin_den: str) -> dict:
    if not den:
        return _fila(anio, mes, tramo, medida, None, num, den, nota_sin_den)
    return _fila(anio, mes, tramo, medida, num / den, num, den)


def _hasta(df, fin: str, columna: str = "fecha"):
    """Solo lo conocido hasta `fin`: lo que tiene fecha posterior no existe todavía."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    return df.filter(F.col(columna) <= F.lit(fin).cast("date"))


def _uno(df, *expresiones):
    return df.agg(*expresiones).take(1)[0]


# --- Tramo de unidades --------------------------------------------------------------
def _unidades(anio, mes, tablas, fin) -> list[dict]:
    from pyspark.sql import functions as F  # noqa: PLC0415

    serie = _hasta(tablas["fact_serie"], fin, "periodo").filter(
        (F.col("entidad_tipo") == "unidad") & (F.col("granularidad") == "mes"))
    rojas = serie.filter((F.col("anio") == anio) & (F.col("mes") == mes) & (F.col("estado") == "rojo"))
    r = _uno(rojas, F.countDistinct("entidad_id").alias("n"), F.sum("kg_acumulados").alias("kg"))
    n, kg = int(r["n"] or 0), float(r["kg"] or 0.0)
    filas = [_fila(anio, mes, "unidades", "unidades_en_rojo", n, n),
             _fila(anio, mes, "unidades", "kg_en_rojo", kg, kg)]
    balance = tablas.get("fact_balance_planta")
    if balance is None:
        filas.append(_fila(anio, mes, "unidades", "kg_bajo_control", None, kg, None,
                           "la entrada no trae fact_balance_planta"))
        return filas
    inicio = TRAMOS["unidades"][0]
    b = balance.withColumn("_f", F.make_date("anio", "mes", F.lit(1)))
    b = b.filter((F.col("_f") >= F.lit(inicio).cast("date")) & (F.col("_f") <= F.lit(fin).cast("date")))
    no_explicados = _uno(b, F.sum("kg_no_explicados").alias("d"))["d"]
    den = float(no_explicados) if no_explicados is not None and no_explicados > 0 else None
    filas.append(_razon(anio, mes, "unidades", "kg_bajo_control", kg, den,
                        "sin diferencia no explicada positiva en el periodo"))
    return filas


# --- Tramo de clientes --------------------------------------------------------------
def _clientes(anio, mes, tablas, fin) -> list[dict]:
    from pyspark.sql import functions as F  # noqa: PLC0415

    a = _hasta(tablas["fact_alerta"], fin).filter(
        F.col("senal").isin("S5", "S10") & (F.col("anio") == anio) & (F.col("mes") == mes))
    r = _uno(a, F.countDistinct("id_alerta").alias("n"), F.sum("kg").alias("kg"))
    n, kg = int(r["n"] or 0), float(r["kg"] or 0.0)
    return [_fila(anio, mes, "clientes", "ventas_revisadas", n, n),
            _fila(anio, mes, "clientes", "kg_ventas_revisadas", kg, kg)]


# --- Tramo de facturas --------------------------------------------------------------
def _facturas(anio, mes, tablas, fin) -> list[dict]:
    from pyspark.sql import functions as F  # noqa: PLC0415

    mf = tablas["modelo_factura"]
    alertas = _hasta(tablas["fact_alerta"], fin).filter(F.col("senal") == "S12")
    del_mes = (F.col("anio") == anio) & (F.col("mes") == mes)
    filas = []

    # Descuadres del mes marcados en la misma carga (por el modelo o por la regla).
    descuadres = _hasta(mf, fin).filter(del_mes & (F.col("etiqueta_s12") == 1))
    marcadas_mes = alertas.filter(del_mes).select("factura_id").distinct()
    den = descuadres.count()
    num = descuadres.join(marcadas_mes, "factura_id", "left_semi").count()
    filas.append(_razon(anio, mes, "facturas", "descuadres_misma_carga", num, den, "sin descuadres S12 en el mes"))

    # Precisión de las alertas del modelo, acumulada desde el inicio del tramo, con IC bootstrap.
    inicio = TRAMOS["facturas"][0]
    modelo = (alertas.filter((F.col("tipo") == "modelo") & (F.col("fecha") >= F.lit(inicio).cast("date")))
              .select("factura_id").distinct())
    y = [float(r["etiqueta_s12"]) for r in mf.join(modelo, "factura_id", "left_semi")
         .filter(F.col("etiqueta_s12").isNotNull()).select("etiqueta_s12").take(100_000)]
    if y:
        b = metricas.bootstrap_precision(y, [1] * len(y))
        filas.append(_fila(anio, mes, "facturas", "precision_alertas", sum(y) / len(y), sum(y), len(y),
                           ic=(b["li"], b["ls"])))
    else:
        filas.append(_fila(anio, mes, "facturas", "precision_alertas", None, 0, 0,
                           "sin alertas del modelo con etiqueta madura hasta el mes"))

    # Semáforo el día del pago.
    dia_pago = F.coalesce(F.col("fecha_pago"), F.col("fecha_vence"))
    pagadas = (mf.withColumn("_dia_pago", dia_pago)
               .filter((F.year("_dia_pago") == anio) & (F.month("_dia_pago") == mes)))
    rojo = ((F.col("clase_s12") == "solo_tesoreria") | (F.col("clase_s12") == "kg_distinto")
            | ((F.col("clase_s12") != "solo_tesoreria") & (F.col("fecha") > F.col("_dia_pago"))))
    pagadas = pagadas.withColumn("_rojo", F.coalesce(rojo, F.lit(False)))
    tiene_monto = "monto_soles" in mf.columns
    r = _uno(pagadas,
             F.sum(F.when((F.col("etiqueta_s12") == 1) & F.col("_rojo"), 1).otherwise(0)).alias("real_rojo"),
             F.sum(F.when(F.col("etiqueta_s12") == 1, 1).otherwise(0)).alias("real"),
             F.sum(F.when(F.col("_rojo"), 1).otherwise(0)).alias("rojas"),
             F.sum(F.when((F.col("etiqueta_s12") == 0) & F.col("_rojo"), 1).otherwise(0)).alias("innecesarias"),
             (F.sum(F.when(F.col("_rojo"), F.col("monto_soles"))) if tiene_monto else F.lit(None)).alias("monto"))
    filas.append(_razon(anio, mes, "facturas", "pagos_retenidos_a_tiempo", int(r["real_rojo"] or 0),
                        int(r["real"] or 0), "sin descuadres reales pagados en el mes"))
    filas.append(_fila(anio, mes, "facturas", "monto_retenido_soles", r["monto"], r["monto"], None,
                       None if tiene_monto else "la entrada no trae monto_soles de las facturas"))
    filas.append(_razon(anio, mes, "facturas", "retenciones_innecesarias", int(r["innecesarias"] or 0),
                        int(r["rojas"] or 0), "sin facturas en rojo el día de su pago"))
    return filas


def _tiempo_hasta_alerta(anio, mes, tramo, tablas) -> dict:
    """Mediana de minutos entre la llegada a landing/ y la fila en fact_alerta (registro de cargas)."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    cargas = tablas.get("cargas")
    if cargas is None:
        return _fila(anio, mes, tramo, "tiempo_hasta_alerta_min", nota="la entrada no trae el registro de cargas")
    c = cargas.filter((F.col("tramo") == tramo) & (F.col("anio") == anio) & (F.col("mes") == mes))
    minutos = (F.unix_timestamp("alerta_escrita") - F.unix_timestamp("llegada_landing")) / 60.0
    r = _uno(c.withColumn("_min", minutos), F.expr("percentile(_min, 0.5)").alias("m"), F.count("*").alias("n"))
    if not r["n"]:
        return _fila(anio, mes, tramo, "tiempo_hasta_alerta_min", nota="sin cargas registradas en el mes")
    return _fila(anio, mes, tramo, "tiempo_hasta_alerta_min", r["m"], None, r["n"])


def medir(mes: str, tramo: str, tablas: dict) -> list[dict]:
    """Medidas de la Tabla 4.8e para `mes` («AAAA-MM») y `tramo`, con lo conocido hasta fin de mes.

    tablas: DataFrames de Spark de Gold. unidades: fact_serie y, opcional, fact_balance_planta;
    facturas: modelo_factura (con monto_soles si se quiere el monto) y fact_alerta; clientes:
    fact_alerta. Opcional en los dos tramos: cargas (tramo, anio, mes, llegada_landing,
    alerta_escrita) para el tiempo hasta la alerta.
    """
    anio, m = (int(x) for x in mes.split("-"))
    fin = _fin_de_mes(anio, m)
    if tramo == "unidades":
        return _unidades(anio, m, tablas, fin) + [_tiempo_hasta_alerta(anio, m, tramo, tablas)]
    if tramo == "facturas":
        return _facturas(anio, m, tablas, fin) + [_tiempo_hasta_alerta(anio, m, tramo, tablas)]
    if tramo == "clientes":
        return _clientes(anio, m, tablas, fin)
    raise ValueError(f"tramo desconocido: {tramo}")


def meses_del_tramo(tramo: str) -> list[str]:
    ini, fin = TRAMOS[tramo]
    return [p.strftime("%Y-%m") for p in pd.period_range(ini[:7], fin[:7], freq="M")]


def medir_tramo(tramo: str, tablas: dict, meses: list[str] | None = None) -> pd.DataFrame:
    """Recorre el tramo mes a mes (o los `meses` dados, p. ej. los que tienen ventas por cliente)."""
    filas = [f for mes in (meses or meses_del_tramo(tramo)) for f in medir(mes, tramo, tablas)]
    return pd.DataFrame(filas, columns=COLUMNAS)


def estabilidad_trimestral(operacion: pd.DataFrame, medida: str = "precision_alertas") -> pd.DataFrame:
    """|precisión acumulada al cierre del trimestre − la del trimestre anterior| (meta < 0.10)."""
    d = operacion[(operacion["medida"] == medida) & operacion["valor"].notna()].copy()
    if d.empty:
        return pd.DataFrame(columns=COLUMNAS)
    d["trimestre"] = pd.PeriodIndex(pd.to_datetime(dict(year=d["anio"], month=d["mes"], day=1)), freq="Q")
    cierre = d.sort_values(["anio", "mes"]).groupby("trimestre").tail(1).reset_index(drop=True)
    filas = []
    for previo, actual in zip(cierre.iloc[:-1].itertuples(), cierre.iloc[1:].itertuples()):
        filas.append(_fila(actual.anio, actual.mes, actual.tramo, "estabilidad_trimestral",
                           abs(actual.valor - previo.valor), actual.valor, previo.valor))
    return pd.DataFrame(filas, columns=COLUMNAS)


def a_spark(spark, operacion: pd.DataFrame):
    """DataFrame de Spark con el esquema de gold/fact_operacion, para escribirlo en Iceberg.

    Pasa por pandas con los tipos del esquema, así Spark lo recibe por Arrow.
    """
    d = operacion.reindex(columns=COLUMNAS).copy()
    for c in ("anio", "mes"):
        d[c] = d[c].astype("int32")
    for c in ("valor", "numerador", "denominador", "ic_inferior", "ic_superior"):
        d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
    for c in ("tramo", "medida", "nota"):
        d[c] = d[c].astype(object).where(d[c].notna(), None)
    return spark.createDataFrame(d, ESQUEMA)
