"""Entrenamiento con registro y cortes de deriva (FR13). Facturas sintéticas de prueba."""
import numpy as np
import pandas as pd
import pytest

from src.models import entrenamiento, registro


def facturas(por_mes=40, semilla=4):
    """feb-2022 a jul-2023; la etiqueta depende del sobreprecio; madura a los 60 días."""
    rng = np.random.default_rng(semilla)
    filas = []
    for m in range(18):
        anio, mes = 2022 + (m + 1) // 12, (m + 1) % 12 + 1
        for i in range(por_mes):
            fecha = pd.Timestamp(anio, mes, 1) + pd.Timedelta(days=int(rng.integers(0, 28)))
            sobre = rng.normal(0, 0.04)
            filas.append({"factura_id": f"{anio}{mes:02d}-{i}", "proveedor_id": rng.choice(["P1", "P2"]),
                          "fecha": fecha.date(), "anio": anio, "mes": mes, "kg": float(rng.uniform(5e3, 3e4)),
                          "usd_kg_vs_mediana": sobre, "desvio_tc": abs(rng.normal(0, 0.005)),
                          "flag_scop_duplicado": int(rng.integers(0, 2)), "ratio_carga_capacidad": np.nan,
                          "etiqueta_s12": float(sobre > 0.04),
                          "fecha_madurez": (fecha + pd.Timedelta(days=60)).date(), "madura": True})
    return pd.DataFrame(filas)


@pytest.fixture()
def datos(spark, monkeypatch):
    from src.common import config

    monkeypatch.setattr(config, "RF_ARBOLES", 10)          # solo para que la prueba corra rápido
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")
    spark.conf.set("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
    return spark.createDataFrame(facturas())


class ModeloFalso:
    """Se serializa con pickle en el registro, como un modelo de scikit-learn."""


def test_particion_valida_con_los_dos_meses_maduros_mas_recientes(datos):
    entreno, validacion = entrenamiento.particion(datos, "2023-01-01")
    # Antes del 1-ene-2023 maduran las facturas de hasta el 1-nov-2022 (+60 días = 31-dic):
    # noviembre ya tiene etiquetas maduras, así que validan octubre y noviembre.
    meses_val = sorted({(r["anio"], r["mes"]) for r in validacion.select("anio", "mes").distinct().take(20)})
    assert meses_val == [(2022, 10), (2022, 11)]
    assert entreno.filter("fecha >= DATE'2022-10-01'").count() == 0
    assert validacion.filter("fecha_madurez >= DATE'2023-01-01'").count() == 0
    assert entrenamiento.particion(datos, "2022-05-01") is None          # aún no hay tres meses maduros


def test_entrenar_deja_umbral_metricas_y_cortes(datos):
    r = entrenamiento.entrenar(datos, "2023-01-01")
    assert r["estado"] == "entrenado" and 0 < r["umbral"] <= 1
    m = r["metricas"]
    assert m["n_validacion"] > 0 and m["n_entrenamiento"] > m["n_validacion"]
    assert 0 <= m["pr_auc"] <= 1 and m["precision"] is not None
    assert set(m["cortes_deriva"]) == set(entrenamiento.VARIABLES_DERIVA)
    assert m["cortes_deriva"]["ratio_carga_capacidad"]["n"] == 0          # sin capacidad conocida: sin cortes


def test_retador_con_recall_bajo_no_se_promueve_y_sus_cortes_quedan(lago, datos, monkeypatch):
    cortes = {"kg": {"cortes": [-np.inf, 10_000.0, np.inf], "esperado": [0.5, 0.5], "n": 100}}

    def fijo(precision, recall):
        return lambda *_a, **_k: {"estado": "entrenado", "modelo": ModeloFalso(), "umbral": 0.4,
                                  "metricas": {"precision": precision, "recall": recall, "umbral": 0.4,
                                               "cortes_deriva": cortes}}

    monkeypatch.setattr(entrenamiento, "entrenar", fijo(0.72, 0.60))
    primero = entrenamiento.entrenar_y_registrar(datos, "2023-01-01")
    assert primero["promovido"] is True

    monkeypatch.setattr(entrenamiento, "entrenar", fijo(0.90, 0.40))      # más preciso, recall 0.4
    retador = entrenamiento.entrenar_y_registrar(datos, "2023-02-01")
    assert retador["promovido"] is False
    assert registro.vigente()["version"] == "s12-2023-01-01"
    assert retador["ficha"]["metricas"]["cortes_deriva"]["kg"]["cortes"][1] == 10_000.0
    assert registro.vigente()["metricas"]["cortes_deriva"] == primero["ficha"]["metricas"]["cortes_deriva"]


def test_deriva_de_las_facturas_nuevas_con_los_cortes_del_vigente():
    rng = np.random.default_rng(1)
    entreno = pd.DataFrame({"kg": rng.uniform(5e3, 3e4, 500)})
    from src.models import deriva

    ficha = {"metricas": {"cortes_deriva": deriva.deciles_entrenamiento(entreno, ["kg"])}}
    iguales = entrenamiento.deriva_de_nuevas(pd.DataFrame({"kg": rng.uniform(5e3, 3e4, 200)}), ficha)
    corridas = entrenamiento.deriva_de_nuevas(pd.DataFrame({"kg": rng.uniform(2.5e4, 6e4, 200)}), ficha)
    assert iguales["requiere_reentreno"] is False and corridas["requiere_reentreno"] is True
    pocas = entrenamiento.deriva_de_nuevas(pd.DataFrame({"kg": [1.0] * 10}), ficha)
    assert pocas["estado"] == "insuficiente" and pocas["requiere_reentreno"] is False
