"""Señales determinísticas en Spark para el job de Gold (informe v16, 4.2 y Tabla 4.3).

Son funciones puras: reciben DataFrames de Silver y devuelven alertas con el
contrato `fact_alerta`. El job `src/glue/gold_job.py` (Wilson) las llama; este
módulo no lee ni escribe en el lago.

Esta versión porta a Spark las señales de `src/signals/senales.py` (pandas) con la
misma lógica, para que la conciliación por evento corra repartida en el clúster:

  S1  placa cargada distinta de la facturada            filtro
  S4  carga superior a la capacidad autorizada           join con broadcast(flota)
  S5  volumen a un cliente superior a su capacidad       join con broadcast(maestro)
  S7  operación de una unidad no habilitada para GLP     left_anti con broadcast(flota habilitada)
  S8  venta sin compra que la respalde (circuito SCOP)   left_anti por codigo_scop
  S10 precio de venta bajo la mediana de su canal        ventana con percentile exacto

S2, S3 y S6 leen la tabla Silver `compras_glp` (contrato de WP 0.2: proveedor,
serie, numero, nro_scop, fecha_factura, kg, monto_usd, tipo_cambio, placa_norm):

  S2  compra sin SCOP o con un SCOP repetido en otra factura   ventana por nro_scop
  S3  USD/kg sobre la mediana móvil del proveedor              ventana rangeBetween de días previos
  S6  tipo de cambio igual a 1 o lejos del oficial del día     join con broadcast(calendario BCRP)

S9, S11 y S12 (F04):

  S9  combustible sin venta, o S/ por t con |z robusto| > UMBRAL_Z_MAD en su rol   unidad × mes
  S11 cierre de planta sin medición física (residuo 0 todo el mes) y ajustes manuales   día y mes
  S12 factura sin pareja o con kg distinto entre tesorería y logística   full_outer por documento

Sin collect().
"""
from __future__ import annotations

from src.common import config, schemas

# Tabla 4.3 del informe: descripción y grado de evidencia de cada señal.
# S1, S4 y S7 son indicios porque la muestra es mínima (2 a 9 casos; Tabla 5.3).
CATALOGO: dict[str, tuple[str, str]] = {
    "S1": ("Placa cargada distinta de la facturada", "indicio"),
    "S2": ("Compra sin SCOP o SCOP repetido", "alta"),
    "S3": ("Precio de compra fuera de lo pactado o de la mediana", "media"),
    "S4": ("Carga superior a la capacidad autorizada", "indicio"),
    "S5": ("Volumen a un distribuidor superior a su capacidad", "media"),
    "S6": ("Tipo de cambio distinto del oficial", "alta"),
    "S7": ("Operación de una unidad no habilitada para GLP", "indicio"),
    "S8": ("Venta sin compra que la respalde (circuito SCOP)", "alta"),
    "S9": ("Combustible sin venta o carga proporcional", "media"),
    "S10": ("Precio de venta bajo la mediana de su canal", "media"),
    "S11": ("Cierre de planta sin medición física", "alta"),
    "S12": ("Factura sin segundo registro o con kg distinto entre tesorería y logística", "alta"),
}

COLUMNAS_ALERTA = schemas.CONTRATOS["fact_alerta"].columnas()


def _alertas(df, senal: str, placa: str, kg: str = "kg", puntaje=None):
    """Lleva las filas que disparan una señal al contrato `fact_alerta`."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    puntaje = F.lit(1.0) if puntaje is None else puntaje
    out = df.select(
        F.lit(senal).alias("senal"),
        F.lit("regla").alias("tipo"),
        F.col("fecha").cast("date").alias("fecha"),
        F.col(placa).cast("string").alias("placa_norm"),
        F.col("documento").cast("string").alias("documento"),
        F.col(kg).cast("double").alias("kg"),
        (F.col(kg).cast("double") * F.lit(config.PRECIO_REF_KG)).alias("valor_soles"),
        puntaje.cast("double").alias("puntaje"),
        F.lit(CATALOGO[senal][1]).alias("grado_evidencia"),
        F.lit("pendiente").alias("estado_revision"),
        F.col("anio").cast("int").alias("anio"),
        F.col("mes").cast("int").alias("mes"),
    )
    # Identificador determinístico: la misma alerta en otra corrida tiene el mismo id (MERGE idempotente).
    clave = F.concat_ws("|", F.col("senal"), F.coalesce(F.col("documento"), F.lit("")),
                        F.coalesce(F.col("placa_norm"), F.lit("")))
    out = out.withColumn("id_alerta", F.substring(F.md5(clave), 1, 12))
    return out.select(*COLUMNAS_ALERTA)


def s1(compras):
    """Placa cargada distinta de la facturada en la misma orden."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    d = compras.filter(F.coalesce(F.col("flag_placa_divergente"), F.lit(False)))
    return _alertas(d, "S1", "placa_cargada")


