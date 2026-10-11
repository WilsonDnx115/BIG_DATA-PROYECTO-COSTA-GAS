"""Limpieza por tabla Silver (informe v6, Tabla 3.5).

Cada función recibe las filas leídas de una fuente, con los nombres estándar del
contrato más `hoja`, `fila`, `_anio`, `_mes` y `_empresa`, y devuelve las columnas
de salida y un diccionario de métricas de calidad. Ninguna regla inventa datos:
lo que no se puede convertir queda nulo y se cuenta.
"""
from __future__ import annotations

import pandas as pd

from src.common import limpieza as L
from src.silver.lector import a_texto


def _col(df: pd.DataFrame, nombre: str) -> pd.Series:
    """Columna del contrato o, si esta fuente no la trae, una serie de nulos."""
    return df[nombre] if nombre in df.columns else pd.Series([None] * len(df), index=df.index, dtype="object")


def _texto(s: pd.Series, mayus: bool = False) -> pd.Series:
    t = s.map(a_texto)
    return t.map(lambda v: v.upper() if isinstance(v, str) else v) if mayus else t


def _num(s: pd.Series) -> pd.Series:
    return s.map(L.a_kg).astype("float64")


def _entero(s: pd.Series) -> pd.Series:
    return _num(s).round().astype("Int64")


def _digitos(s: pd.Series) -> pd.Series:
    return s.map(lambda v: L.solo_digitos(a_texto(v)) or None)


