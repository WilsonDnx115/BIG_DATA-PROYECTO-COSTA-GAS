# 0021 · La Lambda de limpieza con 3 008 MB

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Evidencia:** [ajustes del 26/11/2026](../evidencias/ajustes_aws_2026-11-26.md), sección 2.1

## Contexto
`costagas-bronze-to-silver` lee cada archivo de Bronze con pandas y escribe su Parquet en
Silver. Un Excel no se puede leer en trozos: `openpyxl` lo descomprime entero en memoria, y el
DataFrame que sale ocupa bastante más que el archivo. **El Excel más pesado de la entrega tiene
62 MB**, y varios libros traen decenas de hojas.

Con 1 024 MB la función se queda sin memoria justo en los archivos que más importan. El
despliegue del 25/11 dejó la función en 1 024 MB aunque la plantilla traía 3 008 desde el WP
0.2, porque CloudFormation conservó el valor anterior del parámetro `LambdaMemoriaMB`.

## Alternativas evaluadas
1. **Mantener 1 024 MB.** Descartada: no alcanza para los libros grandes, que son precisamente
   los de compras y ventas.
2. **Mover la limpieza de los archivos pesados a Glue.** Descartada: una corrida de Glue por
   archivo cuesta mucho más que una invocación de Lambda y añade latencia a un flujo que debe
   cerrar en menos de 5 minutos. Glue se reserva para lo que de verdad necesita Spark
   (resoluciones en PDF y GDELT).
3. **Subir a 3 008 MB.** Elegida.

## Criterio
- Cubre con margen el archivo de 62 MB y el DataFrame que produce.
- En Lambda la CPU escala con la memoria, así que además termina antes: más memoria por el mismo
  trabajo puede costar lo mismo o menos.
- **Sigue dentro de la capa gratuita.** El cálculo de la Tabla 2.7 pasa a invocaciones de 3 GB,
  180 000 GB-s, por debajo del umbral gratuito mensual.
- `LambdaMemoriaMB` solo admite 1 024, 3 008 y 10 240 MB. 10 240 queda reservado para la
  prueba de escalabilidad (3.7), así que 3 008 es el escalón que corresponde a la operación.

## Consecuencia
- `LambdaMemoriaMB` queda en **3 008** y el tiempo máximo en 900 segundos
  ([`infra/cloudformation/stack.yaml`](../../infra/cloudformation/stack.yaml)).
- Aplicado el 26/11/2026 con el change set `memoria-lambda-3008`, que solo cambia `MemorySize` y
  reevalúa el bucket sin reemplazar nada. Resultado `UPDATE_COMPLETE`, `MemorySize 3008`, con
  las notificaciones del bucket intactas.
- El informe debe decir **3 008 MB** en las Tablas 2.2c (módulo M2) y 2.7c, y actualizar el
  cálculo de la Tabla 2.7 a 180 000 GB-s.
- Queda una lección para el equipo: `aws cloudformation deploy` **conserva el valor anterior de
  un parámetro** si no se le pasa de nuevo. Un cambio de valor por defecto en la plantilla no
  llega solo a la cuenta; hay que verificarlo en el recurso después de desplegar.
