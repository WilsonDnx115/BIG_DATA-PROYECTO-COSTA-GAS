"""Validacion del detector con escenarios A y B (commit AR06).

La prueba que pide el AR06: con 2 semillas, el JSON del lote trae todas las claves de
la Tabla 4.8h. Alrededor de eso se protege lo que hace valida la medicion: que el
umbral se fije con el escenario A y que el escenario B no lo vuelva a tocar.

Se usa la especificacion de prueba (`tests/datos/spec_prueba.yaml`), nunca la real: la
real no esta en el repositorio y no debe estarlo.
"""
from __future__ import annotations

import json
import pathlib
from pathlib import Path

import pytest

from src.common import config
from src.models import detector
from src.sim import escenario_a
from src.sim import validacion as V

SPEC = Path(__file__).parent / "datos" / "spec_prueba.yaml"
SEMILLAS = [7, 8]


@pytest.fixture(scope="module")
def lote(tmp_path_factory) -> dict:
    """Un lote de verdad, con 2 semillas, escrito en un destino temporal."""
    destino = tmp_path_factory.mktemp("resultados").as_posix()
    return V.ejecutar_lote(1, semillas=SEMILLAS, ruta_spec=SPEC, destino=destino)


# --- Lo que pide el AR06: el JSON trae las claves de la Tabla 4.8h -------------
CLAVES_RESUMEN = ("semillas", "falsas_alarmas_anio_max", "falsas_alarmas_anio_mediana",
                  "h_mediana", "eventos_legitimos_en_alerta_pct_mediana",
                  "errores_digitacion_en_alerta_pct_mediana",
                  "deteccion_faltantes_2pct_mediana", "semanas_hasta_alarma_mediana",
                  "error_semana_inicio_mediana", "error_relativo_kg_mediana",
                  "error_relativo_soles_mediana", "metas", "cumple")


def test_el_json_del_lote_trae_todas_las_claves_de_la_tabla(lote):
    assert set(CLAVES_RESUMEN) <= set(lote["resumen"])
    assert set(V.METAS) == set(lote["resumen"]["cumple"])
    assert lote["resumen"]["metas"] == V.METAS
    assert lote["resumen"]["semillas"] == 2


def test_el_lote_queda_escrito_y_se_puede_releer(lote):
    guardado = json.loads(Path(lote["ruta"]).read_text(encoding="utf-8"))
    assert guardado["lote"] == 1 and guardado["semillas"] == SEMILLAS
    assert set(CLAVES_RESUMEN) <= set(guardado["resumen"])
    assert guardado["fuente_metas"] == "informe v16, Tabla 4.8h"
    assert len(guardado["por_semilla"]) == 2


def test_cada_semilla_mide_los_dos_escenarios(lote):
    for medida in lote["por_semilla"]:
        a, b = medida["escenario_a"], medida["escenario_b"]
        assert a["h"]["semana"] > 0 and a["h"]["mes"] > 0
        assert a["falsas_alarmas_anio"]["semana"] <= config.FALSAS_ALARMAS_ANIO
        assert a["falsas_alarmas_anio"]["mes"] <= config.FALSAS_ALARMAS_ANIO
        assert b["robos_inyectados"] == 6                  # los de la spec de prueba
        assert b["robos_comparables"] >= 1


def test_cada_cifra_va_con_su_meta_y_no_solo_con_el_veredicto(lote):
    """Un «cumple: true» suelto no se puede revisar; el JSON guarda las dos cifras."""
    resumen = lote["resumen"]
    for clave, meta in resumen["metas"].items():
        assert isinstance(meta, (int, float))
        assert clave in resumen["cumple"]
    assert resumen["cumple"]["falsas_alarmas_anio"] is True


# --- Lo que hace valida la medicion -------------------------------------------
def test_el_umbral_sale_solo_del_escenario_a(lote):
    """Si el umbral se recalibrara con B, la deteccion medida no valdria nada."""
    for medida, semilla in zip(lote["por_semilla"], SEMILLAS):
        esperado = detector.calibrar_h(escenario_a.generar(semilla)["semanal"],
                                       V.ENTIDAD, V.VALOR, V.PERIODO, "semana")
        assert medida["escenario_a"]["h"]["semana"] == esperado["h"]


