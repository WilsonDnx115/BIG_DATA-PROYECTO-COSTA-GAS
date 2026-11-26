"""Las señales en Spark disparan sobre los mismos documentos que la versión pandas (F02)."""
import pandas as pd
import pytest

from src.bronze_to_silver import handler
from src.common import lake_io, muestra, rutas, schemas
from src.ingest import internos
from src.signals import senales

SENALES = ("S1", "S4", "S5", "S7", "S8", "S10")


@pytest.fixture()
def silver(lago):
    """Silver de la muestra sintética, leído en pandas (Spark no escribe ni lee archivos aquí)."""
    origen = lago / "entrega"
    muestra.generar(n_unidades=8, semilla=7, destino=origen)
    for a in internos.ingerir(origen, fecha_carga="2026-10-07"):
        handler.procesar_archivo(a)
    leer = lambda *p: lake_io.leer_parquet(rutas.ruta("silver", *p))  # noqa: E731
    return {"compras": leer("compras", "aba_02_ordenes_scop"), "ventas": leer("ventas", "com_19_lineas"),
            "flota": leer("flota", "dis_01_vehiculos"), "maestro": leer("maestro", "red_02_distribuidores")}


def _a_spark(spark, pdf: pd.DataFrame):
    """pandas → Spark por Arrow: la conversión ocurre en la JVM, sin lanzar procesos de Python."""
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return spark.createDataFrame(pdf)


def _documentos(df_pandas, senal):
    return set(df_pandas.loc[df_pandas["senal"] == senal, "documento"].astype(str))


def test_catalogo_tiene_las_12_senales():
    from src.glue import senales_spark

    assert list(senales_spark.CATALOGO) == [f"S{i}" for i in range(1, 13)]
    assert {g for _, g in senales_spark.CATALOGO.values()} <= {"alta", "media", "indicio"}
    assert senales_spark.CATALOGO["S1"][1] == "indicio"


def test_equivalencia_con_pandas(spark, silver):
    from src.glue import senales_spark

    sp = {k: _a_spark(spark, v) for k, v in silver.items()}
    esperado = pd.concat([senales.s1(silver["compras"]), senales.s4(silver["compras"], silver["flota"]),
                          senales.s5(silver["ventas"], silver["maestro"]),
                          senales.s7(silver["compras"], silver["flota"]),
                          senales.s8(silver["ventas"], silver["compras"]), senales.s10(silver["ventas"])])
    obtenido = senales_spark.calcular(sp["compras"], sp["ventas"], sp["flota"], sp["maestro"])

    assert obtenido.columns == schemas.CONTRATOS["fact_alerta"].columnas()
    por_senal = {r["senal"]: r["n"] for r in obtenido.groupBy("senal").count()
                 .withColumnRenamed("count", "n").take(20)}
    for s in SENALES:
        docs = {r["documento"] for r in obtenido.filter(obtenido.senal == s).select("documento").take(10_000)}
        assert docs == _documentos(esperado, s), s
        assert por_senal.get(s, 0) == int((esperado["senal"] == s).sum()), s
    assert por_senal.get("S1", 0) > 0 and por_senal.get("S7", 0) > 0   # la muestra inyecta ambos casos


# --- F03 · S2, S3 y S6 sobre compras_glp --------------------------------------
def _compras(filas):
    """compras_glp mínima con el contrato de WP 0.2."""
    cols = ["proveedor", "serie", "numero", "nro_scop", "fecha_factura", "kg", "monto_usd",
            "tipo_cambio", "placa_norm", "anio", "mes"]
    df = pd.DataFrame(filas, columns=cols)
    df["fecha_factura"] = pd.to_datetime(df["fecha_factura"]).dt.date
    return df


def _docs(df):
    return {r["documento"] for r in df.select("documento").take(1000)}


def test_s2_sin_scop_y_scop_repetido(spark):
    from src.glue import senales_spark

    c = _a_spark(spark, _compras([
        ("PETROPERU", "F001", "1", "11111111111", "2022-03-01", 1000.0, 600.0, 3.8, "ABC123", 2022, 3),
        ("PETROPERU", "F001", "2", "11111111111", "2022-03-02", 1000.0, 600.0, 3.8, "ABC123", 2022, 3),
        ("SOLGAS", "F002", "7", None, "2022-03-03", 1000.0, 600.0, 3.8, "XYZ789", 2022, 3),
        ("SOLGAS", "F002", "8", "  ", "2022-03-03", 1000.0, 600.0, 3.8, "XYZ789", 2022, 3),
        ("SOLGAS", "F002", "9", "22222222222", "2022-03-04", 1000.0, 600.0, 3.8, "XYZ789", 2022, 3),
    ]))
    a = senales_spark.s2(c)
    assert _docs(a) == {"PETROPERU F001-1", "PETROPERU F001-2", "SOLGAS F002-7", "SOLGAS F002-8"}
    assert {r["puntaje"] for r in a.filter(a.documento == "PETROPERU F001-1").take(1)} == {2.0}
    assert a.columns == schemas.CONTRATOS["fact_alerta"].columnas()