def s4(compras, flota):
    """Carga mayor que la capacidad autorizada del vehículo que la llevó."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cap = flota.select(F.col("placa_norm").alias("_placa_flota"), "capacidad_kg")
    d = (compras.join(broadcast(cap), compras["placa_cargada"] == cap["_placa_flota"], "inner")
         .filter(F.col("kg") > F.col("capacidad_kg")))
    return _alertas(d, "S4", "placa_cargada", puntaje=F.col("kg") / F.col("capacidad_kg"))


def s5(ventas, maestro):
    """Venta a un cliente mayor que la capacidad de almacenamiento de su local."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cap = maestro.select("card_code", F.col("capacidad_kg").alias("cap_local"))
    d = (ventas.join(broadcast(cap), "card_code", "inner")
         .filter(F.col("cap_local").isNotNull() & (F.col("kg") > F.col("cap_local"))))
    return _alertas(d, "S5", "placa_norm", puntaje=F.col("kg") / F.col("cap_local"))


def s7(compras, flota):
    """Compras cargadas en una unidad que no está habilitada para trasladar GLP."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    habilitadas = (flota.filter(F.coalesce(F.col("habilitada"), F.lit(False)))
                   .select(F.col("placa_norm").alias("_placa_hab")).dropna().distinct())
    c = compras.withColumn("_placa", F.col("placa_cargada"))
    d = c.join(broadcast(habilitadas), c["_placa"] == habilitadas["_placa_hab"], "left_anti")
    return _alertas(d, "S7", "_placa")


def s8(ventas, compras):
    """Venta con código SCOP que no cierra con ninguna compra."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    con_scop = ventas.filter(F.col("codigo_scop").isNotNull())
    claves = compras.select("codigo_scop").dropna().distinct()
    d = con_scop.join(claves, "codigo_scop", "left_anti")
    return _alertas(d, "S8", "placa_norm")


def s10(ventas):
    """Precio más de TOL_PRECIO_S10 bajo la mediana de su canal, producto y mes."""
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    w = Window.partitionBy("canal", "id_producto", "anio", "mes")
    # percentile(…, 0.5) es la mediana exacta con interpolación (igual que pandas), no la aproximada.
    v = (ventas.filter(F.col("precio").isNotNull())
         .withColumn("mediana", F.expr("percentile(precio, 0.5)").over(w)))
    d = v.filter(F.col("precio") < F.col("mediana") * F.lit(1 - config.TOL_PRECIO_S10))
    return _alertas(d, "S10", "placa_norm", puntaje=F.lit(1.0) - F.col("precio") / F.col("mediana"))


# --- Señales sobre compras_glp (F03) -----------------------------------------
def preparar_compras(compras_glp):
    """Agrega a compras_glp las columnas comunes de las alertas: fecha, documento y usd_kg.

    documento = «PROVEEDOR SERIE-NUMERO», que es la llave natural de la tabla (los
    proveedores son empresas, no personas naturales). usd_kg queda nulo si falta el
    monto o los kg, o si los kg no son positivos: no se inventa un precio.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    return (compras_glp
            .withColumn("fecha", F.col("fecha_factura").cast("date"))
            .withColumn("documento", F.concat_ws(" ", F.col("proveedor"),
                                                 F.concat_ws("-", F.col("serie"), F.col("numero"))))
            .withColumn("usd_kg", F.when(F.col("kg") > 0, F.col("monto_usd") / F.col("kg"))))


def s2(compras_glp):
    """Factura sin código SCOP, o con un SCOP que aparece en más de una factura.

    Solo se usa el código de la propia factura: las órdenes SCOP (F05) cubren
    ene-jul 2023 y un left_anti contra ellas marcaría como «sin SCOP» todo lo demás.
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    c = preparar_compras(compras_glp)
    scop = F.trim(F.col("nro_scop"))
    sin_scop = scop.isNull() | (scop == "")
    w = Window.partitionBy("nro_scop")
    c = c.withColumn("_facturas_scop", F.when(~sin_scop, F.size(F.collect_set("documento").over(w))))
    d = c.filter(sin_scop | (F.col("_facturas_scop") > 1))
    puntaje = F.when(sin_scop, F.lit(1.0)).otherwise(F.col("_facturas_scop").cast("double"))
    return _alertas(d, "S2", "placa_norm", puntaje=puntaje)


