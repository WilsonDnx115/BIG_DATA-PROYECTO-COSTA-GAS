# 0017 · Cola de corridas en Glue con MaxRetries 0

- **Fecha:** 2026-11-25
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Evidencia:** [despliegue del 25/11/2026](../evidencias/despliegue_2026-11-25.md), pasos 3 a 5

## Contexto
El job `costagas-gold-conciliacion` se lanza por eventos: EventBridge agrupa los cambios de los
prefijos internos de Silver en lotes de 10 eventos o 60 segundos y dispara el flujo
`costagas-flujo-gold`. Con varias entregas seguidas pueden llegar dos disparos casi juntos, así
que el job se limita a una corrida a la vez (`MaxConcurrentRuns: 1`) y se activa la **cola de
corridas**, para que el segundo disparo espere en vez de perderse.

El plan original pedía además `MaxRetries: 1`, un reintento automático ante fallo. Al desplegar
el stack el 25/11/2026 **AWS rechazó esa combinación**:

> «Maximum retries was set to 1, must be set to 0 with job run queuing enabled»

CloudFormation deshizo el cambio solo (`UPDATE_ROLLBACK_COMPLETE`, 17:22) y la cuenta quedó como
estaba. No es una preferencia del equipo: es una restricción del servicio. Hay que elegir entre
la cola de corridas y los reintentos automáticos.

## Alternativas evaluadas
1. **Reintentos automáticos sin cola de corridas** (`MaxRetries: 1`, sin encolado). Descartada:
   sin cola, un segundo disparo mientras el job corre se pierde, y con una ventana de 60 s para
   agrupar eventos eso es probable en una entrega de varios archivos. Perder una corrida es peor
   que no reintentar: deja Gold desactualizado sin que nadie se entere.
2. **Cola de corridas con `MaxRetries: 0`.** Elegida.
3. **Subir `MaxConcurrentRuns` para no necesitar cola.** Descartada: dos corridas a la vez sobre
   las mismas tablas Iceberg compiten por el `MERGE` y pueden dejar Gold inconsistente; además
   multiplica el gasto de Glue contra un tope de US$ 1.

## Criterio
- No perder un disparo pesa más que reintentar solo: con marcadores de trabajo, lo pendiente no
  se pierde, simplemente se procesa en la corrida siguiente.
- El job se diseña idempotente y escribe Gold con `MERGE` en Iceberg (W04), así que reprocesar
  lo mismo no duplica filas.
- Una corrida a la vez mantiene el costo acotado y evita el conflicto de escritura en Gold.

## Consecuencia
- En [`infra/cloudformation/stack.yaml`](../../infra/cloudformation/stack.yaml) el job queda con
  `MaxRetries: 0`, `ExecutionProperty: { MaxConcurrentRuns: 1 }`, clase `STANDARD` y la cola de
  corridas activa. Hay un comentario en la plantilla que explica por qué, para que nadie lo
  devuelva a 1.
- **La recuperación no es automática, y así debe decirlo el informe.** Una corrida fallida
  dispara la regla `costagas-glue-fallido`, que avisa al tema SNS de operación; la siguiente
  corrida retoma lo pendiente con los marcadores de trabajo.
- Afecta a las Tablas 2.7c y 2.11 del informe y a la prueba de recuperación de la Tabla 2.9, que
  debe describir el aviso por SNS y no un reintento.
- El mismo límite aplica al flujo `costagas-flujo-operacion` del lago `op/`
  ([ADR 0018](0018-lago-op-operacion-mensual.md)).
