# 0029 · El patrón MapReduce se ejecuta con Spark SQL en Glue, sin EMR

- **Fecha:** 2026-11-27
- **Estado:** aceptada
- **Responsable:** ingeniería de datos, con coordinación (requisito del curso)
- **Referencias:** informe v17, Tabla 2.2c (módulo M5 · MapReduce, p. 29), Tabla 2.6b
  (p. 33) y Tabla 2.8 (técnica S3, p. 42); [ADR 0005](0005-lambda-y-glue.md),
  [ADR 0011](0011-region-us-east-2.md)
- **Reemplaza:** [ADR 0014](0014-emr-transitorio-reglas-v6.md)

## Contexto

El ADR 0014 abrió una excepción a la gestión exclusiva por CloudFormation para
crear un clúster EMR transitorio por CLI y correr Hadoop Streaming, porque las
reglas del informe v6 pedían esa evidencia. Desde entonces cambiaron las dos
cosas que sostenían la excepción:

1. **El informe ya no contempla esa ruta.** La Tabla 2.6b del v17 compara el
   servicio elegido con la alternativa habitual y descarta «Amazon EMR, EMR
   Serverless o Databricks» porque «EMR corre sobre instancias EC2 que cobran por
   hora y la política base las deniega». La Tabla 2.2c define el módulo **M5 ·
   MapReduce** como «Apache Spark 3.5 en AWS Glue (PySpark, API de DataFrames)».
2. **La excepción nunca se pudo ejecutar.** La política base de la cuenta deniega
   `ec2:RunInstances` y eso no cambió; el ADR 0014 ya registraba el bloqueo. Una
   excepción que no se puede usar no deja de costar: `CLAUDE.md` la citaba como
   regla viva y exigía una evidencia que ningún commit podía producir.

## Alternativas evaluadas

1. **Mantener el ADR 0014 vivo** y pedir al administrador que habilite EMR.
   Descartada: suma EC2 por hora más el recargo de EMR a un tope de US$ 1 que
   hoy va en US$ 0 medidos, y depende de un cambio de plan ajeno al equipo. El
   hito final no puede quedar colgado de eso.
2. **Presentar una operación sobre RDD de Spark y llamarla Hadoop MapReduce.**
   Descartada: sería una evidencia falsa. RDD es una API de Spark, no Hadoop.
3. **Ejecutar el patrón MapReduce con Spark SQL en Glue y documentar la
   equivalencia etapa por etapa.** Elegida.

## Criterio

Lo que el curso evalúa en la técnica S3 es el patrón —*map*, combinación local,
*shuffle* por clave y *reduce*—, no el binario que lo ejecuta; así lo registra la
Tabla 2.8 del v17, que mapea «Map, Shuffle y Reduce; Combiner» a «Patrón
MapReduce en Python con PySpark en Glue: map (select/filter), combinación local
(HashAggregate parcial), shuffle por clave y reduce». Las cuatro etapas son
observables en el plan físico de Catalyst, que es evidencia reproducible y no
una captura de consola:

| Etapa de MapReduce | Operador en el plan físico |
|---|---|
| `map` | `Project` / `Filter` por fila |
| `combiner` | `HashAggregate` parcial, antes del intercambio |
| `shuffle` | `Exchange hashpartitioning(producto, anio, mes)` |
| `reduce` | `HashAggregate` final |

La comparación que pedía el ADR 0014 —resultados equivalentes sobre el mismo
universo— se conserva, pero entre las dos implementaciones que sí corren:
`mapreduce_sql.construir` (Spark SQL) y `mapreduce_sql.mapear_reducir_rdd`
(`reduceByKey`), sobre los mismos datos y con la misma llave de reducción. Eso
lo comprueba `tests/test_mapreduce_sql.py` en
`test_sql_y_rdd_dan_los_mismos_totales`.

## Consecuencia

- [CLAUDE.md](../../CLAUDE.md) pierde, en este mismo cambio, la excepción de EMR
  transitorio, el requisito de Hadoop Streaming con mapper, reducer y combiner, y
  la referencia a `src/mr/`. EMR queda prohibido en todas sus formas, junto con
  EC2 independiente. Ningún recurso se crea fuera de
  `infra/cloudformation/stack.yaml`.
- El ADR 0014 pasa a **reemplazada por 0029**. No se borra: su contexto explica
  por qué la regla existió.
- La evidencia de la técnica S3 es el plan físico de
  [src/glue/mapreduce_sql.py](../../src/glue/mapreduce_sql.py) con las cuatro
  etapas, más la igualdad de totales entre la versión SQL y la de RDD. Se guarda
  en `docs/evidencias/` cuando el job corra en Glue, con fecha y captura.
- Lo que no cambia: el tope de US$ 1, la región `us-east-2` (ADR 0011) y el
  reparto de módulos entre Lambda, Glue y Athena (ADR 0005). Esta decisión no
  despliega nada ni toca IAM.
- Queda una consecuencia que no es de este rol: el enunciado del curso es el que
  pide Hadoop. Si la evaluación exige el binario y no el patrón, hay que volver a
  abrir la ruta con el administrador y este ADR se reemplaza a su vez. Coordinación
  lo confirma al revisar el PR.
