"""WR03: las interfaces del WP 0.8, armadas en Spark desde Silver.

El WP 0.8 (`src/signals/contratos.py`) fija lo que las senales esperan recibir:
cinco entradas con sus columnas, su grano y su llave. Ese modulo las lee en
pandas desde el lago; aqui se arman las mismas en Spark, para que el job de Gold
no vuelva a inventar el nombre ni el tipo de cada columna en cada paso.

Un solo esquema por tabla: las columnas salen de `contratos.ENTRADAS`, no de una
lista escrita a mano, y la regla de cada una se reusa de donde ya vive:

* `compras`   `senales_spark.normalizar_compras` (la llave de factura es suya)
* `unidades`  `dimensiones.dim_unidad`, que ya colapsa las placas del maestro
* `tc`        el JSON del BCRP que baja `src/extractores/bcrp.py`

`unidad_mes` se construye desde Silver `ventas_unidad_mes` y `gastos` en
`src/glue/unidad_mes.py`; la salida es Gold `fact_unidad_mes`.

La entrada que no se arma aqui y es a proposito:

* `produccion` es `silver/produccion_diaria`, que **no esta cubierta** en la
  entrega de 35 archivos: el stock diario no aparece en ninguna de las 199 hojas
  (evidencia: `docs/evidencias/hojas_sin_encabezado.md`). S11 queda sin fuente y
  se declara, no se rellena con ceros.
"""
from __future__ import annotations

from src.glue import dimensiones, externos_job, senales_spark
from src.signals import contratos

# Las que esta modulo sabe armar hoy. El resto del contrato se documenta arriba.
DISPONIBLES = ("compras", "unidades", "tc")

# Serie del BCRP: un valor por dia habil. La extraccion baja ventanas que se
# solapan, asi que una fecha puede venir en dos archivos con el mismo valor; se
# colapsa por fecha para respetar el grano que exige el contrato.
ESQUEMA_BCRP = "periods array<struct<name:string, values:array<string>>>"
FORMATO_FECHA_BCRP = "dd.MMM.yy"


def columnas(nombre: str) -> list[str]:
    """Las columnas que el contrato del WP 0.8 exige para esa entrada."""
    return list(contratos.ENTRADAS[nombre][1])


def _solo_del_contrato(df, nombre: str, extra: tuple[str, ...] = ()):
    """Deja las columnas del contrato, mas las opcionales que el df traiga."""
    permitidas = columnas(nombre) + list(contratos.OPCIONALES.get(nombre, [])) + list(extra)
    return df.select([c for c in permitidas if c in df.columns])


def compras(compras_glp):
    """Silver `compras_glp` -> interfaz `compras`.

    `normalizar_compras` ya hace el trabajo fino (llave de factura, SCOP vacio a
    nulo, precio nulo cuando faltan monto o kg). Aqui solo se recortan las
    columnas al contrato; `unidad_id`, `anio` y `mes` se conservan porque el
    contrato las admite como opcionales y las senales las usan para la ventana.
    """
    return _solo_del_contrato(senales_spark.normalizar_compras(compras_glp),
                              "compras", extra=("anio", "mes"))


def unidades(unidades_silver):
    """Silver `unidades` -> interfaz `unidades` (`unidad_id`, `habilitada`).

    Silver trae una fila por maestro y placa; el contrato pide una por unidad.
    El colapso y la regla de habilitacion son los de `dim_unidad`
    (`src/glue/dimensiones.py:74`: `habilitada_glp` = maximo de `traslada_gas`),
    para que la dimension y la senal no puedan discrepar.

    Una placa que no figura en el maestro queda con `habilitada` nula, no falsa:
    no se sabe si traslada gas, y S7 solo se dispara con un «no» explicito.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    return (dimensiones.dim_unidad(unidades_silver)
            .select(F.col("placa_norm").alias("unidad_id"),
                    F.col("habilitada_glp").alias("habilitada")))


def tipo_cambio(spark, lake_uri: str | None = None):
    """JSON del BCRP -> interfaz `tc` (`fecha`, `tc_oficial`), un valor por dia.

    S6 compara el tipo de cambio de cada factura contra el oficial del dia, asi
    que necesita la serie diaria. `externos_job.tipo_cambio_mes` lee el mismo
    archivo pero promedia por mes, que es lo que `mercado_mes` necesita: son dos
    granos de la misma fuente, no dos fuentes.

    Lo que no se puede convertir a fecha o a numero se descarta, no se rellena.
    """
    from pyspark.sql import functions as F  # noqa: PLC0415

    crudo = (spark.read.option("multiLine", "true").schema(ESQUEMA_BCRP)
             .json(f"{externos_job.ruta_fuente('bcrp', lake_uri)}/*/*.json"))
    return (crudo.select(F.explode("periods").alias("p"))
            .select(F.to_date("p.name", FORMATO_FECHA_BCRP).alias("fecha"),
                    F.col("p.values")[0].cast("double").alias("tc_oficial"))
            .filter(F.col("fecha").isNotNull() & F.col("tc_oficial").isNotNull())
            .groupBy("fecha")
            .agg(F.max("tc_oficial").alias("tc_oficial")))


def construir(spark, silver: dict, lake_uri: str | None = None) -> dict:
    """Arma las interfaces que se puedan con lo que haya en `silver`.

    `silver` es {nombre de la tabla de Silver: DataFrame}. Una interfaz cuya
    fuente no esta no se devuelve vacia: se omite, y el paso que la necesite
    dira que le falta. Un DataFrame vacio pasaria por una medicion de cero.
    """
    armadas = {}
    if "compras_glp" in silver:
        armadas["compras"] = compras(silver["compras_glp"])
    if "unidades" in silver:
        armadas["unidades"] = unidades(silver["unidades"])
    if spark is not None:
        try:
            armadas["tc"] = tipo_cambio(spark, lake_uri)
        except Exception as e:                  # noqa: BLE001 - AnalysisException y afines
            # Sin extraccion del BCRP no hay serie: S6 se declarara sin fuente.
            print(f"[interfaces] tc no disponible: {type(e).__name__}: {e}")
    return armadas
