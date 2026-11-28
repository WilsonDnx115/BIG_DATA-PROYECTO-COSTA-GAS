"""Detector de desvíos persistentes (FR02): CUSUM y EWMA frente a los pares.

Flota sintética de prueba (no son datos de la empresa): 10 unidades de tamaños
distintos, 60 semanas, estacionalidad común, caída común de 30 % en la semana 10
(como la cuarentena) y ruido relativo de 1 %.
"""
import numpy as np
import pandas as pd
import pytest

from src.models import detector

H_PRUEBA = 8.0   # más alto que el inicial para que 9 unidades sanas no den falsas alarmas por azar


def flota(faltante=None, desde=20, semanas=60, semilla=11, caida_comun=True, ruido=0.01):
    rng = np.random.default_rng(semilla)
    filas = []
    for u in range(10):
        tam = 1000 * (1 + u / 5)
        for t in range(semanas):
            comun = 1 + 0.1 * np.sin(2 * np.pi * t / 52)
            if caida_comun and t >= 10:
                comun *= 0.7
            kg = tam * comun * (1 + rng.normal(0, ruido))
            if faltante is not None and u == 0 and t >= desde:
                kg *= 1 - faltante
            filas.append((f"U{u}", "reparto", t, kg))
    return pd.DataFrame(filas, columns=["unidad_id", "rol", "periodo", "kg"])


def _det(df, **kw):
    return detector.detectar(df, "unidad_id", "kg", "periodo", h=kw.pop("h", H_PRUEBA), **kw)


# --- Piezas ---------------------------------------------------------------------
def test_cusum_acumula_solo_lo_que_supera_k():
    s = detector.cusum([0, 1.5, 1.5, -3, 0.2], k=0.5)
    assert s.tolist() == pytest.approx([0, 1.0, 2.0, 0, 0])


def test_ewma_y_su_limite():
    e = detector.ewma([1, 1, 1], lam=0.2)
    assert e.tolist() == pytest.approx([0.2, 0.36, 0.488])
    assert detector.limite_ewma(0.2, 3) == pytest.approx(3 * np.sqrt(0.2 / 1.8))


def test_punto_cambio_es_el_siguiente_al_ultimo_cero():
    assert detector.punto_cambio([0, 1, 0, 2, 4, 7, 9], h=6) == 3
    assert detector.punto_cambio([0, 1, 0, 1], h=6) is None


def test_escala_robusta_sin_variacion_no_es_evaluable():
    assert detector.escala_robusta(pd.Series([0.0, 0.0, 0.0])) is None
    assert detector.escala_robusta(pd.Series([-1.0, 0.0, 1.0])) == pytest.approx(1.4826)


def test_esperado_no_mira_el_futuro():
    """Con el ajuste fijado hasta un periodo, agregar periodos posteriores no cambia lo anterior."""
    df = flota()
    a = detector.esperado_regresion(df, "unidad_id", "kg", "periodo", "rol", hasta=None)
    corto = detector.esperado_regresion(df[df.periodo <= 30], "unidad_id", "kg", "periodo", "rol")
    unir = a.merge(corto, on=["unidad_id", "periodo"], suffixes=("", "_corto"))
    assert np.allclose(unir.participacion, unir.participacion_corto, equal_nan=True)
    assert a[a.periodo < 4].participacion.isna().all()       # sin DETECTOR_PERIODOS_BASE previos
    assert a[a.periodo < 4].valor_esperado.isna().all()


# --- Comportamiento -------------------------------------------------------------
def test_faltante_sostenido_de_2_por_ciento():
    serie = _det(flota(faltante=0.02, desde=20))
    rojas = detector.alarmas(serie, "unidad_id", "periodo")
    assert set(rojas.unidad_id) == {"U0"}
    (fila,) = rojas.itertuples(index=False)
    assert fila.periodo >= 20
    assert 18 <= fila.periodo_inicio <= 22                    # inicio estimado en la semana 20 ± 2
    u0 = serie[serie.unidad_id == "U0"].sort_values("periodo")
    assert u0.kg_acumulados.iloc[-1] > 0
    primer_ambar = u0.loc[u0.estado.isin(["ambar", "rojo"]), "periodo"].min()
    assert primer_ambar <= fila.periodo                       # el EWMA avisa antes o junto con el CUSUM


