"""Cada prueba de integración corre sobre un lago temporal (LAKE_URI=file://<tmp>)."""
import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("SEUDONIMO_SAL", "sal-de-prueba")
# Spark arma su URL interna con el nombre del equipo y un guion bajo la invalida
# («Invalid Spark URL: spark://HeartbeatReceiver@Laptop_Anghelo»).
os.environ.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")


def _spark_no_disponible() -> str | None:
    """Motivo por el que no se puede correr Spark aquí, o None si sí se puede."""
    if importlib.util.find_spec("pyspark") is None:
        return "pyspark no instalado (requirements-spark.txt)"
    if os.name == "nt":
        # Sin winutils.exe, Hadoop no puede ni leer archivos locales:
        # UnsatisfiedLinkError: NativeIO$Windows.access0. En Ubuntu no hace falta,
        # y por eso la integración continua corre estas pruebas allí.
        hadoop = os.environ.get("HADOOP_HOME")
        if not (hadoop and Path(hadoop, "bin", "winutils.exe").exists()):
            return "falta winutils.exe en HADOOP_HOME: Spark no accede al disco en Windows"
    return None


@pytest.fixture()
def lago(tmp_path, monkeypatch):
    from src.common import config

    monkeypatch.setattr(config, "LAKE_URI", f"file://{tmp_path.as_posix()}/lake")
    return tmp_path


@pytest.fixture(scope="session")
def spark():
    motivo = _spark_no_disponible()
    if motivo:
        pytest.skip(motivo)
    from src.common.spark import obtener_spark

    s = obtener_spark("tests")
    yield s
    s.stop()