def test_s3_mediana_movil_sin_mirar_el_futuro(spark):
    from src.glue import senales_spark

    base = [("PETROPERU", "F001", str(i), "1", f"2022-03-0{i}", 1000.0, 600.0, 3.8, "ABC123", 2022, 3)
            for i in range(1, 4)]                                           # 0.60 USD/kg
    caro = [("PETROPERU", "F001", "4", "1", "2022-03-05", 1000.0, 640.0, 3.8, "ABC123", 2022, 3)]   # +6.7 %
    normal = [("PETROPERU", "F001", "5", "1", "2022-03-06", 1000.0, 610.0, 3.8, "ABC123", 2022, 3)]  # +1.7 %
    lejano = [("PETROPERU", "F001", "6", "1", "2022-08-01", 1000.0, 700.0, 3.8, "ABC123", 2022, 8)]  # sin pares en 90 días
    sin_kg = [("PETROPERU", "F001", "7", "1", "2022-03-07", 0.0, 900.0, 3.8, "ABC123", 2022, 3)]
    a = senales_spark.s3(_a_spark(spark, _compras(base + caro + normal + lejano + sin_kg)))
    assert _docs(a) == {"PETROPERU F001-4"}
    # La primera factura del proveedor no tiene facturas previas: su mediana es nula y no dispara.
    assert "PETROPERU F001-1" not in _docs(a)


def test_s3_con_precio_pactado(spark):
    from src.glue import senales_spark

    c = _a_spark(spark, _compras([("SOLGAS", "F002", "1", "1", "2022-03-01", 1000.0, 600.0, 3.8, "XYZ789", 2022, 3)]))
    pactos = _a_spark(spark, pd.DataFrame({"proveedor": ["SOLGAS"], "anio": [2022], "mes": [3],
                                           "usd_kg_pactado": [0.55]}))
    assert _docs(senales_spark.s3(c, pactos)) == {"SOLGAS F002-1"}          # 0.60 > 0.55 × 1.05


def test_s6_tipo_de_cambio(spark):
    from src.glue import senales_spark

    tc = pd.DataFrame({"fecha": pd.to_datetime(["2022-03-04", "2022-03-07"]).date, "tc_venta": [3.80, 3.82]})
    c = _a_spark(spark, _compras([
        ("A", "F1", "1", "1", "2022-03-04", 1000.0, 600.0, 1.0, "ABC123", 2022, 3),    # T.C. = 1
        ("A", "F1", "2", "1", "2022-03-04", 1000.0, 600.0, 3.92, "ABC123", 2022, 3),   # 3.2 % sobre el oficial
        ("A", "F1", "3", "1", "2022-03-04", 1000.0, 600.0, 3.81, "ABC123", 2022, 3),   # dentro del 1 %
        ("A", "F1", "4", "1", "2022-03-06", 1000.0, 600.0, 3.80, "ABC123", 2022, 3),   # domingo: usa el viernes
        ("A", "F1", "5", "1", "2022-03-06", 1000.0, 600.0, 3.90, "ABC123", 2022, 3),   # domingo y fuera del 1 %
        ("A", "F1", "6", "1", "2023-01-10", 1000.0, 600.0, 4.50, "ABC123", 2023, 1),   # sin oficial: no dispara
    ]))
    a = senales_spark.s6(c, _a_spark(spark, tc))
    assert _docs(a) == {"A F1-1", "A F1-2", "A F1-5"}