def s3(compras_glp, precios_pactados=None):
    """USD/kg más de TOL_PRECIO_PAGO sobre la mediana móvil del proveedor, o sobre el precio pactado.

    La mediana usa solo las facturas de los VENTANA_MEDIANA_DIAS días anteriores
    (sin el mismo día ni los siguientes), así no hay fuga de información hacia el pasado.
    `precios_pactados` es opcional: columnas proveedor, anio, mes y usd_kg_pactado (F08).
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    c = preparar_compras(compras_glp).withColumn("_dia", F.datediff(F.col("fecha"), F.lit("1970-01-01")))
    w = (Window.partitionBy("proveedor").orderBy("_dia")
         .rangeBetween(-config.VENTANA_MEDIANA_DIAS, -1))
    c = c.withColumn("_mediana", F.expr("percentile(usd_kg, 0.5)").over(w))
    tope = F.lit(1 + config.TOL_PRECIO_PAGO)
    sobre_mediana = F.col("usd_kg") > F.col("_mediana") * tope
    if precios_pactados is not None:
        pactos = precios_pactados.select("proveedor", "anio", "mes", "usd_kg_pactado")
        c = c.join(broadcast(pactos), ["proveedor", "anio", "mes"], "left_outer")
        sobre_pacto = F.col("usd_kg") > F.col("usd_kg_pactado") * tope
        dispara = F.coalesce(sobre_mediana, F.lit(False)) | F.coalesce(sobre_pacto, F.lit(False))
        referencia = F.coalesce(F.col("usd_kg_pactado"), F.col("_mediana"))
    else:
        dispara = F.coalesce(sobre_mediana, F.lit(False))
        referencia = F.col("_mediana")
    d = c.filter(dispara)
    return _alertas(d, "S3", "placa_norm", puntaje=F.col("usd_kg") / referencia - F.lit(1.0))


def calendario_tc(tc_oficial):
    """Tipo de cambio oficial (BCRP, venta) para cada día calendario.

    Los días sin publicación (fines de semana y feriados) toman el último valor
    hábil anterior. La tabla es pequeña (un valor por día), así que la ventana sin
    partición no es un problema y el resultado se une con broadcast().
    Columnas de entrada: fecha y tc_venta (contrato entorno_bcrp, A09).
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    tc = tc_oficial.select(F.col("fecha").cast("date").alias("fecha"), F.col("tc_venta").cast("double"))
    dias = (tc.agg(F.min("fecha").alias("ini"), F.max("fecha").alias("fin"))
            .select(F.explode(F.sequence("ini", "fin")).alias("fecha")))
    w = Window.orderBy("fecha").rowsBetween(Window.unboundedPreceding, 0)
    return (dias.join(tc, "fecha", "left_outer")
            .withColumn("tc_oficial", F.last("tc_venta", ignorenulls=True).over(w))
            .select("fecha", "tc_oficial"))


def s6(compras_glp, tc_oficial):
    """Tipo de cambio registrado igual a 1, o que se aleja más de TOL_TIPO_CAMBIO del oficial del día.

    Si no hay valor oficial para la fecha, la comparación queda nula y no dispara
    (no se inventa el tipo de cambio). Un T.C. igual a 1 dispara siempre.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    c = preparar_compras(compras_glp).join(broadcast(calendario_tc(tc_oficial)), "fecha", "left_outer")
    tc = F.col("tipo_cambio")
    desvio = F.abs(tc - F.col("tc_oficial")) / F.col("tc_oficial")
    es_uno = tc == F.lit(1.0)
    d = c.filter(F.coalesce(es_uno, F.lit(False)) | F.coalesce(desvio > F.lit(config.TOL_TIPO_CAMBIO), F.lit(False)))
    return _alertas(d, "S6", "placa_norm", puntaje=F.coalesce(desvio, F.lit(1.0)))


# --- S9, S11 y S12 (F04) ------------------------------------------------------
TOL_KG_S12 = 1.0   # kg: diferencias menores son redondeo entre tesorería y logística


def _z_robusto_por_grupo(df, valor: str, grupo: str, salida: str):
    """z robusto por grupo, igual que base_mad.z_robusto: 0.6745 × (x − mediana) / MAD.

    Mediana y MAD exactas con percentile(…, 0.5), agregadas por grupo y unidas de vuelta.
    Si el MAD es 0 se usa 1e-9, como en la versión pandas.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    med = df.filter(F.col(valor).isNotNull()).groupBy(grupo).agg(
        F.expr(f"percentile({valor}, 0.5)").alias("_mediana"))
    con_med = df.join(med, grupo, "left_outer")
    mad = (con_med.filter(F.col(valor).isNotNull())
           .withColumn("_desvio", F.abs(F.col(valor) - F.col("_mediana")))
           .groupBy(grupo).agg(F.expr("percentile(_desvio, 0.5)").alias("_mad")))
    mad_seguro = F.when(F.col("_mad") > 0, F.col("_mad")).otherwise(F.lit(1e-9))
    return (con_med.join(mad, grupo, "left_outer")
            .withColumn(salida, F.lit(0.6745) * (F.col(valor) - F.col("_mediana")) / mad_seguro)
            .drop("_mediana", "_mad"))


