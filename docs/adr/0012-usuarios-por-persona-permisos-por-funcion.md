# 0012 · Un usuario de IAM por persona y permisos por función

- **Fecha:** 2026-10-10
- **Estado:** aceptada
- **Responde a:** informe v6, Tabla 3.12 · Plan de Corrección, hallazgo C7 y WP 1.6

## Contexto
El equipo tiene cuatro integrantes cuyos roles rotan en la Semana 8, y la evaluación final es individual por contribución. La cuenta se abrió con el AWS Builder ID de un integrante, que ya actúa como administrador. Hace falta decidir cuántas identidades hay y qué puede hacer cada una.

## Alternativas evaluadas
1. **Un solo usuario administrador compartido.** Descartada: no deja rastro de quién ejecutó cada acción y expone los datos crudos a todos.
2. **Un usuario por persona con `AdministratorAccess`.** Descartada: contradice el mínimo privilegio de la Tabla 3.12.
3. **IAM Identity Center con conjuntos de permisos.** No disponible: el plan gratuito lo bloquea.
4. **Políticas administradas por AWS** (`AmazonS3ReadOnlyAccess`, `AmazonAthenaFullAccess`…). Descartadas: no distinguen prefijos del bucket, así que no pueden impedir la lectura de Bronze.
5. **Un usuario por persona y una política propia por función.** Elegida.

## Criterio
- **Trazabilidad individual:** CloudTrail registra al usuario de cada acción, como Git registra al autor de cada commit.
- **Mínimo privilegio por capa:** solo ingeniería de datos lee `bronze/`, donde están los datos con nombres y DNI. Análisis y gobierno trabajan sobre `silver/` y `gold/`.
- **Separación de funciones:** quien valida y documenta puede ver todo y no puede modificar nada.
- **Rotación barata:** en la Semana 8 se intercambian dos políticas; no se rediseña nada.

## Consecuencia
- Cuatro usuarios de IAM (`frank.trelles`, `wilson.mirano`, `anghelo.alcantara`, `bruno.ordonez`) y cinco políticas propias, versionadas en `infra/iam/`.
- `costagas-base` aplica a todos y contiene las denegaciones: región única, servicios con costo fijo y gestión de identidades.
- Los roles de servicio de Lambda y Glue se crean desde `infra/cloudformation/stack.yaml` con nombre fijo y acceso por prefijo.
- El control de gasto queda en tres capas: límite del plan gratuito, presupuesto de US$ 1 creado por CloudFormation y denegación de servicios con costo fijo.
- Evidencia de las pruebas en `docs/evidencias/seguridad/`.
- Pendiente: usuario técnico `svc-powerbi` en la Semana 12 y la política opcional de EMR si se actualiza la cuenta.