# --- F04 · S9, S11 y S12 ------------------------------------------------------
def test_s9_combustible_sin_venta_y_fuera_de_su_rol(spark):
    from src.glue import senales_spark

    filas = [(f"REP{i:03d}", 2020, 5, "reparto", 10_000.0, 500.0 + 10 * i) for i in range(10)]   # ≈ S/ 50 por t
    filas += [("REP900", 2020, 5, "reparto", 10_000.0, 5_000.0),     # S/ 500 por t: fuera de su rol
              ("REP901", 2020, 5, "reparto", 0.0, 300.0),            # combustible sin venta
              ("REP902", 2020, 5, "reparto", None, 200.0),           # kg nulo con combustible
              ("REP903", 2020, 5, "reparto", 0.0, 0.0)]              # parada: sin combustible ni venta
    filas += [(f"CIS{i:03d}", 2020, 5, "transporte", 100_000.0, 2_000.0 + 50 * i) for i in range(5)]
    um = pd.DataFrame(filas, columns=["placa_norm", "anio", "mes", "rol", "kg", "combustible"])
    a = senales_spark.s9(_a_spark(spark, um))
    assert {r["placa_norm"] for r in a.select("placa_norm").take(100)} == {"REP900", "REP901", "REP902"}
    assert _docs(a) >= {"REP900 2020-05"}


def test_s11_cierre_sin_medicion_y_ajustes(spark):
    from src.glue import senales_spark

    oct18 = pd.date_range("2018-10-01", "2018-10-31")
    prod = pd.DataFrame({"fecha": oct18.date, "anio": 2018, "mes": 10, "residuo_kg": 0.0, "ajuste_kg": None})
    prod.loc[prod.index[-1], "ajuste_kg"] = -9095.0
    nov18 = pd.DataFrame({"fecha": pd.date_range("2018-11-01", "2018-11-03").date, "anio": 2018, "mes": 11,
                          "residuo_kg": [0.0, 12.5, -3.0], "ajuste_kg": None})
    p = pd.concat([prod, nov18], ignore_index=True)
    p["ajuste_kg"] = p["ajuste_kg"].astype("float64")
    a = senales_spark.s11(_a_spark(spark, p))
    assert _docs(a) == {"CIERRE 2018-10", "AJUSTE 2018-10-31"}
    assert {r["kg"] for r in a.filter(a.documento == "AJUSTE 2018-10-31").take(1)} == {9095.0}


def test_s12_cruce_tesoreria_logistica(spark):
    from src.glue import senales_spark

    logistica = _a_spark(spark, _compras([
        ("PETROPERU", "F001", "00123", "1", "2022-03-01", 24_070.0, 1.0, 3.8, "ABC123", 2022, 3),   # coincide
        ("PETROPERU", "F001", "124", "1", "2022-03-02", 24_070.0, 1.0, 3.8, "ABC123", 2022, 3),     # kg distinto
        ("SOLGAS", "F002", "50", "1", "2022-03-03", 10_000.0, 1.0, 3.8, "XYZ789", 2022, 3),         # solo logística
        ("SOLGAS", "F002", "51", "1", "2022-03-04", 10_000.0, 1.0, 3.8, "XYZ789", 2022, 3),         # kg desconocido
    ]))
    tes = pd.DataFrame({
        "proveedor": ["petroperu ", "PETROPERU", "SOLGAS", "SOLGAS"],
        "documento": ["F001-123", "F001-124", "F002-99", "F002-51"],
        "kg": [24_070.5, 240_700.0, 8_000.0, None],
        "fecha_pago": pd.to_datetime(["2022-03-10", "2022-03-11", "2022-04-02", "2022-03-12"]).date,
        "fecha_vence": pd.to_datetime(["2022-03-31", "2022-04-01", "2022-04-30", "2022-04-03"]).date})
    tesoreria = _a_spark(spark, tes)

    cruce = senales_spark.cruce_s12(tesoreria, logistica)
    clases = {r["documento"]: r["clase_s12"] for r in cruce.select("documento", "clase_s12").take(100)}
    assert clases == {"PETROPERU F001-00123": "coincide", "PETROPERU F001-124": "kg_distinto",
                      "SOLGAS F002-50": "solo_logistica", "SOLGAS F002-99": "solo_tesoreria",
                      "SOLGAS F002-51": "kg_desconocido"}

    a = senales_spark.s12(tesoreria, logistica)
    assert _docs(a) == {"PETROPERU F001-124", "SOLGAS F002-50", "SOLGAS F002-99"}
    fila = a.filter(a.documento == "SOLGAS F002-99").take(1)[0]
    assert (fila["anio"], fila["mes"], fila["kg"]) == (2022, 4, 8000.0)   # solo tesorería: fecha de pago


def test_id_alerta_deterministico(spark, silver):
    from src.glue import senales_spark

    c = _a_spark(spark, silver["compras"])
    a = {r["id_alerta"] for r in senales_spark.s1(c).select("id_alerta").take(1000)}
    b = {r["id_alerta"] for r in senales_spark.s1(c).select("id_alerta").take(1000)}
    assert a == b and all(len(i) == 12 for i in a)
