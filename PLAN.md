# Plan de implementación con Claude Code
## Big Data y Analítica para la detección de anomalías y prevención de pérdidas operativas en la cadena de distribución de GLP de Grupo Costa Gas (planta Trujillo, 2016–2024)

**Curso:** Big Data y Analítica de Datos · UPAO 2026-20 · Docente: Ms. Armando Caballero Alvarado
**Equipo:** Trelles Díaz Frank · Alcántara Pérez Oftcher Anghelo · Mirano Ríos Wilson · Ordóñez Gonzales Bruno
**Ruta:** B · Nube (AWS) · **Tope de costo:** menos de US$ 1
**Documento base:** `Proyecto_BigData_CostaGas_Trujillo_final.docx` (secciones 0 a 4.4)

Este plan sigue el informe **punto por punto**, del 0.1 al 4.4, sin saltar ninguno. Cada paso indica qué construir, en qué archivos, qué técnica del curso aplica (S1 a S5), qué instrucción darle a Claude Code y cómo saber que está terminado. Las secciones 5, 6 y 7 quedan preparadas para el hito final.

---

## Índice

- [A. Cómo usar este plan con Claude Code](#a-cómo-usar-este-plan-con-claude-code)
- [B. Decisiones técnicas: qué técnica del curso usar en cada caso](#b-decisiones-técnicas-qué-técnica-del-curso-usar-en-cada-caso)
- [C. Estructura del repositorio](#c-estructura-del-repositorio)
- [D. Reglas de costo (obligatorias)](#d-reglas-de-costo-obligatorias)
- [Fase 0 · Ficha y gestión del equipo (0.1–0.4)](#fase-0--ficha-y-gestión-del-equipo-0104)
- [Fase 1 · Empresa, problema y línea base (1.1–1.7)](#fase-1--empresa-problema-y-línea-base-1117)
- [Fase 2 · Arquitectura en AWS (2.1–2.4)](#fase-2--arquitectura-en-aws-2124)
- [Fase 3 · Pipeline de datos (3.1–3.8)](#fase-3--pipeline-de-datos-3138)
- [Fase 4 · Análisis, modelado y consumo (4.1–4.4)](#fase-4--análisis-modelado-y-consumo-4144)
- [Fase 5 · Preparación del hito final (secciones 5, 6 y 7)](#fase-5--preparación-del-hito-final-secciones-5-6-y-7)
- [E. Cierre: verificación, entrega y desmontaje](#e-cierre-verificación-entrega-y-desmontaje)
- [F. Calendario resumido](#f-calendario-resumido)

---

## A. Cómo usar este plan con Claude Code

1. **Crear el repositorio** en GitHub (por ejemplo `costagas-bigdata`), clonarlo y abrir Claude Code en esa carpeta.
2. **Copiar este archivo** a la raíz como `PLAN.md`.
3. **Crear `CLAUDE.md`** (paso 0.1.3) con las reglas del proyecto. Claude Code lo lee al inicio de cada sesión.
4. **Trabajar un paso por sesión.** Ejemplo de instrucción:
   > Lee `PLAN.md` y `CLAUDE.md`. Ejecuta solo el paso 3.3.2. Al terminar, corre las pruebas, muéstrame el criterio de aceptación cumplido y propón el mensaje de commit.
5. **Revisar antes de aceptar.** Claude Code propone; el integrante responsable revisa, ejecuta y hace el commit con su propio usuario. Así el historial refleja la contribución de cada uno (requisito del curso).
6. **Nunca pegar datos reales en el chat ni subirlos al repositorio.** Claude Code trabaja sobre la muestra anonimizada de `data/sample/` y sobre la cuenta de AWS.
7. **Marcar cada paso terminado** en `PLAN.md` (`[x]`) dentro del mismo commit.

> Responsable por defecto de cada fase según el informe (0.1). Semanas 2–7: Frank (ingeniería de datos), Anghelo (coordinación), Wilson (análisis y modelado), Bruno (calidad y documentación). Desde la Semana 8 los roles rotan.

---

## B. Decisiones técnicas: qué técnica del curso usar en cada caso

Estas decisiones aplican lo visto en las sesiones S1 a S5 y eligen, en cada caso, la opción que mejor se ajusta al volumen y al presupuesto del proyecto.

| Necesidad | Opciones vistas en el curso | Elección para Costa Gas | Por qué |
|---|---|---|---|
| Tipo de arquitectura (S1) | Data Warehouse · Data Lake · Lakehouse | **Data Lake en S3 con capas medallón** | Hay datos estructurados, semiestructurados y no estructurados; un DWH no los admite. Un Lakehouse (Iceberg/Delta) añade transacciones ACID que el proyecto no necesita en lotes mensuales. |
| Proceso de carga (S1) | ETL · ELT | **ELT** | Se carga crudo en Bronze y se transforma después; permite reprocesar si cambia una regla. |
| Esquema (S1, S5) | schema-on-read · esquema declarado | **schema-on-read en Bronze; esquema declarado en Silver y Gold** | Bronze acepta todo; Silver y Gold tienen contrato fijo. Declarar el esquema evita la pasada extra de `inferSchema` y los errores de tipo. |
| Almacenamiento (S2) | HDFS · almacenamiento de objetos | **Amazon S3** | Separa almacenamiento de cómputo y replica por sí mismo; HDFS exigiría administrar un clúster. |
| Archivos pequeños (S2) | Dejarlos · compactar | **Compactar en Parquet de ≈ 128 MB** | Miles de JSON de YouTube, Facilito y GDELT generarían una tarea por archivo. |
| Escalado (S1) | Vertical · horizontal | **Vertical (Lambda) para Bronze→Silver; horizontal (Glue Spark) para Silver→Gold, padrón SUNAT y prueba de escalabilidad** | 124 MB caben en una máquina; el padrón (más de 11 millones de filas) y las réplicas 10× y 100× justifican distribuir. |
| Procesamiento distribuido (S3, S4, S5) | MapReduce · RDD · DataFrames/SQL | **DataFrames de PySpark (y SQL en Athena)** | MapReduce escribe a disco entre etapas; con RDD Catalyst no puede optimizar. Con DataFrames se obtienen predicate pushdown, column pruning y partition pruning. La lógica sigue siendo Map → Shuffle → Reduce. |
| Agregación por clave (S3, S4) | groupByKey · reduceByKey/Combiner | **`groupBy().agg()` de DataFrames** | Agrega dentro de cada partición antes del shuffle, igual que el Combiner o `reduceByKey`. |
| Uniones (S5) | inner · left_outer · left_semi · left_anti · full_outer | **Según la pregunta** (Tabla 3.6 del informe) | `left_anti` encuentra compras sin orden SCOP y ventas sin compra; `left_semi` filtra unidades habilitadas sin traer columnas. |
| Tabla pequeña en un join (S4, S5) | join normal · broadcast | **`broadcast()`** para flota, productos y RUC del maestro | Evita el shuffle de la tabla grande. |
| Reutilizar un resultado (S4) | recalcular · `cache()` | **`cache()`** de la conciliación | Se usa en varias señales; sin caché cada acción recalcula el DAG. |
| Inspeccionar datos (S4) | `collect()` · `take()` / `show()` | **`take()` / `show()`; nunca `collect()`** | `collect()` lleva todo a la memoria del Driver. |
| Formato de Silver y Gold (S5) | CSV · Parquet | **Parquet + Snappy con `partitionBy("anio","mes")`** | Column pruning y partition pruning; menos bytes escaneados en Athena, que es lo que se paga. |
| Sesgo de datos (S3) | ignorar · AQE · salting | **AQE activado; salting solo si una tarea tarda mucho más que la mediana** | El balón de 10 kg y pocas unidades concentran las operaciones. |
| Consulta analítica | Spark SQL · Athena | **Athena** para el tablero y consultas ad hoc | Paga por consulta; no hay clúster encendido. Mismo plan conceptual que Spark SQL. |
| Modelo base | — | **Reglas determinísticas + puntaje z robusto (MAD, umbral 3.5)** | No hay etiquetas de robo; es explicable a la gerencia. |
| Modelo definitivo | MLlib · scikit-learn | **scikit-learn (Isolation Forest frente a LOF)** sobre un extracto de Gold | La tabla agregada por unidad-mes es pequeña; MLlib no trae Isolation Forest. |

---

## C. Estructura del repositorio

```
costagas-bigdata/
├── CLAUDE.md                      # reglas para Claude Code (paso 0.1.3)
├── PLAN.md                        # este plan
├── README.md                      # reproducir desde cero (paso E.1)
├── .gitignore                     # excluye data/raw, .env, credenciales
├── .env.example                   # variables sin valores reales
├── pyproject.toml / requirements.txt
├── docs/
│   ├── informe/                   # docx del informe y figuras
│   ├── adr/                       # bitácora de decisiones (0.4)
│   ├── fichas/                    # fichas de procedencia (3.1)
│   ├── diccionario/               # diccionario de columnas
│   └── evidencias/                # capturas, explain(), tiempos, costos
├── infra/
│   ├── cloudformation/stack.yaml  # bucket, IAM, Lambda, Glue, Athena, Budgets
│   ├── iam/                       # políticas JSON comentadas
│   └── scripts/                   # deploy.sh, teardown.sh
├── src/
│   ├── common/                    # config, esquemas, utilidades (placa, RUC, hash)
│   ├── ingest/                    # extractores a Bronze (uno por fuente)
│   ├── bronze_to_silver/          # Lambda (pandas)
│   ├── silver_to_gold/            # jobs de Glue (PySpark)
│   ├── quality/                   # reglas y reporte de calidad
│   ├── unstructured/              # PDF, subtítulos, comentarios, prensa
│   ├── signals/                   # S1…S11
│   ├── models/                    # modelo base y definitivo
│   └── scaletest/                 # réplicas 10× y 100×
├── sql/athena/                    # DDL y consultas de KPIs
├── notebooks/                     # EDA (4.1) y modelado (4.2, 4.3)
├── dashboard/                     # .pbix y guía de conexión
├── data/
│   ├── sample/                    # muestra anonimizada (sí se versiona)
│   └── raw/                       # datos reales (NUNCA se versiona)
└── tests/                         # pytest
```

---

## D. Reglas de costo (obligatorias)

| Regla | Cómo se aplica |
|---|---|
| Región única | `us-east-1` en todos los recursos. |
| Presupuesto | AWS Budgets con alertas en US$ 0.50 y US$ 1.00 (paso 2.4.4). |
| Sin servicios con costo fijo | Nada de EC2, EMR, NAT Gateway, QuickSight, claves KMS propias ni Glue crawlers. |
| Glue con freno | Máximo 2 trabajadores salvo en la prueba de escalabilidad (5). Usar clase de ejecución **FLEX** cuando no importe la espera. Timeout de 15 minutos por job. |
| Athena con freno | Workgroup con límite de bytes escaneados por consulta (1 GB) y resultados que se borran a los 7 días. |
| Desarrollo local primero | Cada job de Spark se prueba en local con `pyspark` sobre `data/sample/` antes de correr en Glue. |
| Desmontaje | Al terminar, `infra/scripts/teardown.sh` (paso E.3). |

---

## Fase 0 · Ficha y gestión del equipo (0.1–0.4)

### 0.1 · Equipo y roles

- [ ] **0.1.1 Repositorio y permisos.** Crear el repositorio, invitar a los cuatro integrantes y proteger la rama `main` (cambios por pull request).
  - *Aceptación:* los cuatro pueden hacer push a una rama y abrir un PR.
- [ ] **0.1.2 Roles en el repositorio.** Archivo `docs/equipo.md` con la Tabla de roles del informe (Semanas 2–7 y 8–14) y una etiqueta de GitHub por rol.
- [x] **0.1.3 `CLAUDE.md`.** Reglas que Claude Code debe respetar siempre.
  > **Instrucción para Claude Code:** Crea `CLAUDE.md` con estas reglas: región us-east-1; nunca leer, imprimir ni commitear archivos de `data/raw/`; no crear recursos AWS fuera de `infra/cloudformation/stack.yaml`; no usar `collect()` en Spark; esquemas declarados en `src/common/schemas.py`; nombres en snake_case sin tildes; capas `bronze/`, `silver/`, `gold/`; toda función nueva con prueba en `tests/`; antes de proponer un comando AWS que cree recursos, indicar su costo estimado.
  - *Aceptación:* `CLAUDE.md` en `main`.

### 0.2 · Cronograma

- [ ] **0.2.1 Hitos y semanas en GitHub.** Crear un *milestone* por semana (S2 a S14) con las fechas del informe y un *issue* por cada paso de este plan, asignado a su responsable.
  > **Instrucción para Claude Code:** Lee `PLAN.md` y genera un script `scripts/crear_issues.sh` que use `gh issue create` para crear un issue por cada paso (título = número y nombre del paso, cuerpo = criterio de aceptación, milestone = semana del calendario F).
  - *Aceptación:* tablero de GitHub Projects con todos los pasos.

### 0.3 · Riesgos y mitigación

- [ ] **0.3.1 Registro de riesgos vivo.** `docs/riesgos.md` con la tabla del informe y una columna «última revisión». Se revisa cada viernes.
- [ ] **0.3.2 Alertas automáticas de riesgo de costo.** Se cubre con Budgets (paso 2.4.4).

### 0.4 · Bitácora de decisiones

- [x] **0.4.1 ADR por decisión.** Un archivo por decisión en `docs/adr/` (`0001-ruta-nube-aws.md`, `0002-solo-planta-trujillo.md`, …) con: contexto, alternativas, criterio, consecuencia. Se cargan las diez decisiones ya tomadas en el informe.
  - *Aceptación:* diez ADR y plantilla `0000-plantilla.md` para las nuevas.

---

## Fase 1 · Empresa, problema y línea base (1.1–1.7)

Esta fase deja en el repositorio la evidencia que sostiene las cifras del capítulo 1.

### 1.1 · Resumen ejecutivo
- [ ] **1.1.1** Copiar el resumen a `README.md` (sección «Contexto»). Se reescribe al cierre con los resultados.

### 1.2 · La empresa y su contexto
- [ ] **1.2.1 Fuentes de contexto.** Guardar en `docs/fuentes_contexto.md` los enlaces de Gestión, Infomercado, Panamericana, ProActivo y Facilito con fecha de consulta. No se copian artículos completos (derechos de autor).

### 1.3 · Definición del problema de negocio
- [x] **1.3.1 Hipótesis como código.** `src/common/hipotesis.py` con las cinco hipótesis (H1 a H5) y, para cada una, qué señal o variable la contrasta. Las señales y el EDA las referencian por código.

### 1.4 · Línea base del negocio
- [ ] **1.4.1 Script de línea base.** `src/quality/linea_base.py` que, sobre los datos de Bronze, calcula y guarda en `docs/evidencias/linea_base.json`:
  - días de producción con residuo cero en la ecuación de stock;
  - número de registros SCOP disponibles;
  - número de incidencias por campo clave;
  - porcentaje de RUC/DNI con longitud inválida;
  - rango de precio del balón de 10 kg por canal.
  - *Aceptación:* reproduce los valores del informe (22 de 22 días, 79 registros, 16 incidencias, S/ 17.45–24.15) o documenta la diferencia.

### 1.5 · Objetivos del proyecto
- [ ] **1.5.1 Objetivos medibles.** `docs/objetivos.md` con cada objetivo, su indicador, su meta y el script o consulta que lo mide. Cada indicador debe poder calcularse desde Gold.

### 1.6 · Alcance y limitaciones
- [x] **1.6.1 Filtro de alcance en código.** Constantes en `src/common/config.py`: `PLANTA = "TRUJILLO"`, `ANIO_INI = 2016`, `ANIO_FIN = 2024`, `ANIO_PILOTO = 2020`. Toda lectura filtra por ellas.
- [ ] **1.6.2 Matriz de datos.** `docs/fichas/matriz_datos.md` con la matriz origen × formato (Tabla 1.9) y la Tabla 1.10 de aporte por fuente.

### 1.7 · Justificación como problema de Big Data
- [ ] **1.7.1 Medición de volumen.** `src/quality/volumen.py` que recorre `s3://…/bronze/` y reporta tamaño y número de archivos por fuente y por tipo (estructurado, semiestructurado, no estructurado). Salida: `docs/evidencias/volumen.md`.
  - *Técnica:* 5 V (S1).
  - *Aceptación:* tabla de volumen real que reemplaza a las estimaciones de la Tabla 1.12.

---

## Fase 2 · Arquitectura en AWS (2.1–2.4)

### 2.1 · Arquitectura propuesta (capas Bronze, Silver y Gold)

- [ ] **2.1.1 Plantilla de infraestructura.** `infra/cloudformation/stack.yaml` con todos los recursos, para crear y borrar todo de una vez.
  > **Instrucción para Claude Code:** Crea una plantilla CloudFormation con: (1) un bucket S3 `costagas-trujillo-lake-${Sufijo}` con versionado desactivado, Block Public Access, cifrado SSE-S3 y reglas de ciclo de vida para borrar `athena-results/` a los 7 días y `scaletest/` a los 3 días; (2) un rol de IAM para Lambda que solo lea `bronze/*` y escriba `silver/*`; (3) un rol para Glue que lea `silver/*` y `bronze/externo/publico/sunat_padron/*` y escriba `silver/*` y `gold/*`; (4) una base de datos de Glue Data Catalog por capa (`silver`, `gold`); (5) un workgroup de Athena con límite de 1 GB por consulta y resultados en `athena-results/`; (6) un presupuesto de AWS Budgets con alertas en US$ 0.50 y US$ 1.00 a los correos del equipo. Sin KMS, sin crawlers, sin VPC. Comenta el costo de cada recurso.
  - *Aceptación:* `aws cloudformation validate-template` sin errores; el despliegue crea el bucket con los prefijos.
- [ ] **2.1.2 Prefijos de las capas.** Script que crea la estructura de carpetas de 3.2 (`bronze/`, `silver/`, `gold/`, `_manifests/`, `scaletest/`, `athena-results/`).
- [ ] **2.1.3 Diagrama vivo.** Copiar `arquitectura.png` a `docs/informe/` y mantenerlo igual a lo desplegado. Si algo cambia, ADR nuevo.

### 2.2 · Atributos de calidad del diseño

- [x] **2.2.1 Prueba de disponibilidad.** Script `src/common/reproceso.py` que borra una partición de Silver y la regenera desde Bronze.
  - *Técnica:* tolerancia a fallos; Bronze inmutable cumple el papel de la replicación de HDFS (S2).
  - *Aceptación:* la partición regenerada es idéntica (mismo número de filas y misma suma de kg).
- [x] **2.2.2 Contratos entre capas.** `src/common/schemas.py` con el esquema de cada tabla de Silver y Gold (`StructType` de Spark y su equivalente en pandas/pyarrow). Prueba que falla si una tabla escrita no cumple su esquema.

### 2.3 · Prueba de sustitución de componentes

- [x] **2.3.1 URI base como parámetro.** Toda ruta se arma desde `LAKE_URI` en `.env` (`s3://…` en la nube, `file://data/lake` en local). Ningún módulo escribe una ruta fija.
  - *Aceptación:* el mismo job corre en local y en Glue cambiando solo `LAKE_URI`. Esto demuestra que «HDFS es una implementación, no la arquitectura» (S2).

### 2.4 · Stack tecnológico y equivalencia entre rutas

- [ ] **2.4.1 Entorno local reproducible.** `requirements.txt` con versiones fijas: `pandas 2.2`, `pyarrow`, `awswrangler 3.9`, `pyspark 3.5.*` (igual que Glue 5.0), `scikit-learn 1.5`, `openpyxl`, `pdfplumber 0.11`, `yt-dlp`, `boto3`, `pytest`. Python 3.11 para coincidir con Glue 5.0.
- [ ] **2.4.2 Capas de Lambda.** Usar la capa gestionada **AWS SDK for pandas** para Python 3.12 (ARN publicado por AWS para us-east-1) y una capa propia pequeña con `openpyxl` para leer XLSX.
- [ ] **2.4.3 Despliegue.** `infra/scripts/deploy.sh` que empaqueta el código, lo sube a `s3://…/_code/` y despliega el stack.
- [ ] **2.4.4 Control de costo.** Verificar que el presupuesto de 2.1.1 existe y enviar una alerta de prueba. Activar Cost Explorer.
- [x] **2.4.5 Registro de técnicas.** `docs/tecnicas_curso.md` con la Tabla 2.8 del informe, enlazando cada técnica al archivo que la implementa. Se completa a medida que avanza la Fase 3.
  - *Aceptación:* cada fila apunta a un archivo y línea concretos del repositorio.

---

## Fase 3 · Pipeline de datos (3.1–3.8)

### 3.1 · Fuentes de datos y ficha de procedencia

- [ ] **3.1.1 Fichas como datos.** `docs/fichas/fuentes.yaml` con una entrada por fuente (ID, entidad, enlace, fecha de obtención, licencia, período, registros, tamaño, formato, tipo de dato). Un script genera las fichas en Markdown a partir del YAML.
- [ ] **3.1.2 Diccionario de columnas.** `docs/diccionario/columnas.md` con las columnas relevantes (Tabla 3.3) más las que agregue la implementación.
- [ ] **3.1.3 Señales completas.** Extraer del diccionario v2.0 la definición de las once señales (S1 a S11) a `src/signals/catalogo.yaml`.

### 3.2 · Ingesta y organización del data lake (capa Bronze)

Cada extractor escribe en Bronze **sin transformar** (ELT) y registra un manifiesto.

- [x] **3.2.1 Módulo de manifiesto.** `src/ingest/manifest.py`: para cada archivo subido registra fuente, ruta, tamaño, SHA-256, fecha de carga y número de filas cuando aplica, en `_manifests/fecha_carga=YYYY-MM-DD/manifest.json`.
- [ ] **3.2.2 Internos estructurados (35 archivos).** `src/ingest/internos.py`: sube `data/raw/` a `bronze/interno/estructurado/<proceso>/<codigo>/fecha_carga=…/` con el nombre original y `--sse AES256`.
- [ ] **3.2.3 PU-01 Padrón de SUNAT.** `src/ingest/sunat_padron.py`: descarga el ZIP desde el enlace de la ficha y lo sube a `bronze/externo/publico/sunat_padron/`. No se descomprime en local.
- [ ] **3.2.4 PU-02 Tipo de cambio BCRP.** `src/ingest/bcrp.py`: consulta la API de BCRPData para las series PD04640PD (diaria) y PN01207PM (mensual) de 2016 a 2024 y guarda el JSON. Verificar el formato de fechas de la API antes de automatizar.
- [ ] **3.2.5 PU-03 Órdenes SCOP propias.** Carga manual del Excel exportado por la empresa con `internos.py` (mismo flujo que 3.2.2).
- [ ] **3.2.6 EN-01 Facilito.** `src/ingest/facilito.py`: guarda la tabla de plantas, estaciones y locales de la provincia de Trujillo como JSON con fecha de captura. Si la página exige reCAPTCHA, la captura es manual (guardar HTML desde el navegador) y el script solo convierte el HTML a JSON.
- [ ] **3.2.7 NE-01 y NE-02 YouTube.** `src/ingest/youtube.sh` con `yt-dlp` (sin descargar video): `--skip-download --write-info-json --write-auto-subs --sub-langs es --write-comments --extractor-args "youtube:max_comments=200"`, para las cinco búsquedas de 200 y el canal de Osinergmin.
- [ ] **3.2.8 NE-03 a NE-05 TikTok y Facebook.** Lista de URL en `src/ingest/urls_videos.txt` (recopilada con sesión iniciada) y `yt-dlp -a` con `--write-info-json`.
- [ ] **3.2.9 NE-06 Google Maps.** Plantilla CSV `data/raw/maps_resenas.csv` para la carga manual (marca, local, fecha, texto, estrellas). Sin nombres de usuarios.
- [ ] **3.2.10 NE-07 Resoluciones de Osinergmin.** `src/ingest/resoluciones.py`: descarga los PDF de una lista de URL (`urls_resoluciones.txt`, armada con la búsqueda `site:cdn.www.gob.pe osinergmin GLP cilindros`), con pausa de 2 segundos entre descargas.
- [ ] **3.2.11 NE-08 GDELT.** `src/ingest/gdelt.py`: DOC API (`mode=artlist`, `format=json`, `maxrecords=250`) con términos de GLP en Perú y 5 segundos de pausa entre consultas por el límite de peticiones. Para el histórico, una muestra de archivos de `masterfilelist.txt` de los meses con eventos.
- [ ] **3.2.12 NE-09 a NE-12 Prensa y web de Costagas.** `src/ingest/prensa.py`: descarga el HTML de una lista de URL con pausa, respetando `robots.txt`; se guarda el HTML crudo en Bronze.
  - *Aceptación de 3.2:* `src/quality/volumen.py` (1.7.1) lista todas las fuentes en Bronze y cada archivo tiene su entrada en el manifiesto.

### 3.3 · Procesamiento y limpieza (Bronze → Silver → Gold)

**De Bronze a Silver · AWS Lambda con pandas (escalado vertical)**

- [x] **3.3.1 Utilidades de limpieza.** `src/common/limpieza.py` con `normalizar_placa`, `ruc_valido` (dígito verificador módulo 11), `normalizar_dni`, `seudonimizar` (SHA-256 con sal leída de Parameter Store) y `normalizar_estado`. Pruebas en `tests/test_limpieza.py` con los casos de la Tabla 3.5 (cuatro formas de placa, placa con fecha, RUC con ceros perdidos, booleanos en kg, capacidad «5 000 kg», asiento −9 095).
- [x] **3.3.2 Esquemas declarados por fuente.** `src/common/schemas.py`: un esquema por archivo interno con nombre y tipo de cada columna. La lectura usa el esquema declarado; no se infiere.
  - *Técnica:* esquema declarado frente a `inferSchema` (S5).
- [ ] **3.3.3 Función Lambda `bronze_to_silver`.** `src/bronze_to_silver/handler.py`, disparada por evento de S3 en `bronze/interno/`: lee con el esquema, aplica 3.3.1, deduplica por documento + línea, escribe Parquet Snappy particionado por `anio` y `mes` en `silver/<dominio>/<tabla>/` y registra los rechazos en `silver/_rechazos/`.
  - *Aceptación:* al subir un archivo de muestra aparece su tabla en Silver y una entrada de calidad (3.4).
- [x] **3.3.4 Tabla unificada de movimientos.** `silver/movimientos/` con una fila por movimiento: tipo (compra, despacho, venta), placa normalizada, fecha, producto, kg, código SCOP, documento. Es la entrada de la conciliación.

**Padrón de SUNAT · Glue Spark (escalado horizontal)**

- [ ] **3.3.5 Job `silver_padron_sunat`.** `src/silver_to_gold/padron_sunat.py`: lee el padrón (delimitado por `|`, codificación a verificar) con esquema declarado, hace un **`left_semi` join con `broadcast()`** contra los RUC del maestro de distribuidores y escribe solo esos RUC en `silver/sunat_padron/`.
  - *Técnica:* left_semi, broadcast, esquema declarado (S5); escalado horizontal por volumen real de más de 11 millones de filas (S1).
  - *Aceptación:* `explain()` muestra `BroadcastHashJoin` y se guarda en `docs/evidencias/`.

**De Silver a Gold · Glue Spark con DataFrames**

- [ ] **3.3.6 Job `gold_conciliacion`.** `src/silver_to_gold/conciliacion.py` (fragmento del informe, 3.3):
  - lee `silver/movimientos/` filtrando por año (**partition pruning**);
  - **Map → Shuffle → Reduce** con `groupBy("placa_norm","fecha","id_producto").agg(...)`, que combina antes del shuffle (**Combiner**);
  - une con la flota mediante **`broadcast()`** y `left_outer`;
  - calcula `kg_diferencia`, `pct_diferencia` y `valor_ref_soles`;
  - hace **`cache()`** de la conciliación, porque la usan varias señales;
  - escribe con `partitionBy("anio","mes")` en `gold/fact_conciliacion_unidad/`.
  - Sin `collect()`; inspección con `show()` o `take()`.
  - *Aceptación:* corre en local sobre `data/sample/` y luego una vez en Glue (2 trabajadores, FLEX).
- [ ] **3.3.7 Uniones de la Tabla 3.6.** `src/silver_to_gold/uniones.py` con una función por unión y el tipo de join exacto: `left_outer` (compras ↔ SCOP, ventas ↔ maestro, maestro ↔ SUNAT, compras ↔ tipo de cambio, eventos de mercado, notas de precios), **`left_anti`** (compras sin orden SCOP; ventas sin compra), **`left_semi`** (unidades habilitadas) y `full_outer` (compras ↔ ventas).
  - *Aceptación:* prueba con datos de muestra que verifica el número de filas esperado de cada join.
- [ ] **3.3.8 Ingeniería de características.** `src/silver_to_gold/features.py`: `ratio_carga_capacidad`, `precio_vs_mediana_canal`, `flag_placa_divergente`, `desvio_tc`, `es_pandemia_2020`, `evento_mercado`, `indice_quejas_marca`.

**Fuentes no estructuradas y semiestructuradas**

- [ ] **3.3.9 Resoluciones en PDF.** `src/unstructured/resoluciones.py`: texto con `pdfplumber`; extracción con expresiones regulares de empresa, RUC, tipo de infracción, número de cilindros, kg y multa en UIT → `silver/osinergmin_resoluciones/`.
- [ ] **3.3.10 YouTube, TikTok, Facebook y reseñas.** `src/unstructured/textos.py`: VTT a texto; limpieza y anonimización de comentarios y reseñas (se eliminan nombres de usuario y enlaces); clasificación por temas con un diccionario de términos (peso incompleto, mal estado, falsificación, precio) y por marca (NOR GAS, COSTA GAS PLUS, Solgas, Zeta, Llama Gas, etc.) → `silver/textos_clasificados/` y el agregado mensual `indice_quejas_marca`.
- [ ] **3.3.11 Prensa, notas de precios y GDELT.** `src/unstructured/prensa.py`: HTML a texto; las tablas de precios de las notas (NE-09) pasan a `silver/precios_historicos/` (marca, distrito, fecha, precio); GDELT y prensa se resumen en `silver/eventos_mercado/` (mes, tipo de evento, fuente).
- [ ] **3.3.12 Compactación de archivos pequeños.** En los pasos 3.3.9 a 3.3.11, escribir con `coalesce`/`repartition` para que cada partición tenga archivos de ≈ 128 MB (o un solo archivo si el volumen es menor).
  - *Técnica:* problema de los archivos pequeños (S2).
  - *Aceptación:* `volumen.py` muestra que Silver tiene órdenes de magnitud menos archivos que Bronze para las fuentes JSON.

### 3.4 · Control de calidad de los datos

- [x] **3.4.1 Reglas como código.** `src/quality/reglas.py` con las ocho reglas de la Tabla 3.7 y la acción ante el fallo.
- [x] **3.4.2 Reporte por corrida.** Cada ejecución de 3.3.3 y 3.3.6 escribe `silver/_calidad/fecha=…/reporte.json` con registros aceptados, marcados y rechazados por regla, y la completitud de los campos críticos (Tabla 3.8).
- [ ] **3.4.3 Primer KPI de calidad.** Porcentaje del maestro con RUC/DNI válido y existente (cruce con `silver/sunat_padron/`).
  - *Aceptación:* reporte en `docs/evidencias/calidad_<fecha>.md` con las metas cumplidas o la explicación de la brecha.

### 3.5 · Almacenamiento de datos procesados (capas Silver y Gold)

- [ ] **3.5.1 DDL en Athena.** `sql/athena/ddl/` con una sentencia `CREATE EXTERNAL TABLE` por tabla de Silver y Gold, con **proyección de particiones** (como el ejemplo del informe). Sin crawlers.
- [ ] **3.5.2 Script de creación de tablas.** `sql/athena/crear_tablas.py` que ejecuta los DDL en el workgroup del proyecto.
- [x] **3.5.3 Regla de particionado.** Prueba que verifica que ninguna tabla se particiona por columnas de alta cardinalidad (placa, RUC, documento).
  - *Aceptación:* `SELECT COUNT(*)` sobre cada tabla en Athena devuelve las filas esperadas.

### 3.6 · Optimización del rendimiento

Cada optimización se mide **antes y después** y se guarda en `docs/evidencias/optimizacion.md` (tiempo, bytes escaneados y salida de `explain()`).

- [ ] **3.6.1 Column pruning: CSV frente a Parquet.** Misma consulta de conciliación 2020 en Athena sobre una copia CSV y sobre Parquet; anotar bytes escaneados y tiempo.
- [ ] **3.6.2 Partition pruning.** La misma consulta con y sin filtro `anio = 2020`.
- [ ] **3.6.3 Predicate pushdown.** `explain()` del job de conciliación filtrando por producto; capturar `PushedFilters` y `ReadSchema`.
- [ ] **3.6.4 Broadcast join.** Tiempo del join compras ↔ flota con y sin `broadcast()`; capturar `BroadcastHashJoin` frente a `SortMergeJoin` en el plan.
- [ ] **3.6.5 `cache()`.** Tiempo de calcular tres señales con y sin caché de la conciliación.
- [ ] **3.6.6 Data skew.** Medir la duración de la tarea más lenta frente a la mediana en la Spark UI de Glue. Verificar que AQE está activo (`spark.sql.adaptive.enabled` y `spark.sql.adaptive.skewJoin.enabled`); si persiste, aplicar salting a la clave de producto.
  - *Técnica:* Catalyst, column y partition pruning, predicate pushdown (S5); broadcast, cache y skew (S3, S4).
  - *Aceptación:* tabla antes/después completa para las seis optimizaciones.

### 3.7 · Prueba de escalabilidad

- [ ] **3.7.1 Generador de réplicas.** `src/scaletest/replicar.py`: copia `silver/movimientos/` 10 y 100 veces en `scaletest/x10/` y `scaletest/x100/`, desplazando placas y documentos para que las uniones sigan siendo válidas.
- [ ] **3.7.2 Corridas.** El mismo pipeline en: Lambda 1 GB (1×), Lambda 10 GB (10× y 100×), Glue 2 trabajadores (10× y 100×) y Glue 5 trabajadores (100×). Registrar tiempo, memoria pico, número de particiones, Executors y costo.
  - *Técnica:* escalado vertical frente a horizontal (S1); Driver, Executors y particiones (S4); ley de Amdahl.
- [ ] **3.7.3 Análisis.** `docs/evidencias/escalabilidad.md` con la tabla y la respuesta: ¿el tiempo crece en proporción al volumen?, ¿en qué punto deja de alcanzar una sola máquina?
- [ ] **3.7.4 Limpieza.** Borrar `scaletest/` al terminar (además de la regla de ciclo de vida de 3 días).
  - *Aceptación:* la tabla reemplaza los valores esperados de la Tabla 3.11; costo total de la prueba menor a US$ 0.50.

### 3.8 · Seguridad de la plataforma

- [ ] **3.8.1 Cuenta.** MFA en la cuenta raíz, sin claves de acceso en la raíz; un usuario de IAM con MFA por integrante.
- [ ] **3.8.2 Mínimo privilegio.** Revisar las políticas de 2.1.1 con IAM Access Analyzer; guardar las políticas en `infra/iam/` con comentarios.
- [ ] **3.8.3 Política del bucket.** Rechazo de peticiones sin TLS (`aws:SecureTransport = false`), como en el informe.
- [ ] **3.8.4 Secretos.** La sal de seudonimización en Parameter Store (tipo SecureString con la clave gestionada por AWS, sin costo). Instalar `pre-commit` con un detector de secretos.
- [ ] **3.8.5 Datos en el repositorio.** `data/sample/` se genera con `src/common/muestra.py`: toma un subconjunto, seudonimiza identificadores y desplaza cantidades; `data/raw/` está en `.gitignore`.
  - *Aceptación:* capturas en `docs/evidencias/seguridad/` y una búsqueda en el historial de Git que no encuentra RUC, DNI ni nombres reales.

---

## Fase 4 · Análisis, modelado y consumo (4.1–4.4)

### 4.1 · Análisis exploratorio de datos

- [ ] **4.1.1 Notebook de EDA.** `notebooks/41_eda.ipynb`, que lee **solo Silver y Gold** (nunca Bronze) con `awswrangler.athena` o desde `data/sample/`.
- [ ] **4.1.2 Seis gráficos de la Tabla 4.1**, cada uno con su pregunta, su hipótesis y su lectura según la Tabla 4.2:
  1. diferencia mensual 2016–2024 frente a tipo de cambio y precio de referencia, con 2020 sombreado;
  2. Pareto de kg no explicados por unidad en 2020;
  3. S1 por unidad sobre el total de órdenes;
  4. distribución de `pct_diferencia` por unidad;
  5. precio por canal frente a la mediana interna y a Facilito y notas de precios;
  6. picos de diferencia frente a eventos de mercado e índice de quejas por marca.
- [ ] **4.1.3 Figuras al informe.** Exportar a `docs/informe/figuras/` con la interpretación escrita en el notebook.
  - *Aceptación:* cada gráfico confirma o descarta una hipótesis por escrito.

### 4.2 · Modelo base

- [ ] **4.2.1 Señales determinísticas.** `src/signals/`: un módulo por señal (S1, S4, S5, S7, S8, S10 y las restantes de `catalogo.yaml`). Cada una devuelve filas para `gold/fact_alerta/` con su grado de evidencia (nulo, medio, alto) según tenga o no respaldo externo.
- [x] **4.2.2 Puntaje z robusto.** `src/models/base_mad.py`: z modificado con mediana y MAD por producto; alerta cuando |z| > 3.5.
- [ ] **4.2.3 Lista para validación.** Exportar las 20 alertas de mayor puntaje con su expediente (orden SCOP, volumen, fecha, unidad declarada, comprobante) a `docs/evidencias/top20_base.csv`, sin nombres.
- [ ] **4.2.4 Métricas base.** `precision@20`, porcentaje de kg cubiertos y alertas por mes. Mientras la gerencia no valide, se usa como etiqueta débil la coincidencia con evidencia externa de grado alto (S1/S8), y se declara así en el informe.
  - *Aceptación:* `docs/evidencias/linea_base_tecnica.json` con las tres métricas (Tabla 4.4).

### 4.3 · Modelo definitivo, selección y evaluación

- [ ] **4.3.1 Extracto de entrenamiento.** Consulta Athena que agrega Gold por unidad-mes con las variables de 3.3.8 → `notebooks/data/unidad_mes.parquet`.
- [ ] **4.3.2 Partición temporal.** Ajuste con 2016–2019, evaluación en 2020 (piloto) y comprobación de estabilidad en 2021–2024.
- [ ] **4.3.3 Candidatos.** `src/models/definitivo.py`: Isolation Forest y Local Outlier Factor (`novelty=True`), con `RobustScaler`.
- [ ] **4.3.4 Ajuste de hiperparámetros.** Rejilla de la Tabla 4.6 (`n_estimators`, `max_samples`, `contamination`, `n_neighbors`), eligiendo por `precision@20` en 2020. Semilla fija para reproducir.
- [ ] **4.3.5 Comparación y elección.** Tabla de la 4.7 (base frente a Isolation Forest frente a LOF) y justificación del umbral priorizando la precisión, por el costo de un falso positivo sobre un trabajador (Tabla 4.8).
- [ ] **4.3.6 Puntajes a Gold.** Escribir el puntaje del modelo elegido en `gold/fact_alerta/` (tipo = modelo).
  - *Aceptación:* métricas en `docs/evidencias/modelo_definitivo.json` contrastadas con la línea base técnica.

### 4.4 · Modelo dimensional y capa de consumo

- [ ] **4.4.1 Dimensiones.** `src/silver_to_gold/dimensiones.py`: `dim_fecha`, `dim_vehiculo`, `dim_conductor` (solo hash), `dim_producto`, `dim_cliente_distribuidor` (hash, RUC válido, estado, capacidad, canal), `dim_senal`. Sin particionar.
- [ ] **4.4.2 Hechos.** `fact_conciliacion_unidad` (grano unidad × producto × día) y `fact_alerta` (grano alerta), con claves hacia las dimensiones. Prueba de integridad referencial (`left_anti` de cada hecho contra cada dimensión debe devolver 0 filas).
- [ ] **4.4.3 Vistas de KPIs.** `sql/athena/kpis/`: una vista por cada uno de los cinco KPIs de la Tabla 4.10 (diferencia no explicada %, valor de la diferencia S/, divergencia de placa S1, maestro enlazable %, confirmación de alertas %).
- [ ] **4.4.4 Tablero.** Power BI Desktop con el conector de Amazon Athena (controlador ODBC de Athena) y las cuatro páginas de la Tabla 4.11: Resumen, Conciliación por unidad, Bandeja de alertas, Mercado. Guardar `dashboard/costagas.pbix` y `dashboard/conexion.md`.
  - *Aceptación:* cada KPI muestra su fórmula, su frecuencia y su responsable; ningún nombre ni DNI visible.

---

## Fase 5 · Preparación del hito final (secciones 5, 6 y 7)

Estas secciones se redactan para la Semana 14, pero el código deja la evidencia lista:

- [ ] **5.1** Reporte de datos sensibles y de la seudonimización aplicada (sale de 3.3.1 y 3.8.5), con el riesgo de reidentificación que queda.
- [ ] **5.2** Linaje: script que, dado un valor del tablero, recorre Gold → Silver → manifiesto → archivo de Bronze (sale de 3.2.1).
- [ ] **5.3** Análisis de sesgos del modelo por tipo de unidad, producto y canal (sale de 4.3).
- [ ] **5.4** Matriz de obligaciones de la Ley 29733 y cómo las cumple el proyecto.
- [ ] **5.5** Aporte a la región: cifras del tablero para la planta Trujillo.
- [ ] **6.1–6.4** Tabla de trazabilidad del valor, conclusiones por objetivo, recomendaciones y trabajo futuro, alimentadas por las métricas de 4.3 y los KPIs de 4.4.
- [ ] **7 · Anexos** Enlace al repositorio, constancia de la empresa, Anexo A (uso de IA generativa: declarar el uso de Claude Code por paso) y Anexo B (lista de verificación).

---

## E. Cierre: verificación, entrega y desmontaje

- [ ] **E.1 README reproducible.** Requisitos, instalación, variables de `.env`, orden de ejecución (`deploy.sh` → ingesta → Lambda → jobs de Glue → DDL → notebooks → tablero) y cómo correr todo con `data/sample/`.
- [ ] **E.2 Verificación cruzada.** Un integrante que no escribió el código clona el repositorio en limpio y reproduce el pipeline con la muestra; las métricas del informe deben coincidir con las del código.
- [ ] **E.3 Desmontaje.** `infra/scripts/teardown.sh`: vacía el bucket y borra el stack. Registrar en `docs/evidencias/costo_real.md` el costo final de Cost Explorer frente a la Tabla 2.7.
- [ ] **E.4 Actualizar el informe.** Reemplazar las metas y estimaciones de las Tablas 1.12, 3.10, 3.11, 4.4 y 4.7 por los valores medidos, y la Tabla 2.8 con los enlaces al código.

---

## F. Calendario resumido

| Semana | Fechas | Pasos |
|---|---|---|
| 2 | 31/08 – 04/09/2026 | 0.1, 0.2, 0.3, 0.4 |
| 3 | 07/09 – 11/09/2026 | 1.1–1.6, 3.1 |
| 4 | 14/09 – 18/09/2026 | 2.1, 2.2, 2.3, 2.4 |
| 5 | 21/09 – 25/09/2026 | 3.2 (todas las fuentes estructuradas), 1.4.1, 1.7.1 |
| 6 | 28/09 – 02/10/2026 | 3.3.1–3.3.8, 3.4, 3.5 |
| 7 | 05/10 – 09/10/2026 | 3.6.1–3.6.3, 3.7, 3.8, 4.1, 4.2 · **hito parcial** |
| 8 | 12/10 – 16/10/2026 | Rotación de roles · 3.2.7–3.2.12 (no estructuradas) |
| 9 | 19/10 – 23/10/2026 | 3.3.9–3.3.12 |
| 10 | 26/10 – 30/10/2026 | 4.3 |
| 11 | 02/11 – 06/11/2026 | 3.6.4–3.6.6, 4.4.1–4.4.3 |
| 12 | 09/11 – 13/11/2026 | 4.4.4, validación de alertas |
| 13 | 16/11 – 20/11/2026 | Fase 5 |
| 14 | 23/11 – 27/11/2026 | E.1–E.4 · **hito final** |

> **Nota.** El cronograma del informe asume que el semestre empezó el 31/08/2026. Si ya están en la Semana 7, prioricen para el hito parcial los pasos marcados en las semanas 2 a 7 que exige el curso: pipeline de extremo a extremo, una medición de rendimiento, la prueba de escalabilidad, el EDA sobre datos limpios y el modelo base.
