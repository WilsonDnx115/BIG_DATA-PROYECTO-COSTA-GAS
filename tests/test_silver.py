"""Contratos, lector y limpieza de las tablas Silver (WP 0.2 y 1.1).

Los Excel de prueba se construyen aquí con la misma forma que los reales (filas de
título, encabezado, totales, filas vacías), con valores inventados.
"""
import datetime as dt

import pytest
from openpyxl import Workbook

from src.common import limpieza as L
from src.silver import contratos, lector, procesar


def _libro(ruta, hojas: dict):
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for f in filas:
            ws.append(f)
    wb.save(ruta)
    return str(ruta)


ENC_2022 = ["PROVEEDOR", "CODIGO OSINER", "TIPO DE AGENTE", "NUMERO SCOP", "FECHA FACTURA", "SERIE", "NUMERO",
            "GLP-E (Kilogramos)", "GLP-G (Kilogramos)", "PLACA", "GUIA", "REGISTRADO",
            "monto DOLARES (inc impuestos)", "T.C", "MONTO PAGADO"]


def _fila(numero, fecha, placa="T2N - 841 CAMION", tc=3.85, scop="12345678901", kg_e=24070.0):
    return ["proveedor uno", "999", "PLANTA", scop, fecha, "F001", numero, kg_e, None, placa, "G-1", "SI", 15000.0, tc, 57750.0]


@pytest.fixture()
def compras(lago, tmp_path):
    filas = [["COMPRAS FEBRERO 2022"], ENC_2022,
             _fila("100", dt.datetime(2022, 2, 5)),
             _fila("101", dt.datetime(2022, 5, 2)),                       # día y mes invertidos
             _fila("102", "15/02/2022", placa="PLANTA", tc=1),            # no es placa; T.C. de relleno
             _fila("100", dt.datetime(2022, 2, 5)),                       # factura repetida
             ["TOTAL GENERAL", None, None, None, None, None, None, 72210.0],
             [None, None, None, None, None, None, None, None]]
    filas += [[None] * 15] * 40 + [_fila("999", dt.datetime(2022, 2, 9))]  # dato tras muchas filas vacías
    return _libro(tmp_path / "COMPRAS MENSUALES.xlsx", {"Febrero 2022": filas, "RESUMEN": [["x"]]})


# --- Utilidades de limpieza ---------------------------------------------------
@pytest.mark.parametrize("valor,esperado", [
    ("T2N - 841 CAMION", ("T2N841", None, None)), ("B2E-983 (24/7/23)", ("B2E983", "24/7/23", None)),
    ("aox941", ("AOX941", None, None)), ("PLANTA", (None, None, "PLANTA")), (None, (None, None, None)),
    ("T5M - 908 LABO", ("T5M908", None, None))])
def test_parsear_placa(valor, esperado):
    assert L.parsear_placa(valor) == esperado


def test_fecha_invertida_y_tc():
    assert L.corregir_fecha_por_mes(dt.date(2022, 5, 2), 2022, 2) == (dt.date(2022, 2, 5), "invertida")
    assert L.corregir_fecha_por_mes(dt.date(2022, 2, 5), 2022, 2)[1] == "ok"
    assert L.corregir_fecha_por_mes(dt.date(2022, 7, 20), 2022, 2)[1] == "discrepa"
    assert L.a_fecha("15/02/2022") == dt.date(2022, 2, 15) and L.a_fecha(44607) == dt.date(2022, 2, 15)
    assert not L.tc_valido(1) and not L.tc_valido(2_000_000) and L.tc_valido(3.85)


@pytest.mark.parametrize("unidad,cantidad,articulo,kg", [
    ("UNIDADES", 3, "BALON 10 KG", 30.0), ("UNIDADES", 2, "GLP ENVASE DE 45 KLG COSTAGAS TRUJILLO", 90.0),
    ("UNIDADES", 4, "BL10", 40.0), ("GALONES", 100, "GLP GRANEL", 204.0), ("LITROS", 100, None, 54.0),
    ("KILOS", 45, None, 45.0), ("UNIDADES", 2, "VALVULA", None)])
def test_a_kilos(unidad, cantidad, articulo, kg):
    assert L.a_kilos(unidad, cantidad, articulo) == pytest.approx(kg) if kg is not None else L.a_kilos(unidad, cantidad, articulo) is None


# --- Contratos ---------------------------------------------------------------
def test_contratos_cargan_y_son_coherentes():
    cs = contratos.cargar()
    assert {"compras_glp", "scop", "unidades", "ventas_unidad_mes", "ventas_detalle"} <= set(cs)
    for c in cs.values():
        assert set(c.llave) <= set(c.nombres())
        assert c.nombres()[:3] == ["origen", "hoja", "fila"]             # linaje hasta la celda de Excel
        assert not {"conductor", "vendedor", "cliente_nombre"} & set(c.nombres())   # ningún nombre de persona


