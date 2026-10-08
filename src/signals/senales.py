"""Señales determinísticas (paso 4.2.1, Tabla 4.3).

Cada señal compara DOS registros del mismo hecho y devuelve filas con el
contrato `fact_alerta`. El grado de evidencia es «alto» cuando el segundo
registro es externo (Osinergmin/SCOP, MTC, SUNAT) y «medio» si es interno.

  S1  placa cargada ≠ facturada                (ABA-02)               alto   H1/H2
  S4  carga > capacidad autorizada del vehículo (ABA-02 × DIS-01)     medio* H1
  S5  entrega > capacidad autorizada del local  (COM-19 × RED-02)     medio* H1
  S7  volumen a unidad no habilitada para GLP   (left_anti DIS-01)    medio  H1
  S8  venta cuyo SCOP no cierra con una compra  (left_anti COM-19)    alto   H1
  S10 precio bajo la mediana del canal          (COM-19)              medio  H4
  (*) «alto» cuando exista el dato externo del MTC / Registro de Hidrocarburos.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from src.common import config, lake_io, rutas, schemas
from src.common.hipotesis import SENAL_A_HIPOTESIS
from src.silver_to_gold import uniones

CATALOGO = {
    "S1": ("Placa cargada distinta de la facturada", "alto"),
    "S4": ("Carga superior a la capacidad del vehículo", "medio"),
    "S5": ("Entrega superior a la capacidad del local", "medio"),
    "S7": ("Volumen asignado a unidad no habilitada", "medio"),
    "S8": ("Venta sin compra SCOP asociada", "alto"),
    "S10": ("Precio por debajo de la mediana del canal", "medio"),
}


def _alertas(df: pd.DataFrame, senal: str, placa: str, kg: str, puntaje=None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=schemas.CONTRATOS["fact_alerta"].columnas())
    out = pd.DataFrame({
        "senal": senal, "tipo": "regla", "fecha": df["fecha"].values,
        "placa_norm": df[placa].values, "documento": df["documento"].astype(str).values,
        "kg": df[kg].astype(float).values,
        "valor_soles": df[kg].astype(float).values * config.PRECIO_REF_KG,
        "puntaje": puntaje.values if puntaje is not None else 1.0,
        "grado_evidencia": CATALOGO[senal][1], "estado_revision": "pendiente",
        "anio": df["anio"].astype("int32").values, "mes": df["mes"].astype("int32").values,
    })
    out["id_alerta"] = [hashlib.md5(f"{senal}|{d}|{p}".encode()).hexdigest()[:12]
                        for d, p in zip(out["documento"], out["placa_norm"])]
    return out[schemas.CONTRATOS["fact_alerta"].columnas()]


def s1(compras):
    d = compras[compras["flag_placa_divergente"].fillna(False)]
    return _alertas(d, "S1", "placa_cargada", "kg")


def s4(compras, flota):
    d = compras.merge(flota[["placa_norm", "capacidad_kg"]], left_on="placa_cargada",
                      right_on="placa_norm", how="inner")
    d = d[d["kg"] > d["capacidad_kg"]]
    return _alertas(d, "S4", "placa_cargada", "kg", d["kg"] / d["capacidad_kg"])


def s5(ventas, maestro):
    d = ventas.merge(maestro[["card_code", "capacidad_kg"]].rename(columns={"capacidad_kg": "cap_local"}),
                     on="card_code", how="inner")
    d = d[d["cap_local"].notna() & (d["kg"] > d["cap_local"])]
    return _alertas(d, "S5", "placa_norm", "kg", d["kg"] / d["cap_local"])


def s7(compras, flota):
    c = compras.rename(columns={"placa_cargada": "placa_norm"})
    d = uniones.left_anti_pd(c, flota[flota["habilitada"].fillna(False)], "placa_norm")
    return _alertas(d, "S7", "placa_norm", "kg")


def s8(ventas, compras):
    d = uniones.ventas_sin_compra_pd(ventas.dropna(subset=["codigo_scop"]), compras)
    return _alertas(d, "S8", "placa_norm", "kg")


def s10(ventas):
    v = ventas.dropna(subset=["precio"]).copy()
    v["mediana"] = v.groupby(["canal", "id_producto", "anio", "mes"])["precio"].transform("median")
    d = v[v["precio"] < v["mediana"] * (1 - config.TOL_PRECIO_S10)]
    return _alertas(d, "S10", "placa_norm", "kg", 1 - d["precio"] / d["mediana"])


def calcular_todas() -> pd.DataFrame:
    leer = lambda *p: lake_io.leer_parquet(rutas.ruta("silver", *p))  # noqa: E731
    compras = leer("compras", "aba_02_ordenes_scop")
    ventas = leer("ventas", "com_19_lineas")
    flota = leer("flota", "dis_01_vehiculos")
    maestro = leer("maestro", "red_02_distribuidores")
    partes = [s1(compras), s4(compras, flota), s5(ventas, maestro),
              s7(compras, flota), s8(ventas, compras), s10(ventas)]
    return pd.concat([p for p in partes if len(p)], ignore_index=True)


def resumen(alertas: pd.DataFrame) -> pd.DataFrame:
    r = alertas.groupby("senal").agg(alertas=("id_alerta", "count"), kg=("kg", "sum"),
                                     unidades=("placa_norm", "nunique")).reset_index()
    r["hipotesis"] = r["senal"].map(SENAL_A_HIPOTESIS)
    r["descripcion"] = r["senal"].map(lambda s: CATALOGO.get(s, ("",))[0])
    return r


def guardar(alertas: pd.DataFrame) -> str:
    destino = rutas.ruta("gold", "fact_alerta")
    lake_io.escribir_parquet(alertas, destino, contrato="fact_alerta")
    return destino


if __name__ == "__main__":
    a = calcular_todas()
    guardar(a)
    print(resumen(a).to_string(index=False))
