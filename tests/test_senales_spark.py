"""Señales en Spark con el contrato y las interfaces del WP 0.8.

Cada señal que tiene versión en pandas se compara contra ella sobre los mismos datos:
S1, S4, S5, S8 y S10 contra `senales_fixture` (muestra sintética antigua); S2, S7, S9,
S11 y el KPI 4 contra las señales y el modelo base del WP 0.8. S3, S6 y S12 llevan sus
propios casos. Spark recibe los datos por Arrow y no escribe archivos.
"""
import numpy as np
import pandas as pd
import pytest

from src.bronze_to_silver import handler
from src.common import lake_io, muestra, rutas, schemas
from src.ingest import internos
from src.models import base_mad
from src.signals import senales_fixture
from src.signals.s2 import s2 as s2_pd
from src.signals.s7 import s7 as s7_pd
from src.signals.s9 import s9 as s9_pd
from src.signals.s11 import s11 as s11_pd

COLUMNAS = schemas.CONTRATOS["fact_alerta_base"].columnas()


def _a_spark(spark, pdf: pd.DataFrame):
    """pandas → Spark por Arrow: la conversión ocurre en la JVM, sin lanzar procesos de Python."""
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return spark.createDataFrame(pdf)


def _filas(df, *cols, n=10_000):
    return {tuple(r[c] for c in cols) for r in df.select(*cols).take(n)}


# --- Catálogo y contrato ------------------------------------------------------
def test_catalogo_sale_del_yaml_unico():
    """Spark no tiene catálogo propio: descripción y grado salen de src/signals/catalogo.yaml."""
    from src.glue import senales_spark
    from src.signals.common import cargar_catalogo

    yaml_ = cargar_catalogo()
    assert list(senales_spark.CATALOGO) == [f"S{i}" for i in range(1, 13)]
    assert all(senales_spark.CATALOGO[s][0] == yaml_[s]["descripcion"] for s in yaml_)
    grados = {s: g for s, (_, g) in senales_spark.CATALOGO.items()}
    assert grados == {"S1": "indicio", "S2": "alta", "S3": "media", "S4": "indicio", "S5": "media",
                      "S6": "alta", "S7": "indicio", "S8": "alta", "S9": "media", "S10": "media",
                      "S11": "alta", "S12": "alta"}


def test_grado_de_evidencia_y_de_alerta():
    from src.signals.common import grado_alerta, grado_evidencia

    assert grado_evidencia({"evidencia": "alta", "muestra_minima": True}) == "indicio"
    assert grado_evidencia({"evidencia": "alta_si_existe_contraste"}) == "alta"
    assert grado_alerta({"evidencia": "media"}) == "medio"
    assert grado_alerta({"evidencia": "alta"}) == "alto"


# --- Fixture: S1, S4, S5, S8 y S10 contra la versión pandas -----------------------
@pytest.fixture()
def silver(lago):
    """Silver de la muestra sintética antigua, leído en pandas."""
    origen = lago / "entrega"
    muestra.generar(n_unidades=8, semilla=7, destino=origen)
    for a in internos.ingerir(origen, fecha_carga="2026-10-07"):
        handler.procesar_archivo(a)
    leer = lambda *p: lake_io.leer_parquet(rutas.ruta("silver", *p))  # noqa: E731
    return {"compras": leer("compras", "aba_02_ordenes_scop"), "ventas": leer("ventas", "com_19_lineas"),
            "flota": leer("flota", "dis_01_vehiculos"), "maestro": leer("maestro", "red_02_distribuidores")}


