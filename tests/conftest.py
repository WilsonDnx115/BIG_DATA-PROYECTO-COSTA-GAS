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


@pytest.fixture(scope="session")
def spark():
    if importlib.util.find_spec("pyspark") is None:
        pytest.skip("pyspark no instalado (requirements-spark.txt)")
    from src.common.spark import obtener_spark

    s = obtener_spark("tests")
    yield s
    s.stop()
