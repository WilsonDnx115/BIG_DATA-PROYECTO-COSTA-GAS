"""Escenario A: operación sin robos (commit A16).

Las dos pruebas que pide el A16: la misma semilla da el mismo resultado, y ningún
identificador coincide con los de `data/sample`. Las demás comprueban que la serie
está calibrada con los agregados publicados de 2020 y que trae lo que el detector
tiene que aguantar sin confundirlo con un robo.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from src.common import config
from src.sim import escenario_a as E

GRANOS = ("semanal", "mensual", "eventos", "unidades")
RE_PLACA = re.compile(r"\b[A-Z]\d[A-Z]\d{3}\b")


@pytest.fixture(scope="module")
def datos() -> dict:
    return E.generar(config.SEMILLA)


# --- Reproducibilidad ----------------------------------------------------------
def test_la_misma_semilla_da_el_mismo_resultado():
    """Si no es reproducible, el umbral que se calibre con esta serie no se puede defender."""
    a, b = E.generar(123), E.generar(123)
    for grano in GRANOS:
        pd.testing.assert_frame_equal(a[grano], b[grano])


def test_otra_semilla_da_otra_serie():
    a, b = E.generar(123), E.generar(456)
    assert not a["semanal"]["kg"].equals(b["semanal"]["kg"])
    assert a["semilla"] == 123 and b["semilla"] == 456


# --- Identificadores -----------------------------------------------------------
def _placas_de_la_muestra() -> set[str]:
    raiz = config.RAIZ_REPO / "data" / "sample"
    if not raiz.exists():
        pytest.skip("no hay muestra: correr `python -m src.common.muestra`")
    encontradas: set[str] = set()
    for p in raiz.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".csv", ".json"}:
            encontradas |= set(RE_PLACA.findall(p.read_text(encoding="utf-8", errors="ignore").upper()))
    return encontradas


def test_ningun_identificador_coincide_con_la_muestra(datos):
    simuladas = set(datos["unidades"]["placa_norm"])
    assert simuladas & _placas_de_la_muestra() == set()


def test_el_alfabeto_de_placas_es_disjunto_del_de_la_muestra(datos):
    """No es casualidad: los dos alfabetos no comparten ninguna letra, así que
    la colisión es imposible por construcción y no depende de la semilla."""
    from src.common import muestra  # noqa: PLC0415

    letras_muestra = set(re.search(r'letras = "([A-Z]+)"', Path(muestra.__file__)
                                   .read_text(encoding="utf-8")).group(1))
    assert set(E.LETRAS_SIM) & letras_muestra == set()
    assert all(set(p[0] + p[2]) <= set(E.LETRAS_SIM) for p in datos["unidades"]["placa_norm"])


def test_no_hay_ningun_dato_de_persona(datos):
    for grano in GRANOS:
        columnas = " ".join(datos[grano].columns).lower()
        for palabra in ("nombre", "dni", "ruc", "conductor", "vendedor", "apellido"):
            assert palabra not in columnas, f"{grano}.{palabra}"


# --- Calibración con los agregados de 2020 --------------------------------------
def test_el_envasado_de_2020_cuadra_con_los_cinco_millones(datos):
    s = datos["semanal"]
    kg = s[(s["anio"] == 2020) & (s["rol"] == "reparto")]["kg"].sum()
    assert kg == pytest.approx(E.KG_ENVASADO_2020, rel=0.02)


def test_la_correlacion_con_el_combustible_es_la_medida(datos):
    """0.66 es lo que se midió en 2020. Si saliera 0.95 la simulación sería demasiado fácil."""
    m = datos["mensual"]
    rho = m[m["rol"] == "reparto"][["kg", "combustible"]].corr(method="spearman").iloc[0, 1]
    assert rho == pytest.approx(E.SPEARMAN_OBJETIVO, abs=0.08)


def test_la_merma_es_el_supuesto_declarado(datos):
    s = datos["semanal"]
    assert (s["merma_kg"] / s["kg"]).round(6).nunique() == 1
    assert s["merma_kg"].sum() / s["kg"].sum() == pytest.approx(config.MERMA_TECNICA_PCT)
    assert (s["kg_despachado"] > s["kg"]).all()


def test_la_flota_tiene_las_nueve_unidades_de_reparto(datos):
    assert (datos["unidades"]["rol"] == "reparto").sum() == E.UNIDADES_REPARTO
    assert datos["unidades"]["placa_norm"].is_unique


# --- Lo que el detector tiene que tolerar ----------------------------------------
def test_la_serie_cubre_2020_a_2022_en_los_dos_granos(datos):
    assert sorted(datos["semanal"]["anio"].unique()) == [2020, 2021, 2022]
    assert len(datos["mensual"]) == len(datos["unidades"]) * 36


def test_hay_estacionalidad_de_invierno(datos):
    """En la costa norte el consumo sube en invierno; el detector no debe leerlo como desvío."""
    m = datos["mensual"]
    por_mes = m.groupby("mes")["kg"].sum()
    assert por_mes.loc[[6, 7, 8]].mean() > por_mes.loc[[1, 2, 12]].mean()


def test_la_pandemia_hunde_el_segundo_trimestre_de_2020(datos):
    """La magnitud es un supuesto declarado (CAIDA_PANDEMIA), no una medicion: el
    diccionario v3.0 no publica el perfil mensual de 2020. Lo que se fija aqui es que
    el efecto exista, empiece en la cuarentena y se recupere."""
    import datetime as dt  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    fechas = np.array([E.CUARENTENA - dt.timedelta(days=7), E.CUARENTENA,
                       E.CUARENTENA + dt.timedelta(days=364)])
    antes, golpe, un_anio_despues = E._pandemia(fechas)
    assert antes == 1.0
    assert golpe == pytest.approx(1 - E.CAIDA_PANDEMIA)
    assert un_anio_despues > 0.98

    m = datos["mensual"]
    enero_febrero = m[(m["anio"] == 2020) & (m["mes"] <= 2)]["kg"].sum() / 2
    abril_mayo = m[(m["anio"] == 2020) & (m["mes"].isin([4, 5]))]["kg"].sum() / 2
    assert abril_mayo < enero_febrero


def test_hay_quince_eventos_legitimos_con_su_motivo(datos):
    e = datos["eventos"]
    assert len(e) == E.N_EVENTOS_LEGITIMOS
    assert e["motivo"].str.len().gt(0).all() and e["evento_id"].is_unique
    assert datos["semanal"]["evento"].ne("").sum() >= 1


def test_hay_errores_de_digitacion_corregidos_y_sin_corregir(datos):
    conteo = datos["semanal"]["error_digitacion"].value_counts()
    assert conteo.get("corregido", 0) == conteo.get("correccion", 0) > 0
    assert conteo.get("sin_corregir", 0) == E.N_REDIGITADOS_SIN_CORREGIR


def test_los_pares_corregidos_los_compensa_el_a14(datos):
    """El A14 neutraliza justo los pares que el A16 inyecta, y no toca los sueltos.

    Se compensa sobre `kg_error`, el desvio con signo, no sobre los kg absolutos: cada
    semana parte de una base distinta, asi que +X y -X solo se cancelan en el desvio.
    """
    from src.quality.redigitados import compensar  # noqa: PLC0415

    s = datos["semanal"]
    pares = int(s["error_digitacion"].eq("corregido").sum())
    assert s[s["error_digitacion"].isin(["corregido", "correccion"])]["kg_error"].sum()         == pytest.approx(0.0)

    c = compensar(s, entidad="placa_norm", valor="kg_error", periodo="fecha", ventana=1)
    assert int(c["redigitado"].sum()) == pares * 2            # las dos filas de cada par
    sueltos = c[c["error_digitacion"] == "sin_corregir"]
    assert not sueltos["redigitado"].any()                    # lo no corregido sigue visible
    assert (sueltos["kg_error_compensado"] > 0).all()


# --- Dónde se puede escribir -----------------------------------------------------
def test_la_simulacion_no_se_puede_escribir_en_silver_ni_en_gold(datos, tmp_path):
    for prohibido in (f"{tmp_path}/silver/sim", f"{tmp_path}/lake/gold/sim"):
        with pytest.raises(ValueError, match="Silver ni en Gold"):
            E.escribir(datos, prohibido)


def test_la_simulacion_se_escribe_en_sim(datos, tmp_path):
    escritos = E.escribir(datos, f"{tmp_path}/lake/sim/escenario_a")
    assert len(escritos) == 4 and all(Path(p).exists() for p in escritos)