def test_fixture_equivalente_a_pandas(spark, silver):
    from src.glue import senales_spark

    sp = {k: _a_spark(spark, v) for k, v in silver.items()}
    esperado = pd.concat([senales_fixture.s1(silver["compras"]),
                          senales_fixture.s4(silver["compras"], silver["flota"]),
                          senales_fixture.s5(silver["ventas"], silver["maestro"]),
                          senales_fixture.s8(silver["ventas"], silver["compras"]),
                          senales_fixture.s10(silver["ventas"])])
    obtenido = senales_spark.calcular(sp["compras"], sp["ventas"], sp["flota"], sp["maestro"])
    assert obtenido.columns == COLUMNAS
    for s in ("S1", "S4", "S5", "S8", "S10"):
        docs = {d for (d,) in _filas(obtenido.filter(obtenido.senal == s), "factura_id")}
        assert docs == set(esperado.loc[esperado.senal == s, "documento"].astype(str)), s
        assert docs, s                                    # la muestra dispara las cinco
    assert obtenido.filter(obtenido.valor_soles.isNotNull()).count() == 0   # no se valorizan kg


def test_id_alerta_deterministico_y_de_24(spark, silver):
    from src.glue import senales_spark

    c = _a_spark(spark, silver["compras"])
    a = _filas(senales_spark.s1(c), "id_alerta")
    assert a == _filas(senales_spark.s1(c), "id_alerta") and all(len(i) == 24 for (i,) in a)


# --- Interfaz compras: S2, S3 y S6 ------------------------------------------------
def _compras(filas):
    df = pd.DataFrame(filas, columns=["factura_id", "fecha", "proveedor_id", "codigo_scop", "kg",
                                      "precio_usd_kg", "tipo_cambio"])
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["unidad_id"] = "ABC123"
    return df


def test_normalizar_compras_desde_silver(spark):
    from src.glue import senales_spark

    silver = pd.DataFrame({"proveedor": [" petroperu "], "serie": ["F001"], "numero": ["00123"],
                           "nro_scop": ["  "], "fecha_factura": pd.to_datetime(["2022-03-01"]).date,
                           "kg": [1000.0], "monto_usd": [600.0], "tipo_cambio": [3.8], "placa_norm": ["ABC123"]})
    (f,) = senales_spark.normalizar_compras(_a_spark(spark, silver)).take(1)
    assert f["factura_id"] == "PETROPERU|F001|123" and f["proveedor_id"] == "PETROPERU"
    assert f["codigo_scop"] is None and f["precio_usd_kg"] == pytest.approx(0.6)
    assert (f["unidad_id"], f["anio"], f["mes"]) == ("ABC123", 2022, 3)


def test_s2_igual_que_pandas(spark):
    from src.glue import senales_spark

    c = _compras([("F-1", "2022-03-01", "P1", "111", 1000.0, 0.6, 3.8),
                  ("F-2", "2022-03-02", "P1", "111", 1000.0, 0.6, 3.8),     # SCOP repetido
                  ("F-3", "2022-03-03", "P2", None, 1000.0, 0.6, 3.8),      # sin SCOP
                  ("F-4", "2022-03-04", "P2", "222", 1000.0, 0.6, 3.8),
                  ("F-5", "2021-05-04", "P2", None, 1000.0, 0.6, 3.8)])     # fuera de la ventana
    esperado = s2_pd(c.drop(columns="unidad_id"))
    obtenido = senales_spark.s2(_a_spark(spark, c))
    assert _filas(obtenido, "factura_id", "motivo") == set(zip(esperado.factura_id, esperado.motivo))
    assert obtenido.columns == COLUMNAS


def test_s3_mediana_movil_sin_mirar_el_futuro(spark):
    from src.glue import senales_spark

    base = [(f"F-{i}", f"2022-03-0{i}", "P1", "1", 1000.0, 0.60, 3.8) for i in range(1, 4)]
    c = _compras(base + [("F-4", "2022-03-05", "P1", "1", 1000.0, 0.64, 3.8),     # +6.7 %
                         ("F-5", "2022-03-06", "P1", "1", 1000.0, 0.61, 3.8),     # +1.7 %
                         ("F-6", "2022-08-01", "P1", "1", 1000.0, 0.70, 3.8),     # sin pares en 90 días
                         ("F-7", "2022-03-07", "P1", "1", 0.0, None, 3.8)])       # sin precio
    a = senales_spark.s3(_a_spark(spark, c))
    assert _filas(a, "factura_id", "motivo") == {("F-4", "precio_sobre_mediana_movil_proveedor")}