def test_encabezados_se_emparejan_sin_tildes_ni_signos():
    assert contratos.normalizar_encabezado("GLP-E (Kilogramos)") == "GLP E KILOGRAMOS"
    assert contratos.normalizar_encabezado(" N° FACT ") == "N FACT"
    assert contratos.normalizar_encabezado("AÑO") == "ANO"


def test_archivo_duplicado_no_tiene_contrato():
    assert contratos.fuentes_para("COMPRAS MENSUALES.xlsx")
    assert not contratos.fuentes_para("COMPRAS MENSUALES (1).xlsx")


def test_ddl_generado_desde_el_contrato():
    ddl = contratos.cargar()["scop"].ddl("s3://b")
    assert "costagas_silver.scop" in ddl and "flag_placa_divergente boolean" in ddl
    assert "LOCATION 's3://b/silver/compras/scop/'" in ddl


def test_ddl_versionado_coincide_con_los_contratos():
    for c in contratos.cargar().values():
        versionado = (contratos.config.RAIZ_REPO / "sql" / "athena" / "ddl" / f"silver_{c.tabla}.sql")
        assert versionado.read_text(encoding="utf-8") == c.ddl(), f"regenerar con: python -m src.silver.contratos --ddl"


# --- Lector ------------------------------------------------------------------
def test_corte_de_filas_vacias(compras):
    f = contratos.cargar()["compras_glp"].fuentes[0]
    completa = lector.leer_hoja(compras, "Febrero 2022", f)
    assert not completa.cortada and completa.efectivas == 6               # 4 facturas + total + la del final
    cortada = lector.leer_hoja(compras, "Febrero 2022", f, max_vacias=10)
    assert cortada.cortada and cortada.efectivas == 5 and cortada.leidas < completa.leidas


def test_hoja_sin_las_columnas_del_contrato_se_rechaza(lago, tmp_path):
    ruta = _libro(tmp_path / "COMPRAS MENSUALES.xlsx", {"Marzo 2022": [["t"], ["PROVEEDOR", "NUMERO"], ["a", "1"]]})
    r = procesar.procesar_archivo(ruta)[0]
    assert r["estado"] == "sin_filas" and "faltan las columnas" in r["hojas"][0]["motivo"]


# --- Bronze → Silver ----------------------------------------------------------
def test_compras_glp(compras):
    r = procesar.procesar_archivo(compras)[0]
    assert r["estado"] == "ok" and r["filas_salida"] == 5
    assert r["descartes"]["filas_de_total"] == 1 and r["filas_con_llave_repetida"] == 2      # se marcan, no se borran
    assert r["celdas_con_dato"]["numero"] == 5 and r["celdas_con_dato"]["kg_glp_g"] == 0
    assert r["calidad"]["fechas_invertidas"] == 1 and r["calidad"]["tc_fuera_de_rango"] == 1
    todo = procesar.leer_tabla("compras_glp")
    assert todo.loc[todo["numero"] == "100", "llave_repetida"].all() and todo["llave_repetida"].sum() == 2
    df = todo.drop_duplicates("numero").set_index("numero")
    assert df.loc["101", "fecha_factura"] == dt.date(2022, 2, 5) and df.loc["101", "estado_fecha"] == "invertida"
    assert df.loc["100", "placa_norm"] == "T2N841" and df.loc["102", "centro_costo"] == "PLANTA"
    assert df.loc["102", "tc_valido"] == False and df.loc["100", "kg"] == 24070.0   # noqa: E712
    assert df.loc["100", "proveedor"] == "PROVEEDOR UNO" and (df["anio"] == 2022).all() and (df["mes"] == 2).all()


def test_fechas_vacias_en_varias_hojas(lago, tmp_path):
    ruta = _libro(tmp_path / "COMPRAS MENSUALES.xlsx", {
        "Febrero 2022": [["t"], ENC_2022, _fila("200", dt.datetime(2022, 2, 5)), _fila("201", None)],
        "Marzo 2022": [["t"], ENC_2022, _fila("300", None), _fila("301", None)]})
    r = procesar.procesar_archivo(ruta)[0]
    assert r["filas_salida"] == 4 and r["celdas_con_dato"]["fecha_factura"] == 1
    df = procesar.leer_tabla("compras_glp").set_index("numero")
    assert df["estado_fecha"].to_dict() == {"200": "ok", "201": "sin_fecha", "300": "sin_fecha", "301": "sin_fecha"}
    assert df.loc["300", "mes"] == 3 and df["fecha_factura"].notna().sum() == 1


