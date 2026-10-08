"""Casos de la Tabla 3.5 (paso 3.3.1)."""
import pytest

from src.common import limpieza as L


@pytest.mark.parametrize("valor", ["T1A-123", "T1A123", "t1a 123", " T1A123 "])
def test_placa_cuatro_formas(valor):
    assert L.normalizar_placa(valor) == ("T1A123", None)


def test_placa_con_fecha():
    assert L.normalizar_placa("t1a-123 15/07/2023") == ("T1A123", "15/07/2023")


@pytest.mark.parametrize("valor", [None, "", "T1A12", "T1A-1234", float("nan")])
def test_placa_invalida(valor):
    assert L.normalizar_placa(valor)[0] is None


def test_ruc_valido_y_digito_errado():
    assert L.ruc_valido("20131312955")
    assert not L.ruc_valido("20131312954")
    assert not L.ruc_valido("2013131295")


def test_ruc_guardado_como_float():
    assert L.ruc_valido("20131312955.0")


def test_dni_con_ceros_perdidos():
    assert L.normalizar_dni(1234567) == "01234567"
    assert L.normalizar_dni("123456789") is None


@pytest.mark.parametrize("valor,clase", [("20131312955", "RUC"), ("1234567", "DNI"),
                                         ("20131312954", "INVALIDO"), ("", "VACIO"), (None, "VACIO")])
def test_clasificar_documento(valor, clase):
    assert L.clasificar_documento(valor)[1] == clase


@pytest.mark.parametrize("valor,esperado", [("5 000 kg", 5000.0), ("1,250.5", 1250.5), ("12,5", 12.5),
                                            ("1,250", 1250.0), (3000, 3000.0), ("TRUE", None),
                                            (True, None), ("abc", None)])
def test_a_kg(valor, esperado):
    assert L.a_kg(valor) == esperado


def test_estados_catalogo_cerrado():
    assert L.normalizar_estado("Atendido") == L.normalizar_estado("ATENDIDO") == "ATENDIDO"
    assert L.normalizar_estado("algo raro") == "OTRO"


def test_asiento_ajuste():
    assert L.es_asiento_ajuste(-9095, 9095)
    assert not L.es_asiento_ajuste(-100, 9095)


def test_seudonimizar_determinista_y_sin_dato():
    h = L.seudonimizar("CONDUCTOR X", sal="s")
    assert h == L.seudonimizar("conductor x ", sal="s") and len(h) == 16
    assert L.seudonimizar("CONDUCTOR X", sal="otra") != h
    assert L.seudonimizar(None, sal="s") is None


def test_a_bool():
    assert L.a_bool("Sí") is True and L.a_bool("NO") is False and L.a_bool("?") is None