def test_s3_con_precio_pactado(spark):
    from src.glue import senales_spark

    c = _compras([("F-1", "2022-03-01", "P1", "1", 1000.0, 0.60, 3.8)]).assign(precio_pactado_usd_kg=0.55)
    assert _filas(senales_spark.s3(_a_spark(spark, c)), "factura_id", "motivo") == {
        ("F-1", "precio_fuera_de_lo_pactado")}                                       # 0.60 > 0.55 × 1.05


def test_s6_tipo_de_cambio(spark):
    from src.glue import senales_spark

    tc = pd.DataFrame({"fecha": pd.to_datetime(["2022-03-04", "2022-03-07"]).date, "tc_oficial": [3.80, 3.82]})
    c = _compras([("F-1", "2022-03-04", "P", "1", 1000.0, 0.6, 1.0),    # T.C. = 1
                  ("F-2", "2022-03-04", "P", "1", 1000.0, 0.6, 3.92),   # 3.2 % sobre el oficial
                  ("F-3", "2022-03-04", "P", "1", 1000.0, 0.6, 3.81),   # dentro del 1 %
                  ("F-4", "2022-03-06", "P", "1", 1000.0, 0.6, 3.80),   # domingo: usa el viernes
                  ("F-5", "2022-03-06", "P", "1", 1000.0, 0.6, 3.90),   # domingo y fuera del 1 %
                  ("F-6", "2023-01-10", "P", "1", 1000.0, 0.6, 4.50)])  # sin oficial: no dispara
    a = senales_spark.s6(_a_spark(spark, c), _a_spark(spark, tc))
    assert _filas(a, "factura_id", "motivo") == {("F-1", "tipo_cambio_igual_a_1"),
                                                ("F-2", "tipo_cambio_difiere_del_oficial"),
                                                ("F-5", "tipo_cambio_difiere_del_oficial")}


# --- Unidad × mes: KPI 4, S7 y S9 contra el modelo base --------------------------------
def _unidad_mes():
    rng = np.random.default_rng(3)
    filas = []
    for rol, n in (("reparto", 30), ("transporte", 12)):
        for i in range(n):
            filas.append((f"{rol[:3].upper()}{i:03d}", rol, 2020, 5, 10_000.0, 80_000.0,
                          float(500 * np.exp(rng.normal(0, 0.2))), 900.0))
    filas += [("REP900", "reparto", 2020, 5, 10_000.0, 0.0, 9_000.0, 9_500.0),    # atípico
              ("REP901", "reparto", 2020, 5, 0.0, 0.0, 300.0, 400.0),             # sin volumen
              ("REP902", "reparto", 2020, 5, 0.0, 0.0, 0.0, 0.0),                 # parada
              ("REP903", "reparto", 2021, 2, 0.0, 0.0, 300.0, 400.0)]             # fuera de la ventana
    return pd.DataFrame(filas, columns=["unidad_id", "rol", "anio", "mes", "kg_vendidos", "kg_transportados",
                                        "gasto_combustible", "gasto_total"])


def test_kpi4_igual_que_el_modelo_base(spark):
    from src.glue import senales_spark

    um = _unidad_mes()
    esperado = base_mad.puntuar(um).set_index("unidad_id")
    for f in senales_spark.kpi4(_a_spark(spark, um)).take(1000):
        e = esperado.loc[f["unidad_id"]]
        assert f["estado_puntaje"] == e.estado_puntaje, f["unidad_id"]
        assert f["alerta_base"] == bool(e.alerta_base), f["unidad_id"]
        if pd.isna(e.z):
            assert f["z"] is None
        else:
            assert f["z"] == pytest.approx(e.z, rel=1e-9), f["unidad_id"]


def test_kpi4_mad_cero_no_es_evaluable(spark):
    from src.glue import senales_spark

    um = pd.DataFrame({"unidad_id": ["A", "B", "C"], "rol": "reparto", "anio": 2020, "mes": 1,
                       "kg_vendidos": 1000.0, "kg_transportados": 0.0, "gasto_combustible": 50.0,
                       "gasto_total": 60.0})
    estados = _filas(senales_spark.kpi4(_a_spark(spark, um)), "estado_puntaje", "z")
    assert estados == {("mad_cero_o_sin_grupo_evaluable", None)}


