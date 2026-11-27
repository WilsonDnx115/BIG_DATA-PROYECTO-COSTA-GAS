"""Señales determinísticas en Spark para el job de Gold (informe v16, 4.2 y Tabla 4.3).

Son funciones puras: reciben DataFrames y devuelven alertas con el contrato
`fact_alerta_base`, el mismo de las señales en pandas del WP 0.8. El job
`src/glue/gold_job.py` (Wilson) las llama; este módulo no lee ni escribe en el lago.

Un solo esquema por tabla (CLAUDE.md). Este módulo no declara contratos propios:
  * el catálogo, el grado de evidencia y las ventanas salen de `src/signals/common.py`
    y `src/signals/catalogo.yaml`;
  * las entradas usan las interfaces del WP 0.8 (`src/signals/contratos.py`):
    `compras` (factura_id, fecha, proveedor_id, codigo_scop, kg, precio_usd_kg,
    tipo_cambio), `unidad_mes`, `unidades`, `produccion` y `tc`. `normalizar_compras`
    arma `compras` desde la tabla Silver `compras_glp`;
  * las alertas no valorizan kg: `valor_soles` queda nulo, porque unos kg señalados no
    son una pérdida medida.

  S1  placa cargada distinta de la facturada            filtro                       (fixture)
  S2  compra sin SCOP o con SCOP repetido               ventana por codigo_scop
  S3  USD/kg sobre la mediana móvil del proveedor       ventana rangeBetween de días previos
  S4  carga superior a la capacidad autorizada          join con broadcast(flota)    (fixture)
  S5  volumen a un cliente sobre su capacidad           join con broadcast(maestro)  (fixture)
  S6  tipo de cambio igual a 1 o lejos del oficial      join con broadcast(calendario)
  S7  actividad en una unidad no habilitada             join con broadcast(unidades)
  S8  venta sin compra que la respalde (SCOP)           left_anti                    (fixture)
  S9  combustible sin volumen o atípico para su rol     z robusto del log, por rol (base_mad)
  S10 precio de venta bajo la mediana de su canal       ventana con percentile exacto (fixture)
  S11 cierre de planta calculado sin medición física    por día
  S12 factura sin pareja o con kg distinto              full_outer tesorería × logística

Las marcadas «fixture» leen las tablas de la muestra sintética antigua
(`src/signals/senales_fixture.py`) y se prueban contra ella. Sin collect().
"""
from __future__ import annotations

from src.common import config, schemas
from src.signals.common import (ANIO_VENTANA, VENTANAS_FECHA, cargar_catalogo, grado_alerta,
                                grado_evidencia)

REGLAS: dict[str, dict] = cargar_catalogo()

# Descripción y grado de cada señal (dim_senal, W08), desde el catálogo único.
CATALOGO: dict[str, tuple[str, str]] = {
    codigo: (regla["descripcion"], grado_evidencia(regla))
    for codigo, regla in sorted(REGLAS.items(), key=lambda kv: int(kv[0][1:]))}

COLUMNAS_ALERTA = schemas.CONTRATOS["fact_alerta_base"].columnas()


