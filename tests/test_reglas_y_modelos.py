import numpy as np
import pandas as pd

from src.common import config, rutas, schemas
from src.models import base_mad
from src.quality import reglas
from src.silver_to_gold import uniones


def test_particionado_sin_alta_cardinalidad():
    """3.5.3: ninguna tabla se particiona por placa, RUC o documento."""
    assert not set(config.PARTICIONES) & set(config.COLUMNAS_ALTA_CARDINALIDAD)
    for c in schemas.CONTRATOS.values():
        if c.particionada:
            assert c.columnas()[-2:] == list(config.PARTICIONES)


def test_rutas_desde_lake_uri(monkeypatch):
    monkeypatch.setattr(config, "LAKE_URI", "s3://bucket-x")
    assert rutas.ruta("gold", "fact_alerta") == "s3://bucket-x/gold/fact_alerta"
    assert rutas.ruta_spark("silver") == "s3://bucket-x/silver"


def test_joins_anti_y_semi():
    izq = pd.DataFrame({"k": [1, 2, 3, None], "v": list("abcd")})
    der = pd.DataFrame({"k": [2, 2, 3]})
    assert list(uniones.left_anti_pd(izq, der, "k")["v"]) == ["a", "d"]
    assert list(uniones.left_semi_pd(izq, der, "k")["v"]) == ["b", "c"]  # sin duplicar por k=2 repetido


def test_tc_ultimo_habil():
    compras = pd.DataFrame({"fecha": pd.to_datetime(["2020-01-04", "2020-01-06"]).date})  # sábado, lunes
    tc = pd.DataFrame({"fecha": pd.to_datetime(["2020-01-03", "2020-01-06"]).date, "tc_oficial": [3.3, 3.4]})
    assert list(uniones.compras_con_tc_pd(compras, tc)["tc_oficial"]) == [3.3, 3.4]


def test_reglas_reporte():
    rep = reglas.Reporte("x")
    rep.registrar("fecha_coherente", reglas.fecha_coherente(pd.Series(["2015-12-01", "2020-01-01"])))
    assert rep.reglas["fecha_coherente"]["fallan"] == 1
    assert rep.reglas["fecha_coherente"]["cumple_meta"] is False


def test_z_robusto_detecta_atipico():
    rng = np.random.default_rng(0)
    x = pd.Series(np.r_[rng.normal(0.005, 0.002, 200), 0.09])
    z = base_mad.z_robusto(x)
    assert z.iloc[-1] > config.UMBRAL_Z_MAD and (z.iloc[:-1].abs() < 6).all()


def test_precision_at_k():
    p = pd.Series([0.9, 0.8, 0.1, 0.05])
    y = pd.Series([1, 0, 1, 0])
    assert base_mad.precision_at_k(p, y, k=2) == 0.5