def test_s9_igual_que_pandas(spark):
    from src.glue import senales_spark

    um = _unidad_mes()
    esperado = s9_pd(um)
    obtenido = senales_spark.s9(_a_spark(spark, um))
    assert _filas(obtenido, "unidad_id", "motivo", "tipo") == set(zip(esperado.unidad_id, esperado.motivo,
                                                                      esperado.tipo))
    assert {"REP900", "REP901"} <= {u for (u,) in _filas(obtenido, "unidad_id")}


def test_s7_igual_que_pandas(spark):
    from src.glue import senales_spark

    um = _unidad_mes()
    unidades = pd.DataFrame({"unidad_id": um.unidad_id, "habilitada": um.unidad_id.isin(["REP001", "TRA002"]) == False})  # noqa: E712
    unidades.loc[unidades.unidad_id == "REP902", "habilitada"] = False      # sin actividad: no dispara
    esperado = s7_pd(um, unidades)
    obtenido = senales_spark.s7(_a_spark(spark, um), _a_spark(spark, unidades))
    assert _filas(obtenido, "unidad_id") == {(u,) for u in esperado.unidad_id} == {("REP001",), ("TRA002",)}


def test_agregar_senales_por_unidad_mes(spark):
    from src.glue import senales_spark

    um = _a_spark(spark, _unidad_mes())
    extra = pd.DataFrame({"senal": ["S4", "S4", "S10", "S11"], "unidad_id": ["REP901", "REP901", "REP901", None],
                          "anio": [2020] * 4, "mes": [5] * 4})
    alertas = senales_spark.s9(um).select("senal", "unidad_id", "anio", "mes").unionByName(_a_spark(spark, extra))
    r = {(f["unidad_id"], f["anio"], f["mes"]): f for f in senales_spark.agregar_senales(um, alertas).take(100)}
    assert r[("REP901", 2020, 5)]["senales"] == ["S10", "S4", "S9"] and r[("REP901", 2020, 5)]["n_senales"] == 3
    assert r[("REP000", 2020, 5)]["senales"] == [] and r[("REP000", 2020, 5)]["n_senales"] == 0
    assert len(r) == len(_unidad_mes())


# --- S11 y S12 ---------------------------------------------------------------------
def test_s11_igual_que_pandas(spark):
    from src.glue import senales_spark

    prod = pd.DataFrame({"fecha": ["2018-10-01", "2018-10-02", "2018-10-03", "2018-10-04", "2018-11-01"],
                         "stock_inicial": [10.0, 10.0, 10.0, 10.0, 10.0], "produccion": [5.0, -10.0, 5.0, 5.0, 5.0],
                         "ventas": [3.0, 0.0, 3.0, 3.0, 3.0], "bonificaciones": [2.0, 0.0, 2.0, 2.0, 2.0],
                         "stock_final": [10.0, 0.0, 10.0, 10.0, 10.0],
                         "stock_final_es_calculado": [True, True, False, None, True]})
    esperado = s11_pd(prod)
    p = prod.assign(fecha=pd.to_datetime(prod.fecha).dt.date)
    obtenido = senales_spark.s11(_a_spark(spark, p))
    assert _filas(obtenido, "fecha", "motivo") == {(f.date(), m) for f, m in zip(esperado.fecha, esperado.motivo)}
    assert len(esperado) == 2                                   # oct-01 y el ajuste de oct-02


