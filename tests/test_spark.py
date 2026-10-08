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
