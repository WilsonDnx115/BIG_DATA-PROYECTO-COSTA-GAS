"""Deriva de las variables del modelo con PSI (commit A15).

La prueba que pide el A15: dos muestras de la misma distribución dan PSI < 0.1, una
desplazada da PSI > 0.2, y con 50 facturas la respuesta es «insuficiente».
"""
import json

import numpy as np
import pandas as pd
import pytest

from src.common import config
from src.models import deriva

VARIABLES = ["kg", "usd_por_kg"]


@pytest.fixture()
def entrenamiento() -> pd.DataFrame:
    rng = np.random.default_rng(config.SEMILLA)
    return pd.DataFrame({"kg": rng.normal(1000, 100, 4000),
                         "usd_por_kg": rng.normal(0.60, 0.05, 4000)})


@pytest.fixture()
def cortes(entrenamiento) -> dict:
    return deriva.deciles_entrenamiento(entrenamiento, VARIABLES)


def _muestra(n, media_kg=1000, media_precio=0.60, semilla=7) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    return pd.DataFrame({"kg": rng.normal(media_kg, 100, n),
                         "usd_por_kg": rng.normal(media_precio, 0.05, n)})


# --- Cortes -------------------------------------------------------------------
def test_los_cortes_son_deciles_con_los_extremos_abiertos(cortes):
    info = cortes["kg"]
    assert len(info["cortes"]) == config.PSI_BINS + 1
    assert info["cortes"][0] == -np.inf and info["cortes"][-1] == np.inf
    assert info["n"] == 4000
    assert sum(info["esperado"]) == pytest.approx(1.0)
    assert all(p == pytest.approx(0.1, abs=0.02) for p in info["esperado"])


def test_un_valor_fuera_del_rango_del_entrenamiento_no_se_pierde(cortes):
    """Por eso los extremos son -inf y +inf: si no, el PSI ignoraría lo más raro."""
    extremos = pd.DataFrame({"kg": [-99999.0, 99999.0], "usd_por_kg": [0.6, 0.6]})
    p = deriva._proporciones(extremos["kg"], cortes["kg"]["cortes"])
    assert p.sum() == pytest.approx(1.0)
    assert p[0] == pytest.approx(0.5) and p[-1] == pytest.approx(0.5)


# --- PSI ----------------------------------------------------------------------
def test_la_misma_distribucion_queda_estable(cortes):
    r = deriva.evaluar(_muestra(4000), cortes)
    assert r["estado"] == deriva.ESTADO_OK
    assert r["psi"]["kg"] < 0.1 and r["psi"]["usd_por_kg"] < 0.1
    assert r["variables_con_deriva"] == []
    assert deriva.requiere_reentreno(r) is False


def test_una_distribucion_desplazada_pasa_el_umbral(cortes):
    r = deriva.evaluar(_muestra(4000, media_kg=1300), cortes)
    assert r["psi"]["kg"] > 0.2
    assert r["psi"]["usd_por_kg"] < 0.1          # la otra variable no se movió
    assert r["variables_con_deriva"] == ["kg"]
    assert deriva.requiere_reentreno(r) is True


def test_psi_de_una_muestra_contra_si_misma_es_cero(entrenamiento, cortes):
    valor = deriva.psi(entrenamiento["kg"], entrenamiento["kg"], cortes["kg"]["cortes"])
    assert valor == pytest.approx(0.0, abs=1e-9)


def test_psi_es_simetrico_en_la_practica(entrenamiento, cortes):
    otra = _muestra(4000, media_kg=1150)["kg"]
    ida = deriva.psi(entrenamiento["kg"], otra, cortes["kg"]["cortes"])
    vuelta = deriva.psi(otra, entrenamiento["kg"], cortes["kg"]["cortes"])
    assert ida == pytest.approx(vuelta, rel=0.05) and ida > 0


def test_un_tramo_vacio_no_rompe_el_calculo(cortes):
    """Sin el epsilon esto sería una división entre cero."""
    concentrada = pd.DataFrame({"kg": [1000.0] * 500, "usd_por_kg": [0.60] * 500})
    r = deriva.evaluar(concentrada, cortes)
    assert np.isfinite(r["psi"]["kg"]) and r["psi"]["kg"] > 0.2


