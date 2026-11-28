"""Contrato de la tabla Silver pedidos_proveedor (commit A07).

Es el lado de tesorería del cruce S12. Lo que más importa aquí es que exponga las
columnas que `cruce_s12` declara (proveedor, documento «SERIE-NUMERO», kg, fecha_pago
y fecha_vence) y que una fecha que no se puede convertir quede nula y se cuente, en
vez de inventarse.
"""
import pandas as pd
from openpyxl import Workbook

from src.silver import contratos, procesar
from src.silver.transformar import _documento

ARCHIVO = "1. PEDIDOS GLP.xlsx"

#                 A      B         C           D           E         F        G          H          I        J       K        L       M        N                O        P
ENC_PETROPERU = [None, "FECHA", "CANTIDAD", "PRODUCTO", "TOTAL", "FACTURA", "VENCIMIENTO", None, "DEUDA", None, "PAGOS"]
ENC_SOLGAS = [None, "FECHA", "CANTIDAD", "PRODUCTO", "MONEDA", "TOTAL", "MAS PECERPCION", "FACTURA", "VENCE",
              None, "DEUDA DOLARES", None, "PAGOS", "fecha de pago", "banco", "modalidad"]
ENC_PLUSPETROL = [None, "GRUPO", "SEDE", "FECHA FACT", "SCOP", None, "CANTIDAD CARGADA", "S/", "PRODUCTO",
                  "FACTURA", None, "CANTIDAD ORDEN", "SALDO", "PAGOS", "fecha de pago", "CAMBISTA", "BANCO",
                  "T.C.", "SOLES", "CON IMPUESTOS", "SIN IGV SIN FISE", "CON FISE"]


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


# --- Contrato ----------------------------------------------------------------
def test_contrato_declara_lo_que_espera_el_cruce_s12():
    c = contratos.cargar()["pedidos_proveedor"]
    assert c.dominio == "compras" and c.llave == ("proveedor", "documento")
    # cruce_s12() de src/glue/senales_spark.py lee exactamente estas columnas
    for columna in ("proveedor", "documento", "kg", "fecha_pago", "fecha_vence"):
        assert columna in c.nombres(), columna
    assert "LOCATION '${LAKE}/silver/compras/pedidos_proveedor/'" in c.ddl()


def test_ninguna_columna_nombra_a_una_persona():
    c = contratos.cargar()["pedidos_proveedor"]
    assert "cambista" not in c.nombres()          # la columna CAMBISTA no pasa a Silver
    for col in c.columnas:
        assert col.personal is False, f"{col.nombre} quedaría como dato personal sin seudonimizar"


# --- Documento ---------------------------------------------------------------
def test_documento_queda_como_serie_numero():
    assert _documento("F001-00012345")[:3] == ("F001-12345", "F001", "12345")
    assert _documento("  f001 - 12345 ")[0] == "F001-12345"


def test_factura_sin_serie_se_conserva_y_se_marca():
    documento, serie, numero, crudo = _documento("12345")
    assert documento == "12345" and serie is None and numero is None and crudo == "12345"


# --- Lectura de las hojas -----------------------------------------------------
def test_solgas_trae_fecha_de_pago_y_precio_en_dolares(lago, tmp_path):
    ruta = _libro(tmp_path / ARCHIVO, {"SOLGAS": [
        ["PEDIDOS"], ["SOLGAS"], [None], ENC_SOLGAS,
        [None, "05/03/2022", 10000, "GLP-G", "USD", 6000.0, 300.0, "F001-00000123", "20/03/2022",
         None, 0.0, None, 6000.0, "18/03/2022", "BCP", "TRANSFERENCIA"]]})
    r = _resultado(procesar.procesar_archivo(ruta), "pedidos_solgas")
    assert r["filas_salida"] == 1
    df = procesar.leer_tabla("pedidos_proveedor")
    fila = df.iloc[0]
    assert fila["proveedor"] == "SOLGAS" and fila["documento"] == "F001-123"
    assert fila["kg"] == 10000 and fila["usd_por_kg"] == 0.6
    assert str(fila["fecha_pago"]) == "2022-03-18" and str(fila["fecha_vence"]) == "2022-03-20"
    assert fila["anio"] == 2022 and fila["mes"] == 3
    assert r["calidad"]["fecha_pago_registrada"] == 1


def test_vence_invalida_queda_nula_y_se_cuenta(lago, tmp_path):
    """La prueba que pide el A07: lo no convertible pasa a nulo y se cuenta."""
    ruta = _libro(tmp_path / ARCHIVO, {"SOLGAS": [
        ["PEDIDOS"], ["SOLGAS"], [None], ENC_SOLGAS,
        [None, "05/03/2022", 10000, "GLP-G", "USD", 6000.0, 0.0, "F001-1", "20/03/2022",
         None, 0.0, None, 0.0, None, "BCP", "CONTADO"],
        [None, "06/03/2022", 8000, "GLP-G", "USD", 4800.0, 0.0, "F001-2", "POR DEFINIR",
         None, 0.0, None, 0.0, None, "BCP", "CONTADO"],
        [None, "07/03/2022", 9000, "GLP-G", "USD", 5400.0, 0.0, "F001-3", None,
         None, 0.0, None, 0.0, None, "BCP", "CONTADO"]]})
    r = _resultado(procesar.procesar_archivo(ruta), "pedidos_solgas")
    assert r["filas_salida"] == 3                       # ninguna fila se pierde
    assert r["calidad"]["vence_no_convertible"] == 1    # «POR DEFINIR» se cuenta
    assert r["calidad"]["vence_sin_fecha"] == 1         # la celda vacía se cuenta aparte

    df = procesar.leer_tabla("pedidos_proveedor").sort_values("documento").reset_index(drop=True)
    assert df["fecha_vence"].isna().tolist() == [False, True, True]
    assert df["estado_fecha_vence"].tolist() == ["ok", "no_convertible", "sin_fecha"]


