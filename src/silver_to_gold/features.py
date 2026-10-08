"""Ingeniería de características (paso 3.3.8).

Variables a nivel unidad-mes que alimentan señales y modelos:
  ratio_carga_capacidad, precio_vs_mediana_canal, flag_placa_divergente,
  desvio_tc, es_pandemia_2020, evento_mercado, indice_quejas_marca.
Las dos últimas son de nivel mes/marca (fuentes no estructuradas); si aún no
existen en Silver valen 0 y se declara así.
"""
from __future__ import annotations

import pandas as pd

from src.common import lake_io, rutas
from src.silver_to_gold import uniones


def _leer(*partes):
    return lake_io.leer_parquet(rutas.ruta("silver", *partes))


def unidad_mes() -> pd.DataFrame:
    gold = lake_io.leer_parquet(rutas.ruta("gold", "fact_conciliacion_unidad"))
    compras = _leer("compras", "aba_02_ordenes_scop")
    ventas = _leer("ventas", "com_19_lineas")
    tc = _leer("referencia", "tipo_cambio")

    um = (gold.groupby(["placa_norm", "anio", "mes"], as_index=False)
          .agg(kg_comprados=("kg_comprados", "sum"), kg_vendidos=("kg_vendidos", "sum"),
               kg_diferencia=("kg_diferencia", "sum"), n_operaciones=("n_operaciones", "sum"),
               dias_operacion=("fecha", "nunique"), capacidad_kg=("capacidad_kg", "first"),
               max_kg_dia=("kg_comprados", "max")))
    um["pct_diferencia"] = (um["kg_diferencia"] / um["kg_comprados"]).where(um["kg_comprados"] > 0)
    um["ratio_carga_capacidad"] = um["max_kg_dia"] / um["capacidad_kg"]

    # flag_placa_divergente: proporción de compras del mes con placa cargada ≠ facturada (S1)
    div = (compras.rename(columns={"placa_cargada": "placa_norm"})
           .groupby(["placa_norm", "anio", "mes"], as_index=False)
           .agg(flag_placa_divergente=("flag_placa_divergente", "mean")))
    um = um.merge(div, on=["placa_norm", "anio", "mes"], how="left")

    # desvio_tc: |T.C. registrado − oficial| / oficial, promedio del mes
    if len(tc):
        ctc = uniones.compras_con_tc_pd(compras.dropna(subset=["tipo_cambio"]), tc)
        ctc["desvio_tc"] = (ctc["tipo_cambio"] - ctc["tc_oficial"]).abs() / ctc["tc_oficial"]
        dtc = (ctc.rename(columns={"placa_cargada": "placa_norm"})
               .groupby(["placa_norm", "anio", "mes"], as_index=False)["desvio_tc"].mean())
        um = um.merge(dtc, on=["placa_norm", "anio", "mes"], how="left")
    else:
        um["desvio_tc"] = 0.0

    # precio_vs_mediana_canal: precio unitario / mediana del canal-producto-mes, promedio por unidad-mes
    v = ventas.dropna(subset=["precio"]).copy()
    v["mediana"] = v.groupby(["canal", "id_producto", "anio", "mes"])["precio"].transform("median")
    v["precio_vs_mediana_canal"] = v["precio"] / v["mediana"]
    pv = (v.groupby(["placa_norm", "anio", "mes"], as_index=False)["precio_vs_mediana_canal"].mean())
    um = um.merge(pv, on=["placa_norm", "anio", "mes"], how="left")

    um["es_pandemia_2020"] = (um["anio"] == 2020).astype(int)
    eventos = _leer("eventos_mercado")
    if len(eventos):
        um = um.merge(eventos[["anio", "mes", "evento_mercado"]], on=["anio", "mes"], how="left")
    else:
        um["evento_mercado"] = 0
    quejas = _leer("textos_clasificados", "indice_quejas_marca")
    um["indice_quejas_marca"] = (quejas.groupby(["anio", "mes"])["indice"].mean()
                                 .reindex(pd.MultiIndex.from_frame(um[["anio", "mes"]])).to_numpy()
                                 if len(quejas) else 0.0)
    return um.fillna({"evento_mercado": 0, "indice_quejas_marca": 0.0,
                      "flag_placa_divergente": 0.0, "desvio_tc": 0.0})


FEATURES = ["pct_diferencia", "ratio_carga_capacidad", "flag_placa_divergente", "desvio_tc",
            "precio_vs_mediana_canal", "es_pandemia_2020", "evento_mercado", "indice_quejas_marca",
            "n_operaciones"]


def guardar(um: pd.DataFrame) -> str:
    destino = rutas.ruta("gold", "unidad_mes")
    lake_io.escribir_parquet(um, destino)
    return destino


if __name__ == "__main__":
    um = unidad_mes()
    print(guardar(um), len(um))
    print(um[FEATURES].describe().T.round(3))
