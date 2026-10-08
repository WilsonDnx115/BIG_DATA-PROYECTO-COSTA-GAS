# Técnicas del curso (S1–S5) aplicadas en el código

Paso 2.4.5 · Tabla 2.8 del informe. Cada fila apunta al archivo y la línea que la implementa.
Se actualiza cuando cambia el código.

| Sesión | Técnica | Dónde se aplica | Cómo se evidencia |
|---|---|---|---|
| S1 · Fundamentos | 5 V: volumen y variedad medidos, no estimados | [volumen.py](../src/quality/volumen.py) | `docs/evidencias/volumen.md` |
| S1 · Fundamentos | Veracidad: reglas de calidad por corrida | [reglas.py](../src/quality/reglas.py), [handler.py:46](../src/bronze_to_silver/handler.py#L46) | `silver/_calidad/fecha=…/*.json` |
| S1 · Fundamentos | Data Lake medallón (Bronze/Silver/Gold), no DWH | [rutas.py](../src/common/rutas.py), [stack.yaml](../infra/cloudformation/stack.yaml) | estructura del bucket |
| S1 · Fundamentos | ELT: se carga crudo y se transforma después | [internos.py:45](../src/ingest/internos.py#L45) | Bronze inmutable con `fecha_carga=` |
| S1 · Fundamentos | Escalado vertical (Lambda/pandas) vs horizontal (Glue/Spark) | [replicar.py:40](../src/scaletest/replicar.py#L40), [replicar.py:53](../src/scaletest/replicar.py#L53) | `docs/evidencias/escalabilidad.md` |
| S2 · HDFS | Separación almacenamiento/cómputo; S3 sustituible por HDFS cambiando la URI | [rutas.py:31](../src/common/rutas.py#L31), [config.py](../src/common/config.py) (`LAKE_URI`) | mismo job en `file://` y `s3://` |
| S2 · HDFS | Tolerancia a fallos: Bronze inmutable = réplica; regeneración de particiones | [reproceso.py:24](../src/common/reproceso.py#L24) | `tests/test_pipeline.py::test_reproceso_regenera_particion_identica` |
| S2 · HDFS | Problema de archivos pequeños: una escritura por partición, objetivo 128 MB | [lake_io.py:54](../src/common/lake_io.py#L54), [config.py:59](../src/common/config.py#L59) | Silver con muchos menos archivos que Bronze |
| S2 · HDFS | Linaje: manifiesto con SHA-256 por archivo | [manifest.py:53](../src/ingest/manifest.py#L53) | `_manifests/fecha_carga=…/manifest.json` |
| S3 · MapReduce | Map → Shuffle → Reduce en la conciliación | [conciliacion.py:64](../src/silver_to_gold/conciliacion.py#L64) | plan físico con `HashAggregate` parcial y final |
| S3 · MapReduce | Combiner: `groupBy().agg()` agrega antes del shuffle | [conciliacion.py:66](../src/silver_to_gold/conciliacion.py#L66) | `partial_sum` en `explain()` |
| S3 · MapReduce | Data skew: AQE + salting opcional (`SALTING_BUCKETS`) | [spark.py:17](../src/common/spark.py#L17), [conciliacion.py:52](../src/silver_to_gold/conciliacion.py#L52) | Spark UI de Glue: tarea más lenta vs mediana |
| S4 · Spark | Evaluación perezosa y DAG; acción solo al escribir | [conciliacion.py](../src/silver_to_gold/conciliacion.py) | `explain()` |
| S4 · Spark | `broadcast()` de la tabla pequeña (flota) | [conciliacion.py:80](../src/silver_to_gold/conciliacion.py#L80) | `BroadcastHashJoin` vs `SortMergeJoin` (`usar_broadcast=False`) |
| S4 · Spark | `cache()` de la conciliación reutilizada por varias señales | [conciliacion.py:82](../src/silver_to_gold/conciliacion.py#L82) | tiempo con y sin caché (3.6.5) |
| S4 · Spark | Nunca `collect()`; inspección con `show()`/`take()` | [conciliacion.py:120](../src/silver_to_gold/conciliacion.py#L120) | regla en `CLAUDE.md` |
| S4 · Spark | Driver, Executors y particiones | [replicar.py:53](../src/scaletest/replicar.py#L53) | `particiones_entrada` en la tabla de escalabilidad |
| S5 · Spark SQL | Esquema declarado, sin `inferSchema` | [schemas.py](../src/common/schemas.py), [conciliacion.py:44](../src/silver_to_gold/conciliacion.py#L44) | archivo que no cumple → rechazo (`test_esquema_declarado_rechaza_archivo`) |
| S5 · Spark SQL | Partition pruning (`anio`) | [conciliacion.py:47](../src/silver_to_gold/conciliacion.py#L47), [lake_io.py:62](../src/common/lake_io.py#L62) | `PartitionFilters` en `explain()`; bytes escaneados en Athena |
| S5 · Spark SQL | Predicate pushdown (`id_producto`) | [conciliacion.py:49](../src/silver_to_gold/conciliacion.py#L49) | `PushedFilters` |
| S5 · Spark SQL | Column pruning (`select`) | [conciliacion.py:50](../src/silver_to_gold/conciliacion.py#L50) | `ReadSchema` solo con las columnas usadas |
| S5 · Spark SQL | Parquet + Snappy particionado por `anio/mes` | [lake_io.py](../src/common/lake_io.py), [spark.py](../src/common/spark.py) | DDL con proyección de particiones en `sql/athena/ddl/` |
| S5 · Spark SQL | Joins `left_outer`, `left_anti`, `left_semi`, `full_outer` (Tabla 3.6) | [uniones.py](../src/silver_to_gold/uniones.py) | `tests/test_reglas_y_modelos.py::test_joins_anti_y_semi` |
| S5 · Spark SQL | Mismo plan con DataFrames y SQL (Athena) | [sql/athena/](../sql/athena) | vistas de KPIs |
