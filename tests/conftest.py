"""Cada prueba de integración corre sobre un lago temporal (LAKE_URI=file://<tmp>)."""
import importlib
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SEUDONIMO_SAL", "sal-de-prueba")
# Spark arma su URL interna con el nombre del equipo y un guion bajo la invalida
# («Invalid Spark URL: spark://HeartbeatReceiver@Laptop_Anghelo»). Sin esto, en esas
# maquinas la sesion ni siquiera arranca.
os.environ.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")

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


def _spark_no_disponible() -> str | None:
    """Motivo por el que no se puede correr Spark aquí, o None si sí se puede."""
    if _sin_pyspark():
        return "pyspark no instalado (requirements-spark.txt)"
    if os.name == "nt":
        # Sin winutils.exe, Hadoop no puede ni leer un archivo local:
        # UnsatisfiedLinkError: NativeIO$Windows.access0. La sesion llega a crearse,
        # asi que no basta con atrapar el error al crearla: hay que comprobarlo antes
        # para que el motivo de la omision sea el de verdad.
        hadoop = os.environ.get("HADOOP_HOME")
        if not (hadoop and Path(hadoop, "bin", "winutils.exe").exists()):
            return "falta winutils.exe en HADOOP_HOME: Spark no accede al disco en Windows"
    return None


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    """Una sola sesión para toda la suite, ya con el catálogo Iceberg.

    `spark.sql.extensions` solo se aplica al crear la sesión: si una prueba
    abriera antes una sesión sin Iceberg, `MERGE INTO` no se podría ni analizar.
    Por eso hay una sola y la crea esta fixture.

    En Windows, Spark necesita además HADOOP_HOME con winutils.exe; si no está,
    las pruebas se omiten en lugar de fallar. En Linux (CI y Glue) corren.
    """
    motivo = _spark_no_disponible()
    if motivo:
        pytest.skip(motivo)
    # El worker de Python lo lanza la JVM, y si no se le dice con que interprete,
    # usa el `python` del PATH. Cuando ese no es el del entorno virtual, el worker
    # arranca sin pyspark y el driver se queda esperando el saludo:
    # «Python worker failed to connect back» (asi fallaba test_dimensiones.py en
    # Windows). `sys.executable` es el interprete que ya tiene todo instalado.
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
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
