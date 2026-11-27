"""Escenario B: inyección ciega de robos (commit A17).

La prueba que pide el A17: con la especificación de prueba, el robo aparece en la serie
desde el periodo indicado. Las demás cuidan lo que hace útil a esta medición: que la
especificación real no esté en el repositorio, que una especificación rota no se aplique
a medias y que la serie quede sellada contra el archivo con el que se midió.
"""
import datetime as dt
import hashlib
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.common import config
from src.sim import escenario_a as A
from src.sim import escenario_b as B

SPEC = Path(__file__).parent / "datos" / "spec_prueba.yaml"
SEMILLA = 7


@pytest.fixture(scope="module")
def base() -> dict:
    return A.generar(SEMILLA)


@pytest.fixture(scope="module")
def inyectado(base) -> dict:
    return B.inyectar(base, SPEC)


# --- La especificación real no está aquí ----------------------------------------
def test_la_especificacion_real_no_esta_en_el_repositorio():
    """Si estuviera, la validación ciega dejaría de ser ciega."""
    sospechosos = [p for p in (config.RAIZ_REPO).rglob("*.yaml")
                   if "spec" in p.name.lower() and "escenario_b" in p.name.lower()]
    assert sospechosos == []
    assert SPEC.exists() and "prueba" in SPEC.name          # la de prueba sí, y se llama así
    assert "No son los robos reales" in SPEC.read_text(encoding="utf-8")


def test_sin_ruta_ni_variable_de_entorno_falla_claro(monkeypatch):
    """No se sigue sin robos en silencio: eso daría una detección de cero sin avisar."""
    monkeypatch.delenv(B.VARIABLE_RUTA, raising=False)
    with pytest.raises(B.EspecificacionInvalida, match=B.VARIABLE_RUTA):
        B.ruta_por_defecto()


def test_la_ruta_puede_llegar_por_la_variable_de_entorno(monkeypatch, base):
    monkeypatch.setenv(B.VARIABLE_RUTA, str(SPEC))
    assert B.inyectar(base)["spec"]["robos"] == 6


# --- Sellado --------------------------------------------------------------------
def test_la_huella_identifica_el_archivo_con_el_que_se_midio(inyectado):
    esperada = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    assert inyectado["spec"]["huella_sha256"] == esperada
    assert B.huella(SPEC) == esperada


def test_el_formato_publica_la_huella_del_archivo_sellado():
    doc = (config.RAIZ_REPO / "docs" / "modelos" / "formato_spec_b.md").read_text(encoding="utf-8")
    assert len([t for t in doc.split("`") if len(t) == 64 and all(c in "0123456789abcdef" for c in t)]) >= 1
    for tipo in B.TIPOS:
        assert f"`{tipo}`" in doc, tipo


# --- El robo aparece desde el periodo indicado -----------------------------------
def test_el_robo_aparece_desde_el_periodo_indicado(base, inyectado):
    """La prueba del A17, sobre el escalón: antes de la fecha no hay robo y desde ella sí."""
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    escalon = next(r for r in spec["robos"] if r["tipo"] == "escalon")
    desde = escalon["desde"] if isinstance(escalon["desde"], dt.date) \
        else dt.date.fromisoformat(str(escalon["desde"]))
    placa = B.resolver_entidad(escalon["entidad"], base["unidades"])

    s = inyectado["semanal"]
    de_la_unidad = s[s["placa_norm"] == placa]
    antes = de_la_unidad[de_la_unidad["fecha"] < desde]
    despues = de_la_unidad[de_la_unidad["fecha"] >= desde]

    assert antes["robado_kg"].sum() == 0
    assert (despues["robado_kg"] > 0).all()
    # el id se acumula: en 2022 esta unidad tambien recibe el robo de canal
    assert despues["robo_id"].str.contains(escalon["id"]).all()

    # y los kg de la serie bajaron justo en lo robado
    original = base["semanal"]
    orig = original[(original["placa_norm"] == placa) & (original["fecha"] >= desde)]["kg"].sum()
    assert despues["kg"].sum() + despues["robado_kg"].sum() == pytest.approx(orig, rel=1e-6)