def _por_unidad_mes(df):
    """Columnas de alerta para el grano unidad × mes: fecha = día 1 y documento = «PLACA AAAA-MM»."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    return (df.withColumn("fecha", F.make_date(F.col("anio"), F.col("mes"), F.lit(1)))
            .withColumn("documento", F.concat_ws(" ", F.col("placa_norm"),
                                                 F.format_string("%04d-%02d", F.col("anio"), F.col("mes")))))


def s9(unidad_mes):
    """Combustible sin venta, o combustible por tonelada fuera de lo normal para su rol.

    Entrada: fact_unidad_mes con placa_norm, anio, mes, rol, kg y combustible (S/).
    El S/ por t se calcula solo con kg > 0; con kg = 0 o nulo y combustible > 0 es
    «combustible sin venta». El z robusto se calcula dentro de cada rol, porque una
    cisterna y una unidad de reparto no son comparables.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    u = _por_unidad_mes(unidad_mes).withColumn(
        "_soles_t", F.when(F.col("kg") > 0, F.col("combustible") / (F.col("kg") / F.lit(1000.0))))
    u = _z_robusto_por_grupo(u, "_soles_t", "rol", "_z")
    sin_venta = (F.coalesce(F.col("kg"), F.lit(0.0)) <= 0) & (F.col("combustible") > 0)
    fuera = F.abs(F.col("_z")) > F.lit(config.UMBRAL_Z_MAD)
    d = u.filter(sin_venta | F.coalesce(fuera, F.lit(False))).withColumn("kg", F.coalesce(F.col("kg"), F.lit(0.0)))
    puntaje = F.when(sin_venta, F.lit(None).cast("double")).otherwise(F.abs(F.col("_z")))
    return _alertas(d, "S9", "placa_norm", puntaje=F.coalesce(puntaje, F.lit(1.0)))


def s11(produccion):
    """Cierre de planta sin medición física.

    Entrada: producción diaria con fecha, anio, mes, residuo_kg y ajuste_kg (contrato
    de A08). Dispara:
      * una alerta por mes cuando el residuo es exactamente 0 en todos los días del
        mes (al menos 2 días): el cierre se cuadró sin medir;
      * una alerta por día con un ajuste manual distinto de 0 (kg = |ajuste|).
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    p = produccion.withColumn("fecha", F.col("fecha").cast("date"))
    meses = (p.groupBy("anio", "mes").agg(
        F.count("*").alias("_dias"),
        F.sum(F.when(F.col("residuo_kg") == 0, 1).otherwise(0)).alias("_dias_cero"),
        F.max("fecha").alias("fecha"),
        F.sum(F.abs(F.coalesce(F.col("ajuste_kg"), F.lit(0.0)))).alias("kg"))
        .filter((F.col("_dias") >= 2) & (F.col("_dias_cero") == F.col("_dias")))
        .withColumn("documento", F.format_string("CIERRE %04d-%02d", F.col("anio"), F.col("mes")))
        .withColumn("placa_norm", F.lit(None).cast("string")))
    ajustes = (p.filter(F.coalesce(F.col("ajuste_kg"), F.lit(0.0)) != 0)
               .withColumn("kg", F.abs(F.col("ajuste_kg")))
               .withColumn("documento", F.concat(F.lit("AJUSTE "), F.date_format("fecha", "yyyy-MM-dd")))
               .withColumn("placa_norm", F.lit(None).cast("string")))
    return _alertas(meses, "S11", "placa_norm").unionByName(_alertas(ajustes, "S11", "placa_norm"))


def _llave_documento(proveedor, serie, numero):
    """Llave común «PROVEEDOR|SERIE|NUMERO»: mayúsculas, sin espacios, número sin ceros a la izquierda."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    limpio = lambda c: F.regexp_replace(F.upper(F.trim(c)), r"\s+", "")  # noqa: E731
    num = F.regexp_replace(limpio(numero), r"^0+(?=\d)", "")
    return F.concat_ws("|", F.regexp_replace(F.upper(F.trim(proveedor)), r"\s+", " "), limpio(serie), num)


