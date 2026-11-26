# 0011 · Medir la línea base antes de limpiar los datos

- **Fecha:** 2026-10-10 (America/Lima)
- **Estado:** propuesta
- **Responsable:** integrante que revise el PR del paso 1.4.1

## Contexto

El paso 1.4.1 exige medir la calidad inicial desde Bronze. El script anterior
leía Silver, donde la conversión, el relleno de documentos y la deduplicación
ya habían alterado las incidencias. El informe v6 también corrige las cifras
de referencia del plan y distingue problemas catalogados de ocurrencias.

## Alternativas evaluadas

1. Continuar midiendo Silver: reproducible, pero oculta defectos del origen.
2. Sumar todas las versiones de Bronze: conserva defectos, pero una reentrega
   del mismo archivo aumenta artificialmente el volumen y las incidencias.
3. Medir Bronze conservando sus filas y seleccionando la última versión de
   cada archivo lógico; permitir seleccionar una fecha de carga explícita.

## Criterio

Se implementa la tercera opción. Conserva errores y duplicados de la entrega,
evita contar sus reentregas y permite reproducir un corte. No requiere cambios
de infraestructura ni recursos AWS. Las entradas deben cumplir contratos
explícitos; no se infieren encabezados ni se rellenan los datos faltantes.

## Consecuencia

La línea base publica únicamente agregados y cobertura. Las fuentes ausentes
se representan como `null`; todas ausentes producen un error. Los contratos
actuales cubren la muestra v2 y un contrato local de producción basado en los
conceptos de F36, aún sin validar sus encabezados reales. Un renombrado se
considera otro archivo lógico; la selección por defecto puede combinar fechas
de carga distintas, que quedan registradas. No certifica consistencia entre
entregas: para un corte común se debe usar `--fecha-carga`.

Se conservan por separado las referencias de PLAN.md y del informe v6.
Ocurrencias de controles y problemas catalogados no se comparan como la misma
métrica. Un residuo cero tampoco se interpreta como una medición física.

Implementación: [linea_base.py](../../src/quality/linea_base.py).
Definiciones, reproducción y límites: [linea_base.md](../evidencias/linea_base.md).