# --- Piezas comunes -----------------------------------------------------------
def en_ventana(senal: str, fecha: str = "fecha", anio: str = "anio"):
    """Condición de ventana de la señal, la misma que `common._ventana` en pandas."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    if senal in VENTANAS_FECHA:
        condicion = F.lit(False)
        for ini, fin in VENTANAS_FECHA[senal]:
            condicion = condicion | F.col(fecha).between(F.lit(ini).cast("date"), F.lit(fin).cast("date"))
        return condicion
    return F.col(anio) == F.lit(ANIO_VENTANA)


def _texto(valor):
    from pyspark.sql import functions as F  # noqa: PLC0415

    if valor is None:
        return F.lit(None).cast("string")
    return F.lit(valor) if isinstance(valor, str) else valor.cast("string")


def _alertas(df, senal: str, motivo, *, kg, puntaje=None, tipo="regla", unidad=None, rol=None,
             factura=None, scop=None):
    """Lleva las filas que disparan una señal al contrato `fact_alerta_base`.

    El id es determinístico (SHA-256 de señal, tipo, resolución, fecha, unidad, factura y
    motivo, 24 caracteres), así la misma alerta en otra corrida tiene el mismo id y el
    MERGE en Iceberg no la duplica.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    regla = REGLAS[senal]
    out = df.select(
        F.lit(senal).alias("senal"),
        _texto(tipo).alias("tipo"),
        F.lit(regla["resolucion"]).alias("resolucion"),
        F.col("fecha").cast("date").alias("fecha"),
        _texto(unidad).alias("unidad_id"),
        _texto(rol).alias("rol"),
        _texto(factura).alias("factura_id"),
        _texto(scop).alias("codigo_scop"),
        kg.cast("double").alias("kg"),
        F.lit(None).cast("double").alias("valor_soles"),
        (F.lit(1.0) if puntaje is None else puntaje).cast("double").alias("puntaje"),
        F.lit(grado_alerta(regla)).alias("grado_evidencia"),
        F.lit("pendiente").alias("estado_revision"),
        _texto(motivo).alias("motivo"),
        F.lit(",".join(regla["fuentes"])).alias("fuentes"),
    )
    out = out.withColumn("anio", F.year("fecha")).withColumn("mes", F.month("fecha"))
    clave = F.concat_ws("|", *[F.coalesce(F.col(c).cast("string"), F.lit(""))
                               for c in ("senal", "tipo", "resolucion", "fecha", "unidad_id",
                                         "factura_id", "motivo")])
    return out.withColumn("id_alerta", F.substring(F.sha2(clave, 256), 1, 24)).select(*COLUMNAS_ALERTA)


def _z_robusto_por_grupo(df, valor: str, grupo: str, salida: str):
    """z robusto por grupo, igual que base_mad.z_robusto: 0.6745 × (x − mediana) / MAD.

    Mediana y MAD exactas con percentile(…, 0.5). Si el MAD del grupo es 0, el z queda
    nulo: el grupo no es evaluable (CLAUDE.md), no se reemplaza por un número chico.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    med = df.filter(F.col(valor).isNotNull()).groupBy(grupo).agg(
        F.expr(f"percentile({valor}, 0.5)").alias("_mediana"))
    con_med = df.join(med, grupo, "left_outer")
    mad = (con_med.filter(F.col(valor).isNotNull())
           .withColumn("_desvio", F.abs(F.col(valor) - F.col("_mediana")))
           .groupBy(grupo).agg(F.expr("percentile(_desvio, 0.5)").alias("_mad")))
    return (con_med.join(mad, grupo, "left_outer")
            .withColumn(salida, F.when(F.col("_mad") > 0,
                                       F.lit(0.6745) * (F.col(valor) - F.col("_mediana")) / F.col("_mad")))
            .drop("_mediana", "_mad"))


# --- Señales sobre la muestra sintética antigua (fixture) ---------------------
def s1(compras):
    """Placa cargada distinta de la facturada en la misma orden."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    d = compras.filter(F.coalesce(F.col("flag_placa_divergente"), F.lit(False)))
    return _alertas(d, "S1", "placa_cargada_distinta_de_la_facturada", kg=F.col("kg"),
                    unidad=F.col("placa_cargada"), factura=F.col("documento"), scop=F.col("codigo_scop"))


def s4(compras, flota):
    """Carga mayor que la capacidad autorizada del vehículo que la llevó."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cap = flota.select(F.col("placa_norm").alias("_placa_flota"), "capacidad_kg")
    d = (compras.join(broadcast(cap), compras["placa_cargada"] == cap["_placa_flota"], "inner")
         .filter(F.col("kg") > F.col("capacidad_kg")))
    return _alertas(d, "S4", "carga_sobre_capacidad_autorizada", kg=F.col("kg"),
                    puntaje=F.col("kg") / F.col("capacidad_kg"), unidad=F.col("placa_cargada"),
                    factura=F.col("documento"), scop=F.col("codigo_scop"))


def s5(ventas, maestro):
    """Venta a un cliente mayor que la capacidad de almacenamiento de su local."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    cap = maestro.select("card_code", F.col("capacidad_kg").alias("cap_local"))
    d = (ventas.join(broadcast(cap), "card_code", "inner")
         .filter(F.col("cap_local").isNotNull() & (F.col("kg") > F.col("cap_local"))))
    return _alertas(d, "S5", "venta_sobre_capacidad_del_cliente", kg=F.col("kg"),
                    puntaje=F.col("kg") / F.col("cap_local"), unidad=F.col("placa_norm"),
                    factura=F.col("documento"), scop=F.col("codigo_scop"))


