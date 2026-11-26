# Auditoría de la cuenta y ajustes en AWS (26/11/2026)

**Quién:** el titular de la cuenta, desde AWS CloudShell (`us-east-2`). **Costo:** US$ 0.00.

## 1. Auditoría de solo lectura

| Revisión | Resultado |
|---|---|
| Stack `costagas-trujillo` | `UPDATE_COMPLETE` |
| Sal de seudonimización | `/costagas/seudonimo/sal` existe en Parameter Store |
| Script del job de Gold | `s3://costagas-code-upao-g4-2026/_code/glue_conciliacion.py` existe. Es el script antiguo y se reemplaza por `gold_job.py` (plan, 1.3) |
| Presupuesto `costagas-tope-1usd` | 3 alertas (50 % y 100 % del gasto real, 100 % del previsto), cada una con 4 correos |
| Workgroup `costagas-wg` | Activo, configuración obligatoria, límite de 1 GB por consulta |
| Bucket del lago | Notificación a la Lambda de limpieza y a EventBridge. El lago está vacío: falta la carga inicial |
| Reglas de EventBridge | `costagas-glue-fallido` ENABLED; `costagas-silver-actualizado` DISABLED |
| SNS | Operación: 3 confirmadas y 1 pendiente. Negocio: 1 pendiente |
| Usuarios de IAM | Ninguno tiene MFA. Las claves de los cuatro integrantes son del 11/10/2026: falta la rotación de la Semana 8. `svc-dashboard` todavía no tiene clave |
| Usuario raíz | **Sin MFA** |
| Cognito `costagas-portal` | 0 usuarios |
| EventBridge Scheduler | 0 programas (necesitan las Lambdas del plan) |

## 2. Ajustes aplicados

1. **Memoria de la Lambda de limpieza: de 1 024 a 3 008 MB.** El despliegue del 25/11 conservó el valor anterior del parámetro `LambdaMemoriaMB`, aunque la plantilla trae 3 008 MB desde el WP 0.2, porque un Excel pesa 62 MB. Se revisó el change set `memoria-lambda-3008` (cambia `MemorySize` de `BronzeToSilver` y reevalúa `Lago`, sin reemplazar nada) y se ejecutó. Resultado: `UPDATE_COMPLETE`, MemorySize 3008, y las notificaciones del bucket intactas. Sigue dentro de la capa gratuita de Lambda.
2. **Tablas de Silver en el catálogo, creadas por DDL en Athena.** Son los 5 DDL generados desde los contratos (`sql/athena/ddl/silver_*.sql`), con `${LAKE}` reemplazado por el lago. Se comprobó que llegaran intactos con su huella MD5 y los 5 terminaron en `SUCCEEDED`: `compras_glp` (28 columnas), `scop` (15), `unidades` (17), `ventas_detalle` (24) y `ventas_unidad_mes` (18). Los DDL antiguos (`01_silver_movimientos` y los `02`/`03` de Gold) **no** se ejecutaron. Captura: `capturas/2026-11-26_ajustes/01_tablas_silver_athena.jpg`.

## 3. Lo que esto pide en el informe (aplicado en el v16)

1. **Tablas 2.2c (M2) y 2.7c:** la Lambda de limpieza tiene **3 008 MB**. En la Tabla 2.7 (costo de Lambda), el cálculo pasa a invocaciones de 3 GB (180 000 GB-s), que siguen en la capa gratuita.
2. **Tabla 2.11 («Avisar al equipo») y política de los temas:** Budgets avisa por correo directo a los cuatro integrantes, no por el tema `costagas-alertas-operacion`. Agregar el tema como suscriptor del presupuesto obligaría a reemplazar el presupuesto en CloudFormation, y el aviso ya llega a las mismas personas. Por coherencia, `stack.yaml` ya no deja publicar a Budgets en el tema; el cambio se aplica en el próximo despliegue.

## 4. Lo que queda para el titular y el equipo

- **Activar el MFA del usuario raíz** (urgente) y el de cada usuario de IAM.
- Rotar las claves de Frank y Wilson.
- Confirmar las 2 suscripciones pendientes.
- Crear la clave de `svc-dashboard` y la cuenta de Grafana.
- Dar de alta a los usuarios de Cognito.
- Hacer la carga inicial.

Los pasos están en `docs/guias/Guia_Equipo_Avisos_y_Grafana.md`.
