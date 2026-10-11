# Despliegue del lago · stack `costagas-trujillo`

- **Fecha:** 2026-10-10
- **Ejecutó:** `frank.trelles` (perfil `costagas`), con `infra/scripts/deploy.sh`
- **Cuenta y región:** 765656213018 · `us-east-2`
- **Sustenta:** WP 0.2 del Plan de Corrección · informe, secciones 2.1 y 3.8

Todas las comprobaciones son consultas de solo lectura hechas después del despliegue.

## Salida del despliegue

```text
>> Identidad: arn:aws:iam::765656213018:user/frank.trelles · región us-east-2
>> Validando plantilla
>> Sal de seudonimización en Parameter Store
>> Bucket de código costagas-code-upao-g4-2026
>> Empaquetando src/ + openpyxl (sin datos ni credenciales)
>> Desplegando stack costagas-trujillo
Waiting for changeset to be created..
Waiting for stack create/update to complete
Successfully created/updated stack - costagas-trujillo
>> Creando prefijos de las capas (2.1.2)
>> Listo. LAKE_URI=s3://costagas-trujillo-lake-upao-g4-2026
```

## Recursos creados (11, todos `CREATE_COMPLETE`)

| Tipo | Nombre |
|---|---|
| Bucket S3 (lago) | `costagas-trujillo-lake-upao-g4-2026` |
| Política del bucket | Rechazo de peticiones sin TLS |
| Función Lambda | `costagas-bronze-to-silver` |
| Permiso de invocación | S3 → Lambda |
| Rol de IAM | `costagas-lambda-role` |
| Rol de IAM | `costagas-glue-role` |
| Job de Glue | `costagas-gold-conciliacion` |
| Base del catálogo | `costagas_silver` |
| Base del catálogo | `costagas_gold` |
| Workgroup de Athena | `costagas-wg` |
| Presupuesto | `costagas-tope-1usd` |

Fuera del stack: el bucket de código `costagas-code-upao-g4-2026` y el parámetro `/costagas/seudonimo/sal` (SecureString, versión 3).

## Verificación de la configuración

| Control | Valor medido | Esperado |
|---|---|---|
| Prefijos del lago | `bronze/ silver/ gold/ _manifests/ scaletest/ athena-results/ sparkui/` | Los 7 |
| Cifrado en reposo | `AES256` (SSE-S3) | SSE-S3 |
| Bloqueo de acceso público | `True True True True` | Los 4 activos |
| Región del bucket | `us-east-2` | `us-east-2` |
| Lambda | `python3.12`, 1 024 MB, 900 s, rol `costagas-lambda-role` | Igual |
| Capa de la Lambda | `AWSSDKPandas-Python312:29` | AWS SDK for pandas |
| Job de Glue | Glue 5.0, `G.1X` × 2, clase `FLEX`, 15 min | Igual |
| Presupuesto | `costagas-tope-1usd` · 1.0 USD · 3 notificaciones | 50 %, 100 % real y 100 % previsto |
| Costo acumulado de octubre | US$ 0 | — |

## Pendiente

- Cada integrante debe confirmar el correo de suscripción a las alertas del presupuesto.
- Prueba de humo: subir un archivo a `bronze/interno/` y comprobar que la Lambda escribe en `silver/`.
- Pruebas de mínimo privilegio con los perfiles de analítica y gobierno (`bronze/` debe devolver `AccessDenied`).
- Crear las tablas de Athena cuando existan los contratos de las tablas Silver.
