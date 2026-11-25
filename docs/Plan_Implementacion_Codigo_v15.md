# Plan de implementación del código · lo que falta para que el repositorio sea el informe v15

**Fecha:** 25/11/2026 · **Informe de referencia:** `Informe_BigData_CostaGas_Trujillo_v15` · **Último commit:** `ca17f42` (bases de AWS).
**Regla:** el informe es la fuente de verdad. Cada archivo de este plan existe porque una tabla o una figura del informe lo describe; se indica cuál.

Leyenda de la columna «Quién»:
- **Claude:** lo escribe Claude (código, pruebas, DDL, plantilla) y lo despliega desde CloudShell con la sesión del titular, después de indicar el costo y recibir el «sí».
- **Titular:** lo hace el titular, por razones de seguridad (claves, contraseñas, cuentas) o porque toca los datos reales de `data/raw/`, que Claude nunca lee.
- **Frank:** confirma con el código cifras que dependen de los datos reales.

---

## 0. Lo que ya está hecho (no se repite)

| Parte | Estado |
|---|---|
| **IAM** | Rotación de la Semana 8, políticas v3/v4, `costagas-dashboard-lectura`, `svc-dashboard` y CloudFront exceptuado en la política base |
| **Stack `costagas-trujillo` (36 recursos)** | Bucket del lago con EventBridge y ciclos de vida (`sim/`, `op/`); Lambda `costagas-bronze-to-silver` con destino de fallas; SNS de operación y de negocio; SQS; 2 alarmas; regla `costagas-glue-fallido`; flujo `costagas-flujo-gold` con su disparador; regla `costagas-silver-actualizado` (**DISABLED**); job de Gold (STANDARD, cola de corridas, Iceberg, `MaxRetries` 0); portal (bucket, CloudFront, OAC, Cognito); OIDC y `costagas-github-deploy`; bases Silver y Gold; workgroup; presupuesto |
| **Código existente que se reutiliza** | `src/common/*` (config, rutas, limpieza, seudonimización, esquemas, muestra sintética); `src/silver/*` (contratos y procesamiento en Lambda); contratos de 5 tablas Silver; `src/silver_to_gold/mapreduce.py` (versión con RDD); `src/signals/senales.py` (señales en pandas); `src/models/base_mad.py` (z robusto); pruebas en `tests/` |
| **Evidencias** | `docs/evidencias/seguridad/iam_2026-11-25.md`, `servicios_aws_2026-11-25.md`, `despliegue_2026-11-25.md` y `capturas/` |

---

## 1. Ruta mínima para la sustentación (prioridad 1)

Es lo indispensable para mostrar «una carga llega sola al tablero» y el modelo S12 funcionando. **Costo estimado: ≈ US$ 0.20.**

| # | Qué | Archivos | Servicios | Informe | Quién |
|---|---|---|---|---|---|
| 1.1 | **Lambda de ingesta:** `landing/` → `bronze/`, huella SHA-256, manifiesto, rechazo de duplicados, dominio según `_archivos.yaml` | `src/ingest/lambda_ingesta.py` (reutiliza `entrega.py` y `manifest.py`); `tests/test_lambda_ingesta.py` | Lambda, S3 (notificación en `landing/` y `op/landing/`), SQS de fallas | M1; Tabla 2.7c (fila de ingesta) | Claude |
| 1.2 | **Recursos de ingesta en el stack:** función `costagas-ingesta` (512 MB), rol `costagas-ingesta-role`, notificación de S3, alarma `costagas-error-ingesta` y destino de fallas | `infra/cloudformation/stack.yaml` | CloudFormation | Tablas 2.7c, 2.7d y 2.11 | Claude |
| 1.3 | **Job de Gold:** lectura de Silver por catálogo; patrón MapReduce con Spark SQL hacia `gold/mr/`; `fact_balance_planta` (KPI 1 como diferencia bruta); `fact_unidad_mes`; señales S1-S12 en Spark; `calidad_silver`; escritura Iceberg; cubo; marcadores; argumento `--modo` | `src/glue/gold_job.py` (nuevo script del job, en lugar de `conciliacion.py`); `src/glue/senales_spark.py`; `tests/test_gold_job.py` con PySpark local sobre `data/sample` | Glue 5.0, Spark SQL, Iceberg, catálogo de Glue | 3.3, 3.5, 4.2 y 4.4; Tablas 3.6b, 4.3, 4.9 y 4.10; Anexo C.2 | Claude |
| 1.4 | **DDL de Gold en Iceberg y vistas:** `fact_balance_planta`, `fact_unidad_mes`, `fact_alerta`, `revision_alerta`, `fact_serie`, `fact_operacion`, `modelo_factura`, `mercado_mes`, `calidad_silver` y 6 dimensiones, todas con `vacuum_max_snapshot_age_seconds`; vistas `v_alerta`, `v_kpi_1` a `v_kpi_5`, `v_cubo_unidad` y `v_semaforo_unidades` | `sql/athena/ddl/gold_*.sql`, `sql/athena/vistas/*.sql`; `sql/athena/crear_tablas.py` (actualizado) | Athena, Iceberg | Tablas 4.9 y 4.10; 3.5 | Claude |
| 1.5 | **Carga inicial:** subir los 35 archivos a `landing/interno/` con la regla de Gold desactivada | Comando `aws s3 cp` (Claude lo prepara) | S3 | X2 del v15 | **Titular**, porque son los datos reales |
| 1.6 | **Primera corrida de Gold y activación de la regla:** una corrida manual en FLEX y luego `EstadoReglaGold=ENABLED` | Comandos en CloudShell | Glue, EventBridge | Tabla 2.7a | Claude, con aprobación |
| 1.7 | **Tablero en Grafana:** 6 páginas (Resumen, Balance y unidades, Bandeja, Mercado, Semáforo, Revisión ciega) exportadas a JSON | `dashboards/grafana/*.json` | Grafana Cloud y Athena | Tablas 1.6c y 4.11 | Claude arma los JSON; **el titular** crea la cuenta y la clave de `svc-dashboard` (guía en `docs/guias/`) |

