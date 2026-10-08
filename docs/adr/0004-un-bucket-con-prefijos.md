# 0004 · Un bucket con prefijos bronze/, silver/, gold/

- **Fecha:** Oct-2026
- **Estado:** aceptada
- **Fuente:** informe, sección 0.4 (bitácora de decisiones)

## Contexto
Decisión registrada en la bitácora del informe.

## Alternativas evaluadas
Un bucket por capa

## Criterio
Una sola política y un solo registro de accesos

## Consecuencia
Los permisos se definen por prefijo (ver `infra/cloudformation/stack.yaml`)
