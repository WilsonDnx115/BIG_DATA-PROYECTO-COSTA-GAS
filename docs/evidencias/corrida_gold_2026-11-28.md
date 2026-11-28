# Primera corrida de Gold sobre datos reales: qué quedó escrito y qué falta

- **Fecha:** 2026-11-28
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** instantáneas Iceberg de `s3://costagas-trujillo-lake-upao-g4-2026/gold/`, leídas
  con el perfil de gobierno (solo lectura). Las filas de cada tabla salen de `total-records` de su
  **instantánea actual**, que es la cifra que el propio motor registra al confirmar la escritura;
  no de contar archivos, que incluiría instantáneas anteriores.
- **Continúa** [la calidad de la carga inicial](calidad_carga_inicial.md), que midió Silver. Aquí
  se mide Gold.

## La corrida

`costagas-gold-conciliacion` corrió **cinco veces el 28/11/2026** entre las 03:27 y las 03:45
(hora de Lima). **La última terminó en `SUCCEEDED`**; las cuatro anteriores fallaron. Las tablas se
escribieron entre las **08:48:33 y las 08:49:20 UTC**.

Las cinco corridas, porque explican el estado de lo que quedó:

| Hora (Lima) | Error |
|---|---|
| 03:27 | `NotADirectoryError` al leer `src/signals/catalogo.yaml` dentro de `costagas_src.zip` |
| 03:30 | `ValueError: fact_unidad_mes: hay placas sin rol en dim_unidad; se cancela para no inventar el rol` |
| 03:37 | `PATH_NOT_FOUND` de `data/lake/silver/_control/*/*.json`: la ruta del zip en vez de la de S3 |
| 03:40 | `INCONSISTENT_BEHAVIOR_CROSS_VERSION.READ_ANCIENT_DATETIME` leyendo fechas anteriores a 1900 con Spark ≥ 3.0 |
| 03:45 | **`SUCCEEDED`** |

El segundo es el que conviene no perder de vista: el job **se negó a inventar el rol** de una placa
que `dim_unidad` no declaraba. Es exactamente lo que pide `CLAUDE.md` («no inventar datos al
limpiar») y la regla funcionó.

## Lo que quedó escrito

| Tabla | Filas | Archivos | Operación | Hora UTC |
|---|---:|---:|---|---|
| `dim_tiempo` | 108 | 1 | overwrite | 08:48:33 |
| `dim_senal` | 12 | 1 | overwrite | 08:48:38 |
| `dim_persona` | 43 | 1 | overwrite | 08:48:42 |
| `dim_unidad` | 211 | 1 | overwrite | 08:48:48 |
| `dim_producto` | 35 | 1 | overwrite | 08:48:51 |
| `fact_balance_planta` | 57 | 31 | overwrite | 08:48:59 |
| `fact_alerta` | 2 349 | 22 | append | 08:49:14 |
| `fact_unidad_mes` | 287 | 14 | append | 08:49:20 |

Las cinco dimensiones se reescribieron cuatro veces (una por intento que llegó hasta ahí) y **las
cuatro versiones de `dim_unidad` tienen exactamente el mismo conjunto de placas**: la escritura es
determinística, como pide el contrato.

**Siete tablas siguen vacías**, creadas pero sin instantánea: `calidad_silver`, `dim_contraparte`,
`fact_operacion`, `fact_serie`, `mercado_mes`, `modelo_factura` y `revision_alerta`. Las escriben
los modos `entrenar` y `operacion` del job y el portal de revisión, que no se han ejecutado.

## Las 2 349 alertas, por señal

`S12` 1 796, `S10` 457, `S3` 79 y `S2` 17. No hay alertas de `S5`, `S6`, `S7`, `S9` ni `S11`.
Las de S7 y S9 faltan por lo que explica la sección siguiente; S11 no tiene fuente en la entrega
más allá de octubre de 2018 ([evidencia](produccion_diaria_en_la_entrega.md)).

**Una alerta no es un robo confirmado.** Estas 2 349 son candidatas a revisión documental, y su
grado de evidencia lo fija `fact_alerta`; la validación ciega es otra cosa y todavía no se hizo.

## Dos hallazgos que hay que corregir

### 1 · 45 filas de `fact_unidad_mes` no tienen su unidad en `dim_unidad`

Es la prueba de integridad referencial de AR05 (`left_anti` del hecho contra la dimensión debe dar
cero filas) y **hoy no pasa sobre los datos reales**:

- **45 filas huérfanas de 287**, que corresponden a **10 unidades distintas**.
- Son de 2020 (40 filas) y 2021 (5 filas).
- El hecho usa 38 unidades en total, de las cuales **28 sí están** en la dimensión de 211.

Reproducible leyendo la instantánea actual de las dos tablas y comparando `unidad_id` contra
`placa_norm`. Le toca a Ingeniería de datos: o la dimensión incorpora esas diez unidades, o el
hecho las excluye diciéndolo. Mientras tanto, cualquier cruce por unidad pierde esas 45 filas sin
avisar, y por eso no se puede publicar todavía un KPI por unidad.

### 2 · `dim_unidad` tiene 28 placas sin rol

De las 211 placas, **159 son de reparto, 24 de transporte y 28 no tienen rol**. El rol decide qué
volumen se usa en el modelo base —kg vendidos en reparto, kg transportados en transporte—, así que
una placa sin rol no es evaluable. Viene de la calidad medida en Silver: `relacion_unidades` tiene
80.1 % de placas válidas y `soat_2020` 83.7 %
([medición](calidad_carga_inicial.md)).

## El bloqueo por calidad está actuando, y es correcto

Las **287 filas** de `fact_unidad_mes` tienen `estado_puntaje = calidad_fuente_bloqueada` y
`alerta_base = false`. No es un fallo: es `calidad_silver.bloqueos` haciendo lo suyo. `gastos` y
`unidades` incumplen `META_PLACA_VALIDA` (0.98) de la Tabla 3.7, y mientras eso siga así **el
KPI 4 y la señal S9 no se publican**, que es la regla de `CLAUDE.md` sobre no publicar una métrica
de Gold cuando su fuente Silver incumple su contrato.

Para desbloquearlos hay dos caminos, y los dos son decisión del equipo, no de este documento:
subir la tasa de placas válidas en origen, o declarar en el contrato que esas fuentes no aportan
placa y calcular el KPI 4 solo sobre `GASTOS FLOTA`, que es la única hoja de gasto que sí la trae
([evidencia](gastos_posiciones.md)).

## Lo que esta corrida todavía no permite verificar

La conciliación de la Tabla 2.9 pide «diferencia de 0 kg» entre Gold y la suma de Silver **en
Athena**, y el perfil de gobierno no puede ejecutar consultas: `StartQueryExecution` responde
`INSUFFICIENT_PERMISSIONS` porque no tiene `s3:PutObject` sobre `athena-results/`. Queda anotado
en [el plan de pruebas](pruebas_sistema.md).