def _placas(s: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    p = s.map(L.parsear_placa)
    return p.str[0], p.str[1], p.str[2]


def _tasa(serie: pd.Series) -> float:
    return round(float(serie.mean()), 4) if len(serie) else 0.0


def compras_glp(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    o = pd.DataFrame(index=df.index)
    o["anio"] = df["_anio"].astype("Int64")
    o["mes"] = df["_mes"].astype("Int64")
    o["proveedor"] = _texto(df["proveedor"], mayus=True)
    o["codigo_osinergmin"] = _texto(_col(df, "codigo_osinergmin"))
    o["nro_scop"] = _digitos(df["nro_scop"])
    fechas = [L.corregir_fecha_por_mes(L.a_fecha(f), a, m) for f, a, m in
              zip(df["fecha_factura"], df["_anio"].tolist(), df["_mes"].tolist())]
    o["fecha_factura"] = [f for f, _ in fechas]
    o["estado_fecha"] = [e for _, e in fechas]
    o["serie"] = _texto(_col(df, "serie"), mayus=True)
    o["numero"] = _texto(df["numero"], mayus=True)
    o["tipo"] = _texto(_col(df, "tipo"), mayus=True)
    o["kg_glp_e"] = _num(_col(df, "kg_glp_e"))
    o["kg_glp_g"] = _num(_col(df, "kg_glp_g"))
    suma = o[["kg_glp_e", "kg_glp_g"]].sum(axis=1, min_count=1)
    o["kg"] = _num(df["kg"]) if "kg" in df.columns else suma
    o["placa_norm"], _, o["centro_costo"] = _placas(_col(df, "placa"))
    o["guia"] = _texto(_col(df, "guia"))
    o["monto_usd"] = _num(_col(df, "monto_usd"))
    o["tipo_cambio"] = _num(_col(df, "tipo_cambio"))
    o["tc_valido"] = o["tipo_cambio"].map(L.tc_valido).astype("boolean")
    o["monto_pagado"] = _num(_col(df, "monto_pagado"))
    o["precio_unitario"] = _num(_col(df, "precio_unitario"))
    o["total"] = _num(_col(df, "total"))
    o["estado"] = _col(df, "estado").map(L.normalizar_estado)
    o["conductor_hash"] = _col(df, "conductor").map(lambda v: L.seudonimizar(a_texto(v)))
    con_tc = o["tipo_cambio"].notna()
    calidad = {
        "placa_valida": _tasa(o["placa_norm"].notna()),
        "scop_presente": _tasa(o["nro_scop"].notna()),
        "scop_11_digitos": _tasa(o["nro_scop"].str.len() == 11),
        "scop_repetidos": int(o["nro_scop"].dropna().duplicated().sum()),
        "fechas_invertidas": int((o["estado_fecha"] == "invertida").sum()),
        "fechas_que_discrepan": int((o["estado_fecha"] == "discrepa").sum()),
        "tc_registrados": int(con_tc.sum()),
        "tc_fuera_de_rango": int((con_tc & ~o["tc_valido"].fillna(False)).sum()),
        "kg_positivo": _tasa(o["kg"] > 0),
    }
    return o, calidad


def scop(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    o = pd.DataFrame(index=df.index)
    o["fecha"] = df["fecha"].map(L.a_fecha)
    o["nro_scop"] = _digitos(df["nro_scop"])
    o["producto"] = _texto(df["producto"], mayus=True)
    o["proveedor"] = _texto(df["proveedor"], mayus=True)
    o["lugar_origen"] = _texto(df["lugar_origen"], mayus=True)
    o["placa_cargada"], _, _ = _placas(df["placa_cargada"])
    o["placa_facturada"], o["fecha_en_placa"], _ = _placas(df["placa_facturada"])
    ambas = o["placa_cargada"].notna() & o["placa_facturada"].notna()
    o["flag_placa_divergente"] = (ambas & (o["placa_cargada"] != o["placa_facturada"])).astype("boolean")
    o["factura"] = _texto(df["factura"], mayus=True)
    o["estado"] = df["estado"].map(L.normalizar_estado)
    calidad = {
        "ordenes_con_ambas_placas": int(ambas.sum()),
        "ordenes_con_placa_divergente": int(o["flag_placa_divergente"].sum()),
        "fecha_valida": _tasa(o["fecha"].notna()),
    }
    return o, calidad


def unidades(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    o = pd.DataFrame(index=df.index)
    empresa = _texto(_col(df, "empresa"), mayus=True)
    o["empresa"] = empresa.where(empresa.notna(), df["_empresa"])
    o["zonal"] = _texto(_col(df, "zonal"), mayus=True)
    o["placa_norm"], _, _ = _placas(df["placa"])
    o["clase"] = _texto(_col(df, "clase"), mayus=True)
    o["marca"] = _texto(_col(df, "marca"), mayus=True)
    o["modelo"] = _texto(_col(df, "modelo"), mayus=True)
    o["anio_fabricacion"] = _entero(_col(df, "anio_fabricacion"))
    o["capacidad_glp_kg"] = _num(_col(df, "capacidad_glp_kg"))
    o["cert_mercancias_peligrosas"] = _texto(_col(df, "cert_mercancias_peligrosas"))
    o["uso"] = _texto(_col(df, "uso"), mayus=True)
    o["estado_soat"] = _texto(_col(df, "estado_soat"), mayus=True)
    o["traslada_gas"] = _col(df, "traslada_gas").map(L.a_bool).astype("boolean")
    calidad = {
        "placa_valida": _tasa(o["placa_norm"].notna()),
        "con_capacidad": int(o["capacidad_glp_kg"].notna().sum()),
        "traslada_gas_si": int(o["traslada_gas"].fillna(False).sum()),
        "traslada_gas_declarado": int(o["traslada_gas"].notna().sum()),
    }
    return o[o["placa_norm"].notna()], calidad         # sin placa válida no hay vehículo que identificar


def ventas_unidad_mes(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    o = pd.DataFrame(index=df.index)
    o["anio"] = df["_anio"].astype("Int64")
    o["mes"] = df["mes_texto"].map(L.mes_a_numero).astype("Int64")
    o["proyecto"] = _texto(df["proyecto"], mayus=True)
    o["placa_norm"], _, o["centro_costo"] = _placas(df["proyecto"])
    o["articulo"] = _texto(df["articulo"], mayus=True)
    o["tipo"] = _texto(df["tipo"], mayus=True)
    o["unidad_negocio"] = _texto(df["unidad_negocio"], mayus=True)
    o["unidad_medida"] = _texto(df["unidad_medida"], mayus=True)
    o["cantidad"] = _num(df["cantidad"])
    o["precio_promedio"] = _num(df["precio_promedio"])
    o["vendedor_hash"] = df["vendedor"].map(lambda v: L.seudonimizar(a_texto(v)))
    o["kg"] = _num(df["kg"])
    o["balones_galones"] = _num(df["balones_galones"])
    kg_total = float(o["kg"].sum())
    calidad = {
        "mes_reconocido": _tasa(o["mes"].notna()),
        "filas_con_placa": _tasa(o["placa_norm"].notna()),
        "kg_con_placa_valida": round(float(o.loc[o["placa_norm"].notna(), "kg"].sum()) / kg_total, 4) if kg_total else 0.0,
    }
    return o, calidad


def ventas_detalle(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    o = pd.DataFrame(index=df.index)
    o["fecha"] = df["fecha"].map(L.a_fecha)
    fechas = pd.to_datetime(o["fecha"], errors="coerce")
    o["anio"] = fechas.dt.year.astype("Int64")
    o["mes"] = fechas.dt.month.astype("Int64")
    o["proyecto"] = _texto(df["proyecto"], mayus=True)
    o["placa_norm"], _, o["centro_costo"] = _placas(df["proyecto"])
    o["linea"] = _entero(_col(df, "linea"))
    o["articulo_codigo"] = _texto(_col(df, "articulo_codigo"), mayus=True)
    o["articulo"] = _texto(df["articulo"], mayus=True)
    o["unidad_medida"] = _texto(df["unidad_medida"], mayus=True)
    o["cantidad"] = _num(df["cantidad"])
    o["precio_unitario"] = _num(df["precio_unitario"])
    o["importe"] = _num(df["importe"])
    registrado = _num(_col(df, "kg"))
    derivado = pd.Series([L.a_kilos(u, c, a) for u, c, a in zip(o["unidad_medida"], o["cantidad"], o["articulo"])],
                         index=df.index, dtype="float64")
    o["kg"] = registrado.where(registrado.notna(), derivado)
    o["kg_origen"] = "sin_conversion"
    o.loc[derivado.notna(), "kg_origen"] = "derivado"
    o.loc[registrado.notna(), "kg_origen"] = "registrado"
    o["cliente_id"] = _col(df, "cliente_codigo").map(lambda v: L.seudonimizar(a_texto(v)))
    o["indicador"] = _texto(_col(df, "indicador"), mayus=True)
    o["documento"] = _texto(_col(df, "documento"), mayus=True)
    o["vendedor_hash"] = df["vendedor"].map(lambda v: L.seudonimizar(a_texto(v)))
    calidad = {
        "fecha_valida": _tasa(o["fecha"].notna()),
        "lineas_convertibles_a_kg": _tasa(o["kg"].notna()),
        "kg_registrado": int((o["kg_origen"] == "registrado").sum()),
        "kg_derivado": int((o["kg_origen"] == "derivado").sum()),
        "filas_con_placa": _tasa(o["placa_norm"].notna()),
    }
    return o, calidad


TRANSFORMACIONES = {"compras_glp": compras_glp, "scop": scop, "unidades": unidades,
                    "ventas_unidad_mes": ventas_unidad_mes, "ventas_detalle": ventas_detalle}