def s8(ventas, compras):
    """Venta con código SCOP que no cierra con ninguna compra (S8 es no resoluble con datos reales)."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    con_scop = ventas.filter(F.col("codigo_scop").isNotNull())
    claves = compras.select("codigo_scop").dropna().distinct()
    d = con_scop.join(claves, "codigo_scop", "left_anti")
    return _alertas(d, "S8", "venta_sin_compra_scop", kg=F.col("kg"), unidad=F.col("placa_norm"),
                    factura=F.col("documento"), scop=F.col("codigo_scop"))


def s10(ventas):
    """Precio más de TOL_PRECIO_S10 bajo la mediana de su canal, producto y mes."""
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    w = Window.partitionBy("canal", "id_producto", "anio", "mes")
    # percentile(…, 0.5) es la mediana exacta con interpolación (igual que pandas), no la aproximada.
    v = (ventas.filter(F.col("precio").isNotNull())
         .withColumn("mediana", F.expr("percentile(precio, 0.5)").over(w)))
    d = v.filter(F.col("precio") < F.col("mediana") * F.lit(1 - config.TOL_PRECIO_S10))
    return _alertas(d, "S10", "precio_bajo_mediana_del_canal", kg=F.col("kg"),
                    puntaje=F.lit(1.0) - F.col("precio") / F.col("mediana"), unidad=F.col("placa_norm"),
                    factura=F.col("documento"), scop=F.col("codigo_scop"))


def calcular(compras, ventas, flota, maestro):
    """Alertas de las señales que leen la muestra sintética antigua."""
    from functools import reduce  # noqa: PLC0415

    partes = [s1(compras), s4(compras, flota), s5(ventas, maestro), s8(ventas, compras), s10(ventas)]
    return reduce(lambda a, b: a.unionByName(b), partes)


# --- Interfaz `compras` del WP 0.8 desde Silver --------------------------------
def llave_factura(proveedor, serie, numero):
    """Llave «PROVEEDOR|SERIE|NUMERO»: mayúsculas, sin espacios, número sin ceros a la izquierda.

    La misma llave en logística (compras_glp) y en tesorería (pedidos_proveedor).
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    limpio = lambda c: F.regexp_replace(F.upper(F.trim(c)), r"\s+", "")  # noqa: E731
    num = F.regexp_replace(limpio(numero), r"^0+(?=\d)", "")
    return F.concat_ws("|", F.regexp_replace(F.upper(F.trim(proveedor)), r"\s+", " "), limpio(serie), num)


