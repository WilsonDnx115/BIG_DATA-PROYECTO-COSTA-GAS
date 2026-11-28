# Plan de pruebas del sistema (Tabla 2.9): resultado de cada fila

- **Fecha:** 2026-11-28
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** ejecución local de la suite, consulta del historial de GitHub Actions y
  verificación en AWS con el perfil de **gobierno**, que es de solo lectura. Las filas que exigen
  Gold no se pudieron ejecutar y se dice por qué.
- **Cumple** AR17 en la parte que no depende de la corrida de Gold. Las filas que faltan se
  completan cuando corra `costagas-gold-conciliacion`
  ([estado](../estado_y_pendientes.md)).

Las trece filas son las de la **Tabla 2.9 del informe v17** (Anexo C.4). Ninguna queda sin
resultado: o está verificada, o dice qué falta y quién la ejecuta.

## Resultado

| Prueba | Criterio de aceptación | Resultado | Fecha | Evidencia |
|---|---|---|---|---|
| Unitarias e integración | Todas las pruebas pasan | **Cumple.** 674 pruebas pasan y 123 se omiten en local por `pyspark`; en `ci` corren en Ubuntu. El `ci` de `main` posterior al PR #31 terminó en success | 28/11/2026 | `python -m pytest`; run `46119527587` de GitHub Actions |
| Mínimo privilegio | `AccessDenied` con *explicit deny* | **Cumple.** `lambda:ListFunctions` en `us-east-1` responde «not authorized … **with an explicit deny** in an identity-based policy: `costagas-base`». Y `s3:ListBucket` sobre `bronze/` responde «no identity-based policy allows», que es la negación por omisión del prefijo | 28/11/2026 | [abajo](#mínimo-privilegio-medido-el-28112026) |
| Ingesta | El archivo nuevo llega a `bronze/` con su hash; el repetido se rechaza | **No verificable con el perfil de gobierno:** no tiene `s3:ListBucket` sobre `landing/` ni `bronze/`, que es justamente lo que exige la fila anterior. La ejecuta Ingeniería de datos con su perfil | — | — |
| Silver | Conteos iguales a los del diccionario v3.0 | **Cumple.** Los 26 controles de `silver/_control/` de la corrida del 28/11 dan las diez tablas en estado `ok` y sus filas efectivas coinciden con los contratos en nueve de las diez tablas; la décima, `distribuidores`, se corrigió en el README con la cifra medida | 28/11/2026 | [calidad de la carga inicial](calidad_carga_inicial.md) |
| Idempotencia y reproceso | Sin filas duplicadas; mismos conteos | **Probada en local, no corrida en AWS.** `tests/test_pipeline.py`, `tests/test_silver.py` y `tests/test_lambda_ingesta.py` la cubren sobre la muestra; en el lago exige escribir en `landing/`, que el perfil de gobierno no puede | 28/11/2026 (local) | `python -m pytest -q tests/test_pipeline.py tests/test_silver.py tests/test_lambda_ingesta.py` |
| Conciliación en Gold | Diferencia de 0 kg; may-2020 como mes completo | **No superada todavía.** `costagas-gold-conciliacion` corrió cinco veces el 28/11 entre las 03:27 y las 03:45: cuatro fallaron y ninguna terminó en `SUCCEEDED` | 28/11/2026 | [estado](../estado_y_pendientes.md) |
| Validación cruzada | Mismos totales por mes y producto entre DataFrames y RDD | **Probada en local, no corrida en AWS.** La igualdad entre `mapreduce_sql.construir` y `mapear_reducir_rdd` está cubierta por pruebas; sobre datos reales espera la corrida de Gold | 28/11/2026 (local) | [ADR 0029](../adr/0029-mapreduce-con-spark-sin-emr.md) |
| Optimización | `PushedFilters`, `BroadcastHashJoin` y menos bytes leídos | **No corrida.** Exige el plan físico de una corrida de Glue y bytes escaneados en Athena, y el perfil de gobierno no puede consultar Athena | — | [abajo](#lo-que-athena-no-deja-hacer-con-este-perfil) |
| Escalabilidad | Punto de quiebre de Lambda y ganancia de Glue registrados | **Medida sobre réplicas, no sobre la entrega real** | 2026-11-25 | [escalabilidad.md](escalabilidad.md) |
| Modelos | Metas de la Tabla 4.7 | **No corrida.** La validación documental ciega de las 20 alertas de mayor puntaje necesita `fact_alerta` con datos, que sale de Gold | — | [estado](../estado_y_pendientes.md) |
| Extremo a extremo | El cambio aparece en Grafana en menos de 5 minutos | **No corrida.** La cadena se interrumpe en Gold; además `costagas-silver-actualizado` está en DISABLED a propósito mientras dure la carga inicial ([ADR 0020](../adr/0020-regla-gold-prefijos-internos.md)) | — | — |
| Disparadores sin bucle | Solo el archivo interno lanza el flujo de Gold | **No verificable con el perfil de gobierno:** exige escribir en `gold/mr/` y en `silver/entorno/`. La ejecuta Ingeniería de datos | — | — |
| Consulta y tablero | Menos de 5 s y 10 MB; mismos valores que la consulta | **No corrida.** Requiere Athena, que este perfil no puede ejecutar, y vistas de Gold con datos | — | [abajo](#lo-que-athena-no-deja-hacer-con-este-perfil) |
| Portal web | La carga aparece en el estado; sin token responde 401 | **No verificada.** Las cuatro Lambdas del portal están desplegadas, pero la prueba exige iniciar sesión en Cognito y subir un archivo | — | — |

Resumen: **dos filas cumplen con evidencia medida sobre AWS** (mínimo privilegio y Silver), **dos
están probadas en local** a la espera de la corrida, **una está medida sobre réplicas**
(escalabilidad) y **ocho esperan** la corrida de Gold o un perfil con permiso de escritura.

## Mínimo privilegio, medido el 28/11/2026

Con la clave del usuario `anghelo.alcantara` (rol de gobierno), en la cuenta `765656213018`:

```powershell
aws lambda list-functions --region us-east-1 --profile costagas-gobierno
```

> An error occurred (AccessDeniedException) when calling the ListFunctions operation: User:
> arn:aws:iam::765656213018:user/anghelo.alcantara is not authorized to perform:
> lambda:ListFunctions on resource: * **with an explicit deny in an identity-based policy**:
> arn:aws:iam::765656213018:policy/costagas-base

Es exactamente el criterio de aceptación de la fila: fuera de `us-east-2` la política base niega
explícitamente, no simplemente omite el permiso.

```powershell
aws s3 ls s3://costagas-trujillo-lake-upao-g4-2026/bronze/ --profile costagas-gobierno
```

> An error occurred (AccessDenied) … is not authorized to perform: s3:ListBucket … because no
> identity-based policy allows the s3:ListBucket action

El mismo perfil sí lee `silver/` y `gold/`, que son los prefijos que le corresponden. La
separación por prefijo del ADR 0012 funciona como está diseñada.

## Lo que Athena no deja hacer con este perfil

```powershell
aws athena start-query-execution --work-group costagas-wg --query-string "SELECT count(*) FROM costagas_silver.gastos" --profile costagas-gobierno
```

> An error occurred (InvalidRequestException) … `INSUFFICIENT_PERMISSIONS`: Unable to
> verify/create output bucket costagas-trujillo-lake-upao-g4-2026

El workgroup `costagas-wg` escribe sus resultados en `athena-results/`, y el perfil de gobierno no
tiene `s3:PutObject` sobre ese prefijo. Afecta a tres filas de esta tabla —optimización, consulta y
tablero, y la parte de Athena de la conciliación— y se resuelve agregando `s3:ListBucket` sobre el
bucket y `s3:PutObject`/`GetObject` sobre `athena-results/*` a la política del rol de gobierno.
Mientras tanto, las métricas de calidad salen de `silver/_control/`, que es la fuente oficial.