def test_petroperu_sin_fecha_de_pago_ni_moneda(lago, tmp_path):
    ruta = _libro(tmp_path / ARCHIVO, {"PETROPERU": [
        ["PEDIDOS"], [None], ENC_PETROPERU,
        [None, "10/04/2022", 12000, "GLP-G", 40000.0, "E001-00000045", "25/04/2022", None, 0.0, None, 40000.0]]})
    r = _resultado(procesar.procesar_archivo(ruta), "pedidos_petroperu")
    assert r["filas_salida"] == 1 and r["calidad"]["fecha_pago_registrada"] == 0
    fila = procesar.leer_tabla("pedidos_proveedor").iloc[0]
    assert fila["proveedor"] == "PETROPERU" and fila["documento"] == "E001-45"
    assert fila["fecha_pago"] is None and fila["moneda"] is None
    assert pd.isna(fila["usd_por_kg"])                  # sin moneda declarada no se calcula
    assert str(fila["fecha_vence"]) == "2022-04-25"


def test_pluspetrol_es_la_unica_con_tipo_de_cambio(lago, tmp_path):
    ruta = _libro(tmp_path / ARCHIVO, {"PLUSPETROL": [
        ["PEDIDOS"], ["PLUSPETROL"], [None], ENC_PLUSPETROL,
        [None, "GRUPO 1", "TRUJILLO", "12/05/2022", 12345678901, None, 11000, 38000.0, "GLP-G",
         "F002-00000077", None, 11000, 0.0, 38000.0, "20/05/2022", "UN CAMBISTA", "BBVA",
         3.75, 38000.0, 44840.0, 32203.0, 33000.0]]})
    r = _resultado(procesar.procesar_archivo(ruta), "pedidos_pluspetrol")
    assert r["filas_salida"] == 1 and r["calidad"]["tc_registrados"] == 1
    df = procesar.leer_tabla("pedidos_proveedor")
    fila = df.iloc[0]
    assert fila["proveedor"] == "PLUSPETROL" and fila["documento"] == "F002-77"
    assert fila["tipo_cambio"] == 3.75 and bool(fila["tc_valido"]) is True
    assert fila["nro_scop"] == "12345678901" and fila["total"] == 44840.0
    assert str(fila["fecha_pago"]) == "2022-05-20"
    # el nombre del cambista no llega a Silver
    assert not df.astype(str).apply(lambda s: s.str.contains("CAMBISTA", case=False)).any().any()


# --- PRIMAX, el cuarto proveedor (commit AR26) ---------------------------------
# La hoja empieza en datos, asi que se declara por posicion. Que mide cada una esta
# medido sobre la entrega en docs/evidencias/primax_posiciones.md, sin copiar valores.
def test_primax_esta_declarada_como_cuarta_fuente():
    fuentes = {f.id: f for f in contratos.cargar()["pedidos_proveedor"].fuentes}
    assert "pedidos_primax" in fuentes
    assert len(fuentes) == 4


def test_primax_se_lee_por_posicion_desde_la_fila_3():
    f = next(f for f in contratos.cargar()["pedidos_proveedor"].fuentes if f.id == "pedidos_primax")
    assert f.por_posicion and f.primera_fila == 3
    assert f.columnas == {}


def test_primax_mapea_lo_que_el_cruce_s12_necesita():
    """`cruce_s12` lee proveedor, documento, kg, fecha_pago y fecha_vence."""
    f = next(f for f in contratos.cargar()["pedidos_proveedor"].fuentes if f.id == "pedidos_primax")
    # B fecha · D cantidad (kg) · E producto · G total · H factura · Q fecha de pago · R banco
    assert f.posiciones == {"fecha": 1, "cantidad": 3, "producto": 4, "total": 6,
                            "factura": 7, "fecha_pago": 16, "banco": 17}


def test_el_proveedor_de_primax_sale_del_nombre_de_la_hoja():
    """Como en las otras tres: el grupo «empresa» del patron de hojas."""
    f = next(f for f in contratos.cargar()["pedidos_proveedor"].fuentes if f.id == "pedidos_primax")
    assert f.hojas.search("PRIMAX").groupdict()["empresa"] == "PRIMAX"


def test_la_cantidad_de_primax_tiene_su_evidencia():
    """La posicion D es la unica con la firma de CANTIDAD de las hojas con encabezado."""
    evidencia = (contratos.config.RAIZ_REPO / "docs" / "evidencias"
                 / "primax_posiciones.md").read_text(encoding="utf-8")
    assert "100 % enteros" in evidencia
    crudo = (contratos.DIR_CONTRATOS / "pedidos_proveedor.yaml").read_text(encoding="utf-8")
    assert "primax_posiciones.md" in crudo