def normalizar_compras(compras_glp):
    """Silver `compras_glp` → interfaz `compras` del WP 0.8, más `unidad_id`.

    factura_id es la llave del documento; proveedor_id el proveedor en mayúsculas (son
    empresas, no personas naturales); codigo_scop vacío pasa a nulo; precio_usd_kg queda
    nulo si faltan el monto o los kg, o si los kg no son positivos (no se inventa un precio).
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    scop = F.trim(F.col("nro_scop"))
    return compras_glp.select(
        llave_factura(F.col("proveedor"), F.col("serie"), F.col("numero")).alias("factura_id"),
        F.col("fecha_factura").cast("date").alias("fecha"),
        F.regexp_replace(F.upper(F.trim(F.col("proveedor"))), r"\s+", " ").alias("proveedor_id"),
        F.when(scop != "", scop).alias("codigo_scop"),
        F.col("kg").cast("double").alias("kg"),
        F.when(F.col("kg") > 0, F.col("monto_usd") / F.col("kg")).alias("precio_usd_kg"),
        F.col("tipo_cambio").cast("double").alias("tipo_cambio"),
        F.col("placa_norm").alias("unidad_id"),
        F.year(F.col("fecha_factura")).alias("anio"),
        F.month(F.col("fecha_factura")).alias("mes"),
    )


def s2(compras, aplicar_ventana: bool = True):
    """Factura sin código SCOP, o con un SCOP que aparece en más de una factura.

    Solo se usa el código de la propia factura: las órdenes SCOP (F05) cubren
    ene-jul 2023 y un left_anti contra ellas marcaría como «sin SCOP» todo lo demás.
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    c = compras.filter(en_ventana("S2")) if aplicar_ventana else compras
    scop = F.trim(F.col("codigo_scop"))
    sin_scop = scop.isNull() | (scop == "")
    w = Window.partitionBy("codigo_scop")
    c = c.withColumn("_facturas_scop", F.when(~sin_scop, F.size(F.collect_set("factura_id").over(w))))
    d = c.filter(sin_scop | (F.col("_facturas_scop") > 1)).withColumn(
        "_motivo", F.when(sin_scop, "compra_sin_scop").otherwise("scop_repetido"))
    puntaje = F.when(sin_scop, F.lit(1.0)).otherwise(F.col("_facturas_scop").cast("double"))
    return _alertas(d, "S2", F.col("_motivo"), kg=F.col("kg"), puntaje=puntaje, unidad=F.col("unidad_id"),
                    factura=F.col("factura_id"), scop=F.col("codigo_scop"))


def s3(compras, aplicar_ventana: bool = True):
    """USD/kg más de TOL_PRECIO_COMPRA sobre el precio pactado, o sobre la mediana móvil del proveedor.

    La mediana usa solo las facturas de los VENTANA_MEDIANA_DIAS días anteriores (sin
    el mismo día ni los siguientes), así no hay fuga de información (informe v16,
    controles). Si la compra trae `precio_pactado_usd_kg` (opcional en la interfaz del
    WP 0.8), se compara contra él.
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    c = compras.filter(en_ventana("S3")) if aplicar_ventana else compras
    c = c.withColumn("_dia", F.datediff(F.col("fecha"), F.lit("1970-01-01")))
    w = Window.partitionBy("proveedor_id").orderBy("_dia").rangeBetween(-config.VENTANA_MEDIANA_DIAS, -1)
    c = c.withColumn("_mediana", F.expr("percentile(precio_usd_kg, 0.5)").over(w))
    pactado = (F.when(F.col("precio_pactado_usd_kg") > 0, F.col("precio_pactado_usd_kg"))
               if "precio_pactado_usd_kg" in c.columns else F.lit(None).cast("double"))
    c = c.withColumn("_base", F.coalesce(pactado, F.col("_mediana"))).withColumn(
        "_motivo", F.when(pactado.isNotNull(), "precio_fuera_de_lo_pactado")
                    .otherwise("precio_sobre_mediana_movil_proveedor"))
    d = c.filter(F.coalesce(F.col("precio_usd_kg") > F.col("_base") * F.lit(1 + config.TOL_PRECIO_COMPRA),
                            F.lit(False)))
    return _alertas(d, "S3", F.col("_motivo"), kg=F.col("kg"),
                    puntaje=F.col("precio_usd_kg") / F.col("_base") - F.lit(1.0),
                    unidad=F.col("unidad_id"), factura=F.col("factura_id"), scop=F.col("codigo_scop"))


def calendario_tc(tc):
    """Tipo de cambio oficial (interfaz `tc` del WP 0.8: fecha, tc_oficial) para cada día.

    Los días sin publicación (fines de semana y feriados) toman el último valor hábil
    anterior. La tabla es pequeña, así que la ventana sin partición no es un problema y
    el resultado se une con broadcast().
    """
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    t = tc.select(F.col("fecha").cast("date").alias("fecha"), F.col("tc_oficial").cast("double").alias("_tc"))
    dias = (t.agg(F.min("fecha").alias("ini"), F.max("fecha").alias("fin"))
            .select(F.explode(F.sequence("ini", "fin")).alias("fecha")))
    w = Window.orderBy("fecha").rowsBetween(Window.unboundedPreceding, 0)
    return (dias.join(t, "fecha", "left_outer")
            .withColumn("tc_oficial", F.last("_tc", ignorenulls=True).over(w))
            .select("fecha", "tc_oficial"))


def s6(compras, tc, aplicar_ventana: bool = True):
    """Tipo de cambio igual a 1, o que se aleja más de TOL_TIPO_CAMBIO del oficial del día.

    Sin valor oficial para la fecha, la comparación queda nula y no dispara (no se
    inventa el tipo de cambio); un T.C. igual a 1 dispara siempre.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    c = compras.filter(en_ventana("S6")) if aplicar_ventana else compras
    c = c.join(broadcast(calendario_tc(tc)), "fecha", "left_outer")
    registrado = F.col("tipo_cambio")
    desvio = F.abs(registrado - F.col("tc_oficial")) / F.when(F.col("tc_oficial") > 0, F.col("tc_oficial"))
    es_uno = registrado == F.lit(1.0)
    d = c.filter(F.coalesce(es_uno, F.lit(False))
                 | F.coalesce((desvio > F.lit(config.TOL_TIPO_CAMBIO)) & (registrado > 0), F.lit(False)))
    motivo = F.when(es_uno, "tipo_cambio_igual_a_1").otherwise("tipo_cambio_difiere_del_oficial")
    return _alertas(d, "S6", motivo, kg=F.col("kg"), puntaje=F.coalesce(desvio, F.lit(1.0)),
                    unidad=F.col("unidad_id"), factura=F.col("factura_id"), scop=F.col("codigo_scop"))


