# 0014 · EMR transitorio en las reglas del informe v6

- **Fecha:** 2026-10-11
- **Estado:** aceptada para el diseño; ejecución bloqueada en la cuenta actual
- **Responsable del paquete:** calidad y documentación · WP 0.1, B2
- **Referencias:** informe v6, tablas 2.2c y 2.5, sección 3.3; Plan de Corrección, G1 y A2
- **Actualiza:** prohibición general de EMR y regla de recursos exclusivamente CloudFormation de `CLAUDE.md`; complementa ADR 0005 y 0011

## Contexto

Las reglas anteriores prohibían EMR y solo contemplaban Spark para las tareas
distribuidas. El informe v6 y el Plan de Corrección requieren Hadoop MapReduce
real con Hadoop Streaming, además de Spark, y definen un clúster transitorio
creado mediante CLI. La cuenta gratuita mantiene restricciones de servicio y
la política base deniega `ec2:RunInstances`; documentar la arquitectura no
habilita su ejecución.

## Alternativas evaluadas

1. Mantener la prohibición general y presentar RDD de Spark como MapReduce.
   Descartada: no satisface la evidencia Hadoop Streaming solicitada.
2. Usar EC2 independiente, EMR permanente o EMR Serverless. Descartada:
   incumple el diseño y el presupuesto; EMR Serverless no ejecuta MapReduce.
3. Permitir en las reglas únicamente el EMR transitorio definido por el v6,
   separado de la disponibilidad real de la cuenta. Elegida.

## Criterio

Hadoop Streaming debe producir resultados comparables con Spark sobre el
mismo universo. Un nodo `m5.xlarge`, terminación automática y corridas medidas
limitan la duración, pero no garantizan por sí solos el gasto total de US$ 1.
La restricción vigente de región `us-east-2` se conserva.

## Consecuencia

- [CLAUDE.md](../../CLAUDE.md) admite EMR transitorio como excepción a la
  gestión exclusiva mediante `infra/cloudformation/stack.yaml`.
- La futura definición de CLI/pasos debe fijar un nodo `m5.xlarge`,
  `--auto-terminate` y `ActionOnFailure=TERMINATE_CLUSTER`; registrar logs,
  duración, costo estimado antes de ejecutar y costo real después.
- Si la cuenta o IAM impiden ejecutar, registrar el bloqueo. No eludir las
  denegaciones ni certificar una corrida inexistente.
- Este cambio no despliega recursos, no cambia políticas IAM, no actualiza el
  plan de la cuenta y no implementa los módulos o pasos EMR. Esas entregas
  corresponden al paquete de MapReduce y al administrador autorizado.
- Comprobar el cierre del clúster y la limpieza de los recursos de la corrida;
  comprimir GDELT y aplicar su borrado después del filtrado.

---

> ## Revisión pendiente (anotado el 2026-11-26 por Calidad y documentación)
>
> **Esta excepción puede haber quedado sin uso y la decisión no es de este rol.**
>
> El informe v16 ya no contempla la ruta EMR. En su tabla de alternativas descarta «Amazon
> EMR, EMR Serverless o Databricks» porque «EMR corre sobre instancias EC2 que cobran por
> hora y la política base las deniega», y su módulo **M5 · MapReduce** es Apache Spark 3.5
> en AWS Glue con la API de DataFrames. El commit W05 de Ingeniería de datos implementa ese
> patrón en Spark SQL hacia `gold/mr/`.
>
> Quedan dos cosas por decidir, y las dos tocan `CLAUDE.md`, que no es de este rol:
>
> 1. **La excepción de EMR.** `CLAUDE.md` cita este ADR como excepción viva a la regla de
>    recursos exclusivamente por CloudFormation. Si se da por cerrada la ruta EMR, hay que
>    marcar este ADR como reemplazado **y** quitar esa excepción de `CLAUDE.md` en el mismo
>    cambio, para que no apunte a una decisión muerta.
> 2. **La evidencia de Hadoop Streaming.** `CLAUDE.md` exige que «Hadoop MapReduce se ejecuta
>    con Hadoop Streaming, mapper, reducer y combiner» y que «una operación sobre RDD de
>    Spark no sustituye esa evidencia». Eso contradice al v16 y al W05. Es un requisito del
>    curso, no una preferencia técnica, así que debe resolverlo Coordinación con Ingeniería
>    de datos antes del hito final.
>
> Hasta que se decida, **este ADR se deja tal cual**: no se borra ni se cambia su estado.
