# IAM del proyecto: usuarios, políticas y roles de servicio

Responde al informe v6 (Tabla 3.12), al hallazgo C7 y al WP 1.6 del Plan de Corrección. Decisión registrada en el [ADR 0012](../../docs/adr/0012-usuarios-por-persona-permisos-por-funcion.md). Guía paso a paso en `docs/guias/Guia_Implementacion_IAM.pdf`.

Cuenta de trabajo del proyecto en AWS, región `us-east-2` ([ADR 0011](../../docs/adr/0011-region-us-east-2.md)).

## Políticas administradas por el equipo

Cada archivo `.json` de esta carpeta es la política tal como está creada en la cuenta. Si se cambia una en la consola, se actualiza aquí en el mismo pull request.

| Política | Se adjunta a | Permite | No permite |
|---|---|---|---|
| `costagas-base` | Los cuatro usuarios de persona | Gestionar su propia contraseña, clave de acceso y MFA | Actuar fuera de `us-east-2`; EC2, NAT Gateway, QuickSight, KMS propio, crawlers, EMR Serverless, SageMaker, Redshift, RDS; crear usuarios o políticas; ACL públicas |
| `costagas-ingenieria-datos` | Rol de ingeniería de datos | Desplegar el stack, todo el lago, Lambda, Glue, Athena, la sal en Parameter Store, roles `costagas-*` | Crear usuarios; entregar roles a servicios que no sean Lambda o Glue |
| `costagas-analitica` | Rol de análisis y modelado | Leer `silver/` y `gold/`, consultar en el workgroup `costagas-wg`, lanzar jobs de Glue existentes | Leer `bronze/`; escribir en Silver o Gold |
| `costagas-gobierno` | Coordinación; calidad y documentación | Leer `silver/` y `gold/`, Athena, costos, y ver IAM, CloudFormation, Lambda, Glue y logs | Modificar recursos; leer `bronze/` |
| `costagas-powerbi-lectura` | Usuario técnico `svc-powerbi` (Semana 12) | Leer `gold/` y consultar en el workgroup | Todo lo demás |
| `costagas-emr-opcional` | Nadie por ahora | Lanzar un clúster transitorio de EMR | EMR está bloqueado en el plan gratuito; no se ha creado en la cuenta |

Las denegaciones de `costagas-base` son explícitas, así que prevalecen sobre cualquier permiso de las demás.

## Usuarios y asignación por período

Un usuario de IAM por persona; ninguno compartido. Los permisos siguen a la función, y la función rota en la Semana 8.

| Usuario | Semanas 2–7 | Semanas 8–14 |
|---|---|---|
| `frank.trelles` | `costagas-ingenieria-datos` | `costagas-analitica` |
| `wilson.mirano` | `costagas-analitica` | `costagas-ingenieria-datos` |
| `anghelo.alcantara` | `costagas-gobierno` | `costagas-gobierno` |
| `bruno.ordonez` | `costagas-gobierno` | `costagas-gobierno` |

Todos tienen además `costagas-base`. El titular de la cuenta entra con su AWS Builder ID y MFA, sin claves de acceso, y es el único que crea usuarios y adjunta políticas.

### Rotación de la Semana 8

1. El titular intercambia las políticas de función de `frank.trelles` y `wilson.mirano`.
2. Ambos borran su clave de acceso y crean una nueva.
3. Se repiten las pruebas de `docs/evidencias/seguridad/` con los perfiles nuevos.
4. Se registra en un ADR con captura de los permisos antes y después.

## Roles de servicio

Los crea `infra/cloudformation/stack.yaml`; no se crean a mano.

| Rol | Lo asume | Lee | Escribe |
|---|---|---|---|
| `costagas-lambda-role` | Lambda `costagas-bronze-to-silver` | `bronze/interno/*`, la sal en Parameter Store | `silver/*` |
| `costagas-glue-role` | Jobs de Glue `costagas-*` | `bronze/externo/*`, `silver/*`, `gold/*`, `scaletest/*`, el bucket de código | `silver/*`, `gold/*`, `sparkui/*` |

## Equivalencia con la ruta on-premise

| Ruta A (Hadoop) | Ruta B (este proyecto) |
|---|---|
| Kerberos: autenticación de cada usuario | Usuarios de IAM con MFA; Builder ID del titular |
| Apache Ranger: permisos por ruta de HDFS | Políticas de IAM por prefijo del bucket (`bronze/`, `silver/`, `gold/`) |
| Cifrado de HDFS en reposo y en tránsito | SSE-S3 (AES-256) y política del bucket que rechaza tráfico sin TLS |
| Cuotas de YARN | Workgroup de Athena con límite de 1 GB por consulta; Glue con 2 trabajadores y 15 minutos; presupuesto de US$ 1 |

## Limitaciones de la cuenta

- El plan gratuito asigna el proyecto a una sola región (`us-east-2`) y bloquea EMR e IAM Identity Center.
- La consola del plan oculta la pantalla de Budgets; el presupuesto se crea desde CloudFormation.
- `costagas-ingenieria-datos` se validó con `validate-template`; su primer despliegue completo confirmará si falta alguna acción.