def test_s12_cruce_tesoreria_logistica(spark):
    from src.glue import senales_spark

    logistica = _a_spark(spark, pd.DataFrame({
        "proveedor": ["PETROPERU", "PETROPERU", "SOLGAS", "SOLGAS"], "serie": ["F001", "F001", "F002", "F002"],
        "numero": ["00123", "124", "50", "51"], "nro_scop": ["1", "2", "3", "4"],
        "fecha_factura": pd.to_datetime(["2022-03-01", "2022-03-02", "2022-03-03", "2022-03-04"]).date,
        "kg": [24_070.0, 24_070.0, 10_000.0, 10_000.0], "monto_usd": [1.0] * 4, "tipo_cambio": [3.8] * 4,
        "placa_norm": ["ABC123", "ABC123", "XYZ789", "XYZ789"]}))
    compras = senales_spark.normalizar_compras(logistica)
    tesoreria = _a_spark(spark, pd.DataFrame({
        "proveedor": ["petroperu ", "PETROPERU", "SOLGAS", "SOLGAS"],
        "documento": ["F001-123", "F001-124", "F002-99", "F002-51"],
        "kg": [24_070.5, 240_700.0, 8_000.0, None],
        "fecha_pago": pd.to_datetime(["2022-03-10", "2022-03-11", "2022-04-02", "2022-03-12"]).date,
        "fecha_vence": pd.to_datetime(["2022-03-31", "2022-04-01", "2022-04-30", "2022-04-03"]).date}))

    clases = dict(_filas(senales_spark.cruce_s12(tesoreria, compras), "factura_id", "clase_s12"))
    assert clases == {"PETROPERU|F001|123": "coincide", "PETROPERU|F001|124": "kg_distinto",
                      "SOLGAS|F002|50": "solo_logistica", "SOLGAS|F002|99": "solo_tesoreria",
                      "SOLGAS|F002|51": "kg_desconocido"}
    a = senales_spark.s12(tesoreria, compras)
    assert _filas(a, "factura_id", "motivo") == {("PETROPERU|F001|124", "kg_distinto"),
                                                ("SOLGAS|F002|50", "solo_logistica"),
                                                ("SOLGAS|F002|99", "solo_tesoreria")}
    (fila,) = a.filter(a.factura_id == "SOLGAS|F002|99").take(1)
    assert (fila["anio"], fila["mes"], fila["kg"]) == (2022, 4, 8000.0)    # solo tesorería: fecha de pago


# --- FR15 · control de sobrecobros F08 ----------------------------------------------
def _sobrecobros():
    return pd.DataFrame({
        "factura_id": ["PETROPERU|F001|1", "PETROPERU|F001|2", "SOLGAS|F002|3", "SOLGAS|F002|4", "SOLGAS|F002|5"],
        "fecha": pd.to_datetime(["2022-03-01", "2022-03-02", "2022-04-01", "2021-06-01", "2022-05-01"]),
        "monto_facturado_soles": [1_100.0, 900.0, 2_050.0, 3_000.0, 500.0],
        "monto_pactado_soles": [1_000.0, 900.0, 2_000.0, 2_000.0, 0.0]})
    # 1: sobrecobro de S/ 100; 2: igual; 3: S/ 50; 4: fuera de la ventana; 5: sin pactado


def test_control_sobrecobros_igual_que_pandas(spark):
    from src.glue import senales_spark
    from src.signals.s3 import s3_control

    pdf = _sobrecobros()
    esperado = s3_control(pdf)
    obtenido = senales_spark.control_sobrecobros(_a_spark(spark, pdf))
    assert obtenido.columns == COLUMNAS
    assert _filas(obtenido, "factura_id", "motivo", "valor_soles") == set(
        zip(esperado.factura_id, esperado.motivo, esperado.valor_soles))
    assert {f: round(p, 6) for f, p in _filas(obtenido, "factura_id", "puntaje")} == {
        f: round(p, 6) for f, p in zip(esperado.factura_id, esperado.puntaje)}
    assert {r["grado_evidencia"] for r in obtenido.take(5)} == set(esperado.grado_evidencia)


def test_control_sobrecobros_rechaza_contrato_o_facturas_invalidas(spark):
    from src.glue import senales_spark

    with pytest.raises(ValueError, match="incompleto"):
        senales_spark.control_sobrecobros(_a_spark(spark, _sobrecobros().drop(columns="monto_pactado_soles")))
    repetida = _sobrecobros().assign(factura_id=["X"] * 5)
    with pytest.raises(ValueError, match="duplicada"):
        senales_spark.control_sobrecobros(_a_spark(spark, repetida))


