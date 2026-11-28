"""Evidencias de S4/S5 en el plan de Catalyst (se omiten si no hay pyspark)."""
from src.bronze_to_silver import handler
from src.common import muestra
from src.ingest import internos
from src.silver_to_gold import conciliacion


def _preparar(lago):
    origen = lago / "entrega"
    muestra.generar(n_unidades=5, semilla=3, destino=origen)
    for a in internos.ingerir(origen):
        handler.procesar_archivo(a)
    handler.construir_movimientos()


def test_plan_broadcast_y_pruning(spark, lago):
    _preparar(lago)
    conc = conciliacion.conciliar_spark(spark, anios=[2020], producto="B10", guardar_explain=False)
    plan = conc._jdf.queryExecution().toString()
    assert "BroadcastHashJoin" in plan
    assert "PartitionFilters" in plan and "PushedFilters" in plan
    assert conc.count() == len(conciliacion.conciliar_pandas(anios=[2020], producto="B10"))


def test_el_worker_de_python_usa_el_interprete_de_la_suite(spark):
    """WR19: sin esto el worker arranca con el `python` del PATH y no conecta.

    El sintoma era «Python worker failed to connect back» en `test_dimensiones.py`:
    la JVM lanzaba un interprete sin pyspark instalado. Se comprueba despues de la
    fixture porque es ella la que lo fija, antes de crear la sesion.
    """
    import os
    import sys

    assert os.environ["PYSPARK_PYTHON"] == sys.executable
    assert os.environ["PYSPARK_DRIVER_PYTHON"] == sys.executable
    assert spark.range(3).count() == 3          # el worker de verdad responde
