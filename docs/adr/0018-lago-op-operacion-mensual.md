# 0018 · Lago `op/` aparte para la operación mensual

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)

## Contexto
El sistema tiene que demostrar dos cosas distintas con los mismos archivos. Por un lado, la
**carga histórica**: todas las entregas de la empresa procesadas de una vez, que es la base de
las cifras del informe. Por otro, la **operación con entregas mensuales**: los mismos archivos
cargados en orden cronológico, mes a mes (unidades de ene-2020 a feb-2021 y facturas de feb-2022
a jul-2023), para enseñar qué habría visto la planta en cada momento y qué pagos se habrían
retenido el día de pagarlos.

Si las dos escriben en el mismo lago se pisan: la operación mensual sobrescribiría Gold con el
estado parcial de un mes y las cifras del informe dejarían de ser reproducibles. Y al revés, un
reproceso histórico borraría la secuencia mes a mes.

## Alternativas evaluadas
1. **Un solo lago con una columna o partición que distinga el origen.** Descartada: obliga a
   filtrar en cada consulta, en cada vista y en cada panel de Grafana, y basta olvidar un filtro
   para mezclar las cifras.
2. **Un segundo bucket para la operación.** Descartada: duplica políticas, notificaciones,
   alarmas y ciclos de vida, y rompe la regla de un solo bucket con prefijos
   ([ADR 0004](0004-un-bucket-con-prefijos.md)).
3. **Un prefijo `op/` en el mismo bucket, con su propio `LAKE_URI`.** Elegida.

## Criterio
- Toda ruta del lago se construye con `src/common/rutas.py` desde `LAKE_URI`, así que cambiar la
  raíz basta para mover una corrida entera de lago: no hace falta tocar el código del job.
- Se reutilizan las mismas funciones, el mismo job y las mismas reglas; lo único que cambia es
  el parámetro `--LAKE_URI` que el flujo le pasa al job.
- Respeta el bucket único con prefijos y no añade recursos con costo fijo.
- La separación es física, no un filtro que alguien pueda olvidar.

## Consecuencia
- La operación mensual corre con
  `LAKE_URI = s3://costagas-trujillo-lake-<sufijo>/op/`, aparte de la carga histórica.
- Notificaciones de S3 en `op/landing/` y `op/bronze/interno/`; regla `costagas-op-actualizado`
  sobre los prefijos internos de `op/silver/`; flujo `costagas-flujo-operacion`, que pasa ese
  `LAKE_URI` al job. Son las mismas Lambdas y el mismo job de Gold.
- Ciclo de vida de **30 días** en el prefijo `op/`
  ([`infra/cloudformation/stack.yaml`](../../infra/cloudformation/stack.yaml)): es material de
  demostración, no el lago de verdad, y no debe acumular costo de almacenamiento.
- Las cifras del informe salen **solo** de la carga histórica. Lo que produce `op/` se reporta
  aparte, como la operación mes a mes, y nunca se mezcla con las tablas de resultados.
- El flujo de la operación hereda el límite de una corrida a la vez sin reintentos
  ([ADR 0017](0017-cola-de-corridas-maxretries-0.md)).