def cruce_s12(tesoreria, compras_glp):
    """Cruce full_outer entre tesorería y logística por documento, con la clase de cada par.

    tesoreria: proveedor, documento («SERIE-NUMERO»), kg, fecha_pago, fecha_vence (A07).
    compras_glp: la tabla de logística (F06), con serie y numero por separado.
    Clases: coincide, kg_distinto (|Δkg| > TOL_KG_S12), solo_logistica, solo_tesoreria y
    kg_desconocido (ambos registros existen pero a uno le faltan los kg: no se afirma que
    coincidan ni que difieran, y no genera alerta).
    Lo usan s12() y la tabla de modelado modelo_factura (F07) para la etiqueta y el KPI 3.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    t = tesoreria.select(
        _llave_documento(F.col("proveedor"), F.split(F.col("documento"), "-").getItem(0),
                         F.split(F.col("documento"), "-").getItem(1)).alias("llave"),
        F.col("proveedor").alias("proveedor_t"), F.col("documento").alias("documento_t"),
        F.col("kg").cast("double").alias("kg_tesoreria"),
        F.col("fecha_pago").cast("date").alias("fecha_pago"),
        F.col("fecha_vence").cast("date").alias("fecha_vence"))
    lg = preparar_compras(compras_glp).select(
        _llave_documento(F.col("proveedor"), F.col("serie"), F.col("numero")).alias("llave"),
        F.col("documento").alias("documento_l"), "placa_norm", "fecha", "anio", "mes",
        F.col("kg").cast("double").alias("kg_logistica"))
    j = lg.join(t, "llave", "full_outer")
    clase = (F.when(F.col("documento_t").isNull(), "solo_logistica")
             .when(F.col("documento_l").isNull(), "solo_tesoreria")
             .when(F.col("kg_logistica").isNull() | F.col("kg_tesoreria").isNull(), "kg_desconocido")
             .when(F.abs(F.col("kg_logistica") - F.col("kg_tesoreria")) > F.lit(TOL_KG_S12), "kg_distinto")
             .otherwise("coincide"))
    fecha = F.coalesce(F.col("fecha"), F.col("fecha_pago"), F.col("fecha_vence"))
    return (j.withColumn("clase_s12", clase)
            .withColumn("documento", F.coalesce(F.col("documento_l"),
                                                F.concat_ws(" ", F.col("proveedor_t"), F.col("documento_t"))))
            .withColumn("fecha", fecha)
            .withColumn("anio", F.coalesce(F.col("anio"), F.year(fecha)))
            .withColumn("mes", F.coalesce(F.col("mes"), F.month(fecha))))


def s12(tesoreria, compras_glp):
    """Alertas S12: facturas solo en logística, solo en tesorería o con kg distinto.

    El puntaje es la diferencia relativa de kg cuando hay pareja (|Δ| / máx) y 1.0
    cuando falta el segundo registro.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    c = cruce_s12(tesoreria, compras_glp).filter(
        F.col("clase_s12").isin("solo_logistica", "solo_tesoreria", "kg_distinto"))
    kg = F.coalesce(F.col("kg_logistica"), F.col("kg_tesoreria"))
    dif = F.abs(F.col("kg_logistica") - F.col("kg_tesoreria")) / F.greatest(F.col("kg_logistica"), F.col("kg_tesoreria"))
    d = c.withColumn("kg", kg)
    return _alertas(d, "S12", "placa_norm", puntaje=F.coalesce(dif, F.lit(1.0)))


def calcular(compras, ventas, flota, maestro):
    """Une las alertas de las señales de esta versión en un solo DataFrame."""
    from functools import reduce  # noqa: PLC0415

    partes = [s1(compras), s4(compras, flota), s5(ventas, maestro),
              s7(compras, flota), s8(ventas, compras), s10(ventas)]
    return reduce(lambda a, b: a.unionByName(b), partes)
