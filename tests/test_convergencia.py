"""Convergencia de señales y riesgo de sustracción (FR11). Datos de prueba sintéticos."""
import numpy as np
import pandas as pd
import pytest

from src.models import convergencia


def _alertas():
    return pd.DataFrame([
        # proveedor PETROPERU, mar-2022: S12 (alto) + S3 (medio) → converge, puntaje 5
        {"senal": "S12", "factura_id": "PETROPERU|F001|1", "unidad_id": "ABC123", "anio": 2022, "mes": 3, "grado_evidencia": "alto"},
        {"senal": "S3", "factura_id": "PETROPERU|F001|2", "unidad_id": "ABC123", "anio": 2022, "mes": 3, "grado_evidencia": "medio"},
        # S12 repetida en el mismo mes: la fuente cuenta una sola vez
        {"senal": "S12", "factura_id": "PETROPERU|F001|3", "unidad_id": "ABC123", "anio": 2022, "mes": 3, "grado_evidencia": "alto"},
        # SOLGAS, abr-2022: una sola fuente → no converge
        {"senal": "S2", "factura_id": "SOLGAS|F002|9", "unidad_id": None, "anio": 2022, "mes": 4, "grado_evidencia": "alto"},
        # fuera de la ventana de proveedor (2020): no cuenta
        {"senal": "S12", "factura_id": "SOLGAS|F002|5", "unidad_id": None, "anio": 2020, "mes": 5, "grado_evidencia": "alto"},
        {"senal": "S3", "factura_id": "SOLGAS|F002|6", "unidad_id": None, "anio": 2020, "mes": 5, "grado_evidencia": "medio"},
        # unidad REP1, may-2020: S9 (medio) + S7 (indicio)
        {"senal": "S9", "factura_id": None, "unidad_id": "REP1", "anio": 2020, "mes": 5, "grado_evidencia": "medio"},
        {"senal": "S7", "factura_id": None, "unidad_id": "REP1", "anio": 2020, "mes": 5, "grado_evidencia": "indicio"},
    ])


def test_regla_de_convergencia_y_puntaje():
    r = convergencia.puntaje_convergencia(convergencia.desde_alertas(_alertas()))
    fila = lambda g, e, a, m: r[(r.grupo == g) & (r.entidad_id == e) & (r.anio == a) & (r.mes == m)].iloc[0]  # noqa: E731
    petro = fila("proveedor", "PETROPERU", 2022, 3)
    assert (petro.puntaje_convergencia, petro.n_fuentes, petro.etiqueta_probable) == (5.0, 2, 1)
    assert petro.fuentes == "S12,S3"
    assert fila("proveedor", "SOLGAS", 2022, 4).etiqueta_probable == 0
    assert not ((r.entidad_id == "SOLGAS") & (r.anio == 2020)).any()        # fuera de la ventana
    rep = fila("unidad", "REP1", 2020, 5)
    assert (rep.puntaje_convergencia, rep.etiqueta_probable) == (3.0, 1)


def test_cusum_y_rareza_suman_como_evidencia_estadistica():
    serie = pd.DataFrame({"entidad_tipo": ["unidad", "unidad"], "entidad_id": ["REP2", "REP3"],
                          "anio": [2020, 2020], "mes": [6, 6], "estado": ["rojo", "verde"]})
    um = pd.DataFrame({"unidad_id": [f"U{i}" for i in range(50)] + ["REP2"], "anio": 2020, "mes": 6,
                       "puntaje_rareza": list(np.linspace(0, 1, 50)) + [5.0]})
    ev = pd.concat([convergencia.desde_detector(serie), convergencia.desde_rareza(um)], ignore_index=True)
    r = convergencia.puntaje_convergencia(ev)
    rep2 = r[r.entidad_id == "REP2"].iloc[0]
    assert rep2.fuentes == "CUSUM,IF" and rep2.puntaje_convergencia == 4.0 and rep2.etiqueta_probable == 1
    assert "REP3" not in set(r.entidad_id)


def test_el_riesgo_no_puede_usar_senales():
    with pytest.raises(ValueError):
        convergencia.validar_contexto(["kg", "n_senales"])
    with pytest.raises(ValueError):
        convergencia.validar_contexto(["kg", "S9"])
    with pytest.raises(ValueError):
        convergencia.validar_contexto(["kg", "z"])
    convergencia.validar_contexto(["kg", "documentos", "clientes_atendidos", "proveedor_id", "mes", "zona"])


def test_riesgo_rf_con_contexto(spark):
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    rng = np.random.default_rng(3)
    n = 200
    kg = rng.uniform(1_000, 50_000, n)
    datos = pd.DataFrame({"kg": kg, "documentos": rng.integers(1, 40, n).astype(float),
                          "proveedor_id": rng.choice(["P1", "P2"], n), "mes": rng.integers(1, 13, n).astype(float),
                          "etiqueta_probable": (kg > 40_000).astype(int)})
    modelo = convergencia.riesgo_rf(spark.createDataFrame(datos), ["kg", "documentos", "proveedor_id", "mes"])
    importancias = modelo.stages[-1].featureImportances.toArray()
    assert importancias[0] == importancias.max()          # aprende del volumen, que es lo que marca la etiqueta
    puntuado = modelo.transform(spark.createDataFrame(datos.drop(columns="etiqueta_probable")))
    assert "probabilidad_riesgo" in puntuado.columns
