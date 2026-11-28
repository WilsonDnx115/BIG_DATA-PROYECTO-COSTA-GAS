"""WR07: el trabajo de Glue de Gold corre `gold_job.py` con sus dependencias.

Estas pruebas no hablan con AWS. Lo que vigilan es que las tres piezas digan lo
mismo: la plantilla (que script y con que argumentos), `deploy.sh` (que archivo
sube a esa clave) y el `argparse` del job (que argumentos entiende). Si una se
mueve sin las otras, el trabajo falla en la corrida de Glue, que es donde cuesta
dinero y tiempo, y no en la revision.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.glue import gold_job

PLANTILLA = Path("infra/cloudformation/stack.yaml")
DEPLOY = Path("infra/scripts/deploy.sh")
JOB = "JobConciliacion"
CLAVE_SCRIPT = "_code/glue_gold_job.py"


class _Etiquetas(yaml.SafeLoader):
    """CloudFormation usa `!Sub`, `!Ref` y demas; aqui solo interesa la forma."""


def _etiqueta(loader, sufijo, nodo):
    """Conserva el texto de `!Sub s3://...`, que es lo que estas pruebas leen."""
    if isinstance(nodo, yaml.ScalarNode):
        return loader.construct_scalar(nodo)
    if isinstance(nodo, yaml.SequenceNode):
        return loader.construct_sequence(nodo)
    return loader.construct_mapping(nodo)


_Etiquetas.add_multi_constructor("!", _etiqueta)


@pytest.fixture(scope="module")
def plantilla() -> dict:
    return yaml.load(PLANTILLA.read_text(encoding="utf-8"), Loader=_Etiquetas)


@pytest.fixture(scope="module")
def trabajo(plantilla) -> dict:
    return plantilla["Resources"][JOB]["Properties"]


@pytest.fixture(scope="module")
def deploy() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def test_el_script_del_trabajo_es_el_job_de_gold(trabajo):
    assert CLAVE_SCRIPT in trabajo["Command"]["ScriptLocation"]


def test_deploy_sube_gold_job_a_esa_misma_clave(deploy):
    """Si la plantilla apunta a una clave que nadie sube, el trabajo no arranca."""
    assert f'src/glue/gold_job.py "s3://${{CODE_BUCKET}}/{CLAVE_SCRIPT}"' in deploy


def test_el_job_entiende_los_argumentos_que_le_pasa_glue(trabajo):
    """Glue agrega `--JOB_NAME` y los suyos; `argumentos` debe ignorarlos."""
    argv = []
    for clave, valor in trabajo["DefaultArguments"].items():
        if clave in ("--modo", "--lake_uri"):
            argv += [clave, str(valor)]
    argv += ["--JOB_NAME", "costagas-gold-conciliacion"]

    args = gold_job.argumentos(argv)

    assert args.modo == "evento"
    assert args.lake_uri.startswith("<Sub>") or args.lake_uri.startswith("s3://")


def test_el_modo_del_trabajo_es_uno_de_los_que_existen(trabajo):
    assert trabajo["DefaultArguments"]["--modo"] in gold_job.MODOS


def test_el_codigo_y_los_contratos_viajan_con_el_trabajo(trabajo, deploy):
    """El job lee el esquema de cada tabla del contrato: sin los YAML no corre."""
    assert "--extra-py-files" in trabajo["DefaultArguments"]
    assert 'pathlib.Path("contracts").glob("*.yaml")' in deploy


def test_scikit_learn_va_con_version_fija(trabajo):
    """Una version distinta cambia el modelo guardado y el registro no cuadraria."""
    modulos = trabajo["DefaultArguments"]["--additional-python-modules"]

    assert modulos.startswith("scikit-learn==")


def test_el_trabajo_mide_lo_que_necesita_la_prueba_de_escalabilidad(trabajo):
    """Sin Spark UI ni metricas no hay con que dimensionar el clster (WR21)."""
    args = trabajo["DefaultArguments"]

    assert args["--enable-spark-ui"] == "true"
    assert args["--enable-metrics"] == "true"
    assert "sparkui" in args["--spark-event-logs-path"]


def test_el_trabajo_sigue_dentro_del_presupuesto(trabajo):
    """G.1X, dos trabajadores por defecto, 15 minutos y sin reintentos (ADR 0031)."""
    assert trabajo["WorkerType"] == "G.1X"
    assert trabajo["Timeout"] == 15
    assert trabajo["MaxRetries"] == 0
    assert trabajo["ExecutionProperty"]["MaxConcurrentRuns"] == 1


def test_la_lambda_de_limpieza_conserva_los_3008_mb_del_adr_0021(plantilla):
    parametro = plantilla["Parameters"]["LambdaMemoriaMB"]

    assert parametro["Default"] == 3008