def test_las_demas_alertas_no_valorizan_kg(spark):
    from src.glue import senales_spark

    c = _compras([("F-3", "2022-03-03", "P2", None, 1000.0, 0.6, 3.8)])
    assert senales_spark.s2(_a_spark(spark, c)).filter("valor_soles IS NOT NULL").count() == 0


# --- FR16 · S10 sobre ventas_detalle de Silver --------------------------------------
def _ventas_detalle(filas):
    cols = ["documento", "fecha", "articulo_codigo", "articulo", "es_glp", "precio_unitario", "kg", "cliente_id"]
    df = pd.DataFrame(filas, columns=cols)
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["anio"] = [f.year for f in df["fecha"]]
    df["mes"] = [f.month for f in df["fecha"]]
    return df


def test_s10_doce_por_ciento_bajo_la_mediana_dispara_y_cinco_no(spark):
    from src.glue import senales_spark

    v = _ventas_detalle([
        ("B-1", "2020-05-03", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c1"),
        ("B-2", "2020-05-04", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c2"),
        ("B-3", "2020-05-05", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c3"),
        ("B-4", "2020-05-06", "GLP10", "GLP 10 KG", True, 88.0, 10.0, "c4"),      # 12 % bajo: dispara
        ("B-5", "2020-05-07", "GLP10", "GLP 10 KG", True, 95.0, 10.0, "c5"),      # 5 % bajo: no
        ("B-6", "2020-05-07", "ARROZ", "ARROZ 5 KG", False, 10.0, None, "c6"),    # no es GLP
        ("B-7", "2020-05-08", "GLP10", "GLP 10 KG", True, 0.0, 10.0, "c7"),       # precio cero: falta el dato
        ("B-8", "2022-05-08", "GLP10", "GLP 10 KG", True, 50.0, 10.0, "c8"),      # fuera de la ventana
        ("B-9", "2022-05-09", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c9"),
    ])
    a = senales_spark.s10_ventas(_a_spark(spark, v))
    assert a.columns == COLUMNAS
    (fila,) = a.take(5)
    assert (fila["factura_id"], fila["unidad_id"], fila["rol"]) == ("B-4", "c4", "cliente")
    assert fila["puntaje"] == pytest.approx(0.12) and fila["resolucion"] == "linea_venta"
    assert fila["valor_soles"] is None


def test_s10_compara_cada_articulo_con_su_propia_mediana(spark):
    from src.glue import senales_spark

    v = _ventas_detalle([
        ("A-1", "2024-04-02", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c1"),
        ("A-2", "2024-04-03", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c2"),
        ("A-3", "2024-04-04", "GLP45", "GLP 45 KG", True, 400.0, 45.0, "c3"),
        ("A-4", "2024-04-05", "GLP45", "GLP 45 KG", True, 400.0, 45.0, "c4"),
        ("A-5", "2024-04-06", "GLP45", "GLP 45 KG", True, 330.0, 45.0, "c5"),    # mediana 400: 17.5 % bajo
    ])
    assert _filas(senales_spark.s10_ventas(_a_spark(spark, v)), "factura_id") == {("A-5",)}


def test_s10_usa_el_canal_cuando_la_tabla_lo_trae(spark):
    from src.glue import senales_spark

    v = _ventas_detalle([
        ("D-1", "2020-05-02", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c1"),
        ("D-2", "2020-05-03", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c2"),
        ("D-3", "2020-05-04", "GLP10", "GLP 10 KG", True, 100.0, 10.0, "c3"),
        ("I-1", "2020-05-05", "GLP10", "GLP 10 KG", True, 85.0, 10.0, "c4"),    # 15 % bajo la mediana de todas
    ])
    sin_canal = senales_spark.s10_ventas(_a_spark(spark, v))
    assert _filas(sin_canal, "factura_id", "motivo") == {("I-1", "precio_bajo_mediana_de_la_presentacion")}
    con_canal = v.assign(canal=["directa", "directa", "directa", "indirecta"])
    assert senales_spark.s10_ventas(_a_spark(spark, con_canal)).count() == 0   # cada canal, su propia mediana


# --- FR17 · S5 con la capacidad de distribuidores -----------------------------------
SAL = "sal-de-prueba"


def _clientes_y_distribuidores():
    from src.common.limpieza import seudonimizar

    clientes = pd.DataFrame({
        # Hoja2: código SN y nombre; Hoja1/Hoja3: documento y nombre (como los deja Silver)
        "codigo_sn": ["C001", "C002", "C003", None, None, None, None],
        "razon_social": ["GAS NORTE SAC", None, "DOBLE SAC", "GAS NORTE SAC", None, "DOBLE SAC", "DOBLE SAC"],
        "nombre_hash": [None, "hn2", None, None, "hn2", None, None],
        "ruc": [None, None, None, "20111111111", None, "20333333333", "20444444444"],
        "documento_hash": [None, None, None, None, "hd2", None, None],
        "entidad_id": ["C001", "C002", "C003", "20111111111", "hd2", "20333333333", "20444444444"]})
    distribuidores = pd.DataFrame({
        "entidad_id": ["20111111111", "20111111111", "20111111111", "hd2"],
        "direccion": ["AV. UNO 1", "AV. UNO 1", "JR. DOS 2", None],   # AV. UNO 1 repetida en dos hojas
        "capacidad_kg": [1_000.0, 1_000.0, 500.0, 300.0]})
    ids = {c: seudonimizar(c, SAL) for c in ("C001", "C002", "C003", "C009")}
    return clientes, distribuidores, ids


def test_puente_por_codigo_sn_y_nombre(spark):
    from src.glue import senales_spark

    clientes, _, ids = _clientes_y_distribuidores()
    puente = senales_spark.puente_cliente_distribuidor(_a_spark(spark, clientes), SAL)
    # C003 queda fuera: su nombre corresponde a dos RUC distintos (ambiguo)
    assert _filas(puente, "cliente_id", "entidad_id") == {(ids["C001"], "20111111111"), (ids["C002"], "hd2")}


def test_s5_volumen_del_mes_sobre_la_capacidad(spark):
    from src.glue import senales_spark

    clientes, distribuidores, ids = _clientes_y_distribuidores()
    ventas = _ventas_detalle([
        ("V-1", "2021-02-03", "GLP45", "GLP 45 KG", True, 400.0, 900.0, ids["C001"]),
        ("V-2", "2021-02-20", "GLP45", "GLP 45 KG", True, 400.0, 700.0, ids["C001"]),   # 1 600 > 1 500
        ("V-3", "2021-02-10", "GLP45", "GLP 45 KG", True, 400.0, 250.0, ids["C002"]),   # 250 < 300
        ("V-4", "2021-02-11", "GLP45", "GLP 45 KG", True, 400.0, 9_000.0, ids["C009"]),  # sin capacidad
        ("V-5", "2020-06-11", "GLP45", "GLP 45 KG", True, 400.0, 9_000.0, ids["C002"]),  # fuera de la ventana
    ])
    v, d = _a_spark(spark, ventas), _a_spark(spark, distribuidores)
    puente = senales_spark.puente_cliente_distribuidor(_a_spark(spark, clientes), SAL)
    a = senales_spark.s5_distribuidores(v, d, puente)
    assert a.columns == COLUMNAS
    (fila,) = a.take(5)
    assert (fila["unidad_id"], fila["rol"], fila["kg"], fila["anio"], fila["mes"]) == (ids["C001"], "cliente", 1_600.0, 2021, 2)
    assert fila["puntaje"] == pytest.approx(1_600.0 / 1_500.0) and fila["resolucion"] == "cliente_mes"
    cob = senales_spark.cobertura_s5(v, d, puente)
    assert cob == {"distribuidores_con_capacidad": 2, "distribuidores_con_ventas": 2,
                   "clientes_con_ventas": 3, "clientes_no_evaluables": 1}
