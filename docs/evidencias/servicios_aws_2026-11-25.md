# Disponibilidad de los servicios del informe v15 en la cuenta (25/11/2026)

Prueba de solo lectura hecha por el titular desde CloudShell, en `us-east-2`. Para cada servicio se lanzó una llamada de listado y se buscaron denegaciones (`AccessDenied`, política de control de servicios o servicio no habilitado). Captura: `capturas/2026-11-25_servicios/01_servicios_aws_disponibles.jpg`.

| Servicio | Resultado | Uso en el informe |
|---|---|---|
| S3, Lambda, Glue (jobs y flujos de trabajo), Athena | Disponible | Lago, ingesta, Gold y consulta |
| EventBridge y EventBridge Scheduler | Disponible | Flujo por eventos y tareas programadas |
| SNS, SQS y CloudWatch | Disponible | Ambiente automatizado (Tabla 2.11) |
| Cognito y CloudFront | Disponible | Portal web (M9) |
| IAM (proveedores OIDC), SSM Parameter Store | Disponible | CI/CD por OIDC; sal y clave de YouTube |
| Budgets y Cost Explorer | Disponible | Control de costo |
| CloudFormation | Disponible. El stack `costagas-trujillo` está en `UPDATE_COMPLETE` desde el 11/10/2026 | Infraestructura como código |
| Cola de corridas de Glue | La CLI de la cuenta incluye `--job-run-queuing-enabled`, y `cfn-lint` valida `JobRunQueuingEnabled` | A1 del v15 |
| Proveedor OIDC de GitHub | Todavía no existe; lo crea el stack | Tabla 2.12 |
| Costo acumulado | Octubre: US$ 0.00 · noviembre (hasta el 25): US$ 0.00 | Tope de US$ 1 |

## Grafana Cloud

El complemento **Amazon Athena** (`grafana-athena-datasource`, versión 3.4.2, de Grafana Labs, actualizado el 2/11/2026) está disponible en Grafana Cloud. Según su documentación de configuración, en Grafana Cloud se autentica por defecto con **clave de acceso**, el esquema del usuario `svc-dashboard`. La política mínima que recomienda Grafana está cubierta por `costagas-dashboard-lectura`, que da acceso de lectura a Athena y a Glue y escritura solo en `athena-results/`.

Para usarlo falta:

1. Crear la cuenta gratuita en Grafana Cloud.
2. Crear la clave de acceso de `svc-dashboard` (la crea el titular).
3. Agregar el origen de datos Amazon Athena con la región `us-east-2`, el catálogo `AwsDataCatalog`, la base `costagas_gold` y el workgroup `costagas-wg`.
