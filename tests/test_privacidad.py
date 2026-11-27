"""Ningún dato personal llega a Silver ni a Gold (commit A12).

Tres frentes, de más barato a más caro:

1. Los nombres de columna de todos los contratos y de todos los DDL generados.
2. La salida real del pipeline de contratos sobre hojas de prueba que traen DNI y RUC
   de persona natural a propósito.
3. El lago local, si alguien ya corrió `python -m src.pipeline`, incluidas las tablas
   que todavía usan los contratos de `schemas.py`.

La regla viene de `CLAUDE.md`: no publicar nombres, DNI ni RUC de personas naturales en
Silver, Gold, muestras, tableros, registros ni evidencias.
"""
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from openpyxl import Workbook

from src.common import config
from src.silver import contratos, procesar

# Palabras que nombran a una persona. Si una columna las usa, tiene que estar
# seudonimizada (`_hash`) o ser un identificador opaco (`_id`).
PALABRAS_DE_PERSONA = ("nombre", "dni", "apellido", "conductor", "vendedor")
SUFIJOS_PERMITIDOS = ("_hash", "_id")

# Un DNI son 8 dígitos seguidos; el \b evita confundirlo con un SCOP de 11 ni con
# los dígitos de dentro de un hash.
RE_DNI = re.compile(r"\b\d{8}\b")
# RUC de persona natural: 11 dígitos que empiezan en 10, 15 o 17.
RE_RUC_PERSONA = re.compile(r"\b(?:10|15|17)\d{9}\b")

DIR_DDL = config.RAIZ_REPO / "sql" / "athena" / "ddl"


def _es_segura(columna: str) -> bool:
    if not any(p in columna.lower() for p in PALABRAS_DE_PERSONA):
        return True
    return columna.lower().endswith(SUFIJOS_PERMITIDOS)


# --- 1 · Nombres de columna ----------------------------------------------------
def test_ninguna_columna_de_contrato_nombra_a_una_persona():
    malas = [(t, n) for t, c in contratos.cargar().items() for n in c.nombres() if not _es_segura(n)]
    assert not malas, f"columnas sin seudonimizar: {malas}"


def test_ningun_ddl_generado_nombra_a_una_persona():
    malas = []
    for sql in sorted(DIR_DDL.glob("*.sql")):
        for linea in sql.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s{2}(\w+)\s+\w+", linea)          # «  columna tipo …»
            if m and not _es_segura(m.group(1)):
                malas.append((sql.name, m.group(1)))
    assert not malas, f"columnas sin seudonimizar en los DDL: {malas}"


def test_toda_columna_personal_esta_declarada_y_hasheada():
    for tabla, c in contratos.cargar().items():
        for col in c.columnas:
            if col.personal:
                assert col.nombre.endswith(SUFIJOS_PERMITIDOS), f"{tabla}.{col.nombre}"
            if col.nombre.endswith("_hash"):
                assert col.personal, f"{tabla}.{col.nombre} parece personal pero no está marcada"


# --- 2 · Salida real del pipeline de contratos ---------------------------------
def _libro(ruta, hojas: dict):
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for f in filas:
            ws.append(f)
    wb.save(ruta)
    return str(ruta)


def _celdas_de_texto(df: pd.DataFrame) -> list[str]:
    return [str(v) for col in df.columns if df[col].dtype == object
            for v in df[col].dropna().tolist() if isinstance(v, str)]


def test_un_dni_y_un_ruc_de_persona_no_sobreviven_a_silver(lago, tmp_path):
    """Entran un DNI y un RUC 10…; de Silver no sale ninguno de los dos."""
    dni, ruc_persona, ruc_empresa = "45678912", "10456789019", "20123456786"
    enc = [None, "ITEM", "DPTO.", "PROVINCIA", "DISTRITO", "NOMBRE Y/O RAZON SOCIAL", "RUC/DNI",
           "UBICACIÓN DEL ESTABLECIMIENTO", "CAP. ALMAC, TOTAL (KILOGRAMOS)", "EMPRESA ENVASADORA",
           "TIPO", "UIT"]
    ruta = _libro(tmp_path / "RELACION DE DISTRIBUIDORES 2020-2021 Act 24092020.xlsx",
                  {"DISTRIBUIDORES": [*[[None]] * 6, enc,
                   [None, 1, "LA LIBERTAD", "TRUJILLO", "TRUJILLO", "EMPRESA REAL S.A.C.", ruc_empresa,
                    "AV. A 1", 5000, "COSTA GAS", "DISTRIBUIDOR", 4.3],
                   [None, 2, "LA LIBERTAD", "TRUJILLO", "LAREDO", "PERSONA FICTICIA UNO", ruc_persona,
                    "CALLE B 2", 1500, "COSTA GAS", "DISTRIBUIDOR", 4.3],
                   [None, 3, "LA LIBERTAD", "TRUJILLO", "MOCHE", "PERSONA FICTICIA DOS", dni,
                    "CALLE C 3", 900, "COSTA GAS", "DISTRIBUIDOR", 4.3]]})
    procesar.procesar_archivo(ruta)
    df = procesar.leer_tabla("distribuidores")
    assert len(df) == 3                                        # no se pierde ninguna fila

    texto = " ".join(_celdas_de_texto(df))
    assert dni not in texto and ruc_persona not in texto
    assert not RE_DNI.search(texto) and not RE_RUC_PERSONA.search(texto)
    assert "FICTICIA" not in texto                             # tampoco su nombre
    assert ruc_empresa in texto                                # el de la empresa sí se conserva


# --- 3 · El lago local, si existe ----------------------------------------------
def _parquets_del_lago() -> list[Path]:
    raiz = config.RAIZ_REPO / "data" / "lake" / "silver"
    return sorted(p for p in raiz.rglob("*.parquet")) if raiz.exists() else []


def test_el_lago_local_no_tiene_dni_ni_ruc_de_persona():
    archivos = _parquets_del_lago()
    if not archivos:
        pytest.skip("no hay lago local: correr `python -m src.pipeline --regenerar-muestra`")
    hallazgos = []
    for p in archivos:
        df = pq.read_table(p).to_pandas()
        for valor in _celdas_de_texto(df):
            if RE_DNI.search(valor) or RE_RUC_PERSONA.search(valor):
                hallazgos.append((p.relative_to(config.RAIZ_REPO).as_posix(), valor[:40]))
    assert not hallazgos, f"posible dato personal en Silver: {hallazgos[:5]}"
