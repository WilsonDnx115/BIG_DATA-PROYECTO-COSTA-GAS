# Evidencia · Despliegue de la funcion de ingesta (W03)

**Estado: PENDIENTE DE EJECUCION.** Este documento es el guion del despliegue y la
plantilla de su evidencia. Las casillas se marcan y las capturas se agregan
**despues** de la corrida real, con la fecha y la cuenta que la hizo. Mientras
sigan vacias, no hay recurso desplegado: lo unico verificado hoy es el analisis
estatico de la plantilla.

- **Responsable:** Wilson Mirano Rios (ingenieria de datos), perfil `costagas`
- **Region:** us-east-2 (ADR 0011) · **Stack:** `costagas-trujillo`
- **Commit de la plantilla:** se anota al ejecutar (`git rev-parse --short HEAD`)

## Lo que agrega este despliegue

| Recurso | Nombre | Para que |
|---|---|---|
| `AWS::IAM::Role` | `costagas-ingesta-role` | Lee `landing/` y `op/landing/`; escribe `bronze/`, `op/bronze/` y `_manifests/`; publica en la cola de fallas |
| `AWS::Lambda::Function` | `costagas-ingesta` | Python 3.12, 512 MB, 300 s, `/tmp` de 1 GB. Handler `src.ingest.lambda_ingesta.lambda_handler` |
| `AWS::Lambda::Permission` | `PermisoS3InvocaIngesta` | Deja que S3 invoque la funcion |
| Notificaciones del bucket | prefijos `landing/` y `op/landing/` | Cada objeto nuevo dispara la ingesta |
| `AWS::Lambda::EventInvokeConfig` | `DestinoFallasIngesta` | 2 reintentos y, si no, a `costagas-eventos-fallidos` |
| `AWS::CloudWatch::Alarm` | `costagas-error-ingesta` | `Errors >= 1` en 5 min -> tema `costagas-alertas-operacion` |

El tema SNS y la cola SQS ya existian (despliegue del 25/11/2026): este cambio
solo los referencia.

## Costo

**US$ 0.00.** Lambda, SQS, SNS y las alarmas de CloudWatch estan dentro de las
capas siempre gratuitas (1 M de invocaciones y 400 000 GB-s de Lambda al mes,
1 M de solicitudes SQS, 1 000 correos SNS, 10 alarmas). Los 35 archivos de la
entrega consumen del orden de 5 250 GB-s. CloudFormation no cobra por el stack.

## Verificacion estatica (hecha el 26/11/2026)

- [x] `python -m pytest -q`: 114 pruebas pasan, 2 omitidas (pyspark no instalado).
- [x] `cfn-lint` sobre `infra/cloudformation/stack.yaml` acotado a us-east-2:
      **0 hallazgos**. La plantilla pasa de 36 a 41 recursos.

## Pasos del despliegue (pendientes)

- [ ] 1. Empaquetar y subir el codigo, y crear el change set sin ejecutarlo:

      ./infra/scripts/deploy.sh --validar
      aws cloudformation deploy --stack-name costagas-trujillo \
        --template-file infra/cloudformation/stack.yaml \
        --capabilities CAPABILITY_NAMED_IAM --no-execute-changeset --profile costagas

- [ ] 2. Revisar el change set (`describe-change-set`): ningun `Remove` y ningun
      `Replacement: True` inesperado. **Atencion:** el cambio toca
      `NotificationConfiguration` del bucket del lago; se espera `Modify` sobre
      `Lago`, nunca `Replacement: True`. Captura en
      `capturas/despliegue_ingesta/02_change_set.jpg`.
- [ ] 3. Ejecutar el change set y esperar `UPDATE_COMPLETE`.
      Captura: `03_stack_update_complete.jpg`.
- [ ] 4. Prueba de extremo a extremo con un archivo de `data/sample/`:

      aws s3 cp data/sample/entrega/<archivo>.xlsx s3://costagas-trujillo-lake-<sufijo>/landing/interno/ --sse AES256

      Comprobar que aparece en `bronze/interno/estructurado/<dominio>/...` y que
      `_manifests/fecha_carga=<fecha>/` tiene su entrada con el SHA-256.
      Captura: `04_bronze_y_manifiesto.jpg`.
- [ ] 5. Repetir el mismo archivo y comprobar en los registros de CloudWatch el
      estado `duplicado`, sin copia nueva en Bronze.
      Captura: `05_duplicado_en_logs.jpg`.
- [ ] 6. Subir un archivo con una extension no admitida (por ejemplo `.txt`) y
      comprobar que el evento termina en `costagas-eventos-fallidos`.
      Captura: `06_cola_de_fallas.jpg`.

## Resultado

| Paso | Fecha | Observacion |
|---|---|---|
| | | |
