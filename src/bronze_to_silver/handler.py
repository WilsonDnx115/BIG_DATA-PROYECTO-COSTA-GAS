"""Bronze → Silver con pandas (paso 3.3.3). Escalado VERTICAL (S1).

Corre igual en AWS Lambda (disparada por evento de S3 en `bronze/interno/`) y en
local. Para cada archivo:
  1. Lee como texto (Bronze es schema-on-read) y exige las columnas DECLARADAS
     en `schemas.FUENTES` (S5: esquema declarado, sin inferSchema). Si falta una
     columna, el archivo completo se rechaza.
  2. Convierte tipos explícitamente; lo no convertible pasa a nulo y se cuenta.
  3. Aplica limpieza (Tabla 3.5) y reglas de calidad (Tabla 3.7).
  4. Escribe Parquet Snappy particionado por anio/mes en silver/<dominio>/<tabla>/,
     los rechazos en silver/_rechazos/ y el reporte en silver/_calidad/.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd

from src.common import lake_io, limpieza, rutas, schemas
from src.quality import reglas
from src.quality.reglas import Reporte

_RE_CODIGO = re.compile(r"/(?:interno/estructurado/[^/]+|externo/publico)/([^/]+)/fecha_carga=")


# --- Lectura con esquema declarado -------------------------------------------
def leer_crudo(ruta: str) -> pd.DataFrame:
    suf = Path(ruta).suffix.lower()
    if ruta.startswith("s3://"):
        import awswrangler as wr  # noqa: PLC0415

        if suf == ".csv":
            return wr.s3.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""])
        return wr.s3.read_excel(ruta, dtype=str)
    if suf == ".csv":
        return pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(ruta, dtype=str)
    raise ValueError(f"Formato no soportado en Bronze→Silver: {suf}")


def aplicar_esquema(df: pd.DataFrame, fuente: str, rep: Reporte) -> pd.DataFrame:
    decl = schemas.FUENTES[fuente].columnas
    faltan = [c for c in decl if c not in df.columns]
    if faltan:
        raise ValueError(f"{fuente}: el archivo no cumple el esquema declarado; faltan {faltan}")
    df = df[list(decl)].rename(columns=schemas.columnas_destino(fuente))
    conv = {}
    for col, tipo in schemas.tipos_destino(fuente).items():
        antes = df[col].notna().sum()
        if tipo == "date":
            df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed", dayfirst=True).dt.date
        elif tipo == "double":
            df[col] = df[col].map(limpieza.a_kg).astype("float64")
        elif tipo == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")
        elif tipo == "bool":
            df[col] = df[col].map(limpieza.a_bool).astype("boolean")
        else:
            df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.strip())
        conv[col] = int(antes - df[col].notna().sum())
    rep.reglas["_conversion_a_nulo"] = conv     # Tabla 3.5: «lo no convertible pasa a nulo y se cuenta»
    return df


def _anio_mes(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.to_datetime(df["fecha"])
    df["anio"] = f.dt.year.astype("int32")
    df["mes"] = f.dt.month.astype("int32")
    return df


def _separar(df: pd.DataFrame, cumple: pd.Series, motivo: str, rechazos: list) -> pd.DataFrame:
    malos = df[~cumple]
    if len(malos):
        rechazos.append(malos.assign(motivo=motivo))
    return df[cumple].copy()


# --- Transformaciones por fuente ---------------------------------------------
def transformar_aba_02(df, rep, rechazos):
    cargada = df["placa_cargada_raw"].map(limpieza.normalizar_placa)
    facturada = df["placa_facturada_raw"].map(limpieza.normalizar_placa)
    df["placa_cargada"] = cargada.str[0]
    df["placa_facturada"] = facturada.str[0]
    df["fecha_en_placa"] = facturada.str[1]                        # «T1A123 15/07/2023»
    df["flag_placa_divergente"] = (df["placa_cargada"].notna() & df["placa_facturada"].notna()
                                   & (df["placa_cargada"] != df["placa_facturada"]))
    df["estado"] = df["estado"].map(limpieza.normalizar_estado)
    df["codigo_scop"] = df["codigo_scop"].where(df["codigo_scop"].fillna("").str.len() > 0)
    rep.registrar("placa_valida", reglas.placa_valida(df["placa_cargada"]))
    rep.registrar("kg_en_rango", reglas.kg_en_rango(df["kg"]))
    df = _separar(df, rep.registrar("fecha_coherente", reglas.fecha_coherente(df["fecha"])), "fecha_fuera_de_alcance", rechazos)
    df = _separar(df, rep.registrar("unicidad", reglas.unicidad(df, ("documento",))), "duplicado", rechazos)
    df = _anio_mes(df)
    rep.medir_completitud(df, ["placa_cargada", "codigo_scop", "kg", "tipo_cambio"])
    return df.drop(columns=["placa_cargada_raw", "placa_facturada_raw"])


def transformar_com_19(df, rep, rechazos):
    df["placa_norm"] = df["placa_raw"].map(lambda v: limpieza.normalizar_placa(v)[0])
    df["codigo_scop"] = df["codigo_scop"].where(df["codigo_scop"].fillna("").str.len() > 0)
    rep.registrar("placa_valida", reglas.placa_valida(df["placa_norm"]))
    rep.registrar("kg_en_rango", reglas.kg_en_rango(df["kg"]))
    df = _separar(df, rep.registrar("fecha_coherente", reglas.fecha_coherente(df["fecha"])), "fecha_fuera_de_alcance", rechazos)
    df = _separar(df, rep.registrar("unicidad", reglas.unicidad(df, ("documento", "linea"))), "duplicado", rechazos)
    df = _anio_mes(df)
    df["flag_precio_atipico"] = ~rep.registrar("precio_en_rango", reglas.precio_en_rango(df))
    rep.medir_completitud(df, ["placa_norm", "codigo_scop", "card_code", "precio"])
    return df.drop(columns=["placa_raw"])


def transformar_dis_01(df, rep, rechazos):
    df["placa_norm"] = df["placa_raw"].map(lambda v: limpieza.normalizar_placa(v)[0])
    df["conductor_hash"] = df["conductor"].map(limpieza.seudonimizar)   # Ley 29733
    rep.registrar("placa_valida", reglas.placa_valida(df["placa_norm"]))
    df = _separar(df, df["placa_norm"].notna(), "placa_invalida", rechazos)
    df = df.drop_duplicates("placa_norm")
    rep.medir_completitud(df, ["capacidad_kg", "habilitada"])
    return df[schemas.CONTRATOS["flota"].columnas()]


def transformar_red_02(df, rep, rechazos):
    clas = df["documento_raw"].map(limpieza.clasificar_documento)
    df["documento_norm"] = clas.str[0]
    df["clase_documento"] = clas.str[1]
    df["ruc"] = df["documento_norm"].where(df["clase_documento"] == "RUC")
    df["ruc_valido"] = df["clase_documento"] == "RUC"
    df["documento_hash"] = df["documento_norm"].map(limpieza.seudonimizar)
    df["estado"] = df["estado"].map(limpieza.normalizar_estado)
    rep.registrar("ruc_valido", df["clase_documento"].isin(["RUC", "DNI", "INVALIDO", "VACIO"]))
    rep.reglas["clases_documento"] = df["clase_documento"].value_counts().to_dict()
    df = _separar(df, rep.registrar("unicidad", reglas.unicidad(df, ("card_code",))), "duplicado", rechazos)
    rep.medir_completitud(df, ["documento_norm", "capacidad_kg", "canal"])
    return df[schemas.CONTRATOS["maestro"].columnas()]


TRANSFORMACIONES = {"aba_02": transformar_aba_02, "com_19": transformar_com_19,
                    "dis_01": transformar_dis_01, "red_02": transformar_red_02}
CONTRATO_SALIDA = {"dis_01": "flota", "red_02": "maestro"}


def destino_silver(fuente: str) -> str:
    f = schemas.FUENTES[fuente]
    return rutas.ruta("silver", f.dominio, f.tabla)


# --- Orquestación ------------------------------------------------------------
def procesar_archivo(ruta_bronze: str, fuente: str | None = None) -> dict:
    fuente = fuente or codigo_desde_ruta(ruta_bronze)
    if fuente == "bcrp_tc":
        return procesar_bcrp(ruta_bronze)
    if fuente not in TRANSFORMACIONES:
        return {"fuente": fuente, "estado": "omitido", "motivo": "sin transformación declarada"}
    rep = Reporte(fuente)
    crudo = leer_crudo(ruta_bronze)
    rep.filas_entrada = len(crudo)
    rechazos: list[pd.DataFrame] = []
    df = aplicar_esquema(crudo, fuente, rep)
    df = TRANSFORMACIONES[fuente](df, rep, rechazos)
    lake_io.escribir_parquet(df, destino_silver(fuente), contrato=CONTRATO_SALIDA.get(fuente))
    rep.filas_salida = len(df)
    hoy = date.today().isoformat()
    if rechazos:
        r = pd.concat(rechazos, ignore_index=True).astype(str)
        rep.rechazadas = len(r)
        lake_io.escribir_parquet(r.drop(columns=["anio", "mes"], errors="ignore"),
                                 rutas.ruta("silver", "_rechazos", schemas.FUENTES[fuente].tabla, f"fecha_proceso={hoy}"))
    lake_io.escribir_json(rep.a_dict(), rutas.ruta("silver", "_calidad", f"fecha={hoy}", f"{fuente}.json"))
    return rep.a_dict()


def procesar_bcrp(ruta_bronze: str) -> dict:
    """PU-02: JSON de BCRPData → silver/referencia/tipo_cambio (fecha, tc_oficial)."""
    with open(ruta_bronze, encoding="utf-8") if not ruta_bronze.startswith("s3://") else _abrir_s3(ruta_bronze) as f:
        datos = json.load(f)
    meses = {"Ene": "Jan", "Abr": "Apr", "Ago": "Aug", "Set": "Sep", "Dic": "Dec"}
    filas = []
    for p in datos["periods"]:
        nombre = p["name"]
        for es, en in meses.items():
            nombre = nombre.replace(es, en)
        valor = limpieza.a_kg(p["values"][0]) if p["values"][0] not in ("n.d.", "") else None
        filas.append({"fecha": pd.to_datetime(nombre, format="%d.%b.%y", errors="coerce"), "tc_oficial": valor})
    df = pd.DataFrame(filas).dropna()
    df["fecha"] = df["fecha"].dt.date
    df = _anio_mes(df)
    lake_io.escribir_parquet(df, rutas.ruta("silver", "referencia", "tipo_cambio"))
    return {"fuente": "bcrp_tc", "filas_salida": len(df)}


def _abrir_s3(uri: str):
    import io  # noqa: PLC0415

    import boto3  # noqa: PLC0415

    bucket, key = uri[5:].split("/", 1)
    return io.StringIO(boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"))


def codigo_desde_ruta(ruta: str) -> str:
    m = _RE_CODIGO.search(ruta.replace("\\", "/"))
    if not m:
        raise ValueError(f"No se reconoce la fuente en la ruta: {ruta}")
    return m.group(1)


# --- Tabla unificada de movimientos (3.3.4) ----------------------------------
def construir_movimientos() -> pd.DataFrame:
    """Una fila por movimiento (compra/venta) con placa normalizada: entrada de la conciliación."""
    cols = schemas.CONTRATOS["movimientos"].columnas()
    compras = lake_io.leer_parquet(destino_silver("aba_02"))
    ventas = lake_io.leer_parquet(destino_silver("com_19"))
    c = pd.DataFrame({
        "tipo_mov": "compra", "documento": compras["documento"], "linea": 0,
        "placa_norm": compras["placa_cargada"], "fecha": compras["fecha"],
        "id_producto": compras["id_producto"], "kg_comprados": compras["kg"],
        "kg_despachados": compras["kg"], "kg_vendidos": 0.0,
        "codigo_scop": compras["codigo_scop"], "card_code": None, "precio": None,
        "canal": None, "anio": compras["anio"], "mes": compras["mes"]})
    v = pd.DataFrame({
        "tipo_mov": "venta", "documento": ventas["documento"], "linea": ventas["linea"],
        "placa_norm": ventas["placa_norm"], "fecha": ventas["fecha"],
        "id_producto": ventas["id_producto"], "kg_comprados": 0.0, "kg_despachados": 0.0,
        "kg_vendidos": ventas["kg"], "codigo_scop": ventas["codigo_scop"],
        "card_code": ventas["card_code"], "precio": ventas["precio"],
        "canal": ventas["canal"], "anio": ventas["anio"], "mes": ventas["mes"]})
    mov = pd.concat([c.dropna(axis=1, how="all"), v], ignore_index=True)[cols]
    mov = mov[mov["placa_norm"].notna()][cols]       # placa inválida: se excluye de la conciliación (Tabla 3.7)
    lake_io.escribir_parquet(mov, rutas.ruta("silver", "movimientos"), contrato="movimientos")
    return mov


# --- Punto de entrada de AWS Lambda ------------------------------------------
def lambda_handler(event, context):  # pragma: no cover - se prueba en AWS
    resultados = []
    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        resultados.append(procesar_archivo(f"s3://{bucket}/{key}"))
        if codigo_desde_ruta(key) in ("aba_02", "com_19"):
            construir_movimientos()
    return {"procesados": len(resultados), "resultados": resultados}
