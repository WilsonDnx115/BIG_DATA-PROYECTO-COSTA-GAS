# Costa Gas Trujillo · Big Data para la detección de anomalías en GLP

Plataforma en AWS (S3 como data lake medallón, Lambda, Glue Spark, Athena) que concilia por
unidad vehicular el GLP comprado, despachado y vendido por la planta Trujillo (2016–2024,
piloto 2020) y emite alertas respaldadas por registros públicos.
Región **`us-east-2`** ([ADR 0011](docs/adr/0011-region-us-east-2.md)) · costo estimado
**US$ 0.89** sobre un tope de **US$ 1**.

UPAO 2026-20 · Big Data y Analítica de Datos · Plan paso a paso en [PLAN.md](PLAN.md) ·
Reglas para Claude Code en [CLAUDE.md](CLAUDE.md)

## Arquitectura

```
landing/
   │  Lambda costagas-ingesta              manifiesto SHA-256, rechaza el archivo repetido
   ▼
bronze/                                     copia inmutable, schema-on-read, fecha_carga=YYYY-MM-DD
   │  Lambda costagas-bronze-to-silver      3 008 MB, pandas, un contrato YAML por tabla
   ▼
silver/                                     esquema declarado, seudonimizado, Parquet Snappy
   │  EventBridge                           solo los prefijos internos de silver/ (10 eventos o 60 s)
   ▼
flujo costagas-flujo-gold
   │  Glue 5.0 · Spark 3.5 · gold_job.py    MapReduce en Spark SQL, MLlib y MERGE en Iceberg
   ▼
gold/                                       balance de planta, unidad-mes, señales S1–S12, modelo en estrella
   │
   ▼
Athena ──┬─▶ Grafana Cloud                  tablero de gerencia, refresco cada minuto
         └─▶ portal web                     CloudFront + Cognito: carga, seguimiento y revisión ciega
```

La regla de EventBridge escucha **solo** los prefijos internos de `silver/`: lo que escriben los
jobs de Glue (`gold/`, `gold/mr/` y `silver/entorno/`) no la dispara, de modo que una corrida
nunca lanza otra. La meta es que un archivo nuevo se vea en el tablero en menos de 5 minutos.

## Inicio rápido (local, con muestra sintética)

```bash
python -m pip install -r requirements.txt
```

```bash
cp .env.example .env
```

```bash
python -m src.pipeline --regenerar-muestra
```

```bash
python -m pytest -q
```

El pipeline genera la muestra (`data/sample/entrega/`), la carga a `data/lake/bronze/`, procesa
Silver y Gold y calcula las señales y modelos v2 con módulos `*_fixture.py`. La línea base y el
top sintéticos usan nombres `*_fixture`; no certifican el modelo v6.

Para Gold con Spark local (Java 17 + Python 3.11): `pip install -r requirements-spark.txt` y
`python -m src.pipeline --motor spark`.

## Señales S1–S12

El catálogo [S1–S12](src/signals/catalogo.yaml) declara por señal su resolución, fuente, ventana,
estado y evidencia. Las doce tienen implementación en Spark
(`src/glue/senales_spark.py`); **S8** está marcada `no_ejecutar` en el catálogo porque ventas y
compras no comparten ventana con código SCOP, y **S12** es la etiqueta documental del modelo
definitivo (4.3).

El modelo base usa el z robusto de `log(S/ combustible por tonelada)`, separado por rol, con
`abs(z) > 3.5`. Con las tablas Silver/Gold disponibles en `LAKE_URI`:

```bash
python -m src.models.evaluacion_base --tipo-datos muestra_enmascarada
```

Genera top, expedientes para revisión ciega y métricas. La precisión documental, recuperación y
cobertura permanecen `null` hasta disponer de revisión independiente, casos conocidos y
diferencias atribuibles. Los contratos, las tablas faltantes y el comando posterior a la revisión
están en [la evidencia del WP 0.8](docs/evidencias/wp_0.8_modelo_base.md).

## Parametrización

Todo se controla con variables de `.env` (ver [.env.example](.env.example)) leídas en
[src/common/config.py](src/common/config.py):

| Grupo | Variables |
|---|---|
| Lago | `LAKE_URI` (`file://data/lake` ↔ `s3://…`), `AWS_REGION`, `ATHENA_WORKGROUP` |
| Alcance | `PLANTA`, `ANIO_INI`, `ANIO_FIN`, `ANIO_PILOTO` |
| Spark | `SPARK_SHUFFLE_PARTITIONS`, `SALTING_BUCKETS`, `TAMANO_OBJETIVO_MB` |
| Calidad | `META_PLACA_VALIDA`, `META_KG_EN_RANGO`, `TOL_TIPO_CAMBIO`, `TOL_RESIDUO_STOCK` |
| Modelo base | `UMBRAL_Z_MAD`, `TOP_K`, `MUESTRA_REVISION_ALEATORIA`, `TOL_PRECIO_COMPRA`, `TOL_PRECIO_S10`, `MERMA_TECNICA`, `PRECIO_REF_KG`, `SEMILLA` |
| Metas documentales WP 0.8 | `META_PRECISION_DOCUMENTAL`, `META_RECUPERACION_CASOS`, `META_KG_CUBIERTOS`, `META_ALERTAS_MES` |
| Modelo definitivo S12 | `MADUREZ_DIAS`, `META_PRECISION`, `META_AUC`, `RF_ARBOLES`, `RF_PROFUNDIDAD` |
| Deriva y detector | `PSI_UMBRAL`, `PSI_MIN_OBS`, `PSI_BINS`, `FALSAS_ALARMAS_ANIO`, `SEMILLAS_DETECTOR`, `LOTE_SEMILLAS` |

