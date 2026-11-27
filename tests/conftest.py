"""Cada prueba de integración corre sobre un lago temporal (LAKE_URI=file://<tmp>)."""
import importlib
import os

import pytest

os.environ.setdefault("SEUDONIMO_SAL", "sal-de-prueba")

# Los paquetes de Spark se resuelven al arrancar la JVM, no al crear la sesión:
# si se piden después, Iceberg queda fuera del classpath. Por eso se declaran
# aquí, antes de que cualquier prueba cree una sesión.
if importlib.util.find_spec("pyspark") is not None:
    from src.glue.iceberg import PAQUETE

    os.environ.setdefault("PYSPARK_SUBMIT_ARGS", f"--packages {PAQUETE} pyspark-shell")


@pytest.fixture()
def lago(tmp_path, monkeypatch):
    from src.common import config

    monkeypatch.setattr(config, "LAKE_URI", f"file://{tmp_path.as_posix()}/lake")
    return tmp_path


def _sin_pyspark() -> bool:
    return importlib.util.find_spec("pyspark") is None


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    """Una sola sesión para toda la suite, ya con el catálogo Iceberg.

    `spark.sql.extensions` solo se aplica al crear la sesión: si una prueba
    abriera antes una sesión sin Iceberg, `MERGE INTO` no se podría ni analizar.
    Por eso hay una sola y la crea esta fixture.

    En Windows, Spark necesita además HADOOP_HOME con winutils.exe; si no está,
    las pruebas se omiten en lugar de fallar. En Linux (CI y Glue) corren.
    """
    if _sin_pyspark():
        pytest.skip("pyspark no instalado (requirements-spark.txt)")
    almacen = "file:///" + tmp_path_factory.mktemp("almacen").as_posix().lstrip("/")
    from src.glue.gold_job import crear_sesion

    try:
        s = crear_sesion(almacen, almacen=almacen, tipo="hadoop", app="tests")
    except Exception as e:                      # noqa: BLE001
        pytest.skip(f"no se pudo iniciar Spark local: {e}")
    yield s
    s.stop()


@pytest.fixture(scope="session")
def spark_iceberg(spark):
    """La misma sesión: el catálogo `glue_catalog` apunta a una carpeta temporal."""
    return spark