## 2. Sistema de aprendizaje automático (prioridad 2)

**Costo:** el entrenamiento corre dentro de las corridas de Glue que ya cuenta la Tabla 2.7a (reentrenamiento en FLEX, 2 corridas). La validación del detector usa Lambda, dentro de la capa gratuita.

| # | Qué | Archivos | Servicios | Informe | Quién |
|---|---|---|---|---|---|
| 2.1 | **Tabla de modelado y etiqueta S12:** cruce full_outer entre tesorería y logística; variables calculadas a la fecha de la factura (mediana móvil de 90 días); fecha de madurez de la etiqueta (vencimiento + 30 días) | `src/glue/modelo_factura.py`; contrato nuevo `contracts/tesoreria.yaml` (`1. PEDIDOS GLP`: fecha de pago y «VENCE») | Glue, Iceberg | 4.3 («Cómo se obtiene la etiqueta» y «Madurez»); Tabla 4.6 | Claude |
| 2.2 | **Clasificador S12:** Pipeline (StringIndexer y VectorAssembler); Random Forest (100 árboles, profundidad 6, `weightCol`); regresión logística L-BFGS como referencia; árbol de decisión para las reglas | `src/models/mllib.py` → `pipeline_s12()`, `entrenar_clasificador_s12()` | Spark MLlib en Glue | Tablas 4.5, 4.6, 4.6a y 4.6b; Anexo C.3 | Claude |
| 2.3 | **Evaluación honesta:** umbral elegido en los meses de validación; evaluación hacia adelante desde ago-2022; métricas acumuladas con bootstrap; PR-AUC; comparación con la regla S2 + S6 | `src/models/mllib.py` → `evaluar_s12()`; `src/models/metricas.py` | MLlib, pandas en el driver | Tablas 4.7 y 4.8e; 4.3 (C3 y C4) | Claude |
| 2.4 | **Puntuación al llegar a logística, registro de modelos y deriva:** escribe `fact_alerta` con MERGE; publica en SNS de negocio sobre el umbral vigente; guarda el modelo en `gold/_modelos/s12/corrida=<fecha>/` con `vigente.json` (modelo y umbral); compara retador contra vigente; PSI trimestral con al menos 100 facturas | `src/models/registro.py`, `src/models/deriva.py` | S3, Iceberg, SNS | 4.3 («Arquitectura del sistema de ML»); Tablas 4.8b y 4.8c; Figura 4.2 | Claude |
| 2.5 | **Regresión del combustible (S9):** kg movidos y rol; sin escalar; exclusión mensual; RMSE frente al modelo trivial | `src/models/mllib.py` → `regresion_combustible()` | MLlib | Tabla 4.6b; Anexo C.3 | Claude |
| 2.6 | **Isolation Forest y LOF:** scikit-learn en el driver y puntuación con `mapInPandas`, por unidad-mes y por factura. **Reemplaza** `src/models/definitivo.py` y `artifacts/modelo_definitivo.json`, que hoy son de LOF | `src/models/rareza.py`; `--additional-python-modules scikit-learn==1.5.2` en el job | Glue (driver y executors) | Tablas 4.5 y 4.8c | Claude |
| 2.7 | **Detector de desvíos persistentes:** valor esperado frente a los pares; CUSUM de un solo lado y EWMA; punto de cambio; umbral calibrado con el escenario A en semanas y en meses; presupuesto de 12 falsas alarmas al año; compensación de pares redigitados | `src/models/detector.py`; `src/glue/fact_serie.py`; `tests/test_detector.py` | Glue, Iceberg | 4.3 (detector); Tablas 4.8g y 4.8h; Figura 4.5 | Claude |
| 2.8 | **Convergencia y riesgo de sustracción:** puntaje ponderado por grado de evidencia; Random Forest con variables de contexto (no las de la regla); solo donde las ventanas se cruzan | `src/models/convergencia.py` | MLlib | 4.3 (C5); Figura 4.4 | Claude |
| 2.9 | **Validación del detector:** escenarios A y B, 100 semillas en lotes de 10, solo en `sim/` | `src/sim/validacion.py` (usa `generar_sim.py` del paquete sintético); Lambda `costagas-validacion-detector` en el stack | Lambda (3 GB, 15 min), S3 `sim/` | Tabla 4.8h | Claude. **Anghelo** define los robos sin revelarlos (inyección ciega) |
| 2.10 | **Reentrenamiento programado:** Scheduler semanal, con `start-job-run --execution-class FLEX --arguments --modo entrenar` | `stack.yaml` (programa `costagas-reentrenamiento-semanal` y rol `costagas-scheduler-role`) | EventBridge Scheduler | 4.3 («Cuándo se reentrena») | Claude |