Las columnas de cada archivo interno se declaran en
[src/common/schemas.py](src/common/schemas.py). Si un archivo real trae otro encabezado, se
ajusta solo ahí.

## Ejecución por pasos

| Paso | Comando |
|---|---|
| 3.2 Ingesta a Bronze | `python -m src.ingest.internos --origen data/raw` |
| 3.3.3 Bronze → Silver | se dispara por evento de S3 (Lambda) o lo llama `src.pipeline` |
| 3.3 Gold | lo reescribe el flujo `costagas-flujo-gold` (Glue); en local, `python -m src.pipeline --motor spark` |
| 4.2 Señales | `python -m src.signals.senales` |
| 4.2.2–4.2.4 Modelo base | `python -m src.models.evaluacion_base --tipo-datos muestra_enmascarada` |
| 2.2.1 Reproceso | `python -m src.common.reproceso --fuente aba_02 --anio 2020 --mes 7` |
| 3.7 Escalabilidad | `python -m src.scaletest.replicar --factores 1 10 --motores pandas spark` |
| 1.7.1 Volumen | `python -m src.quality.volumen` |
| 1.4.1 Línea base | `python -m src.quality.linea_base` |

## Despliegue en AWS

Costo estimado de la plataforma completa: **US$ 0.89**, con margen de 0.11 para reintentos.

```bash
SUFIJO=equipo01 CORREOS=correo@ejemplo.com ./infra/scripts/deploy.sh
```

```bash
LAKE_URI=s3://costagas-trujillo-lake-equipo01 python -m sql.athena.crear_tablas
```

Al terminar: `SUFIJO=equipo01 ./infra/scripts/teardown.sh`.

## Estado real al 28/11/2026

Implementado, probado, desplegado y corrido son cuatro cosas distintas, y esta tabla dice cuál
alcanzó cada parte. El estado completo, con lo que falta y de quién depende, está en
[docs/estado_y_pendientes.md](docs/estado_y_pendientes.md).

| Parte | Hasta dónde llega | Evidencia |
|---|---|---|
| Contratos de las diez tablas Silver | **Corrido** sobre los 35 archivos de la entrega | [contracts/README.md](contracts/README.md) |
| Ingesta y Bronze → Silver en AWS | **Corrido** el 28/11/2026: 26 Parquet y sus controles en `silver/`, las diez tablas en el catálogo `costagas_silver` | [calidad de la carga inicial](docs/evidencias/calidad_carga_inicial.md) |
| Calidad de Silver frente a la Tabla 3.7 | **Medida** sobre la corrida real, por tabla y por fuente | [calidad de la carga inicial](docs/evidencias/calidad_carga_inicial.md) |
| Tablas y vistas de Gold | **Desplegadas**: las trece tablas Iceberg existen y cinco vistas están catalogadas | catálogo `costagas_gold` |
| Job de Gold, KPI, señales y semáforo | **No corrido**: `costagas-gold-conciliacion` no tiene ninguna ejecución y `gold/` no tiene archivos de datos | [docs/estado_y_pendientes.md](docs/estado_y_pendientes.md) |
| Pipeline completo de punta a punta | **Corrido en local** con la muestra sintética; sus cifras no son resultados del negocio | [docs/evidencias/linea_base.md](docs/evidencias/linea_base.md) |
| Modelo base y detector | **Implementados y probados**; su validación con datos reales espera la corrida de Gold | [docs/evidencias/wp_0.8_modelo_base.md](docs/evidencias/wp_0.8_modelo_base.md) |

Mientras Gold no corra, **ninguna cifra de KPI, señal o semáforo puede presentarse como resultado
de la empresa**.

## Equipo y responsabilidades

Los roles rotan en la Semana 8 (informe v16, 0.1). Estas son las responsabilidades de la
**Semana 8 a la 14**, la mitad que cubre este repositorio:

| Integrante | Rol Semanas 8-14 | Qué cuida en el repositorio |
|---|---|---|
| Mirano Ríos, Wilson | Ingeniería de datos | `infra/`, `src/ingest/`, `src/glue/`, `sql/athena/` y el despliegue |
| Trelles Díaz, Frank | Análisis y modelado | `src/models/` (salvo `deriva.py`), `src/signals/` y los parámetros de modelado de `src/common/config.py` |
| Alcántara Pérez, Oftcher Anghelo | Calidad y documentación | `contracts/`, `src/quality/`, `src/sim/`, `src/models/deriva.py`, `docs/adr/`, `docs/modelos/`, `README.md`, `PLAN.md`, `docs/tecnicas_curso.md` y la integración continua |
| Ordóñez Gonzales, Bruno | Coordinación | `docs/evidencias/`, el tablero de Grafana, el portal de revisión ciega y los controles preventivos |

Cada cambio entra por pull request y lo revisa el integrante de apoyo; `main` está protegida.
Las etiquetas de rol por issue están en [docs/equipo.md](docs/equipo.md).

## Técnicas del curso

Cada técnica de ingeniería y de modelado, con su archivo y su línea, en
[docs/tecnicas_curso.md](docs/tecnicas_curso.md).
