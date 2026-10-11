"""Línea base calculada en Bronze; fixtures exclusivamente sintéticas."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.common import config, muestra, rutas, schemas
from src.ingest import internos
from src.quality import linea_base


def escribir_bronze(codigo, filas, nombre="datos.csv", fecha="2026-10-10"):
    fuente = schemas.FUENTES_LINEA_BASE[codigo]
    p = Path(rutas.ruta("bronze", "interno", "estructurado", fuente.proceso, codigo,
                       f"fecha_carga={fecha}", nombre))
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).to_csv(p, index=False)
    return p


def produccion(fecha, inicial, producido, ventas, bono, final):
    return {"FECHA": fecha, "Stock inicial": inicial, "Producción": producido,
            "Ventas": ventas, "Bonificaciones": bono, "Stock final": final}


def venta(precio, canal="MAYORISTA", producto="B10", fecha="2020-01-01", doc="V1"):
    return {"DocNum": doc, "LineNum": 0, "DocDate": fecha, "CardCode": "C1",
            "U_CTG_SCOPNUM": "999", "U_PLACA": "T1A123", "ItemCode": producto,
            "Kg": 10, "Price": precio, "Canal": canal}


def compra(scop="999", fecha="2020-01-01", kg="10", doc="F1"):
    return {"SCOP": scop, "FECHA": fecha, "PLACA CARGADA": "T1A123", "PLACA FACTURADA": "T1A123",
            "PRODUCTO": "B10", "KG": kg, "T.C.": "3.5", "N DOC": doc, "ESTADO": "ATENDIDO"}


def maestro(documentos):
    return [{"CardCode": f"C{i}", "RUC/DNI": d, "CAP. ALMAC. TOTAL (KG)": "5 000 kg",
             "ESTADO": "ACTIVO", "CANAL": "MAYORISTA"} for i, d in enumerate(documentos)]


def test_cinco_metricas_desde_bronze_y_json_sin_identificadores(lago):
    escribir_bronze("aba_02", [compra(), compra(scop="", kg="TRUE", doc="F2"), compra(fecha="2015-01-01")])
    escribir_bronze("com_19", [venta(17.45), venta(24.15, "DIRECTO", doc="V2"), venta(100, producto="B45")])
    escribir_bronze("red_02", maestro(["20131312955", "20131312954", "01234567", "1234567", "", "123456789"]))
    escribir_bronze("pro_01", [produccion("2018-10-22", 10, 5, 3, 2, 10),
                              produccion("2018-10-23", 10, -10, 0, 0, 0),
                              produccion("2018-10-24", 10, 5, 3, 2, 9)])
    r = linea_base.calcular(tipo_datos="sinteticos")
    assert not Path(rutas.ruta("silver")).exists()
    assert r["capa_origen"] == "bronze"
    assert r["stock"]["dias_produccion"] == 3
    assert r["stock"]["dias_residuo_cero"] == 2
    assert r["stock"]["dias_con_residuo"] == 1
    assert r["stock"]["producciones_negativas"] == 1
    assert r["registros_scop"] == 1  # fecha fuera del alcance excluida; falta SCOP en otra
    assert r["pct_compras_con_scop"] == 50
    docs = r["documentos_maestro"]
    assert docs["longitud_invalida"] == 2
    assert docs["vacios"] == 1
    assert docs["ruc_digito_verificador_invalido"] == 1  # 11 dígitos: longitud correcta
    assert docs["pct_longitud_invalida"] == pytest.approx(100 * 2 / 6, abs=1e-4)
    assert r["precio_b10"]["por_canal"]["MAYORISTA"]["min"] == 17.45
    assert r["precio_b10"]["por_canal"]["DIRECTO"]["max"] == 24.15
    assert r["incidencias"]["por_campo"]["aba_02"]["kg"] == 1
    assert r["incidencias"]["por_campo"]["aba_02"]["fecha"] == 1
    assert r["incidencias"]["por_campo"]["red_02"]["documento_raw"] == 4
    assert {c["estado"] for c in r["comparacion"]} >= {"difiere", "no_comparable"}
    p = linea_base.guardar(r, lago / "evidencia" / "linea_base.json")
    texto = p.read_text()
    assert json.loads(texto) == r
    for identificador in ("20131312955", "01234567", "T1A123"):
        assert identificador not in texto


def test_stock_incompleto_duplicado_y_cero_con_tolerancia(lago):
    escribir_bronze("pro_01", [produccion("2018-10-01", 1, 1, 1, 0, 1 + 5e-7),
                              produccion("2018-10-02", 1, 1, 1, 0, ""),
                              produccion("2018-10-03", 1, 1, 1, 0, 1),
                              produccion("03/10/2018", 1, 1, 1, 0, 1),
                              produccion("2015-01-01", 1, 1, 1, 0, 1)])
    r = linea_base.calcular()["stock"]
    assert r["dias_produccion"] == 3
    assert r["dias_evaluables"] == r["dias_residuo_cero"] == 1
    assert r["filas_incompletas"] == 1
    assert r["dias_con_registros_duplicados"] == 1


def test_reentregas_no_duplican_y_fecha_carga_selecciona(lago):
    escribir_bronze("aba_02", [compra(), compra()], fecha="2026-10-01")
    escribir_bronze("aba_02", [compra()], fecha="2026-10-10")
    assert linea_base.calcular()["registros_scop"] == 1
    assert linea_base.calcular(fecha_carga="2026-10-01")["registros_scop"] == 2
    assert linea_base.calcular(fecha_carga="2026-10-01")["incidencias"]["por_campo"]["aba_02"]["clave_unica"] == 1
    with pytest.raises(FileNotFoundError, match="No hay fuentes"):
        linea_base.calcular(fecha_carga="2026-09-01")


def test_ausencia_no_es_cero_y_contrato_falla(lago):
    with pytest.raises(FileNotFoundError):
        linea_base.calcular()
    escribir_bronze("aba_02", [compra()])
    r = linea_base.calcular()
    assert r["stock"] is None and r["documentos_maestro"] is None and r["precio_b10"] is None
    assert r["cobertura"]["pro_01"]["estado"] == "sin_archivos"
    escribir_bronze("com_19", [{"DocNum": "V1"}])
    with pytest.raises(ValueError, match="com_19.*contrato"):
        linea_base.calcular()
    with pytest.raises(ValueError, match="tipo_datos"):
        linea_base.calcular(tipo_datos="inventados")


def test_longitud_antes_de_rellenar_y_vacios_separados(lago):
    escribir_bronze("red_02", maestro(["1234567", "01234567", "20131312955.0", "abcdefgh", ""]))
    r = linea_base.calcular()["documentos_maestro"]
    assert r["longitud_invalida"] == 1
    assert r["formato_invalido_con_longitud_correcta"] == 1
    assert r["vacios"] == 1
    assert r["pct_longitud_invalida"] == 20
    assert r["pct_longitud_invalida_entre_informados"] == 25


def test_precio_positivo_en_soles_por_balon_y_ventana_2020(lago):
    escribir_bronze("com_19", [venta(17.45), venta(24.15, doc="V2"), venta(90, fecha="2021-01-01"),
                              venta("TRUE"), venta("inf"), venta(-1), venta(20, canal=""),
                              venta(99, producto="B45"), venta(10, fecha="2015-01-01")])
    r = linea_base.calcular()
    assert r["precio_b10"]["global"]["max"] == 90
    assert r["precio_b10_2020"]["global"]["max"] == 24.15
    assert r["precio_b10"]["filas_precio_invalido"] == 3
    assert r["precio_b10"]["filas_sin_canal"] == 1
    assert r["precio_b10"]["por_canal"]["MAYORISTA"]["filas"] == 3


def test_lectura_excel_y_numeros(lago):
    fuente = schemas.FUENTES_LINEA_BASE["aba_02"]
    p = Path(rutas.ruta("bronze", "interno", "estructurado", fuente.proceso, "aba_02",
                       "fecha_carga=2026-10-10", "datos.xlsx"))
    p.parent.mkdir(parents=True)
    pd.DataFrame([compra(kg="1e3")]).to_excel(p, index=False)
    assert linea_base.calcular()["registros_scop"] == 1
    assert linea_base.calcular()["incidencias"]["por_campo"]["aba_02"]["kg"] == 0
    numeros = linea_base._numeros(pd.Series([True, False, "1e3", "5 000 kg", "inf", "TRUE"]))
    assert numeros.isna().tolist() == [True, True, False, False, True, True]
    assert numeros[2] == 1000 and numeros[3] == 5000


def test_bronze_s3_con_lectura_simulada(lago, monkeypatch):
    import awswrangler as wr
    monkeypatch.setattr(config, "LAKE_URI", "s3://bucket-prueba/lake")
    uri = rutas.ruta("bronze", "interno", "estructurado", "abastecimiento", "aba_02",
                     "fecha_carga=2026-10-10", "datos.csv")
    monkeypatch.setattr(wr.s3, "list_objects", lambda p: [uri] if "/aba_02/" in p else [])
    monkeypatch.setattr(wr.s3, "read_csv", lambda *args, **kw: pd.DataFrame([compra()]))
    assert linea_base.calcular()["registros_scop"] == 1


def test_compatibilidad_pipeline_con_muestra_existente(lago):
    origen = lago / "entrega"
    muestra.generar(n_unidades=5, semilla=7, destino=origen)
    internos.ingerir(origen, fecha_carga="2026-10-10")
    r = linea_base.calcular(tipo_datos="sinteticos")
    assert r["registros_scop"] > 0
    assert r["precio_b10"]["global"]["min"] > 0
    assert r["stock"] is None  # el generador actual no inventa producción
    assert r["referencia_informe_v6"]["ordenes_scop_enero_julio_2023"] == 29