def test_la_verdad_cubre_los_seis_tipos(inyectado):
    v = inyectado["verdad"]
    assert set(v["tipo"]) == set(B.TIPOS)
    assert v["robado_kg"].gt(0).all()
    assert v["robo_id"].nunique() == 6


def test_el_robo_a_la_sombra_solo_cae_en_semanas_con_evento(base, inyectado):
    """El tipo que el detector no contempló: se esconde detrás de un evento legítimo."""
    s = inyectado["semanal"]
    sombra = s[s["robo_id"].str.contains("P6")]
    assert len(sombra) >= 1
    assert sombra["evento"].ne("").all()


def test_el_robo_de_canal_toca_a_toda_la_flota(inyectado):
    s = inyectado["semanal"]
    canal = s[s["robo_id"].str.contains("P5")]
    assert canal["placa_norm"].nunique() == len(inyectado["unidades"])


def test_la_rampa_crece_y_los_pulsos_son_intermitentes(inyectado):
    v = inyectado["verdad"]
    rampa = v[v["tipo"] == "rampa"].sort_values("fecha")["robado_kg"].to_numpy()
    assert rampa[-1] > rampa[0] * 3

    s = inyectado["semanal"]
    pulsos = s[s["placa_norm"] == s[s["robo_id"].str.contains("P4")]["placa_norm"].iloc[0]]
    assert 0 < pulsos["robado_kg"].gt(0).sum() < len(pulsos) / 2


def test_sin_robos_la_serie_no_cambia(base, inyectado):
    """Las unidades y semanas que ningún robo toca quedan idénticas."""
    s, o = inyectado["semanal"], base["semanal"]
    limpias = s["robado_kg"] == 0
    assert s.loc[limpias, "kg"].round(6).tolist() == o.loc[limpias, "kg"].round(6).tolist()


def test_el_mensual_arrastra_lo_robado(inyectado):
    assert inyectado["mensual"]["robado_kg"].sum() == \
        pytest.approx(inyectado["semanal"]["robado_kg"].sum())


# --- Una especificación rota no se aplica a medias --------------------------------
def _escribir(tmp_path, robos) -> str:
    ruta = tmp_path / "spec.yaml"
    ruta.write_text(yaml.safe_dump({"version": 1, "robos": robos}), encoding="utf-8")
    return str(ruta)


@pytest.mark.parametrize("robo,mensaje", [
    ({"id": "X", "tipo": "escalon", "entidad": "*", "desde": "2021-01-01"}, "magnitud"),
    ({"id": "X", "tipo": "teletransporte", "entidad": "*", "desde": "2021-01-01", "magnitud": 0.1}, "tipo desconocido"),
    ({"id": "X", "tipo": "escalon", "entidad": "*", "desde": "2021-01-01", "magnitud": 1.5}, "entre 0 y 1"),
])
def test_una_especificacion_invalida_no_se_aplica(tmp_path, robo, mensaje):
    with pytest.raises(B.EspecificacionInvalida, match=mensaje):
        B.cargar_spec(_escribir(tmp_path, [robo]))


def test_un_id_repetido_se_rechaza(tmp_path):
    r = {"id": "X", "tipo": "escalon", "entidad": "*", "desde": "2021-01-01", "magnitud": 0.1}
    with pytest.raises(B.EspecificacionInvalida, match="repetido"):
        B.cargar_spec(_escribir(tmp_path, [r, dict(r)]))


def test_una_entidad_que_no_existe_en_esa_semilla_se_rechaza(tmp_path, base):
    robo = {"id": "X", "tipo": "escalon", "entidad": "reparto#99",
            "desde": "2021-01-01", "magnitud": 0.1}
    with pytest.raises(B.EspecificacionInvalida, match="solo hay"):
        B.inyectar(base, _escribir(tmp_path, [robo]))


def test_la_especificacion_sirve_con_cualquier_semilla():
    """Con 100 semillas, los selectores por rol tienen que resolver en todas."""
    for semilla in (1, 42, 777):
        r = B.inyectar(A.generar(semilla), SPEC)
        assert r["verdad"]["robo_id"].nunique() == 6