## 3. Controles preventivos y operación mensual (prioridad 3)

| # | Qué | Archivos | Servicios | Informe | Quién |
|---|---|---|---|---|---|
| 3.1 | **Control previo al pago:** rojo, ámbar o verde por factura en menos de 5 s | `src/controles/control_pago.py`; Lambda con URL de función y rol `costagas-control-role` | Lambda, Athena | Tabla 4.8i; Figura 4.6 | Claude |
| 3.2 | **Semáforo diario a las 6:30** (SNS y Grafana) | `src/controles/semaforo_diario.py`; programa de Scheduler | Lambda, Scheduler, SNS | Tabla 4.8i | Claude |
| 3.3 | **Revisión por cliente** antes de la siguiente entrega (S5 y S10) | Dentro de `gold_job.py` y `v_semaforo_unidades` | Glue, Athena | Tabla 4.8i, carril 3 | Claude |
| 3.4 | **Entregas mensuales:** de Bronze a `op/landing/`, mes a mes y con el formato de cada año | `src/operacion/entregas_mensuales.py`; Lambda `costagas-entregas-mensuales`; notificaciones `op/`; regla `costagas-op-actualizado`; flujo `costagas-flujo-operacion` | Lambda, S3, EventBridge, Glue | 4.3 («Operación con entregas mensuales»); Tabla 2.7c | Claude |
| 3.5 | **Medición de 32 meses** (`--modo operacion`) hacia `fact_operacion` | `src/glue/operacion.py` | Glue FLEX | Tabla 4.8e | Claude (una corrida de US$ 0.044, con aprobación) |

## 4. Fuentes externas (prioridad 4)

| # | Qué | Archivos | Servicios | Informe | Quién |
|---|---|---|---|---|---|
| 4.1 | **Extractores:** BCRP (diario), Facilito y YouTube (semanales), GDELT (carga histórica) y resoluciones | `src/extractores/{bcrp,facilito,youtube,gdelt,resoluciones}.py`; contratos `contracts/entorno_*.yaml`; Lambdas en el stack | Lambda, Scheduler | M1; Tabla 3.1 | Claude. **El titular** guarda la clave de YouTube en `/costagas/youtube/api_key` |
| 4.2 | **Job de externos:** pdfplumber, LDA con MLlib, conteo de GDELT con MapReduce; salida en `silver/entorno/` y `gold/mr/`; programa mensual en FLEX | `src/glue/externos_job.py`; job `costagas-externos` en el stack | Glue FLEX | M4; 3.3; Tabla 1.6b | Claude |

## 5. Portal, mantenimiento y CI/CD (prioridad 5)

