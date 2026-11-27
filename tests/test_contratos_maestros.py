"""Contratos de los maestros distribuidores y clientes (commit A08).

Lo que se verifica aquí es la regla de identidad: el RUC de una empresa (prefijo 20)
se conserva para poder cruzarlo con SUNAT, y el DNI o el RUC de una persona natural
sale hasheado, igual que su nombre. Ningún dato de persona natural llega a Silver.
"""
import pytest
from openpyxl import Workbook

from src.common import limpieza as L
from src.silver import contratos, procesar
from src.silver.transformar import _identidad

DISTRIBUIDORES = "RELACION DE DISTRIBUIDORES 2020-2021 Act 24092020.xlsx"
CLIENTES = "CLIENTES TOTAL.xlsx"

ENC_DISTRIBUIDORES = [None, "ITEM", "DPTO.", "PROVINCIA", "DISTRITO", "NOMBRE Y/O RAZON SOCIAL",
                      "RUC/DNI", "UBICACIÓN DEL ESTABLECIMIENTO", "CAP. ALMAC, TOTAL (KILOGRAMOS)",
                      "EMPRESA ENVASADORA", "TIPO", "UIT"]
TITULOS_6 = [["RELACION DE DISTRIBUIDORES"], [None], [None], [None], [None], [None]]


def _ruc(base10: str) -> str:
    """RUC de prueba con su dígito verificador correcto (módulo 11)."""
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    d = 11 - sum(int(a) * b for a, b in zip(base10, pesos)) % 11
    return base10 + str({10: 0, 11: 1}.get(d, d))


RUC_EMPRESA = _ruc("2012345678")      # persona jurídica
RUC_PERSONA = _ruc("1045678901")      # persona natural


def _libro(ruta, hojas: dict):
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for f in filas:
            ws.append(f)
    wb.save(ruta)
    return str(ruta)


def _resultado(resultados, fuente: str) -> dict:
    return next(r for r in resultados if r["fuente"] == fuente)


# --- Contratos ----------------------------------------------------------------
@pytest.mark.parametrize("tabla", ["distribuidores", "clientes"])
def test_los_maestros_van_a_silver_maestros(tabla):
    c = contratos.cargar()[tabla]
    assert c.dominio == "maestros"
    assert f"LOCATION '${{LAKE}}/silver/maestros/{tabla}/'" in c.ddl()


@pytest.mark.parametrize("tabla", ["distribuidores", "clientes"])
def test_ninguna_columna_publica_datos_de_persona(tabla):
    c = contratos.cargar()[tabla]
    nombres = c.nombres()
    assert "dni" not in nombres and "nombre" not in nombres and "razon_social" in nombres
    # todo lo que identifica a una persona está marcado y lleva sufijo _hash
    for col in c.columnas:
        if col.personal:
            assert col.nombre.endswith("_hash"), col.nombre
    assert set(c.personales()) == {"documento_hash", "nombre_hash"}


# --- Regla de identidad --------------------------------------------------------
def test_ruc_de_empresa_se_conserva_y_el_de_persona_se_hashea():
    """La prueba que pide el A08: un RUC 10… queda como hash y un RUC 20… queda tal cual."""
    empresa = _identidad(RUC_EMPRESA, "DISTRIBUIDORA X S.A.C.")
    assert empresa["tipo_persona"] == "JURIDICA"
    assert empresa["ruc"] == RUC_EMPRESA and empresa["entidad_id"] == RUC_EMPRESA
    assert empresa["razon_social"] == "DISTRIBUIDORA X S.A.C." and empresa["nombre_hash"] is None

    persona = _identidad(RUC_PERSONA, "JUAN PEREZ FICTICIO")
    assert persona["tipo_persona"] == "NATURAL"
    assert persona["ruc"] is None and persona["razon_social"] is None
    assert persona["documento_hash"] == L.seudonimizar(RUC_PERSONA)
    assert persona["nombre_hash"] and RUC_PERSONA not in str(persona)


def test_el_dni_tambien_se_hashea():
    r = _identidad("45678912", "MARIA LOPEZ FICTICIA")
    assert r["tipo_persona"] == "NATURAL" and r["documento_hash"] == L.seudonimizar("45678912")
    assert r["razon_social"] is None


