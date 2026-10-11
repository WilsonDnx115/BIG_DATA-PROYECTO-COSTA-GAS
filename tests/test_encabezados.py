"""Pruebas del inventario de encabezados (`src/ingest/encabezados.py`).

Las dos ultimas son las importantes: verifican que ningun valor de celda de
datos aparece en la salida, que es la regla de `CLAUDE.md` sobre los datos
reales. Los valores de `DATOS_SECRETOS` imitan los casos que rompieron la
primera version del script (razon social, decimal largo, fecha con hora).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from src.ingest import encabezados as enc

DATOS_SECRETOS = [
    "PEREZ QUISPE JUAN",
    "20481234567",
    "T2A-845",
    "plus petrol corporation SA",
    "896902.3618644068",
]


@pytest.fixture()
def entrega(tmp_path):
    """Entrega sintetica: xlsx con titulos y dos hojas, y csv con `;`."""
    from openpyxl import Workbook

    carpeta = tmp_path / "abastecimiento" / "aba_02"
    carpeta.mkdir(parents=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "ORDENES"
    ws.append(["COSTA GAS TRUJILLO"])                       # fila 1: titulo
    ws.append([])                                           # fila 2: vacia
    ws.append(["SCOP", "FECHA", "PLACA CARGADA", "KG", "N DOC", ""])   # fila 3: encabezado
    ws.append(["SC-1", dt.date(2020, 1, 2), DATOS_SECRETOS[2], 120.5, "F001-1", None])
    ws.append(["SC-2", dt.date(2020, 1, 3), DATOS_SECRETOS[2], 98.25, "F001-2", None])

    ws2 = wb.create_sheet("RESUMEN")
    ws2.append(["TOTAL", "TOTAL"])                          # encabezado duplicado
    ws2.append([1, 2])
    wb.save(carpeta / "ABA-02 ordenes scop.xlsx")

    red = tmp_path / "redes" / "red_02"
    red.mkdir(parents=True)
    (red / "RED-02 distribuidores.csv").write_text(
        "Maestro de distribuidores\n"
        "CardCode;RUC/DNI;CANAL\n"
        f"C001;{DATOS_SECRETOS[1]};MAYORISTA\n"
        f"C002;{DATOS_SECRETOS[1]};MINORISTA\n",
        encoding="utf-8",
    )
    return tmp_path


# --- utilidades ---------------------------------------------------------------
def test_tipo_celda_distingue_dato_de_encabezado():
    assert enc.tipo_celda("SCOP") == "texto"
    assert enc.tipo_celda(None) == "vacia"
    assert enc.tipo_celda("   ") == "vacia"
    assert enc.tipo_celda(896902.36) == "numero"
    assert enc.tipo_celda("76,902.97") == "numero"
    assert enc.tipo_celda("S/ 1,200.50") == "numero"
    assert enc.tipo_celda("0.70%") == "numero"
    assert enc.tipo_celda(dt.datetime(2021, 11, 4)) == "fecha"
    assert enc.tipo_celda("2021-11-04") == "fecha"


def test_inferir_codigo_de_ruta_y_de_nombre():
    assert enc.inferir_codigo(Path("abastecimiento/aba_01/x.xlsx")) == "aba_01"
    assert enc.inferir_codigo(Path("ABA-03 despachos.xlsx")) == "aba_03"
    assert enc.inferir_codigo(Path("VENTAS ENERO.xls")) is None


def test_normalizar_nombre_quita_tildes_y_espacios():
    assert enc.normalizar_nombre("  Capacidad  Autorizada ") == "CAPACIDAD AUTORIZADA"
    assert enc.normalizar_nombre("Año") == "ANO"


# --- eleccion de la fila de encabezado ---------------------------------------
def test_elige_la_fila_de_texto_no_la_mas_llena():
    """La fila 2 tiene mas celdas llenas, pero son datos: gana la 1."""
    filas = [
        ["PLACA", "FECHA", "KG", None],
        ["T2A-845", dt.date(2020, 1, 1), 120.5, 9.9],
        ["T2A-846", dt.date(2020, 1, 2), 118.0, 8.1],
    ]
    fila, valores, dudoso = enc.elegir_encabezado(filas)
    assert (fila, dudoso) == (1, False)
    assert valores[0] == "PLACA"


def test_la_ultima_fila_no_gana_por_no_tener_fila_debajo():
    """Cuadro por años: las dos filas son ambiguas, debe quedarse con la primera."""
    filas = [
        ["CONCEPTO", 2019, 2020, 2021],
        ["COMPRAS", 1000, 1100, 1200],
    ]
    fila, _, _ = enc.elegir_encabezado(filas)
    assert fila == 1


def test_hoja_solo_de_datos_se_marca_dudosa_y_no_publica_nombres():
    filas = [
        ["plus petrol corporation SA", 0.022, 0],
        ["plus petrol corporation SA", 0.019, 1],
    ]
    fila, _, dudoso = enc.elegir_encabezado(filas)
    assert dudoso is True

    cols = enc._columnas(filas[fila - 1], dudoso, sin_nombres=False)
    assert all(c["nombre"] == "" for c in cols)
    assert all(c["omitido"] for c in cols)


def test_numero_corto_pasa_y_decimal_largo_se_omite():
    assert enc._valor_encabezado(2020) == ("2020", False)
    assert enc._valor_encabezado("15") == ("15", False)
    assert enc._valor_encabezado(896902.3618644068) == ("", True)
    assert enc._valor_encabezado(dt.datetime(2021, 11, 4)) == ("", True)
    assert enc._valor_encabezado("CardCode") == ("CardCode", False)


# --- inventario ---------------------------------------------------------------
def test_detecta_fila_de_encabezado_bajo_filas_de_titulo(entrega):
    inv = enc.inventariar(entrega)
    xlsx = next(a for a in inv["archivos"] if a["extension"] == ".xlsx")
    ordenes = next(h for h in xlsx["hojas"] if h["hoja"] == "ORDENES")

    assert ordenes["fila_encabezado"] == 3
    assert ordenes["encabezado_dudoso"] is False
    assert [c["nombre"] for c in ordenes["columnas"]] == [
        "SCOP", "FECHA", "PLACA CARGADA", "KG", "N DOC",
    ]
    assert ordenes["filas_datos"] == 2
    assert xlsx["codigo"] == "aba_02"
    assert xlsx["proceso"] == "abastecimiento"


def test_lista_todas_las_hojas_y_avisa_encabezados_duplicados(entrega):
    inv = enc.inventariar(entrega)
    xlsx = next(a for a in inv["archivos"] if a["extension"] == ".xlsx")

    assert [h["hoja"] for h in xlsx["hojas"]] == ["ORDENES", "RESUMEN"]
    resumen = next(h for h in xlsx["hojas"] if h["hoja"] == "RESUMEN")
    assert resumen["duplicadas"] == ["TOTAL"]


def test_csv_detecta_delimitador_codificacion_y_titulo(entrega):
    inv = enc.inventariar(entrega)
    csv_ = next(a for a in inv["archivos"] if a["extension"] == ".csv")
    hoja = csv_["hojas"][0]

    assert hoja["delimitador"] == ";"
    assert hoja["codificacion"].startswith("utf-8")
    assert hoja["fila_encabezado"] == 2
    assert [c["nombre"] for c in hoja["columnas"]] == ["CardCode", "RUC/DNI", "CANAL"]
    assert hoja["filas_datos"] == 2


def test_csv_cp1252_con_tildes(tmp_path):
    (tmp_path / "ventas.csv").write_bytes(
        "AÑO;MES;DESCRIPCIÓN;KG\n".encode("cp1252") + b"2020;1;GLP ENVASADO;100\n"
    )
    inv = enc.inventariar(tmp_path)
    hoja = inv["archivos"][0]["hojas"][0]
    assert hoja["codificacion"] == "cp1252"
    assert [c["nombre"] for c in hoja["columnas"]] == ["AÑO", "MES", "DESCRIPCIÓN", "KG"]


def test_xls_antiguo_se_lee_con_xlrd(tmp_path):
    xlwt = pytest.importorskip("xlwt", reason="xlwt solo se usa para crear el .xls de prueba")
    pytest.importorskip("xlrd")

    libro = xlwt.Workbook()
    hoja = libro.add_sheet("VENTAS")
    for col, nombre in enumerate(["FECHA", "PLACA", "KG"]):
        hoja.write(0, col, nombre)
    hoja.write(1, 0, "2020-01-01")
    hoja.write(1, 1, DATOS_SECRETOS[2])
    hoja.write(1, 2, 120.5)
    libro.save(str(tmp_path / "VENTAS ENERO.xls"))

    inv = enc.inventariar(tmp_path)
    archivo = inv["archivos"][0]
    assert archivo["legible"] is True
    assert [c["nombre"] for c in archivo["hojas"][0]["columnas"]] == ["FECHA", "PLACA", "KG"]


def test_xlsx_con_extension_xls_se_rescata(entrega, tmp_path):
    origen = entrega / "abastecimiento" / "aba_02" / "ABA-02 ordenes scop.xlsx"
    destino = tmp_path / "solo" / "MAL NOMBRADO.xls"
    destino.parent.mkdir()
    destino.write_bytes(origen.read_bytes())

    inv = enc.inventariar(destino.parent)
    assert inv["archivos"][0]["legible"] is True
    assert len(inv["archivos"][0]["hojas"]) == 2


def test_xls_que_es_html_avisa_claro(tmp_path):
    (tmp_path / "REPORTE.xls").write_bytes(b"<html><table><tr><td>1</td></tr></table></html>")
    inv = enc.inventariar(tmp_path)
    assert inv["archivos"][0]["legible"] is False
    assert "HTML" in inv["archivos"][0]["motivo"]


def test_contrasta_contra_los_esquemas_declarados(entrega):
    inv = enc.inventariar(entrega)
    xlsx = next(a for a in inv["archivos"] if a["codigo"] == "aba_02")
    ce = xlsx["contraste_esquema"]

    assert "PRODUCTO" in ce["declaradas_no_encontradas"]
    assert "T.C." in ce["declaradas_no_encontradas"]
    assert "SCOP" not in ce["declaradas_no_encontradas"]
    assert ce["hoja"] == "ORDENES"
    assert ce["coincidencias"] == 5
    assert "TOTAL" not in ce["encontradas_no_declaradas"]


def test_fuente_sin_esquema_declarado_no_contrasta(tmp_path):
    (tmp_path / "VENTAS FLOTA 2020.csv").write_text("PLACA,KG\nT2A-845,120\n", encoding="utf-8")
    inv = enc.inventariar(tmp_path)
    assert inv["archivos"][0]["contraste_esquema"] is None
    assert inv["resumen"]["sin_esquema_declarado"] == 1


def test_archivo_ilegible_no_detiene_el_inventario(entrega):
    (entrega / "abastecimiento" / "aba_02" / "roto.xlsx").write_bytes(b"no es un excel")

    inv = enc.inventariar(entrega)
    malo = next(a for a in inv["archivos"] if a["ruta"].endswith("roto.xlsx"))
    assert malo["legible"] is False
    assert inv["resumen"]["ilegibles"] == 1
    assert inv["resumen"]["archivos"] == 3        # los otros dos se inventariaron igual


def test_origen_inexistente_da_mensaje_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="data/sample/entrega"):
        enc.inventariar(tmp_path / "no_existe")


# --- la salida no filtra datos ------------------------------------------------
def test_la_salida_no_contiene_ningun_dato_de_las_filas(entrega, tmp_path):
    inv = enc.inventariar(entrega)
    pj, pm = enc.guardar(inv, tmp_path / "e.json", tmp_path / "e.md")

    textos = [
        json.dumps(inv, ensure_ascii=False),
        pj.read_text(encoding="utf-8"),
        pm.read_text(encoding="utf-8"),
    ]
    for secreto in DATOS_SECRETOS:
        for texto in textos:
            assert secreto not in texto, f"se filtro un dato de fila: {secreto}"


def test_hoja_sin_encabezado_no_filtra_nada_y_queda_para_revisar(tmp_path):
    """El caso que rompio la primera version: una hoja que empieza en datos."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "CALCULO PLUS PETROL"
    ws.append([DATOS_SECRETOS[3], 0.022, 0, dt.datetime(2021, 11, 4)])
    ws.append([DATOS_SECRETOS[3], 0.019, 1, dt.datetime(2021, 11, 5)])
    ws.append([DATOS_SECRETOS[3], float(DATOS_SECRETOS[4]), 2, dt.datetime(2021, 11, 6)])
    wb.save(tmp_path / "1. PEDIDOS GLP.xlsx")

    inv = enc.inventariar(tmp_path)
    hoja = inv["archivos"][0]["hojas"][0]
    assert hoja["encabezado_dudoso"] is True
    assert hoja["n_columnas"] == 4
    assert all(c["nombre"] == "" for c in hoja["columnas"])
    assert inv["resumen"]["hojas_sin_encabezado_claro"] == 1
    assert inv["hojas_para_revisar"][0]["hoja"] == "CALCULO PLUS PETROL"

    pj, pm = enc.guardar(inv, tmp_path / "e.json", tmp_path / "e.md")
    for texto in (pj.read_text(encoding="utf-8"), pm.read_text(encoding="utf-8")):
        assert DATOS_SECRETOS[3] not in texto
        assert "0.022" not in texto
        assert "2021-11-04" not in texto