def test_flota_sana_sin_alarmas():
    serie = _det(flota())
    assert (serie.estado != "rojo").all()


def test_caida_comun_no_es_desvio():
    """La cuarentena baja a todos: comparado con sus pares, nadie se desvía."""
    serie = _det(flota(caida_comun=True))
    caida = serie[(serie.periodo >= 10) & (serie.periodo <= 14)]
    assert (caida.estado.isin(["verde", "no_evaluable"])).all()


def test_par_redigitado_no_dispara_y_el_suelto_si_se_ve():
    base = flota(caida_comun=False)
    base["kg_error"] = 0.0
    hueco = 0.6 * base.loc[(base.unidad_id == "U3") & (base.periodo == 30), "kg"].item()
    for t, x in ((30, -hueco), (31, hueco)):                 # error corregido a la semana siguiente
        fila = (base.unidad_id == "U3") & (base.periodo == t)
        base.loc[fila, "kg"] += x
        base.loc[fila, "kg_error"] = x
    con_par = _det(base)
    u3 = con_par[con_par.unidad_id == "U3"]
    assert u3.redigitado.sum() == 2 and (u3.estado != "rojo").all()

    sin_correccion = base.drop(columns="kg_error")          # sin saber que fue digitación, el hueco dispara
    u3_crudo = _det(sin_correccion)
    u3_crudo = u3_crudo[u3_crudo.unidad_id == "U3"]
    assert (u3_crudo.estado == "rojo").any()
    assert u3_crudo.cusum.max() > 5 * u3.cusum.max()


def test_sin_variacion_queda_no_evaluable():
    plano = pd.DataFrame([(f"U{u}", "reparto", t, 100.0) for u in range(4) for t in range(10)],
                         columns=["unidad_id", "rol", "periodo", "kg"])
    serie = _det(plano)
    assert (serie.estado == "no_evaluable").all()


def test_columnas_para_fact_serie():
    serie = _det(flota(faltante=0.02))
    for c in ("valor_esperado", "residuo", "z", "cusum", "ewma", "estado", "periodo_inicio",
              "kg_acumulados", "soles_acumulados"):
        assert c in serie.columns
    assert set(serie.estado) <= set(detector.ESTADOS)


# --- FR03 · calibración con el escenario A ------------------------------------------
def flota_grande(unidades=50, semanas=156, semilla=5):
    rng = np.random.default_rng(semilla)
    filas = [(f"U{u}", "reparto", t, 1000 * (1 + u / 25) * (1 + 0.1 * np.sin(2 * np.pi * t / 52))
              * (1 + rng.normal(0, 0.03))) for u in range(unidades) for t in range(semanas)]
    return pd.DataFrame(filas, columns=["unidad_id", "rol", "periodo", "kg"])


def test_contar_alarmas_reinicia_tras_cada_senal():
    assert detector.contar_alarmas([2, 2, 2, 2, 2, 2], k=0.5, h=2.9) == 3   # 1.5, 3.0→señal, 1.5, 3.0→señal…
    assert detector.contar_alarmas([0.4] * 20, k=0.5, h=1.0) == 0


def test_calibrar_h_respeta_el_presupuesto_y_es_el_minimo():
    serie = flota_grande()
    cal = detector.calibrar_h(serie, "unidad_id", "kg", "periodo", "semana")
    assert cal["falsas_alarmas_anio"] <= 12 and cal["entidades"] == 50 and cal["anios"] == 3.0
    if cal["h"] > 0.5:                                   # un h un poco menor ya se pasa del presupuesto
        menos = detector.calibrar_h(serie, "unidad_id", "kg", "periodo", "semana",
                                    rejilla=[round(cal["h"] - 0.1, 4)], presupuesto=10_000)
        assert menos["falsas_alarmas_anio"] > 12


def test_mas_entidades_piden_un_umbral_mas_alto():
    """El presupuesto es del sistema: con más unidades vigiladas, cada una necesita un h mayor."""
    chica = detector.calibrar_h(flota_grande(unidades=10), "unidad_id", "kg", "periodo", "semana")
    grande = detector.calibrar_h(flota_grande(unidades=50), "unidad_id", "kg", "periodo", "semana")
    assert grande["h"] >= chica["h"]


