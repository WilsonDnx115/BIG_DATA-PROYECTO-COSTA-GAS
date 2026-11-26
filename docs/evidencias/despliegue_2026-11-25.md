# Despliegue del stack `costagas-trujillo` con las bases del informe v15 (25/11/2026)

**Quién:** el titular de la cuenta, desde AWS CloudShell (`us-east-2`).
**Plantilla:** `infra/cloudformation/stack.yaml`. Antes de desplegarla se validó con `cfn-lint`, que no dio ningún error.
**Costo del despliegue:** US$ 0.00. No se lanzó ninguna corrida de Glue y la regla de Gold quedó desactivada.

## Procedimiento

1. **La plantilla viajó intacta a CloudShell.** Se pasó comprimida en base64 y se comprobó que su huella MD5 fuera la del archivo del repositorio, con los saltos de línea normalizados a LF.
2. **Se revisó un change set antes de aplicar.** Con `aws cloudformation deploy --no-execute-changeset` se obtuvieron **25 recursos nuevos y 5 modificados sin reemplazo**, sin ningún borrado. Los parámetros existentes (correos) conservaron su valor.
3. **Primer intento, revertido.** Glue respondió *«Maximum retries was set to 1, must be set to 0 with job run queuing enabled»*. CloudFormation deshizo todo solo (`UPDATE_ROLLBACK_COMPLETE`, 17:22) y la cuenta quedó como antes.
4. **Corrección.** `MaxRetries: 0` en el job. Es una restricción de AWS: la cola de corridas y los reintentos automáticos no se pueden combinar.
5. **Segundo intento.** Mismo change set salvo ese valor. Resultado: **`UPDATE_COMPLETE`**, a las 22:30 UTC (17:30 en Perú). El stack queda con 36 recursos.

## Verificación posterior (solo lectura)

| Recurso | Estado verificado |
|---|---|
| Job `costagas-gold-conciliacion` | Clase STANDARD, MaxRetries 0, MaxConcurrentRuns 1, cola de corridas activa, 2 trabajadores, Iceberg |
| Regla `costagas-silver-actualizado` | **DISABLED**, para la carga inicial (X2). Escucha solo los 7 prefijos internos de Silver (X1) |
| Disparador `costagas-al-actualizar-silver` | Por evento, lotes de 10 eventos o 60 s |
| Regla `costagas-glue-fallido` | ENABLED. Envía al tema de operación |
| Cola `costagas-eventos-fallidos` | Creada (14 días, cifrado administrado) |
| Alarmas `costagas-error-limpieza` y `costagas-eventos-fallidos` | Estado OK |
| Temas SNS | Al desplegar: `costagas-alertas-operacion` con 2 suscripciones confirmadas y 2 pendientes, y `costagas-alertas-negocio` con 1 pendiente. A las 17:40 había 3 confirmadas en operación, y se reenvió la confirmación a la pendiente y a la de negocio |
| Portal | CloudFront `d1zqoo9nh9fg5e.cloudfront.net` **Deployed**; grupo de usuarios de Cognito `costagas-portal` |
| CI/CD | Proveedor OIDC `token.actions.githubusercontent.com` y rol `costagas-github-deploy` |
| Bucket del lago | Notificaciones a EventBridge activas; la notificación a la Lambda de limpieza se mantiene |

Capturas en `capturas/2026-11-25_stack/`, del 01 al 07.

## Cambios que esto pide en el informe

1. **El job de Glue:** «MaxRetries = 1» pasa a **«MaxRetries = 0, porque con la cola de corridas activa Glue no admite reintentos automáticos»**. La recuperación de una corrida fallida queda así: aviso por SNS (`costagas-glue-fallido`) y la siguiente corrida retoma lo pendiente con los marcadores de trabajo. Afecta a las Tablas 2.7c y 2.11 y a la prueba de recuperación de la Tabla 2.9.
2. **La Lambda de limpieza:** este despliegue la dejó con 1 024 MB, porque conservó el valor anterior del parámetro. El 26/11 se subió a 3 008 MB (ver `ajustes_aws_2026-11-26.md`), así que el informe debe decir 3 008 MB.