| # | Qué | Archivos | Servicios | Informe | Quién |
|---|---|---|---|---|---|
| 5.1 | **Página del portal:** inicio de sesión con Cognito (SRP), subida con URL prefirmada, estado por capa, resumen de KPI, formulario de revisión | `portal/index.html`, `portal/app.js` | S3 del portal, CloudFront | M9 y M10; 4.4 | Claude |
| 5.2 | **Funciones del portal:** firmar, estado, kpis y revisión. Validan el JWT (firma, emisor y vigencia) y usan CORS limitado al dominio de CloudFront. La revisión solo inserta en `revision_alerta` | `src/portal/{firmar,estado,kpis,revision}.py`; Lambdas con URL de función y rol `costagas-portal-role` en el stack | Lambda | Tablas 2.7c, 2.7d y 3.12 | Claude |
| 5.3 | **Usuarios del portal** (equipo, gerencia y docente) | Consola de Cognito | Cognito | M9 | **Titular**: cada usuario define su contraseña |
| 5.4 | **Mantenimiento de Iceberg:** `OPTIMIZE` y `VACUUM` semanales | `src/mantenimiento/iceberg.py`; Lambda y programa de Scheduler | Lambda, Athena | 3.5; Tabla 4.8c | Claude |
| 5.5 | **CI:** pytest (con PySpark local sobre `data/sample`), cfn-lint y validación de contratos | `.github/workflows/ci.yml` | GitHub Actions | Tabla 2.12 | Claude |
| 5.6 | **CD:** change set por OIDC con aprobación en un `environment` protegido | `.github/workflows/cd.yml` | GitHub Actions, CloudFormation | Tabla 2.12 | Claude. **El titular** configura el `environment` en GitHub |

## 6. Coherencia del repositorio con el informe (prioridad 1, rápido)

| Qué | Archivo |
|---|---|
| Power BI → Grafana Cloud; S1-S10 → S1-S12; costo US$ 0.89 | `README.md` |
| `us-east-1` → `us-east-2`; pasos de los WP nuevos | `PLAN.md` |
| ADR nuevos (desde la plantilla `0000`):<br>• 0013 YouTube Data API (reemplaza 0007 yt-dlp)<br>• 0014 Grafana Cloud (reemplaza 0010 Power BI)<br>• 0015 cola de corridas con `MaxRetries` 0<br>• 0016 lago `op/` para la operación mensual<br>• 0017 `revision_alerta` de solo inserciones<br>• 0018 regla de Gold solo con prefijos internos | `docs/adr/` |
| Parámetros nuevos: `MADUREZ_DIAS=30`, `UMBRAL_PRECISION=0.70`, `PSI_UMBRAL=0.2`, `PSI_MIN_OBS=100`, `FALSAS_ALARMAS_ANIO=12` y `merma_tecnica_pct` (con fuente) | `src/common/config.py` |
| Contrato de gastos (F20) | `contracts/gastos.yaml` |
| Técnicas del curso con archivo y línea | `docs/tecnicas_curso.md` |

## 7. Correcciones al informe que salen de la implementación

1. **Glue con cola de corridas exige `MaxRetries = 0`.** Afecta a las Tablas 2.7c, 2.11 y 2.9 y a la nota de recuperación. La corrida fallida avisa por SNS y la siguiente retoma lo pendiente con los marcadores.
2. **La Lambda de limpieza tiene 3 008 MB** (un Excel pesa 62 MB). El informe dice 1 024 MB. Afecta a las Tablas 2.2c y 2.7c.
3. **Tablas de resultados.** Cuando corra el código, se llenan con cifras reales las Tablas 3.10, 3.11, 4.4, 4.7, 4.8e y 4.8h y la columna «Estado» de la 6.1b.

## 8. Cifras que **Frank** confirma con el código

1. El Spearman entre kg y combustible (0.66) y los S/ 54.7 por tonelada.
2. Las ventas por unidad cubren cerca del 75 % del envasado.
3. Las unidades-mes: 146 con venta, 82 de reparto con venta y combustible, y 48 con venta y sin combustible.
4. Cerca de 1 000 líneas de venta por semana.
5. Cuántas de las 77 etiquetas S12 están maduras.

## 9. Orden de trabajo propuesto

1. **Bloque 6 y 1.1-1.4:** coherencia del repositorio, ingesta, Gold y DDL. Es código y plantilla, sin costo hasta desplegar.
2. **1.5-1.7:** carga inicial (titular), primera corrida y Grafana. Es la demostración de la sustentación.
3. **Bloque 2:** el sistema de ML completo, con su evidencia de métricas.
4. **Bloques 3, 4 y 5.**
5. **Bloques 7 y 8:** volver al informe con las cifras reales.

Cada bloque termina con pruebas locales (`python -m pytest -q`), `cfn-lint`, un change set revisado, el despliegue, las capturas en `docs/evidencias/capturas/` y un commit que hace Frank.