# --- Unidad × mes: KPI 4, S7 y S9 ----------------------------------------------
def kpi4(unidad_mes):
    """KPI 4 y modelo base por unidad-mes, igual que `base_mad.puntuar` (interfaz `unidad_mes`).

    kg_base_rol: kg vendidos en reparto y kg transportados en transporte (no se cruzan
    roles). soles_comb_por_t = gasto_combustible ÷ (kg_base_rol ÷ 1 000), solo con volumen
    y gasto positivos. z: z robusto del log de ese cociente dentro del rol. puntaje = |z|;
    alerta_base si supera UMBRAL_Z_MAD. estado_puntaje dice por qué una fila no es evaluable.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    volumen = F.when(F.col("rol") == "reparto", F.col("kg_vendidos")).otherwise(F.col("kg_transportados"))
    gasto = F.col("gasto_combustible").cast("double")
    u = unidad_mes.withColumn("kg_base_rol", volumen.cast("double"))
    validos = (F.col("kg_base_rol") > 0) & (gasto > 0)
    u = (u.withColumn("soles_comb_por_t", F.when(validos, gasto / (F.col("kg_base_rol") / F.lit(1000.0))))
         .withColumn("log_combustible_por_t", F.log(F.col("soles_comb_por_t"))))
    u = _z_robusto_por_grupo(u, "log_combustible_por_t", "rol", "z")
    return (u.withColumn("puntaje", F.abs(F.col("z")))
            .withColumn("alerta_base", F.coalesce(F.col("puntaje") > F.lit(config.UMBRAL_Z_MAD), F.lit(False)))
            .withColumn("estado_puntaje",
                        F.when(F.col("soles_comb_por_t").isNull(), "sin_combustible_o_volumen_positivo")
                         .when(F.col("z").isNull(), "mad_cero_o_sin_grupo_evaluable")
                         .otherwise("evaluable")))


def _primer_dia(df):
    from pyspark.sql import functions as F  # noqa: PLC0415

    return df.withColumn("fecha", F.make_date(F.col("anio"), F.col("mes"), F.lit(1)))


def s7(unidad_mes, unidades, aplicar_ventana: bool = True):
    """Actividad (gasto o volumen) en una unidad declarada no habilitada para GLP."""
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    um = unidad_mes.filter(en_ventana("S7")) if aplicar_ventana else unidad_mes
    um = um.join(broadcast(unidades.select("unidad_id", "habilitada")), "unidad_id", "left_outer")
    actividad = F.lit(False)
    for c in ("gasto_total", "gasto_combustible", "kg_vendidos", "kg_transportados"):
        actividad = actividad | F.coalesce(F.col(c) > 0, F.lit(False))
    d = _primer_dia(um.filter((F.col("habilitada") == F.lit(False)) & actividad))
    kg = F.when(F.col("rol") == "reparto", F.col("kg_vendidos")).otherwise(F.col("kg_transportados"))
    return _alertas(d, "S7", "actividad_en_unidad_no_habilitada", kg=kg, unidad=F.col("unidad_id"),
                    rol=F.col("rol"))


def s9(unidad_mes, aplicar_ventana: bool = True):
    """Combustible sin volumen del rol, o combustible por tonelada atípico (|z| > UMBRAL_Z_MAD)."""
    from pyspark.sql import functions as F  # noqa: PLC0415

    um = unidad_mes.filter(en_ventana("S9")) if aplicar_ventana else unidad_mes
    p = kpi4(um)
    sin_volumen = (F.col("gasto_combustible") > 0) & (F.col("kg_base_rol") == 0)
    raro = F.col("alerta_base")
    d = _primer_dia(p.filter(F.coalesce(sin_volumen, F.lit(False)) | raro))
    motivo = F.when(sin_volumen, "combustible_sin_volumen_del_rol").otherwise("combustible_por_tonelada_atipico")
    return _alertas(d, "S9", motivo, kg=F.col("kg_base_rol"),
                    puntaje=F.when(raro, F.col("puntaje")).otherwise(F.lit(1.0)),
                    tipo=F.when(raro, "regla_y_modelo").otherwise("regla"),
                    unidad=F.col("unidad_id"), rol=F.col("rol"))


def agregar_senales(fact_unidad_mes, alertas):
    """Agrega a cada unidad-mes las señales que dispararon sobre ella (llave unidad_id, anio, mes).

    senales: arreglo sin repetidos y ordenado como texto (por ejemplo ["S10", "S4", "S9"]);
    n_senales: cuántas distintas. Una unidad-mes sin alertas queda con arreglo vacío y 0.
    Las alertas sin unidad (S11, S12 solo en tesorería) no se asignan. Lo llama el job (W07).
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    llave = ["unidad_id", "anio", "mes"]
    por_unidad = (alertas.filter(F.col("unidad_id").isNotNull())
                  .groupBy(*llave).agg(F.array_sort(F.collect_set("senal")).alias("senales")))
    vacio = F.array().cast("array<string>")
    return (fact_unidad_mes.join(por_unidad, llave, "left_outer")
            .withColumn("senales", F.coalesce(F.col("senales"), vacio))
            .withColumn("n_senales", F.size("senales")))