def test_celdas_vacias_de_cualquier_tipo():
    import pandas as pd

    for v in (None, float("nan"), pd.NaT, "  ", "#VALUE!", "#N/A"):
        assert lector.a_texto(v) is None and L.a_fecha(v) is None and L.parsear_placa(v) == (None, None, None)


def test_reproceso_es_idempotente(compras):
    procesar.procesar_archivo(compras)
    antes = procesar.leer_tabla("compras_glp")
    procesar.procesar_archivo(compras)
    despues = procesar.leer_tabla("compras_glp")
    assert len(antes) == len(despues) == 5 and antes.equals(despues)


def test_scop_y_placa_divergente(lago, tmp_path):
    enc = ["FECHA", "SCOP CARGADO", "PRODUCTO", "PROVEEDOR", "ORIGEN", "PLACA CARGADA", "PLACA FACTURADA", "FACTURA", "ESTADO"]
    ruta = _libro(tmp_path / "1. PEDIDOS GLP.xlsx", {"SCOPS GENERADOS": [
        ["titulo"], enc,
        ["15/07/2023", 12345678901, "GLP-G", "prov", "callao", "T1A-123", "T1A123 (15/7/23)", "F1-1", "Atendido"],
        ["16/07/2023", 12345678902, "GLP-G", "prov", "callao", "T1A-123", "B2E-983", "F1-2", "ATENDIDO"],
        ["17/07/2023", None, "GLP-G", "prov", "callao", "T1A-123", "B2E-983", "F1-3", "ATENDIDO"]]})
    r = procesar.procesar_archivo(ruta)[0]
    assert r["filas_salida"] == 3 and r["calidad"]["ordenes_con_placa_divergente"] == 2      # la orden sin número se conserva
    df = procesar.leer_tabla("scop")
    assert df["nro_scop"].tolist() == ["12345678901", "12345678902", None]
    assert df["fecha_en_placa"].iloc[0] == "15/7/23" and df["estado"].nunique() == 1 and df["estado"].iloc[0] == "ATENDIDO"


def test_ventas_sin_nombres_de_persona(lago, tmp_path):
    enc = ["MES", "Proyecto", "Descripcion", "TIPO", "Unidad de negocio", "Unidad", "Cantidad", "Promedio",
           "Vendedor", "Cant Klg", "Cant balones/galones"]
    ruta = _libro(tmp_path / "VENTAS FLOTA 2020.xlsx", {"VENTAS": [
        enc,
        ["ENERO", "T2N - 841 CAMION", "BALON 10 KG", "ENVASADO", "INDIRECTA", "UNIDADES", 100, 20.5, "VENDEDOR FICTICIO", 1000, 100],
        ["SETIEMBRE", "PLANTA", "GLP GRANEL", "GRANEL", "DIRECTA", "GALONES", 50, 5.1, "VENDEDOR FICTICIO", 102, 50]]})
    r = procesar.procesar_archivo(ruta)[0]
    assert r["filas_salida"] == 2 and r["calidad"]["kg_con_placa_valida"] == pytest.approx(1000 / 1102, abs=1e-3)
    df = procesar.leer_tabla("ventas_unidad_mes")
    assert df["mes"].tolist() == [1, 9] and (df["anio"] == 2020).all()
    assert "vendedor" not in df.columns and not df.astype(str).apply(lambda s: s.str.contains("FICTICIO")).any().any()
    assert df["vendedor_hash"].nunique() == 1 and df["vendedor_hash"].str.len().eq(16).all()


def test_ventas_detalle_deriva_kg(lago, tmp_path):
    enc = ["#", "Proyecto", "Codigo Articulo", "Descripcion", "Unidad", "Cantidad", "Precio", "Importe", "DocDate",
           "CardCode", "CardName", "Indicator", "Documento", "Vendedor"]
    ruta = _libro(tmp_path / "Ventas Por Proyecto.xlsx", {"Hoja1": [
        enc,
        [1, "T2N - 841 CAMION", "A10", "GLP ENVASE DE 10 KLG COSTAGAS", "UNIDADES", 3, 20.0, 60.0, dt.datetime(2024, 4, 2), "C001", "CLIENTE FICTICIO", "01", "B001-1", "VEND"],
        [2, "PLANTA", "A99", "FILETE DE ATUN 1 KG", "KILOS", 1, 5.0, 5.0, dt.datetime(2024, 4, 3), "C002", "OTRO FICTICIO", "01", "B001-2", "VEND"]]})
    r = procesar.procesar_archivo(ruta)[0]
    assert r["filas_salida"] == 2 and r["calidad"]["kg_derivado"] == 1
    df = procesar.leer_tabla("ventas_detalle")
    assert df["kg"].iloc[0] == 30.0 and df["kg_origen"].tolist() == ["derivado", "no_glp"]
    assert df["es_glp"].tolist() == [True, False] and df["kg"].isna().iloc[1]          # los abarrotes no suman kg
    assert r["calidad"]["lineas_glp_convertibles_a_kg"] == 1.0 and r["calidad"]["lineas_no_glp"] == 1
    assert not {"cliente_nombre", "cliente_codigo"} & set(df.columns) and df["cliente_id"].nunique() == 2
    assert (df["anio"] == 2024).all() and (df["mes"] == 4).all()


