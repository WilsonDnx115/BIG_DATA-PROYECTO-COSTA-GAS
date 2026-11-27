"""Limpieza por tabla Silver (informe v6, Tabla 3.5).

Cada función recibe las filas leídas de una fuente, con los nombres estándar del
contrato más `hoja`, `fila`, `_anio`, `_mes` y `_empresa`, y devuelve las columnas
de salida y un diccionario de métricas de calidad. Ninguna regla inventa datos:
lo que no se puede convertir queda nulo y se cuenta.
"""
from __future__ import annotations

import re

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
    if "kg" in df.columns:                                  # 2020: una sola cantidad y el producto en TIPO
        o["kg_glp_e"] = o["kg"].where(o["tipo"] == "GLP-E")
        o["kg_glp_g"] = o["kg"].where(o["tipo"] == "GLP-G")
    o["placa_norm"], _, o["centro_costo"] = _placas(_col(df, "placa"))
    o["guia"] = _texto(_col(df, "guia"))
    o["monto_usd"] = _num(_col(df, "monto_usd"))
    o["tipo_cambio"] = _num(_col(df, "tipo_cambio"))
    o["tc_valido"] = o["tipo_cambio"].map(L.tc_valido).astype("boolean")
    o["monto_pagado"] = _num(_col(df, "monto_pagado"))
    o["precio_unitario"] = _num(_col(df, "precio_unitario"))
    o["total"] = _num(_col(df, "total"))
    o["estado"] = _texto(_col(df, "estado"), mayus=True)
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
    o["estado"] = _texto(df["estado"], mayus=True)
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
    o["placa_texto"] = _texto(df["placa"], mayus=True)
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
        "traslada_gas_si_con_placa_valida": int((o["traslada_gas"].fillna(False) & o["placa_norm"].notna()).sum()),
        "placas_distintas": int(o["placa_norm"].nunique()),
        "traslada_gas_declarado": int(o["traslada_gas"].notna().sum()),
    }
    return o, calidad                                  # las filas sin placa válida se conservan con placa_norm nulo


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
    o["es_glp"] = o["articulo"].map(L.es_glp).astype("boolean")
    glp = o["es_glp"].fillna(False).astype(bool)
    registrado = _num(_col(df, "kg")).where(glp)
    derivado = pd.Series([L.a_kilos(u, c, a) if g else None
                          for u, c, a, g in zip(o["unidad_medida"], o["cantidad"], o["articulo"], glp)],
                         index=df.index, dtype="float64")
    o["kg"] = registrado.where(registrado.notna(), derivado)
    o["kg_origen"] = "no_glp"
    o.loc[glp, "kg_origen"] = "sin_conversion"
    o.loc[derivado.notna(), "kg_origen"] = "derivado"
    o.loc[registrado.notna(), "kg_origen"] = "registrado"
    o["cliente_id"] = _col(df, "cliente_codigo").map(lambda v: L.seudonimizar(a_texto(v)))
    o["indicador"] = _texto(_col(df, "indicador"), mayus=True)
    o["documento"] = _texto(_col(df, "documento"), mayus=True)
    o["vendedor_hash"] = df["vendedor"].map(lambda v: L.seudonimizar(a_texto(v)))
    calidad = {
        "fecha_valida": _tasa(o["fecha"].notna()),
        "lineas_glp": int(glp.sum()),
        "lineas_no_glp": int((~glp).sum()),
        "lineas_glp_convertibles_a_kg": _tasa(o.loc[glp, "kg"].notna()),
        "kg_registrado": int((o["kg_origen"] == "registrado").sum()),
        "kg_derivado": int((o["kg_origen"] == "derivado").sum()),
        "filas_con_placa": _tasa(o["placa_norm"].notna()),
    }
    return o, calidad


# --- pedidos_proveedor (A07) -------------------------------------------------
_RE_DOCUMENTO = re.compile(r"^([A-Za-z0-9]+)\s*[-/]\s*0*(\d+)$")


def _documento(valor) -> tuple[str | None, str | None, str | None, str | None]:
    """«F001-00012345» → («F001-12345», «F001», «12345», None).

    Devuelve (documento, serie, numero, crudo). Lo que no se puede separar en serie y
    número se conserva tal cual en `documento` y se copia a `crudo` para poder contarlo:
    sin serie, `cruce_s12` no encuentra su pareja en logística y la factura sale como
    «solo_tesoreria». No se inventa una serie.
    """
    t = a_texto(valor)
    if t is None:
        return None, None, None, None
    limpio = t.upper().replace(" ", "")
    m = _RE_DOCUMENTO.match(limpio)
    if not m:
        return limpio, None, None, t          # `crudo` conserva el texto original de la celda
    serie, numero = m.group(1), m.group(2)
    return f"{serie}-{numero}", serie, numero, None


