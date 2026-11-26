"""Parámetros del modelado, del detector y del KPI 1 (F01)."""
import importlib
from pathlib import Path

import pytest

from src.common import config

NUEVAS = ("MERMA_TECNICA_PCT", "MERMA_TECNICA_FUENTE", "MADUREZ_DIAS", "VENTANA_MEDIANA_DIAS", "PSI_UMBRAL",
          "PSI_MIN_OBS", "FALSAS_ALARMAS_ANIO", "TOL_PRECIO_PAGO", "RECALL_MIN_RETADOR")


@pytest.fixture
def recargar(monkeypatch):
    """Recarga config sin leer el .env local, para probar solo el código y las variables del test."""
    def _hacer(**valores):
        for nombre in NUEVAS:
            monkeypatch.delenv(nombre, raising=False)
        for nombre, valor in valores.items():
            monkeypatch.setenv(nombre, valor)
        with monkeypatch.context() as m:
            m.setattr(Path, "exists", lambda self: False)
            return importlib.reload(config)
    yield _hacer
    monkeypatch.undo()
    importlib.reload(config)   # deja el módulo como lo usan las demás pruebas


def test_opcional_sin_variable_es_none(monkeypatch):
    monkeypatch.delenv("PARAM_DE_PRUEBA", raising=False)
    assert config._env_float_opcional("PARAM_DE_PRUEBA") is None


def test_opcional_vacia_es_none(monkeypatch):
    monkeypatch.setenv("PARAM_DE_PRUEBA", "  ")
    assert config._env_float_opcional("PARAM_DE_PRUEBA") is None


def test_opcional_con_valor(monkeypatch):
    monkeypatch.setenv("PARAM_DE_PRUEBA", "0.01")
    assert config._env_float_opcional("PARAM_DE_PRUEBA") == 0.01


def test_merma_sin_valor_queda_nula(recargar):
    c = recargar()
    assert c.MERMA_TECNICA_PCT is None
    assert c.MERMA_TECNICA_FUENTE == ""


def test_merma_con_valor(recargar):
    assert recargar(MERMA_TECNICA_PCT="0.01").MERMA_TECNICA_PCT == 0.01


def test_valores_por_defecto(recargar):
    c = recargar()
    assert c.MADUREZ_DIAS == 30
    assert c.VENTANA_MEDIANA_DIAS == 90
    assert c.PSI_UMBRAL == 0.2
    assert c.PSI_MIN_OBS == 100
    assert c.FALSAS_ALARMAS_ANIO == 12
    assert c.TOL_PRECIO_PAGO == 0.05
    assert c.RECALL_MIN_RETADOR == 0.50


def test_env_example_declara_los_parametros():
    texto = (config.RAIZ_REPO / ".env.example").read_text(encoding="utf-8")
    for linea in ("MERMA_TECNICA_PCT=", "MADUREZ_DIAS=30", "PSI_UMBRAL=0.2", "FALSAS_ALARMAS_ANIO=12",
                  "TOL_PRECIO_PAGO=0.05"):
        assert linea in texto