def test_sin_nombres_no_publica_ningun_encabezado(entrega, tmp_path):
    inv = enc.inventariar(entrega, sin_nombres=True)
    _, pm = enc.guardar(inv, tmp_path / "e.json", tmp_path / "e.md")
    texto = pm.read_text(encoding="utf-8")

    assert "SCOP" not in texto
    assert "CardCode" not in texto
    xlsx = next(a for a in inv["archivos"] if a["extension"] == ".xlsx")
    ordenes = next(h for h in xlsx["hojas"] if h["hoja"] == "ORDENES")
    assert ordenes["n_columnas"] == 5          # el recuento si se conserva


# --- tercera barrera: identificadores -----------------------------------------
def test_parece_identificador_detecta_ruc_razon_social_y_placa():
    assert enc.parece_identificador("P20127765279 - COESTI S.A.") is True
    assert enc.parece_identificador("20481234567") is True
    assert enc.parece_identificador("COESTI S.A.") is True
    assert enc.parece_identificador("GAS DEL NORTE E.I.R.L.") is True
    assert enc.parece_identificador("5530-5B") is True
    assert enc.parece_identificador("T2A-845") is True
    # y no se come encabezados legitimos
    assert enc.parece_identificador("GLP-E (KILOGRAMOS)") is False
    assert enc.parece_identificador("GLP-G") is False
    assert enc.parece_identificador("Km-Gl") is False
    assert enc.parece_identificador("RUC/DNI") is False
    assert enc.parece_identificador("NOMBRE/RAZÓN SOCIAL") is False
    assert enc.parece_identificador("NUMERO SCOP") is False
    assert enc.parece_identificador("T.C") is False


