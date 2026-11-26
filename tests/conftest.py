"""Cada prueba de integración corre sobre un lago temporal (LAKE_URI=file://<tmp>)."""
import importlib
import os

import pytest

os.environ.setdefault("SEUDONIMO_SAL", "sal-de-prueba")


@pytest.fixture()
def lago(tmp_path, monkeypatch):
    from src.common import config

    monkeypatch.setattr(config, "LAKE_URI", f"file://{tmp_path.as_posix()}/lake")
    return tmp_path


def _sin_pyspark() -> bool:
    return importlib.util.find_spec("pyspark") is None


@pytest.fixture(scope="session")
def spark():
    if _sin_pyspark():
        pytest.skip("pyspark no instalado (requirements-spark.txt)")
    from src.common.spark import obtener_spark

    try:
        s = obtener_spark("tests")
    except Exception as e:                      # noqa: BLE001
        pytest.skip(f"no se pudo iniciar Spark local: {e}")
    yield s
    s.stop()


@pytest.fixture(scope="session")
def spark_iceberg(tmp_path_factory):
    """Sesión con un catálogo Iceberg `hadoop` sobre una carpeta temporal (W04).

    En Windows, Spark necesita además HADOOP_HOME con winutils.exe; si no está,
    la prueba se omite en lugar de fallar. En Linux (CI y Glue) corre tal cual.
    """
    if _sin_pyspark():
        pytest.skip("pyspark no instalado (requirements-spark.txt)")
    almacen = "file:///" + tmp_path_factory.mktemp("almacen").as_posix().lstrip("/")
    from src.glue.gold_job import crear_sesion

    try:
        s = crear_sesion(almacen, almacen=almacen, tipo="hadoop", app="tests-iceberg")
    except Exception as e:                      # noqa: BLE001
        pytest.skip(f"no se pudo iniciar Spark con Iceberg: {e}")
    yield s
    s.stop()
