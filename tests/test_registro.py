"""W13: registro de modelos S12, vigente.json y promocion del retador."""
from __future__ import annotations

import json
from pathlib import Path

from src.common import config, rutas
from src.models import registro


class ModeloFalso:
    """Objeto serializable que hace de modelo entrenado."""

    def __init__(self, nombre: str = "rf"):
        self.nombre = nombre


def test_guardar_deja_la_corrida_y_sus_metricas(lago):
    metricas = {"precision": 0.72, "recall": 0.61, "pr_auc": 0.55, "umbral": 0.38}

    ficha = registro.guardar(ModeloFalso(), metricas, fecha="2026-11-26")

    assert ficha["corrida"] == "2026-11-26"
    assert ficha["version"] == "s12-2026-11-26"
    assert ficha["umbral"] == 0.38
    assert "gold/_modelos/s12/corrida=2026-11-26" in ficha["ruta"]
    assert Path(ficha["ruta"]).exists()
    guardado = json.loads(
        Path(f"{registro.ruta_corrida('2026-11-26')}/metricas.json").read_text(encoding="utf-8")
    )
    assert guardado["metricas"] == metricas


def test_guardar_no_promueve_por_si_solo(lago):
    registro.guardar(ModeloFalso(), {"precision": 0.9, "recall": 0.9}, fecha="2026-11-26")
    assert registro.vigente() is None


def test_el_primer_modelo_entra_si_cumple_el_recall(lago):
    retador = registro.guardar(ModeloFalso(), {"precision": 0.71, "recall": 0.60},
                               fecha="2026-11-26")

    assert registro.promover_si_mejora(retador) is True
    assert registro.vigente()["version"] == "s12-2026-11-26"


def test_retador_con_mejor_precision_y_recall_bajo_no_se_promueve(lago):
    actual = registro.guardar(ModeloFalso("vigente"), {"precision": 0.70, "recall": 0.62},
                              fecha="2026-11-01")
    registro.promover_si_mejora(actual)

    retador = registro.guardar(ModeloFalso("retador"), {"precision": 0.85, "recall": 0.40},
                               fecha="2026-11-26")

    assert config.RECALL_MIN_RETADOR == 0.50
    assert registro.promover_si_mejora(retador) is False
    assert registro.vigente()["version"] == "s12-2026-11-01"


def test_retador_con_mejor_precision_y_recall_suficiente_si_se_promueve(lago):
    actual = registro.guardar(ModeloFalso("vigente"), {"precision": 0.70, "recall": 0.62},
                              fecha="2026-11-01")
    registro.promover_si_mejora(actual)

    retador = registro.guardar(ModeloFalso("retador"), {"precision": 0.85, "recall": 0.60},
                               fecha="2026-11-26")

    assert registro.promover_si_mejora(retador) is True
    assert registro.vigente()["version"] == "s12-2026-11-26"
    assert registro.vigente()["metricas"]["precision"] == 0.85


def test_retador_sin_mejor_precision_no_se_promueve(lago):
    actual = registro.guardar(ModeloFalso(), {"precision": 0.80, "recall": 0.60},
                              fecha="2026-11-01")
    registro.promover_si_mejora(actual)

    retador = registro.guardar(ModeloFalso(), {"precision": 0.80, "recall": 0.95},
                               fecha="2026-11-26")

    assert registro.promover_si_mejora(retador) is False


def test_las_rutas_salen_de_rutas_py(lago):
    assert registro.ruta_base() == rutas.ruta("gold", "_modelos", "s12")
    assert registro.ruta_vigente().endswith("gold/_modelos/s12/vigente.json")