def test_fila_con_ruc_invalida_la_hoja_completa(tmp_path):
    """Caso real de GASTOS 2020: la fila 'encabezado' traía placa y RUC."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "GASTOS FLOTA"
    ws.append(["ENERO", "5530-5B", "COMBUSTIBLE", "P20127765279 - COESTI S.A.", "TRUJILLO"])
    ws.append(["FEBRERO", "5530-5B", "COMBUSTIBLE", "P20127765279 - COESTI S.A.", "TRUJILLO"])
    wb.save(tmp_path / "GASTOS 2020.xlsx")

    inv = enc.inventariar(tmp_path)
    hoja = inv["archivos"][0]["hojas"][0]
    assert hoja["encabezado_dudoso"] is True
    assert hoja["motivo_dudoso"] == "identificador_en_la_fila"
    assert all(c["nombre"] == "" for c in hoja["columnas"])

    pj, pm = enc.guardar(inv, tmp_path / "e.json", tmp_path / "e.md")
    for texto in (pj.read_text(encoding="utf-8"), pm.read_text(encoding="utf-8")):
        assert "20127765279" not in texto
        assert "COESTI" not in texto
        assert "5530-5B" not in texto
        assert "ENERO" not in texto


def test_encabezado_legitimo_de_compras_no_se_invalida(tmp_path):
    """El encabezado real de COMPRAS MENSUALES debe pasar entero."""
    from openpyxl import Workbook

    reales = ["PROVEEDOR", "CODIGO OSINER", "TIPO DE AGENTE", "NUMERO SCOP",
              "FECHA FACTURA", "SERIE", "NUMERO", "GLP-E (KILOGRAMOS)",
              "GLP-G (KILOGRAMOS)", "PLACA", "GUIA", "REGISTRADO",
              "MONTO DOLARES (INC IMPUESTOS)", "T.C", "MONTO PAGADO"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Febrero 2022"
    ws.append(["COMPRAS DE GLP"])
    ws.append(reales)
    ws.append(["PETROPERU", "1234", "PLANTA", "SC-1", dt.date(2022, 2, 1), "F001", "123",
               7000.0, 0.0, "T2A-845", "G-1", "SI", 20000.5, 3.85, 77000.25])
    wb.save(tmp_path / "COMPRAS MENSUALES.xlsx")

    inv = enc.inventariar(tmp_path)
    hoja = inv["archivos"][0]["hojas"][0]
    assert hoja["encabezado_dudoso"] is False
    assert hoja["fila_encabezado"] == 2
    assert [c["nombre"] for c in hoja["columnas"]] == reales