@pytest.mark.parametrize("nombre,juridica", [
    ("GAS DEL NORTE S.A.", True), ("INVERSIONES EIRL", True), ("COMERCIAL S.R.L.", True),
    ("PEDRO QUISPE FICTICIO", False), ("SARA MENDOZA", False), ("ROSA SAAVEDRA", False)])
def test_sin_documento_solo_se_conserva_el_nombre_con_forma_societaria(nombre, juridica):
    r = _identidad(None, nombre)
    assert (r["razon_social"] == nombre) is juridica
    assert (r["nombre_hash"] is None) is juridica


def test_ruc_20_con_digito_verificador_malo_no_se_publica():
    r = _identidad("20123456780", "DV MALO S.A.C.")
    assert r["tipo_persona"] == "INVALIDO" and r["ruc"] is None     # no se publica un RUC que no valida
    assert r["razon_social"] == "DV MALO S.A.C."                    # pero por prefijo 20 no es una persona


# --- Lectura de las hojas ------------------------------------------------------
def test_distribuidores_conserva_la_capacidad_y_oculta_el_domicilio(lago, tmp_path):
    ruta = _libro(tmp_path / DISTRIBUIDORES, {"DISTRIBUIDORES": [
        *TITULOS_6, ENC_DISTRIBUIDORES,
        [None, 1, "LA LIBERTAD", "TRUJILLO", "TRUJILLO", "DISTRIBUIDORA X S.A.C.", RUC_EMPRESA,
         "AV. SIEMPRE VIVA 123", 5000, "COSTA GAS", "DISTRIBUIDOR", 4.3],
        [None, 2, "LA LIBERTAD", "TRUJILLO", "LAREDO", "JUAN PEREZ FICTICIO", RUC_PERSONA,
         "CALLE FALSA 456", 1500, "COSTA GAS", "DISTRIBUIDOR", 4.3]]})
    r = _resultado(procesar.procesar_archivo(ruta), "distribuidores_hoja_maestra")
    assert r["filas_salida"] == 2
    assert r["calidad"]["juridicas"] == 1 and r["calidad"]["naturales"] == 1
    assert r["calidad"]["direccion_omitida_por_privacidad"] == 1

    df = procesar.leer_tabla("distribuidores").sort_values("item").reset_index(drop=True)
    empresa, persona = df.iloc[0], df.iloc[1]
    assert empresa["ruc"] == RUC_EMPRESA and empresa["direccion"] == "AV. SIEMPRE VIVA 123"
    assert empresa["capacidad_kg"] == 5000 and empresa["distrito"] == "TRUJILLO"
    assert persona["ruc"] is None and persona["direccion"] is None
    assert persona["capacidad_kg"] == 1500          # la capacidad sí se conserva
    assert persona["distrito"] == "LAREDO"          # la geografía gruesa también

    plano = df.astype(str)
    assert not plano.apply(lambda s: s.str.contains("FICTICIO|CALLE FALSA")).any().any()
    assert not plano.apply(lambda s: s.str.contains(RUC_PERSONA)).any().any()


def test_clientes_desde_las_tres_hojas(lago, tmp_path):
    ruta = _libro(tmp_path / CLIENTES, {
        "Hoja3": [["RUC", "CLIENTE"], [RUC_EMPRESA, "DISTRIBUIDORA X S.A.C."]],
        "Hoja1": [["Name", "RUC", "Nombre/Razón Social"], ["X", RUC_PERSONA, "JUAN PEREZ FICTICIO"]],
        "Hoja2": [["Código SN", "Nombre SN"], ["C001", "GAS DEL NORTE S.A."]]})
    resultados = procesar.procesar_archivo(ruta)
    assert {r["fuente"] for r in resultados} == {"clientes_ruc_cliente", "clientes_razon_social", "clientes_codigo_sn"}
    assert all(r["filas_salida"] == 1 for r in resultados)

    df = procesar.leer_tabla("clientes")
    assert set(df["tipo_persona"]) == {"JURIDICA", "NATURAL"}
    assert df.loc[df["tipo_persona"] == "NATURAL", "ruc"].isna().all()
    assert (df["entidad_id"] == "C001").any()                      # la hoja sin documento usa el Código SN
    assert not df.astype(str).apply(lambda s: s.str.contains("FICTICIO")).any().any()