def test_unidades_conserva_filas_sin_placa_valida(lago, tmp_path):
    enc = ["EMPRESA", "PLACA", "CLASE", "MARCA", "MODELO", "NRO. MOTOR", "NRO. SERIE", "AÑO", "ASIENTOS", "USO",
           "FECHA", "ESTADO", "TRASLADO DE GAS (SI/NO)"]
    ruta = _libro(tmp_path / "Grupo Costa Gas Soat 2020(1).xlsx", {"Hoja1": [
        ["t"], ["t"], ["t"], enc,
        ["Costa Gas", "T2N-841", "CAMION", "JMC", "NKR", "m", "s", 2015, 3, "CARGA", "01/01/2020", "VIGENTE", "SI"],
        ["Costa Gas", "AOX 941", "CAMION", "JMC", "NKR", "m", "s", 2016, 3, "CARGA", "01/01/2020", "VIGENTE", "NO"],
        ["Costa Gas", "sin placa", "CAMION", "JMC", "NKR", "m", "s", 2016, 3, "CARGA", "01/01/2020", "VIGENTE", "NO"],
        enc]})                                                              # encabezado repetido dentro del detalle
    r = procesar.procesar_archivo(ruta)[0]
    df = procesar.leer_tabla("unidades")
    assert r["descartes"]["encabezados_repetidos"] == 1
    assert r["filas_salida"] == 3 and df["placa_norm"].tolist() == ["T2N841", "AOX941", None]
    assert df["placa_texto"].tolist() == ["T2N-841", "AOX 941", "SIN PLACA"] and r["calidad"]["placas_distintas"] == 2
    assert df["traslada_gas"].tolist() == [True, False, False] and df["anio_fabricacion"].tolist() == [2015, 2016, 2016]


# --- Ingesta de la entrega a Bronze -------------------------------------------
def test_ingesta_por_dominio_y_rechazo_de_duplicados(lago, tmp_path):
    from src.common import rutas
    from src.ingest import entrega

    origen = tmp_path / "entrega"
    origen.mkdir()
    _libro(origen / "COMPRAS MENSUALES.xlsx", {"Febrero 2022": [["t"], ENC_2022]})
    (origen / "COMPRAS MENSUALES (1).xlsx").write_bytes((origen / "COMPRAS MENSUALES.xlsx").read_bytes())
    _libro(origen / "VENTAS FLOTA 2020.xlsx", {"VENTAS": [["MES"]]})
    (origen / "DATASETS.rar").write_bytes(b"x")

    assert entrega.dominio("Grupo Costa Gas Soat 2020(1).xlsx") == "flota"
    assert entrega.dominio("GASTOS 2020.xls") == "gastos" and entrega.dominio("otro.xlsx") == "referencia"
    assert entrega.codigo("COMPRAS MENSUALES (1).xlsx") == "compras_mensuales_1"

    simulado = entrega.ingerir(origen, "2026-10-10", simular=True)
    assert not list((lago / "lake").rglob("*.xlsx"))                      # simular no copia nada

    r = {x["archivo"]: x for x in entrega.ingerir(origen, "2026-10-10")}
    assert len(simulado) == len(r) == 3 and "DATASETS.rar" not in r
    assert r["COMPRAS MENSUALES (1).xlsx"]["estado"] == "duplicado_rechazado"
    assert r["COMPRAS MENSUALES.xlsx"]["destino"] == rutas.ruta(
        "bronze", "interno", "estructurado", "compras", "compras_mensuales", "fecha_carga=2026-10-10", "COMPRAS MENSUALES.xlsx")
    assert "/ventas_unidad/ventas_flota_2020/" in r["VENTAS FLOTA 2020.xlsx"]["destino"]
    assert len(list((lago / "lake" / "bronze").rglob("*.xlsx"))) == 2