def test_granularidad_invalida():
    with pytest.raises(ValueError):
        detector.calibrar_h(flota_grande(unidades=5), "unidad_id", "kg", "periodo", "trimestre")


def test_calibracion_con_el_escenario_a_en_semanas_y_meses():
    import inspect
    import json

    cal = detector.calibrar_con_escenario_a(semilla=42)
    json.dumps(cal)                                      # serializable para gold/_modelos/detector/umbral.json
    for g in ("semana", "mes"):
        assert cal[g]["falsas_alarmas_anio"] <= 12
        assert set(cal[g]["sigma"]) == {"reparto", "transporte"}
        assert cal[g]["h"] > 0
    assert "escenario_b" not in inspect.getsource(detector.calibrar_con_escenario_a).replace(
        "El escenario B nunca", "")                      # solo el escenario A: B mide la detección después


def test_la_escala_calibrada_se_reutiliza_al_detectar():
    serie = flota_grande(unidades=10, semanas=60)
    cal = detector.calibrar_h(serie, "unidad_id", "kg", "periodo", "semana")
    a = detector.detectar(serie, "unidad_id", "kg", "periodo", h=cal["h"], sigma=cal["sigma"])
    b = detector.desvios(serie, "unidad_id", "kg", "periodo", sigma=cal["sigma"])
    assert np.allclose(a.sort_index().z, b.sort_index().z, equal_nan=True)



# --- FR26 · valor esperado con regresión sobre los pares --------------------------------
def flota_fechas(semanas=60, semilla=13):
    """Como `flota`, con periodos semanales reales desde ene-2020 (calendario y pandemia)."""
    base = flota(semanas=semanas, semilla=semilla, caida_comun=False)
    inicio = pd.Timestamp("2020-01-06")
    base["periodo"] = [(inicio + pd.Timedelta(weeks=int(t))).date() for t in base["periodo"]]
    return base


def test_variables_de_calendario_y_pandemia():
    v = detector.variables_del_esperado(flota_fechas(), "unidad_id", "kg", "periodo", "rol")
    marzo = v[pd.to_datetime(v.periodo) == pd.Timestamp("2020-03-16")]
    enero = v[pd.to_datetime(v.periodo) == pd.Timestamp("2020-01-06")]
    assert (marzo.pandemia == 1.0).all() and (enero.pandemia == 0.0).all()
    assert v.semana_sin.between(-1, 1).all() and v.semana_cos.between(-1, 1).all()
    assert detector._columnas_regresion(v) == detector.VARIABLES_BASE


def test_sin_fechas_solo_entran_los_pares():
    v = detector.variables_del_esperado(flota(), "unidad_id", "kg", "periodo", "rol")
    assert detector._columnas_regresion(v) == ["base_pares"]


def test_el_contexto_entra_si_se_entrega():
    df = flota_fechas().assign(eventos_mercado=1.0)
    v = detector.variables_del_esperado(df, "unidad_id", "kg", "periodo", "rol")
    assert "eventos_mercado" in detector._columnas_regresion(v)


def test_numpy_y_mllib_dan_el_mismo_esperado(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    df = flota_fechas().rename(columns={"unidad_id": "entidad_id", "rol": "grupo", "kg": "valor"})
    np_ = detector.esperado_regresion(df, "entidad_id", "valor", "periodo", "grupo")
    sp = detector.esperado_mllib(spark.createDataFrame(df))
    filas = {(r["entidad_id"], str(r["periodo"])): r["valor_esperado"]
             for r in sp.select("entidad_id", "periodo", "valor_esperado").take(10_000)}
    for fila in np_.itertuples(index=False):
        esperado_sp = filas[(fila.entidad_id, str(fila.periodo))]
        if pd.isna(fila.valor_esperado):
            assert esperado_sp is None
        else:
            assert esperado_sp == pytest.approx(fila.valor_esperado, rel=1e-6)


def test_la_regresion_detecta_el_faltante_con_fechas():
    df = flota_fechas()
    df.loc[(df.unidad_id == "U0") & (pd.to_datetime(df.periodo) >= pd.Timestamp("2020-05-25")), "kg"] *= 0.98
    rojas = detector.alarmas(_det(df), "unidad_id", "periodo")
    assert set(rojas.unidad_id) == {"U0"}