# --- S11: producción diaria ----------------------------------------------------
def s11(produccion, aplicar_ventana: bool = True):
    """Cierre diario calculado sin medición física independiente (interfaz `produccion`).

    residuo = stock_inicial + produccion − ventas − bonificaciones − stock_final. Dispara
    el día con residuo ≈ 0 (TOL_RESIDUO_STOCK), los cinco valores presentes y un stock
    final calculado. Si la producción es negativa y cancela el stock inicial, el motivo es
    «cierre_calculado_con_ajuste». Igual que `src/signals/s11.py`.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    p = produccion.withColumn("fecha", F.col("fecha").cast("date"))
    p = p.filter(en_ventana("S11")) if aplicar_ventana else p
    cols = ["stock_inicial", "produccion", "ventas", "bonificaciones", "stock_final"]
    n = {c: F.col(c).cast("double") for c in cols}
    residuo = n["stock_inicial"] + n["produccion"] - n["ventas"] - n["bonificaciones"] - n["stock_final"]
    tol = F.lit(config.TOL_RESIDUO_STOCK)
    completo = F.lit(True)
    for c in cols:
        completo = completo & n[c].isNotNull()
    dispara = (F.abs(residuo) <= tol) & completo & F.coalesce(F.col("stock_final_es_calculado") == True, F.lit(False))  # noqa: E712
    ajuste = (n["produccion"] < 0) & (F.abs(n["produccion"] + n["stock_inicial"]) <= tol)
    d = p.filter(dispara)
    motivo = F.when(ajuste, "cierre_calculado_con_ajuste").otherwise("cierre_calculado_sin_medicion_independiente")
    return _alertas(d, "S11", motivo, kg=F.lit(None).cast("double"))


# --- S12: tesorería × logística -------------------------------------------------
def cruce_s12(tesoreria, compras):
    """Cruce full_outer entre tesorería y logística por factura, con la clase de cada par.

    tesoreria: Silver `pedidos_proveedor` (proveedor, documento «SERIE-NUMERO», kg,
    fecha_pago, fecha_vence). compras: interfaz `compras` (normalizar_compras).
    Clases: coincide, kg_distinto (|Δkg| > config.TOL_KG_S12), solo_logistica, solo_tesoreria y
    kg_desconocido (los dos registros existen, pero a uno le faltan los kg: no se afirma
    que coincidan ni que difieran, y no genera alerta). Lo usan s12() y modelo_factura (F07).
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    partes = F.split(F.col("documento"), "-")
    t = tesoreria.select(
        llave_factura(F.col("proveedor"), partes.getItem(0), partes.getItem(1)).alias("_llave_t"),
        F.col("kg").cast("double").alias("kg_tesoreria"),
        F.col("fecha_pago").cast("date").alias("fecha_pago"),
        F.col("fecha_vence").cast("date").alias("fecha_vence"))
    lg = compras.select(F.col("factura_id").alias("_llave_l"), "unidad_id", "codigo_scop",
                        F.col("fecha").alias("_fecha_l"), F.col("kg").cast("double").alias("kg_logistica"))
    j = lg.join(t, lg["_llave_l"] == t["_llave_t"], "full_outer")
    clase = (F.when(F.col("_llave_t").isNull(), "solo_logistica")
             .when(F.col("_llave_l").isNull(), "solo_tesoreria")
             .when(F.col("kg_logistica").isNull() | F.col("kg_tesoreria").isNull(), "kg_desconocido")
             .when(F.abs(F.col("kg_logistica") - F.col("kg_tesoreria")) > F.lit(config.TOL_KG_S12), "kg_distinto")
             .otherwise("coincide"))
    fecha = F.coalesce(F.col("_fecha_l"), F.col("fecha_pago"), F.col("fecha_vence"))
    return (j.withColumn("factura_id", F.coalesce(F.col("_llave_l"), F.col("_llave_t")))
            .withColumn("clase_s12", clase)
            .withColumn("fecha", fecha)
            .withColumn("anio", F.year(fecha)).withColumn("mes", F.month(fecha))
            .drop("_llave_l", "_llave_t", "_fecha_l"))


def s12(tesoreria, compras, aplicar_ventana: bool = True):
    """Alertas S12: facturas solo en logística, solo en tesorería o con kg distinto.

    puntaje: diferencia relativa de kg cuando hay pareja (|Δ| ÷ máx) y 1.0 cuando falta
    el segundo registro.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    c = cruce_s12(tesoreria, compras).filter(
        F.col("clase_s12").isin("solo_logistica", "solo_tesoreria", "kg_distinto"))
    c = c.filter(en_ventana("S12")) if aplicar_ventana else c
    kg = F.coalesce(F.col("kg_logistica"), F.col("kg_tesoreria"))
    dif = (F.abs(F.col("kg_logistica") - F.col("kg_tesoreria"))
           / F.greatest(F.col("kg_logistica"), F.col("kg_tesoreria")))
    return _alertas(c, "S12", F.col("clase_s12"), kg=kg, puntaje=F.coalesce(dif, F.lit(1.0)),
                    unidad=F.col("unidad_id"), factura=F.col("factura_id"), scop=F.col("codigo_scop"))