def test_el_retardo_nunca_es_negativo(lote):
    """Una alarma anterior al robo no es deteccion: es una falsa alarma del escenario A."""
    for medida in lote["por_semilla"]:
        for robo in medida["escenario_b"]["robos"]:
            if robo["semanas_hasta_alarma"] is not None:
                assert robo["semanas_hasta_alarma"] >= 0
            for detalle in robo["por_entidad"]:
                if detalle["semanas_hasta_alarma"] is not None:
                    assert detalle["semanas_hasta_alarma"] >= 0


def test_el_robo_que_toca_a_toda_la_flota_no_entra_al_denominador(lote):
    """Comparando unidades entre si no se puede ver; lo ve el balance de planta (KPI 1)."""
    for medida in lote["por_semilla"]:
        b = medida["escenario_b"]
        assert b["robos_no_detectables_por_diseno"]        # la spec de prueba trae uno
        assert b["robos_comparables"] < b["robos_inyectados"]
        for robo in b["robos"]:
            if robo["robo_id"] in b["robos_no_detectables_por_diseno"]:
                assert robo["entidades"] > 1


def test_la_huella_de_la_especificacion_queda_en_el_resultado(lote):
    """Despues se tiene que poder demostrar contra que archivo se midio (AR19)."""
    import hashlib                                          # noqa: PLC0415

    esperada = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    for medida in lote["por_semilla"]:
        assert medida["spec"]["huella_sha256"] == esperada


def test_los_kg_se_comparan_en_la_misma_ventana(lote):
    """Lo acumulado hasta la alarma contra lo robado hasta esa misma semana."""
    comparados = 0
    for medida in lote["por_semilla"]:
        for robo in medida["escenario_b"]["robos"]:
            for d in robo["por_entidad"]:
                if not d["entidad_detectada"]:
                    continue
                assert d["kg_inyectados_hasta_la_alarma"] <= d["kg_inyectados_total"] + 1e-6
                assert d["kg_estimados"] is not None
                comparados += 1
    assert comparados > 0


# --- Semillas y lotes ----------------------------------------------------------
def test_las_semillas_de_un_lote_son_reproducibles():
    assert V.semillas_del_lote(1) == V.semillas_del_lote(1)
    assert len(V.semillas_del_lote(1)) == V.TAMANO_LOTE
    assert V.semillas_del_lote(2)[0] == V.semillas_del_lote(1)[-1] + 1


def test_los_diez_lotes_dan_cien_semillas_distintas():
    todas = [s for n in range(1, 11) for s in V.semillas_del_lote(n)]
    assert len(todas) == V.SEMILLAS_TOTALES == len(set(todas))


def test_el_lote_cero_no_existe():
    with pytest.raises(ValueError, match="desde 1"):
        V.semillas_del_lote(0)


def test_la_ruta_del_lote_va_al_prefijo_de_simulacion():
    assert V.ruta_lote(3).endswith("sim/resultados/lote=3.json")
    for capa in ("/silver/", "/gold/"):
        assert capa not in V.ruta_lote(3)


def test_sin_especificacion_no_se_mide_un_escenario_sin_robos(monkeypatch):
    """Seguir sin robos daria una deteccion de cero sin avisar de nada."""
    from src.sim import escenario_b                          # noqa: PLC0415

    monkeypatch.delenv(escenario_b.VARIABLE_RUTA, raising=False)
    with pytest.raises(escenario_b.EspecificacionInvalida):
        V.medir_semilla(7, ruta_spec=None)


# --- W19: el punto de entrada en Lambda ---------------------------------------
# `lambda_handler` no mide nada por su cuenta: parte el trabajo en lotes y baja
# la especificacion sellada. Lo que se prueba es eso, no la medicion, que ya
# esta cubierta arriba con la especificacion de prueba.

class _S3Falso:
    """Lo minimo del cliente de S3 que usa `descargar_spec`."""

    def __init__(self, claves):
        self.claves = list(claves)
        self.bajados = []

    def list_objects_v2(self, Bucket, Prefix):          # noqa: N803 - firma de boto3
        self.prefijo = Prefix
        return {"Contents": [{"Key": k} for k in self.claves]}

    def download_file(self, bucket, clave, destino):
        self.bajados.append((bucket, clave, destino))
        pathlib.Path(destino).write_text("escenario: sellado\n", encoding="utf-8")


