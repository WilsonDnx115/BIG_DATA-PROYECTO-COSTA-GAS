"""Uniones de la Tabla 3.6 con el tipo de join exacto (paso 3.3.7, S5).

| Unión                               | Clave                       | Join        |
|-------------------------------------|-----------------------------|-------------|
| Compras ↔ órdenes SCOP propias      | codigo_scop                 | left_outer  |
| Compras sin orden SCOP              | codigo_scop                 | left_anti   |
| Compras ↔ ventas por unidad         | placa_norm+fecha+producto   | full_outer  |
| Ventas sin compra asociada (S8)     | codigo_scop                 | left_anti   |
| Ventas ↔ maestro de clientes        | card_code                   | left_outer  |
| Maestro ↔ padrón SUNAT              | ruc                         | left_outer  |
| Vehículos habilitados (S7)          | placa_norm                  | left_semi   |
| Compras ↔ tipo de cambio            | fecha                       | left_outer + último hábil |

Las tablas pequeñas (flota, maestro, tipo de cambio) van con broadcast() (S4).
Se ofrecen versiones Spark (Glue) y pandas (Lambda, señales y pruebas) con la
misma semántica.
"""
from __future__ import annotations

import pandas as pd


# ============================ pandas =========================================
def left_anti_pd(izq: pd.DataFrame, der: pd.DataFrame, on) -> pd.DataFrame:
    """Filas de `izq` sin pareja en `der` (no trae columnas de `der`)."""
    on = [on] if isinstance(on, str) else list(on)
    claves = der[on].dropna().drop_duplicates()
    m = izq.merge(claves, on=on, how="left", indicator=True)
    return m[m["_merge"] == "left_only"].drop(columns="_merge")


def left_semi_pd(izq: pd.DataFrame, der: pd.DataFrame, on) -> pd.DataFrame:
    """Filas de `izq` con pareja en `der`, sin duplicar ni traer columnas."""
    on = [on] if isinstance(on, str) else list(on)
    claves = der[on].dropna().drop_duplicates()
    return izq.merge(claves, on=on, how="inner")


def compras_sin_scop_pd(compras: pd.DataFrame, ordenes_scop: pd.DataFrame | None = None) -> pd.DataFrame:
    """left_anti contra las órdenes SCOP propias (PU-03); sin PU-03, código vacío."""
    if ordenes_scop is None:
        return compras[compras["codigo_scop"].isna()]
    return left_anti_pd(compras, ordenes_scop, "codigo_scop")


def ventas_sin_compra_pd(ventas: pd.DataFrame, compras: pd.DataFrame) -> pd.DataFrame:
    return left_anti_pd(ventas, compras, "codigo_scop")


def unidades_habilitadas_pd(movs: pd.DataFrame, flota: pd.DataFrame) -> pd.DataFrame:
    return left_semi_pd(movs, flota[flota["habilitada"].fillna(False)], "placa_norm")


def compras_con_tc_pd(compras: pd.DataFrame, tc: pd.DataFrame) -> pd.DataFrame:
    """left_outer por fecha; días no hábiles toman el último valor hábil anterior."""
    c = compras.assign(_f=pd.to_datetime(compras["fecha"])).sort_values("_f")
    t = tc.assign(_f=pd.to_datetime(tc["fecha"]))[["_f", "tc_oficial"]].sort_values("_f")
    return pd.merge_asof(c, t, on="_f", direction="backward").drop(columns="_f")


# ============================ Spark ==========================================
def compras_con_scop(compras, ordenes_scop):
    return compras.join(ordenes_scop, "codigo_scop", "left_outer")


def compras_sin_scop(compras, ordenes_scop):
    return compras.join(ordenes_scop, "codigo_scop", "left_anti")


def compras_vs_ventas(compras, ventas):
    from pyspark.sql import functions as F  # noqa: PLC0415

    clave = ["placa_norm", "fecha", "id_producto"]
    c = compras.groupBy(*clave).agg(F.sum("kg").alias("kg_comprados"))
    v = ventas.groupBy(*clave).agg(F.sum("kg").alias("kg_vendidos"))
    return (c.join(v, clave, "full_outer")
            .fillna(0.0, subset=["kg_comprados", "kg_vendidos"]))


def ventas_sin_compra(ventas, compras):
    return ventas.join(compras.select("codigo_scop").dropna().distinct(), "codigo_scop", "left_anti")


def ventas_con_maestro(ventas, maestro):
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    return ventas.join(broadcast(maestro), "card_code", "left_outer")


def maestro_con_sunat(maestro, padron):
    from pyspark.sql import functions as F  # noqa: PLC0415

    return (maestro.join(padron.select("ruc", "estado_sunat", "condicion_domicilio"), "ruc", "left_outer")
            .withColumn("clase_sunat",
                        F.when(~F.col("ruc_valido"), "INVALIDO")
                         .when(F.col("estado_sunat").isNull(), "INEXISTENTE")
                         .otherwise("VALIDO")))


def unidades_habilitadas(movs, flota):
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    return movs.join(broadcast(flota.filter(F.col("habilitada"))), "placa_norm", "left_semi")


def compras_con_tc(compras, tc):
    """left_outer + último valor hábil anterior (ventana sobre la unión)."""
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    j = compras.join(broadcast(tc.select("fecha", "tc_oficial")), "fecha", "left_outer")
    w = Window.orderBy("fecha").rowsBetween(Window.unboundedPreceding, 0)
    return j.withColumn("tc_oficial", F.last("tc_oficial", ignorenulls=True).over(w))


def gold_con_eventos(gold, eventos):
    from pyspark.sql import functions as F  # noqa: PLC0415
    from pyspark.sql.functions import broadcast  # noqa: PLC0415

    return (gold.join(broadcast(eventos), ["anio", "mes"], "left_outer")
            .fillna({"evento_mercado": 0})
            .withColumn("evento_mercado", F.col("evento_mercado").cast("int")))
