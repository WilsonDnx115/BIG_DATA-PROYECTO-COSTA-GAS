# 0006 · Tablas del catálogo creadas por DDL en Athena

- **Fecha:** Oct-2026
- **Estado:** aceptada
- **Fuente:** informe, sección 0.4 (bitácora de decisiones)

## Contexto
Decisión registrada en la bitácora del informe.

## Alternativas evaluadas
Glue crawler

## Criterio
El crawler factura por DPU-hora

## Consecuencia
El esquema queda versionado en `sql/athena/ddl/` con proyección de particiones
