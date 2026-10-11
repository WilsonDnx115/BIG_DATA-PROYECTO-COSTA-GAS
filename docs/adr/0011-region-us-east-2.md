# 0011 · Región us-east-2 (Ohio) en lugar de us-east-1

- **Fecha:** 2026-10-10
- **Estado:** aceptada
- **Reemplaza a:** la regla «región única us-east-1» del plan original y de la Tabla 2.7 del informe

## Contexto
El plan y el informe fijaban `us-east-1` (Norte de Virginia). Al abrir la cuenta de AWS del equipo con el plan gratuito, la consola respondió: «Your project is assigned to Estados Unidos (Ohio) us-east-2». Para usar otra región hay que pasar al plan de pago y activar las «características avanzadas», lo que además elimina el límite de gasto que impone el plan.

## Alternativas evaluadas
1. **Actualizar el plan para usar us-east-1.** Descartada: quita el límite de gasto del plan y no aporta nada al proyecto.
2. **Usar us-east-2.** Elegida.

## Criterio
- Todos los servicios del hito (S3, Lambda, Glue 5.0, Athena, Systems Manager, CloudFormation) están disponibles en `us-east-2`.
- Los precios de referencia son prácticamente los mismos que en `us-east-1`.
- Se conserva el límite de gasto del plan gratuito, coherente con el tope de US$ 1.

## Consecuencia
- `AWS_REGION` por defecto pasa a `us-east-2` en `src/common/config.py`, `.env.example` e `infra/scripts/`.
- La capa de pandas de `infra/cloudformation/stack.yaml` usa el ARN de `us-east-2`.
- La política `costagas-base` deniega toda acción fuera de `us-east-2` (ver `infra/iam/`).
- El informe debe actualizar la región en la Tabla 2.7 y en la sección 2.4.
- EMR sigue bloqueado por el plan; la decisión sobre MapReduce se registra en un ADR aparte.