# --- Mínimo de observaciones ---------------------------------------------------
def test_con_cincuenta_facturas_responde_insuficiente(cortes):
    r = deriva.evaluar(_muestra(50), cortes)
    assert r["estado"] == deriva.ESTADO_INSUFICIENTE
    assert r["n"] == 50 and r["minimo"] == config.PSI_MIN_OBS
    assert "psi" not in r                        # no se publica un número que no sostiene nada


def test_insuficiente_no_dispara_reentreno(cortes):
    """No saber si hay deriva no es lo mismo que saber que la hay."""
    assert deriva.requiere_reentreno(deriva.evaluar(_muestra(50), cortes)) is False


def test_justo_en_el_minimo_ya_se_calcula(cortes):
    r = deriva.evaluar(_muestra(config.PSI_MIN_OBS), cortes)
    assert r["estado"] == deriva.ESTADO_OK and "kg" in r["psi"]


# --- Casos sucios --------------------------------------------------------------
def test_una_variable_sin_cortes_se_informa_y_no_se_inventa():
    cortes = {"kg": {"cortes": [], "esperado": [], "n": 0}}
    r = deriva.evaluar(_muestra(500), cortes)
    assert r["psi"] == {} and r["variables_sin_cortes"] == ["kg"]
    assert deriva.requiere_reentreno(r) is False


def test_los_nulos_y_los_infinitos_se_descartan(cortes):
    sucia = _muestra(500)
    sucia.loc[:20, "kg"] = np.nan
    sucia.loc[21:30, "kg"] = np.inf
    r = deriva.evaluar(sucia, cortes)
    assert np.isfinite(r["psi"]["kg"])


# --- Guardar los cortes con el modelo (commit AR08) ---------------------------
def test_ida_y_vuelta_sin_perdida(cortes):
    """Los cortes se guardan con el modelo (FR13): lo que vuelve es lo que se guardo."""
    recuperados = deriva.desde_dict(json.loads(json.dumps(deriva.a_dict(cortes))))
    assert set(recuperados) == set(cortes)
    for var, info in cortes.items():
        assert recuperados[var]["cortes"] == pytest.approx(info["cortes"])
        assert recuperados[var]["esperado"] == pytest.approx(info["esperado"])
        assert recuperados[var]["n"] == info["n"]


def test_el_json_guardado_es_json_estricto(cortes):
    """`Infinity` es JSON invalido: lo relee Python y lo rechaza cualquier otro lector."""
    texto = json.dumps(deriva.a_dict(cortes))
    assert "Infinity" not in texto and "NaN" not in texto
    json.loads(texto, parse_constant=lambda c: (_ for _ in ()).throw(
        AssertionError(f"constante no estandar en el JSON: {c}")))
    assert deriva.a_dict(cortes)["kg"]["cortes"][0] is None       # tramo abierto por abajo
    assert deriva.a_dict(cortes)["kg"]["cortes"][-1] is None      # y por arriba


def test_el_psi_sale_igual_despues_de_guardar_y_leer(cortes):
    """Lo que importa de la ida y vuelta: el PSI no cambia por haber pasado por disco."""
    nuevas = _muestra(4000, media_kg=1300)
    antes = deriva.evaluar(nuevas, cortes)
    despues = deriva.evaluar(nuevas, deriva.desde_dict(deriva.a_dict(cortes)))
    assert despues["psi"] == antes["psi"]
    assert despues["variables_con_deriva"] == antes["variables_con_deriva"]


def test_los_tipos_guardados_son_nativos(cortes):
    """Un np.float64 suelto rompe la serializacion mas adelante y cuesta de encontrar."""
    guardado = deriva.a_dict(cortes)["kg"]
    assert isinstance(guardado["n"], int)
    assert all(isinstance(p, float) for p in guardado["esperado"])
    assert all(b is None or isinstance(b, float) for b in guardado["cortes"])


def test_una_variable_sin_cortes_tambien_va_y_vuelve():
    vacia = {"kg": {"cortes": [], "esperado": [], "n": 0}}
    assert deriva.desde_dict(deriva.a_dict(vacia)) == vacia


def test_un_borde_nulo_en_el_medio_se_rechaza():
    """Con un borde perdido el PSI daria un numero que parece bueno y no lo es."""
    corrupto = {"kg": {"cortes": [None, 1.0, None, 3.0, None], "esperado": [0.25] * 4, "n": 10}}
    with pytest.raises(ValueError, match="no es un extremo"):
        deriva.desde_dict(corrupto)
