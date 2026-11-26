# Costa Gas Trujillo · Big Data para la detección de anomalías en GLP

Plataforma en AWS (S3 como data lake medallón, Lambda, Glue Spark, Athena) que concilia por unidad vehicular el GLP comprado, despachado y vendido por la planta Trujillo (2016–2024, piloto 2020) y emite alertas respaldadas por registros públicos. Tope de costo: **US$ 1**.
UPAO 2026-20 · Big Data y Analítica de Datos · Plan paso a paso en [PLAN.md](PLAN.md) · Reglas para Claude Code en [CLAUDE.md](CLAUDE.md)

## Arquitectura

```
entrega empresa / fuentes públicas
        │  src/ingest/ (ELT, manifiesto SHA-256)
        ▼
bronze/   inmutable, schema-on-read, fecha_carga=YYYY-MM-DD
        │  src/bronze_to_silver/handler.py   Lambda · pandas · escalado vertical
        ▼
silver/   esquema declarado, limpio, seudonimizado, Parquet Snappy anio/mes
        │  src/silver_to_gold/conciliacion.py  Glue · PySpark · escalado horizontal
        ▼
gold/     fact_conciliacion_unidad, fact_alerta, unidad_mes
        │  src/signals/ · src/models/        reglas S1–S10 · MAD · IsolationForest/LOF
        ▼
Athena (sql/athena/) → Power BI Desktop
```

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

El pipeline genera la muestra (`data/sample/entrega/`), la carga a `data/lake/bronze/`, procesa Silver y Gold y calcula las señales y modelos v2 con módulos `*_fixture.py`. La línea base y el top sintéticos usan nombres `*_fixture`; no certifican el modelo v6.

Para Gold con Spark local (Java 17 + Python 3.11): `pip install -r requirements-spark.txt` y `python -m src.pipeline --motor spark`.

## Modelo base v6 · WP 0.8

El catálogo [S1–S12](src/signals/catalogo.yaml) y las seis señales S2, S3, S6, S7,
S9 y S11 siguen el informe v6. El modelo usa el z robusto de
`log(S/ combustible por tonelada)`, separado por rol. S8 queda no resoluble y
S12 corresponde al WP 0.11.

Con las tablas normalizadas Silver/Gold disponibles en `LAKE_URI`:

```bash
python -m src.models.evaluacion_base --tipo-datos muestra_enmascarada
```

Genera top, expedientes para revisión ciega y métricas. La precisión documental,
recuperación y cobertura permanecen `null` hasta disponer de revisión independiente,
casos conocidos y diferencias atribuibles. Los contratos, las tablas faltantes y
el comando posterior a la revisión están en
[la evidencia del WP 0.8](docs/evidencias/wp_0.8_modelo_base.md).

## Parametrización

Todo se controla con variables de `.env` (ver [.env.example](.env.example)) leídas en [src/common/config.py](src/common/config.py):

| Grupo | Variables |
|---|---|
| Lago | `LAKE_URI` (`file://data/lake` ↔ `s3://…`), `AWS_REGION`, `ATHENA_WORKGROUP` |
| Alcance | `PLANTA`, `ANIO_INI`, `ANIO_FIN`, `ANIO_PILOTO` |
| Spark | `SPARK_SHUFFLE_PARTITIONS`, `SALTING_BUCKETS` |
| Calidad | `META_PLACA_VALIDA`, `META_KG_EN_RANGO`, `TOL_TIPO_CAMBIO` |
| Modelos | `UMBRAL_Z_MAD`, `TOP_K`, `MUESTRA_REVISION_ALEATORIA`, `TOL_PRECIO_COMPRA`, `TOL_PRECIO_S10`, `MERMA_TECNICA`, `PRECIO_REF_KG`, `SEMILLA` |
| Metas documentales WP 0.8 | `META_PRECISION_DOCUMENTAL`, `META_RECUPERACION_CASOS`, `META_KG_CUBIERTOS`, `META_ALERTAS_MES` |

Las columnas de cada archivo interno se declaran en [src/common/schemas.py](src/common/schemas.py). Si un archivo real trae otro encabezado, se ajusta solo ahí.

## Ejecución por pasos

| Paso | Comando |
|---|---|
| 3.2 Ingesta a Bronze | `python -m src.ingest.internos --origen data/raw` |
| 3.3.3 Bronze → Silver | se dispara por evento S3 (Lambda) o lo llama `src.pipeline` |
| 3.3.6 Conciliación | `python -m src.silver_to_gold.conciliacion --motor pandas --anio 2020` |
| 4.2 Señales | `python -m src.signals.senales` |
| 4.2.2–4.2.4 Modelo base v6 | `python -m src.models.evaluacion_base --tipo-datos muestra_enmascarada` |
| 2.2.1 Reproceso | `python -m src.common.reproceso --fuente aba_02 --anio 2020 --mes 7` |
| 3.7 Escalabilidad | `python -m src.scaletest.replicar --factores 1 10 --motores pandas spark` |
| 1.7.1 Volumen | `python -m src.quality.volumen` |
| 1.4.1 Línea base | `python -m src.quality.linea_base` |

## Despliegue en AWS (costo estimado < US$ 0.10 por corrida completa)

```bash
SUFIJO=equipo01 CORREOS=correo@ejemplo.com ./infra/scripts/deploy.sh
```

```bash
LAKE_URI=s3://costagas-trujillo-lake-equipo01 python -m sql.athena.crear_tablas
```

Al terminar: `SUFIJO=equipo01 ./infra/scripts/teardown.sh`.

## Técnicas del curso

Mapa S1–S5 → archivo y línea en [docs/tecnicas_curso.md](docs/tecnicas_curso.md).

# BIG_DATA-PROYECTO-COSTA-GAS
