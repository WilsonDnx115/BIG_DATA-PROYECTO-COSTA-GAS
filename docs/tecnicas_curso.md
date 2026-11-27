# Técnicas del curso (S1–S5) aplicadas en el código

Paso 2.4.5 · Tabla 2.8 del informe. Cada fila apunta al archivo y la línea que la implementa.
Se actualiza cuando cambia el código.

| Sesión | Técnica | Dónde se aplica | Cómo se evidencia |
|---|---|---|---|
| S1 · Fundamentos | 5 V: volumen y variedad medidos, no estimados | [volumen.py](../src/quality/volumen.py) | `docs/evidencias/volumen.md` |
| S1 · Fundamentos | Veracidad: reglas de calidad por corrida | [reglas.py](../src/quality/reglas.py), [handler.py:46](../src/bronze_to_silver/handler.py#L46) | `silver/_calidad/fecha=…/*.json` |
| S1 · Fundamentos | Veracidad y trazabilidad del modelo base v6 | [contratos.py:23](../src/signals/contratos.py#L23), [evaluacion_base.py:71](../src/models/evaluacion_base.py#L71) | Claves y fechas validadas; revisión independiente; métricas ausentes como `null`, sin etiquetas débiles S1/S8 |
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
| S5 · Spark SQL | Schema-on-read en Bronze: los encabezados reales se inventarían antes de declarar el esquema | [encabezados.py:244](../src/ingest/encabezados.py#L244) | `docs/evidencias/encabezados_raw.md` con el contraste declarado vs. hallado por fuente |
| S5 · Spark SQL | Esquema declarado, sin `inferSchema` | [schemas.py](../src/common/schemas.py), [conciliacion.py:44](../src/silver_to_gold/conciliacion.py#L44) | archivo que no cumple → rechazo (`test_esquema_declarado_rechaza_archivo`) |
| S5 · Spark SQL | Contrato de salida y selección de columnas para WP 0.8 | [schemas.py](../src/common/schemas.py), [contratos.py:23](../src/signals/contratos.py#L23) | `gold/fact_alerta_base/` en Parquet; pruebas rechazan entradas incompatibles y verifican que columnas personales extra no se exporten |
| S5 · Spark SQL | Partition pruning (`anio`) | [conciliacion.py:47](../src/silver_to_gold/conciliacion.py#L47), [lake_io.py:62](../src/common/lake_io.py#L62) | `PartitionFilters` en `explain()`; bytes escaneados en Athena |
| S5 · Spark SQL | Predicate pushdown (`id_producto`) | [conciliacion.py:49](../src/silver_to_gold/conciliacion.py#L49) | `PushedFilters` |
| S5 · Spark SQL | Column pruning (`select`) | [conciliacion.py:50](../src/silver_to_gold/conciliacion.py#L50) | `ReadSchema` solo con las columnas usadas |
| S5 · Spark SQL | Parquet + Snappy particionado por `anio/mes` | [lake_io.py](../src/common/lake_io.py), [spark.py](../src/common/spark.py) | DDL con proyección de particiones en `sql/athena/ddl/` |
| S5 · Spark SQL | Joins `left_outer`, `left_anti`, `left_semi`, `full_outer` (Tabla 3.6) | [uniones.py](../src/silver_to_gold/uniones.py) | `tests/test_reglas_y_modelos.py::test_joins_anti_y_semi` |
| S5 · Spark SQL | Mismo plan con DataFrames y SQL (Athena) | [sql/athena/](../sql/athena) | vistas de KPIs |

## Técnicas de la segunda mitad (commit AR15)

Las de arriba son las sesiones S1-S5 del curso. Estas entraron con los paquetes de Gold, la
operación en la nube y las fuentes externas. Mismo criterio: cada fila apunta a un archivo y una
línea que existen hoy en `main`, y la columna de evidencia dice **cómo se comprueba**, no qué se
pretende.

| Técnica | Dónde se aplica | Cómo se evidencia |
|---|---|---|
| **MapReduce con Spark SQL** (módulo M5): las cuatro etapas del patrón en el plan físico | [mapreduce_sql.py:62](../src/glue/mapreduce_sql.py#L62) (`mapear`), [:71](../src/glue/mapreduce_sql.py#L71) (`reducir`), [:77](../src/glue/mapreduce_sql.py#L77) (`construir`) | `Project`/`Filter`, `HashAggregate` parcial, `Exchange hashpartitioning` y `HashAggregate` final en `explain()` ([ADR 0029](adr/0029-mapreduce-con-spark-sin-emr.md)) |
| **MapReduce sobre RDD** como control de la versión SQL | [mapreduce_sql.py:82](../src/glue/mapreduce_sql.py#L82) (`mapear_reducir_rdd`, con `reduceByKey`) | `tests/test_mapreduce_sql.py`: los totales de las dos versiones coinciden sobre el mismo universo |
| **Combiner frente a `groupByKey`**: `reduceByKey` suma dentro de la partición antes del shuffle | [mapreduce.py:53](../src/silver_to_gold/mapreduce.py#L53) y [:59](../src/silver_to_gold/mapreduce.py#L59) | `mapreduce.comparar()` mide los bytes de shuffle de las dos; `groupByKey` está como contraejemplo, no como alternativa |
| **`MERGE INTO` de Iceberg** por la llave del grano, nunca `overwrite` | [iceberg.py:70](../src/glue/iceberg.py#L70) (`escribir_merge`), sentencia en [:87](../src/glue/iceberg.py#L87) | `tests/test_gold_job.py`: el mismo MERGE dos veces deja una fila por llave (idempotencia) |
| **Lectura incremental** con marcadores de Glue: cada corrida lee solo lo nuevo | [stack.yaml:366](../infra/cloudformation/stack.yaml#L366) y [:1008](../infra/cloudformation/stack.yaml#L1008) (`--job-bookmark-option: job-bookmark-enable`) | una segunda corrida sin archivos nuevos no reprocesa nada |
| **AQE** y *salting* opcional contra el sesgo de datos | [spark.py:17](../src/common/spark.py#L17), [conciliacion.py:52](../src/silver_to_gold/conciliacion.py#L52) | Spark UI de Glue: tarea más lenta frente a la mediana |
| **`broadcast()`** de la tabla pequeña (flota) | [conciliacion.py:80](../src/silver_to_gold/conciliacion.py#L80) | `BroadcastHashJoin` en lugar de `SortMergeJoin` en `explain()` |
| **Orquestación por eventos con EventBridge**: la carga dispara la limpieza y Silver dispara Gold | [stack.yaml:521](../infra/cloudformation/stack.yaml#L521) y [:568](../infra/cloudformation/stack.yaml#L568) (`AWS::Events::Rule`) | la regla de Gold escucha solo los siete prefijos internos de Silver ([ADR 0020](adr/0020-regla-gold-prefijos-internos.md)) |
| **Flujos de Glue**: un *workflow* con su *trigger*, y los jobs declarados en la plantilla | [stack.yaml:336](../infra/cloudformation/stack.yaml#L336) y [:983](../infra/cloudformation/stack.yaml#L983) (`AWS::Glue::Job`), [:539](../infra/cloudformation/stack.yaml#L539) (`Workflow`), [:542](../infra/cloudformation/stack.yaml#L542) y [:1021](../infra/cloudformation/stack.yaml#L1021) (`Trigger`) | `cfn-lint` sobre `us-east-2` en la integración continua |
| **EventBridge Scheduler** para lo que va por horario, no por evento | [stack.yaml:917](../infra/cloudformation/stack.yaml#L917), [:932](../infra/cloudformation/stack.yaml#L932), [:947](../infra/cloudformation/stack.yaml#L947), [:962](../infra/cloudformation/stack.yaml#L962) (`AWS::Scheduler::Schedule`) | el semáforo de las 6:30 y los extractores externos ([ADR 0015](adr/0015-youtube-data-api.md)) |
| **LDA de MLlib** sobre el texto de las fuentes externas | [externos_job.py:248](../src/glue/externos_job.py#L248) (`temas`), pipeline en [:232](../src/glue/externos_job.py#L232) | con menos documentos que temas devuelve `(None, None, None)` en vez de un modelo que no significa nada (`tests/test_externos_job.py`) |
| **pdfplumber en el executor**, nunca en el driver | [externos_job.py:152](../src/glue/externos_job.py#L152) (`_texto_pdf`), import diferido en [:155](../src/glue/externos_job.py#L155) | el texto se extrae dentro de cada partición; el driver solo coordina ([resoluciones.py](../src/extractores/resoluciones.py)) |

Dos cosas que esta tabla deja dichas, además de la técnica:

- **El patrón MapReduce se ejecuta con Spark SQL, no con Hadoop Streaming.** Es una decisión
  registrada, no una omisión: EMR corre sobre EC2 por hora y la política base de la cuenta lo
  deniega ([ADR 0029](adr/0029-mapreduce-con-spark-sin-emr.md), que reemplaza al 0014). La
  equivalencia se demuestra etapa por etapa en el plan físico y comparando los totales con la
  versión sobre RDD.
- **Tener el código no es haberlo ejecutado.** Las filas que apuntan a
  `infra/cloudformation/stack.yaml` acreditan que el recurso está declarado y que `cfn-lint` lo
  valida; la corrida en AWS se acredita aparte, en `docs/evidencias/`, con su fecha y su captura.
