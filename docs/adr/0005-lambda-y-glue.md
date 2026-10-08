# 0005 · Lambda para Bronze→Silver; Glue Spark para Silver→Gold y escalabilidad

- **Fecha:** Oct-2026
- **Estado:** aceptada
- **Fuente:** informe, sección 0.4 (bitácora de decisiones)

## Contexto
Decisión registrada en la bitácora del informe.

## Alternativas evaluadas
Todo en Glue; Amazon EMR

## Criterio
Lambda entra en la capa gratuita; EMR cobra por hora de clúster

## Consecuencia
Glue se usa en pocas corridas medidas. El código de conciliación tiene motor `pandas` y `spark` con el mismo contrato
