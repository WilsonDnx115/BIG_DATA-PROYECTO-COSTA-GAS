"""Esquemas declarados (pasos 2.2.2 y 3.3.2).

Bronze es schema-on-read; Silver y Gold tienen contrato fijo. Leer con un
esquema declarado evita la pasada extra de `inferSchema` y los errores de tipo
(S5). Cada fuente interna declara:
  * `columnas`: nombre original en el archivo → (nombre destino, tipo lógico)
  * `dominio` / `tabla`: destino en `silver/<dominio>/<tabla>/`
  * `clave_unica`: clave para deduplicar (documento + línea)

IMPORTANTE: los nombres de columna originales siguen el diccionario v2.0. Si
un archivo real usa otro encabezado, se corrige aquí y en ningún otro lugar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pyarrow as pa

# Tipos lógicos → pyarrow y Spark
_PA = {
    "string": pa.string(), "double": pa.float64(), "int": pa.int32(),
    "long": pa.int64(), "bool": pa.bool_(), "date": pa.date32(),
}


@dataclass(frozen=True)
class FuenteInterna:
    codigo: str
    proceso: str
    dominio: str
    tabla: str
    columnas: dict[str, tuple[str, str]]
    clave_unica: tuple[str, ...] = ()
    descripcion: str = ""


# --- Fuentes internas (Bronze → Silver) ---------------------------------------
FUENTES: dict[str, FuenteInterna] = {
    "aba_02": FuenteInterna(
        codigo="aba_02", proceso="abastecimiento", dominio="compras", tabla="aba_02_ordenes_scop",
        descripcion="Órdenes SCOP y compras de GLP (placa cargada/facturada, T.C.)",
        columnas={
            "SCOP": ("codigo_scop", "string"),
            "FECHA": ("fecha", "date"),
            "PLACA CARGADA": ("placa_cargada_raw", "string"),
            "PLACA FACTURADA": ("placa_facturada_raw", "string"),
            "PRODUCTO": ("id_producto", "string"),
            "KG": ("kg", "double"),
            "T.C.": ("tipo_cambio", "double"),
            "N DOC": ("documento", "string"),
            "ESTADO": ("estado", "string"),
        },
        clave_unica=("documento",),
    ),
    "com_19": FuenteInterna(
        codigo="com_19", proceso="comercial", dominio="ventas", tabla="com_19_lineas",
        descripcion="Líneas de venta del ERP con código SCOP (U_CTG_SCOPNUM)",
        columnas={
            "DocNum": ("documento", "string"),
            "LineNum": ("linea", "int"),
            "DocDate": ("fecha", "date"),
            "CardCode": ("card_code", "string"),
            "U_CTG_SCOPNUM": ("codigo_scop", "string"),
            "U_PLACA": ("placa_raw", "string"),
            "ItemCode": ("id_producto", "string"),
            "Kg": ("kg", "double"),
            "Price": ("precio", "double"),
            "Canal": ("canal", "string"),
        },
        clave_unica=("documento", "linea"),
    ),
    "dis_01": FuenteInterna(
        codigo="dis_01", proceso="distribucion", dominio="flota", tabla="dis_01_vehiculos",
        descripcion="Flota: capacidad autorizada y habilitación para GLP",
        columnas={
            "PLACA": ("placa_raw", "string"),
            "Capacidad Total de GLP Autorizado (KG)": ("capacidad_kg", "double"),
            "TRASLADO DE GAS (SI/NO)": ("habilitada", "bool"),
            "TIPO UNIDAD": ("tipo_unidad", "string"),
            "CONDUCTOR": ("conductor", "string"),
        },
        clave_unica=("placa_norm",),
    ),
    "red_02": FuenteInterna(
        codigo="red_02", proceso="redes", dominio="maestro", tabla="red_02_distribuidores",
        descripcion="Maestro de distribuidores (RUC/DNI, capacidad del local, canal)",
        columnas={
            "CardCode": ("card_code", "string"),
            "RUC/DNI": ("documento_raw", "string"),
            "CAP. ALMAC. TOTAL (KG)": ("capacidad_kg", "double"),
            "ESTADO": ("estado", "string"),
            "CANAL": ("canal", "string"),
        },
        clave_unica=("card_code",),
    ),
}


# --- Contratos de Silver y Gold -----------------------------------------------
@dataclass(frozen=True)
class Contrato:
    nombre: str
    campos: list[tuple[str, str]] = field(default_factory=list)
    particionada: bool = True

    def pyarrow(self) -> pa.Schema:
        return pa.schema([(n, _PA[t]) for n, t in self.campos])

    def spark(self):
        from pyspark.sql import types as T  # noqa: PLC0415  (pyspark solo en Glue/local con Spark)

        m = {"string": T.StringType(), "double": T.DoubleType(), "int": T.IntegerType(),
             "long": T.LongType(), "bool": T.BooleanType(), "date": T.DateType()}
        return T.StructType([T.StructField(n, m[t], True) for n, t in self.campos])

    def columnas(self) -> list[str]:
        return [n for n, _ in self.campos]


_PART = [("anio", "int"), ("mes", "int")]

CONTRATOS: dict[str, Contrato] = {
    "movimientos": Contrato("movimientos", [
        ("tipo_mov", "string"), ("documento", "string"), ("linea", "int"),
        ("placa_norm", "string"), ("fecha", "date"), ("id_producto", "string"),
        ("kg_comprados", "double"), ("kg_despachados", "double"), ("kg_vendidos", "double"),
        ("codigo_scop", "string"), ("card_code", "string"), ("precio", "double"),
        ("canal", "string"), *_PART]),
    "flota": Contrato("flota", [
        ("placa_norm", "string"), ("capacidad_kg", "double"), ("habilitada", "bool"),
        ("tipo_unidad", "string"), ("conductor_hash", "string")], particionada=False),
    "maestro": Contrato("maestro", [
        ("card_code", "string"), ("documento_hash", "string"), ("clase_documento", "string"),
        ("ruc", "string"), ("ruc_valido", "bool"), ("capacidad_kg", "double"),
        ("estado", "string"), ("canal", "string")], particionada=False),
    "fact_conciliacion_unidad": Contrato("fact_conciliacion_unidad", [
        ("placa_norm", "string"), ("fecha", "date"), ("id_producto", "string"),
        ("kg_comprados", "double"), ("kg_despachados", "double"), ("kg_vendidos", "double"),
        ("n_operaciones", "long"), ("kg_diferencia", "double"), ("pct_diferencia", "double"),
        ("valor_ref_soles", "double"), ("capacidad_kg", "double"), ("habilitada", "bool"),
        *_PART]),
    "fact_alerta": Contrato("fact_alerta", [
        ("id_alerta", "string"), ("senal", "string"), ("tipo", "string"),
        ("fecha", "date"), ("placa_norm", "string"), ("documento", "string"),
        ("kg", "double"), ("valor_soles", "double"), ("puntaje", "double"),
        ("grado_evidencia", "string"), ("estado_revision", "string"), *_PART]),
}


def columnas_destino(fuente: str) -> dict[str, str]:
    """Mapa nombre original → nombre destino para `DataFrame.rename`."""
    return {orig: dest for orig, (dest, _) in FUENTES[fuente].columnas.items()}


def tipos_destino(fuente: str) -> dict[str, str]:
    return {dest: t for dest, t in FUENTES[fuente].columnas.values()}


def validar(df, contrato: str) -> list[str]:
    """Devuelve la lista de violaciones del contrato (vacía si cumple)."""
    c = CONTRATOS[contrato]
    errores = [f"falta columna {n}" for n in c.columnas() if n not in df.columns]
    extra = [n for n in df.columns if n not in c.columnas()]
    errores += [f"columna no declarada {n}" for n in extra]
    return errores
