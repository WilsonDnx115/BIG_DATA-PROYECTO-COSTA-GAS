# Costa Gas Trujillo · Big Data para la detección de anomalías en GLP

Plataforma en AWS (S3 como data lake medallón, Lambda, Glue Spark, Athena) que concilia por unidad vehicular el GLP comprado, despachado y vendido por la planta Trujillo (2016–2024, piloto 2020) y emite alertas respaldadas por registros públicos. Tope de costo: **US$ 1**.
UPAO 2026-20 · Big Data y Analítica de Datos · Plan paso a paso en [PLAN.md](PLAN.md) · Reglas para Claude Code en [CLAUDE.md](CLAUDE.md).

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

El pipeline genera la muestra (`data/sample/entrega/`), la carga a `data/lake/bronze/`, procesa Silver y Gold, calcula señales y modelos, y deja la evidencia en `docs/evidencias/`.

Para Gold con Spark local (Java 17 + Python 3.11): `pip install -r requirements-spark.txt` y `python -m src.pipeline --motor spark`.

## Parametrización

Todo se controla con variables de `.env` (ver [.env.example](.env.example)) leídas en [src/common/config.py](src/common/config.py):

| Grupo | Variables |
|---|---|
| Lago | `LAKE_URI` (`file://data/lake` ↔ `s3://…`), `AWS_REGION`, `ATHENA_WORKGROUP` |
| Alcance | `PLANTA`, `ANIO_INI`, `ANIO_FIN`, `ANIO_PILOTO` |
| Spark | `SPARK_SHUFFLE_PARTITIONS`, `SALTING_BUCKETS` |
| Calidad | `META_PLACA_VALIDA`, `META_KG_EN_RANGO`, `TOL_TIPO_CAMBIO` |
| Modelos | `UMBRAL_Z_MAD`, `TOP_K`, `TOL_PRECIO_S10`, `MERMA_TECNICA`, `PRECIO_REF_KG`, `SEMILLA` |

Las columnas de cada archivo interno se declaran en [src/common/schemas.py](src/common/schemas.py). Si un archivo real trae otro encabezado, se ajusta solo ahí.

## Ejecución por pasos

| Paso | Comando |
|---|---|
| 3.2 Ingesta a Bronze | `python -m src.ingest.internos --origen data/raw` |
| 3.3.3 Bronze → Silver | se dispara por evento S3 (Lambda) o lo llama `src.pipeline` |
| 3.3.6 Conciliación | `python -m src.silver_to_gold.conciliacion --motor pandas --anio 2020` |
| 4.2 Señales | `python -m src.signals.senales` |
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