def _fechas(serie: pd.Series) -> tuple[list, list]:
    """Fechas convertidas y su estado: ok, sin_fecha o no_convertible. Nada se inventa."""
    valores = [L.a_fecha(v) for v in serie]
    crudos = [a_texto(v) for v in serie]
    estados = ["sin_fecha" if c is None else ("ok" if f is not None else "no_convertible")
               for f, c in zip(valores, crudos)]
    return valores, estados


def pedidos_proveedor(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Lado de tesorería del cruce S12: una fila por factura registrada en el pedido.

    El proveedor es el nombre de la hoja (PETROPERU, SOLGAS o PLUSPETROL). El documento
    se normaliza a «SERIE-NUMERO» porque así lo parte `cruce_s12` para cruzarlo contra
    `compras_glp`. Las fechas que no se pueden convertir quedan nulas y se cuentan en
    `silver/_control/`.
    """
    o = pd.DataFrame(index=df.index)
    o["proveedor"] = _texto(_col(df, "_empresa"), mayus=True)

    doc = _col(df, "factura").map(_documento)
    o["documento"] = doc.str[0]
    o["serie"] = doc.str[1]
    o["numero"] = doc.str[2]
    o["documento_crudo"] = doc.str[3]

    o["nro_scop"] = _digitos(_col(df, "nro_scop"))
    o["producto"] = _texto(_col(df, "producto"), mayus=True)
    o["kg"] = _num(_col(df, "cantidad"))
    o["moneda"] = _texto(_col(df, "moneda"), mayus=True)
    o["total"] = _num(_col(df, "total"))
    o["percepcion"] = _num(_col(df, "percepcion"))
    o["tipo_cambio"] = _num(_col(df, "tipo_cambio"))
    o["tc_valido"] = o["tipo_cambio"].map(L.tc_valido).astype("boolean")
    en_usd = o["moneda"].isin(["USD", "US$", "DOLARES", "DÓLARES", "$"])
    o["usd_por_kg"] = (o["total"] / o["kg"]).where(en_usd & (o["kg"] > 0))
    o["deuda"] = _num(_col(df, "deuda"))
    o["pagos"] = _num(_col(df, "pagos"))

    o["fecha"], _ = _fechas(_col(df, "fecha"))
    o["fecha_pago"], _ = _fechas(_col(df, "fecha_pago"))
    o["fecha_vence"], estado_vence = _fechas(_col(df, "fecha_vence"))
    o["estado_fecha_vence"] = estado_vence
    fecha = pd.to_datetime(pd.Series(o["fecha"], index=o.index), errors="coerce")
    o["anio"] = fecha.dt.year.astype("Int64")
    o["mes"] = fecha.dt.month.astype("Int64")

    o["grupo"] = _texto(_col(df, "grupo"), mayus=True)
    o["sede"] = _texto(_col(df, "sede"), mayus=True)
    o["banco"] = _texto(_col(df, "banco"), mayus=True)
    o["modalidad"] = _texto(_col(df, "modalidad"), mayus=True)

    con_tc = o["tipo_cambio"].notna()
    calidad = {
        "documento_presente": _tasa(o["documento"].notna()),
        "documento_sin_serie": int(o["documento_crudo"].notna().sum()),
        "fecha_valida": _tasa(pd.Series(o["fecha"], index=o.index).notna()),
        "vence_no_convertible": int((o["estado_fecha_vence"] == "no_convertible").sum()),
        "vence_sin_fecha": int((o["estado_fecha_vence"] == "sin_fecha").sum()),
        "fecha_pago_registrada": int(pd.Series(o["fecha_pago"], index=o.index).notna().sum()),
        "tc_registrados": int(con_tc.sum()),
        "tc_fuera_de_rango": int((con_tc & ~o["tc_valido"].fillna(False)).sum()),
        "kg_positivo": _tasa(o["kg"] > 0),
    }
    return o, calidad


# --- maestros: distribuidores y clientes (A08) --------------------------------
# Formas societarias peruanas. Un nombre que las lleva es de una persona juridica,
# asi que no es dato personal y se conserva legible.
_RE_PERSONA_JURIDICA = re.compile(
    r"\b(S\.?\s?A\.?\s?C|E\.?\s?I\.?\s?R\.?\s?L|S\.?\s?R\.?\s?L|S\.?\s?C\.?\s?R\.?\s?L|S\.?\s?A\.?\s?A|S\.?\s?A)\.?\s*$",
    re.IGNORECASE)


# Categorias de gasto que son combustible. La posicion E de `GASTOS FLOTA` trae 13
# categorias y una de ellas es de combustible; cubre el 15.6 % de las filas, y el texto
# libre de la posicion F confirma la misma proporcion (15.8 %). La medicion esta en
# docs/evidencias/gastos_posiciones.md.
RE_COMBUSTIBLE = re.compile(r"COMBUSTIBLE|PETROLEO|DIESEL|GASOLINA|GASOHOL|GRIFO|GLP|GNV")
# Un documento de 8 a 11 digitos pegado a la razon social: DNI, RUC de empresa o de
# persona natural. No pasa a Silver (CLAUDE.md, privacidad).
RE_DOCUMENTO = re.compile(r"\b\d{8,11}\b")


def _sin_documento(s: pd.Series) -> pd.Series:
    """Quita del texto cualquier documento pegado, y deja la razon social."""
    def limpiar(v):
        if not isinstance(v, str):
            return v
        limpio = re.sub(r"\s{2,}", " ", RE_DOCUMENTO.sub(" ", v)).strip(" -,;")
        return limpio or None
    return s.map(limpiar)


def gastos(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Gastos de la operacion. De aqui sale `gasto_combustible` de `fact_unidad_mes`.

    `es_combustible` queda **nulo** cuando la fuente no trae categoria: un falso diria
    que ese gasto no es combustible, y lo que pasa es que no se sabe. La agregacion de
    Gold se queda con las filas en verdadero, asi que un nulo no infla el KPI 4.
    """
    o = pd.DataFrame(index=df.index)
    o["mes_texto"] = _texto(_col(df, "mes_texto"), mayus=True)
    o["fecha"] = _col(df, "fecha").map(L.a_fecha)

    fecha = pd.to_datetime(o["fecha"], errors="coerce")
    o["anio"] = fecha.dt.year.astype("Int64")
    mes_de_la_fecha = fecha.dt.month.astype("Int64")
    mes_del_texto = o["mes_texto"].map(L.mes_a_numero).astype("Int64")
    o["mes"] = mes_de_la_fecha.where(mes_de_la_fecha.notna(), mes_del_texto)

    o["unidad_codigo"] = _texto(_col(df, "unidad_codigo"), mayus=True)
    o["placa_norm"], _, _ = _placas(_col(df, "placa_norm"))
    o["area"] = _texto(_col(df, "area"), mayus=True)
    o["proyecto"] = _texto(_col(df, "proyecto"), mayus=True)
    o["documento_gasto"] = _texto(_col(df, "documento_gasto"), mayus=True)
    o["categoria"] = _texto(_col(df, "categoria"), mayus=True)
    o["es_combustible"] = o["categoria"].map(
        lambda v: None if not isinstance(v, str) else bool(RE_COMBUSTIBLE.search(v))).astype("boolean")
    o["descripcion"] = _texto(_col(df, "descripcion"))
    o["comentarios"] = _texto(_col(df, "comentarios"))
    o["monto_soles"] = _num(_col(df, "monto_soles"))
    o["proveedor"] = _sin_documento(_texto(_col(df, "proveedor"), mayus=True))
    o["planta"] = _texto(_col(df, "planta"), mayus=True)

    calidad = {
        "placa_valida": _tasa(o["placa_norm"].notna()),
        "monto_valido": _tasa(o["monto_soles"].notna()),
        "fecha_valida": _tasa(o["fecha"].notna()),
        "con_categoria": _tasa(o["categoria"].notna()),
        "filas_de_combustible": int(o["es_combustible"].fillna(False).sum()),
    }
    return o, calidad


def _identidad(documento, nombre_razon, codigo_sn=None) -> dict:
    """Separa empresa de persona natural y seudonimiza lo que identifica a una persona.

    - RUC valido con prefijo 20 → persona juridica: el RUC y la razon social se conservan,
      porque la razon social no es dato personal y el RUC permite cruzar con SUNAT.
    - DNI, o RUC con otro prefijo (10, 15, 17) → persona natural: el numero y el nombre
      salen hasheados con sal; ni el numero ni el nombre pasan a Silver.
    - RUC de 11 digitos con prefijo 20 pero digito verificador malo → se trata como
      empresa (`INVALIDO`), pero sin publicar el RUC: por construccion no es una persona.
    - Sin documento → solo se conserva el nombre si lleva forma societaria; si no, se
      hashea, porque no hay forma de descartar que sea una persona.
    """
    doc, clase = L.clasificar_documento(documento)
    nombre = a_texto(nombre_razon)
    nombre = nombre.upper() if nombre else None
    codigo = a_texto(codigo_sn)
    vacio = {"entidad_id": None, "tipo_persona": "VACIO", "ruc": None, "documento_hash": None,
             "razon_social": None, "nombre_hash": None}

    if clase == "RUC" and doc.startswith("20"):
        return {**vacio, "entidad_id": doc, "tipo_persona": "JURIDICA", "ruc": doc, "razon_social": nombre}
    if clase in {"RUC", "DNI"}:                                   # 10, 15, 17 y DNI: persona natural
        h = L.seudonimizar(doc)
        return {**vacio, "entidad_id": h, "tipo_persona": "NATURAL",
                "documento_hash": h, "nombre_hash": L.seudonimizar(nombre)}
    if clase == "INVALIDO" and doc.startswith("20") and len(doc) == 11:
        return {**vacio, "entidad_id": codigo or L.seudonimizar(nombre), "tipo_persona": "INVALIDO",
                "razon_social": nombre}
    if clase == "INVALIDO":
        h = L.seudonimizar(doc)
        return {**vacio, "entidad_id": h, "tipo_persona": "NATURAL",
                "documento_hash": h, "nombre_hash": L.seudonimizar(nombre)}
    if nombre and _RE_PERSONA_JURIDICA.search(nombre):            # sin documento, pero con forma societaria
        return {**vacio, "entidad_id": codigo or L.seudonimizar(nombre), "tipo_persona": "JURIDICA",
                "razon_social": nombre}
    return {**vacio, "entidad_id": codigo or L.seudonimizar(nombre), "nombre_hash": L.seudonimizar(nombre)}


def _aplicar_identidad(o: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    ident = [_identidad(d, n, c) for d, n, c in
             zip(_col(df, "documento"), _col(df, "nombre_razon"), _col(df, "codigo_sn"))]
    for campo in ("entidad_id", "tipo_persona", "ruc", "documento_hash", "razon_social", "nombre_hash"):
        o[campo] = [i[campo] for i in ident]
    return o


def _calidad_maestro(o: pd.DataFrame) -> dict:
    return {
        "juridicas": int((o["tipo_persona"] == "JURIDICA").sum()),
        "naturales": int((o["tipo_persona"] == "NATURAL").sum()),
        "sin_documento": int((o["tipo_persona"] == "VACIO").sum()),
        "ruc_invalido": int((o["tipo_persona"] == "INVALIDO").sum()),
        "ruc_publicado": _tasa(o["ruc"].notna()),
        "entidad_id_presente": _tasa(o["entidad_id"].notna()),
    }


def distribuidores(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Maestro de distribuidores. La direccion exacta solo se conserva de una empresa."""
    o = _aplicar_identidad(pd.DataFrame(index=df.index), df)
    o["departamento"] = _texto(_col(df, "departamento"), mayus=True)
    o["provincia"] = _texto(_col(df, "provincia"), mayus=True)
    o["distrito"] = _texto(_col(df, "distrito"), mayus=True)
    direccion = _texto(_col(df, "direccion"))
    o["direccion"] = direccion.where(o["tipo_persona"] != "NATURAL")
    o["capacidad_kg"] = _num(_col(df, "capacidad_kg"))
    o["empresa_envasadora"] = _texto(_col(df, "empresa_envasadora"), mayus=True)
    o["tipo"] = _texto(_col(df, "tipo"), mayus=True)
    o["uit"] = _num(_col(df, "uit"))
    o["item"] = _entero(_col(df, "item"))
    calidad = {**_calidad_maestro(o),
               "capacidad_declarada": _tasa(o["capacidad_kg"] > 0),
               "direccion_omitida_por_privacidad": int((direccion.notna() & o["direccion"].isna()).sum())}
    return o, calidad


def clientes(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Maestro de clientes. Misma regla de identidad que distribuidores."""
    o = _aplicar_identidad(pd.DataFrame(index=df.index), df)
    o["codigo_sn"] = _texto(_col(df, "codigo_sn"), mayus=True)
    return o, _calidad_maestro(o)


TRANSFORMACIONES = {"compras_glp": compras_glp, "scop": scop, "unidades": unidades,
                    "ventas_unidad_mes": ventas_unidad_mes, "ventas_detalle": ventas_detalle,
                    "pedidos_proveedor": pedidos_proveedor,
                    "distribuidores": distribuidores, "clientes": clientes,
                    "gastos": gastos}