def _falsear_boto3(monkeypatch, s3):
    import sys                                             # noqa: PLC0415
    import types                                            # noqa: PLC0415

    modulo = types.ModuleType("boto3")
    modulo.client = lambda servicio, *a, **k: s3
    monkeypatch.setitem(sys.modules, "boto3", modulo)
    return s3


def test_el_handler_corre_el_lote_que_pide_el_evento(monkeypatch):
    vistos = {}

    def falso(numero, ruta_spec=None, tamano=None, **extra):
        vistos.update(numero=numero, ruta_spec=ruta_spec, tamano=tamano)
        return {"lote": numero, "semillas": [1], "ruta": "s3://x/sim/resultados/lote=3.json",
                "resumen": {"cumple": True}, "por_semilla": [{"semilla": 1}]}

    monkeypatch.setattr(V, "ejecutar_lote", falso)
    salida = V.lambda_handler({"lote": "3", "tamano": "2", "spec": str(SPEC)})

    assert vistos == {"numero": 3, "ruta_spec": str(SPEC), "tamano": 2}
    assert salida["lote"] == 3


def test_el_handler_devuelve_el_resumen_y_no_el_detalle_por_semilla(monkeypatch):
    """El detalle queda en el JSON del lote: en la respuesta solo abulta el log."""
    monkeypatch.setattr(V, "ejecutar_lote", lambda *a, **k: {
        "lote": 1, "semillas": [1], "ruta": "r", "resumen": {"cumple": True},
        "por_semilla": [{"semilla": 1, "robos": "donde estan"}]})

    salida = V.lambda_handler({"spec": str(SPEC)})

    assert set(salida) == {"lote", "semillas", "ruta", "resumen"}


def test_un_evento_vacio_corre_el_primer_lote_completo(monkeypatch):
    vistos = {}
    monkeypatch.setattr(V, "ejecutar_lote", lambda numero, **k: vistos.update(
        numero=numero, **k) or {"lote": numero, "semillas": [], "ruta": "r", "resumen": {}})
    monkeypatch.setattr(V, "descargar_spec", lambda: "/tmp/spec.yaml")       # noqa: S108

    V.lambda_handler({})

    assert vistos["numero"] == 1 and vistos["tamano"] == V.TAMANO_LOTE


def test_la_especificacion_se_baja_de_sim_spec_y_de_ningun_otro_prefijo(monkeypatch, tmp_path):
    s3 = _falsear_boto3(monkeypatch, _S3Falso(["sim/_spec/escenario_b.yaml"]))
    destino = tmp_path / "spec.yaml"

    ruta = V.descargar_spec(str(destino), lake_uri="s3://lago-de-prueba")

    assert s3.prefijo == "sim/_spec/"
    assert s3.bajados == [("lago-de-prueba", "sim/_spec/escenario_b.yaml", str(destino))]
    assert ruta == str(destino) and destino.exists()


def test_con_dos_especificaciones_no_se_adivina_la_vigente(monkeypatch, tmp_path):
    """La huella SHA-256 sella la medicion: elegir una al azar la invalida."""
    from src.sim import escenario_b                          # noqa: PLC0415

    _falsear_boto3(monkeypatch, _S3Falso(["sim/_spec/v1.yaml", "sim/_spec/v2.yaml"]))

    with pytest.raises(escenario_b.EspecificacionInvalida, match="exactamente una"):
        V.descargar_spec(str(tmp_path / "spec.yaml"), lake_uri="s3://lago-de-prueba")


def test_sin_especificacion_en_el_prefijo_falla_en_vez_de_medir_sin_robos(monkeypatch, tmp_path):
    from src.sim import escenario_b                          # noqa: PLC0415

    _falsear_boto3(monkeypatch, _S3Falso([]))

    with pytest.raises(escenario_b.EspecificacionInvalida, match="hay 0"):
        V.descargar_spec(str(tmp_path / "spec.yaml"), lake_uri="s3://lago-de-prueba")


def test_en_local_descargar_spec_dice_que_variable_apuntar(monkeypatch, tmp_path):
    from src.sim import escenario_b                          # noqa: PLC0415

    with pytest.raises(escenario_b.EspecificacionInvalida, match=escenario_b.VARIABLE_RUTA):
        V.descargar_spec(str(tmp_path / "spec.yaml"), lake_uri=str(tmp_path))
