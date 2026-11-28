"""Medición de la operación con entregas mensuales (FR14). Tablas pequeñas de prueba."""
import datetime as dt

import pandas as pd
import pytest

from src.glue import operacion

D = dt.date


@pytest.fixture()
def arrow(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return spark


def _valor(filas, medida):
    (f,) = [f for f in filas if f["medida"] == medida]
    return f


def serie(meses_extra=False):
    filas = [("unidad", "REP1", "mes", D(2020, 5, 1), 2020, 5, "rojo", 1_200.0),
             ("unidad", "REP2", "mes", D(2020, 5, 1), 2020, 5, "verde", 0.0),
             ("unidad", "TRA1", "mes", D(2020, 5, 1), 2020, 5, "rojo", 800.0),
             ("cliente", "C1", "mes", D(2020, 5, 1), 2020, 5, "rojo", 99.0)]      # otro tipo: no cuenta
    if meses_extra:
        filas += [("unidad", "REP2", "mes", D(2020, 6, 1), 2020, 6, "rojo", 5_000.0)]
    return pd.DataFrame(filas, columns=["entidad_tipo", "entidad_id", "granularidad", "periodo", "anio", "mes",
                                        "estado", "kg_acumulados"])


def balance(meses_extra=False):
    filas = [("GLP", 2020, m, 2_000.0) for m in range(1, 6)]
    if meses_extra:
        filas += [("GLP", 2020, 6, 50_000.0)]
    return pd.DataFrame(filas, columns=["producto", "anio", "mes", "kg_no_explicados"])


def test_unidades_en_rojo_y_kg_bajo_control(arrow):
    t = {"fact_serie": arrow.createDataFrame(serie()), "fact_balance_planta": arrow.createDataFrame(balance())}
    filas = operacion.medir("2020-05", "unidades", t)
    assert _valor(filas, "unidades_en_rojo")["valor"] == 2
    assert _valor(filas, "kg_en_rojo")["valor"] == 2_000.0
    control = _valor(filas, "kg_bajo_control")
    assert control["valor"] == pytest.approx(2_000.0 / 10_000.0) and control["denominador"] == 10_000.0
    assert _valor(filas, "tiempo_hasta_alerta_min")["valor"] is None          # sin registro de cargas: nulo con causa
    assert "cargas" in _valor(filas, "tiempo_hasta_alerta_min")["nota"]


def test_la_medida_de_un_mes_no_cambia_al_llegar_meses_posteriores(arrow):
    antes = {"fact_serie": arrow.createDataFrame(serie()), "fact_balance_planta": arrow.createDataFrame(balance())}
    despues = {"fact_serie": arrow.createDataFrame(serie(True)),
               "fact_balance_planta": arrow.createDataFrame(balance(True))}
    assert operacion.medir("2020-05", "unidades", antes) == operacion.medir("2020-05", "unidades", despues)


def modelo_factura():
    cols = ["factura_id", "anio", "mes", "fecha", "clase_s12", "etiqueta_s12", "fecha_pago", "fecha_vence",
            "monto_soles"]
    filas = [
        # descuadre real, solo en tesorería: rojo el día de su pago (retención correcta)
        ("A", 2022, 3, D(2022, 3, 5), "solo_tesoreria", 1.0, D(2022, 3, 5), None, 10_000.0),
        # kg distintos: rojo al pagar
        ("B", 2022, 3, D(2022, 3, 2), "kg_distinto", 1.0, None, D(2022, 3, 20), 8_000.0),
        # coincide, pero logística la registró después del pago: rojo innecesario
        ("C", 2022, 3, D(2022, 3, 25), "coincide", 0.0, D(2022, 3, 10), None, 5_000.0),
        # coincide y a tiempo: verde
        ("D", 2022, 3, D(2022, 3, 1), "coincide", 0.0, D(2022, 3, 15), None, 7_000.0),
        # descuadre real que llega en marzo y se paga en abril
        ("E", 2022, 3, D(2022, 3, 28), "kg_distinto", 1.0, D(2022, 4, 3), None, 4_000.0),
    ]
    return pd.DataFrame(filas, columns=cols)


def alertas():
    cols = ["id_alerta", "senal", "tipo", "fecha", "anio", "mes", "factura_id", "kg"]
    return pd.DataFrame([("a1", "S12", "modelo", D(2022, 3, 2), 2022, 3, "B", 100.0),
                         ("a2", "S12", "modelo", D(2022, 3, 1), 2022, 3, "D", 100.0),
                         ("a3", "S12", "regla", D(2022, 3, 5), 2022, 3, "A", 100.0),
                         ("a4", "S5", "regla", D(2021, 2, 10), 2021, 2, None, 3_000.0),
                         ("a5", "S10", "regla", D(2021, 2, 11), 2021, 2, None, 400.0)], columns=cols)


def test_facturas_marcadas_retenidas_e_innecesarias(arrow):
    t = {"modelo_factura": arrow.createDataFrame(modelo_factura()), "fact_alerta": arrow.createDataFrame(alertas())}
    filas = operacion.medir("2022-03", "facturas", t)
    misma = _valor(filas, "descuadres_misma_carga")                 # A y B de los tres descuadres de marzo
    assert (misma["numerador"], misma["denominador"]) == (2, 3)
    precision = _valor(filas, "precision_alertas")                  # modelo marcó B (real) y D (no)
    assert precision["valor"] == 0.5 and precision["ic_inferior"] <= 0.5 <= precision["ic_superior"]
    a_tiempo = _valor(filas, "pagos_retenidos_a_tiempo")            # A y B pagados en marzo, los dos en rojo
    assert (a_tiempo["numerador"], a_tiempo["denominador"]) == (2, 2)
    assert _valor(filas, "monto_retenido_soles")["valor"] == 23_000.0   # A + B + C
    innecesarias = _valor(filas, "retenciones_innecesarias")
    assert (innecesarias["numerador"], innecesarias["denominador"]) == (1, 3)


def test_ventas_de_clientes_revisadas(arrow):
    filas = operacion.medir("2021-02", "clientes", {"fact_alerta": arrow.createDataFrame(alertas())})
    assert _valor(filas, "ventas_revisadas")["valor"] == 2 and _valor(filas, "kg_ventas_revisadas")["valor"] == 3_400.0


def test_estabilidad_trimestral_y_esquema(arrow):
    serie_p = pd.DataFrame([operacion._fila(2022, m, "facturas", "precision_alertas", v)  # noqa: SLF001
                            for m, v in [(3, 0.70), (6, 0.76), (9, 0.74)]], columns=operacion.COLUMNAS)
    e = operacion.estabilidad_trimestral(serie_p)
    assert e["valor"].round(4).tolist() == [0.06, 0.02]
    df = operacion.a_spark(arrow, serie_p)
    assert df.columns == operacion.COLUMNAS and df.count() == 3
    assert operacion.a_spark(arrow, e).filter("medida = 'estabilidad_trimestral'").count() == 2
    assert operacion.meses_del_tramo("facturas")[0] == "2022-02" and len(operacion.meses_del_tramo("facturas")) == 18
    assert len(operacion.meses_del_tramo("unidades")) == 14
