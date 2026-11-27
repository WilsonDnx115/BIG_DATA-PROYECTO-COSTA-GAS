# Bitácora de decisiones y riesgos de la implementación

Registro de lo que se decidió **durante la implementación del informe v16**, con su fecha y el
ADR donde queda la decisión completa. Complementa la bitácora del informe (sección 0.4): aquí
van los hechos que salieron del código y del despliegue, no los del diseño.

Las decisiones formales viven en [`docs/adr/`](adr/). Esta bitácora anota el porqué, los
tropiezos y lo que queda abierto.

## Decisiones registradas

| Fecha | Decisión | ADR |
|---|---|---|
| 12/11/2026 | El tablero pasa de Power BI Desktop a Grafana Cloud | [0016](adr/0016-grafana-cloud.md) |
| 25/11/2026 | El job de Glue usa cola de corridas, y por eso `MaxRetries` 0 | [0017](adr/0017-cola-de-corridas-maxretries-0.md) |
| 26/11/2026 | Los videos se obtienen con la YouTube Data API v3, no con `yt-dlp` | [0015](adr/0015-youtube-data-api.md) |
| 26/11/2026 | La operación mensual escribe en un lago `op/` aparte | [0018](adr/0018-lago-op-operacion-mensual.md) |
| 26/11/2026 | `revision_alerta` solo recibe INSERT; `v_alerta` resuelve la última | [0019](adr/0019-revision-alerta-solo-inserciones.md) |
| 26/11/2026 | La regla de Gold escucha solo los 7 prefijos internos de Silver | [0020](adr/0020-regla-gold-prefijos-internos.md) |
| 26/11/2026 | La Lambda de limpieza sube a 3 008 MB | [0021](adr/0021-lambda-limpieza-3008-mb.md) |
| 26/11/2026 | Un solo catálogo S1-S12 y un solo esquema por tabla para Spark, pandas y Gold | [0030](adr/0030-un-esquema-por-tabla.md) |
| 26/11/2026 | La merma técnica se fija en 0.5 % con referencia de mercado, no con un supuesto propio | [0027](adr/0027-merma-tecnica-referencia-de-mercado.md) |
| 10/10/2026 | La línea base se mide **antes** de limpiar, para que la mejora sea comparable | [0022](adr/0022-linea-base-bronze.md) |
| 27/11/2026 | La Lambda de ingesta ignora `landing/externo/` en vez de rechazarlo | [0023](adr/0023-landing-externo-ignorado-por-la-ingesta.md) |
| 27/11/2026 | Los endpoints externos quedan configurables y sin corrida programada | [0024](adr/0024-endpoints-externos-sin-contrato-de-api.md) |
| 27/11/2026 | El token de Cognito se verifica sin agregar una capa de criptografía | [0025](adr/0025-jwt-verificado-sin-capa-de-criptografia.md) |
| 27/11/2026 | Las réplicas de escalabilidad van a `sim/escala/`, nunca a Silver ni a Gold | [0026](adr/0026-replicas-de-escala-en-sim-escala.md) |

Los ADR 0015 a 0027 y el 0030 están en `main`. El **0028** (parámetros del detector con su
fuente) está escrito en la rama `dev-frank` y entra a `main` con su pull request; no hay ningún
ADR 0029. Lo anterior al 0015 corresponde al diseño y vive en la bitácora del informe (0.4).

## Riesgos que se materializaron

### 1 · Dos ADR con el mismo número (26/11/2026)

**Qué pasó.** El [Plan de Implementación](Plan_Implementacion_Codigo_v15.md) pedía crear los ADR
0013 a 0018, pero esos números ya estaban ocupados en `docs/adr/`. Se crearon como **0015 a
0021**, y el `0011` que estaba duplicado desde antes pasó a **0022**.

**Por qué pasó.** No fue un borrado: `git log --all --diff-filter=D -- docs/adr/` no devuelve
nada, nadie borró nunca un ADR. Fue una **rama vieja sin rebasar**:

| Momento | Hecho |
|---|---|
| — | `wp-0.3-bases-aws` sale de `9cfa82c`, donde `docs/adr/` terminaba en **0012** |
| 10/10/2026 00:48 | El PR #9 mergea **0013** (modelo base v6) a `main` |
| 10/10/2026 02:00 | El PR #10 mergea **0014** (EMR transitorio) a `main` |
| 25/11/2026 | El Plan v15 se escribe **sobre esa rama**, nunca rebasada. Ahí `docs/adr/` sigue terminando en 0012, así que numera 0013-0018 de buena fe |
| 26/11/2026 14:38 | El PR #11 mergea la rama. Git no da conflicto, porque son archivos distintos: `main` queda con el plan desactualizado **y** con los 0013/0014 reales |

El `0011` duplicado es el mismo patrón, más antiguo: `0011-linea-base-bronze.md` se añadió sin
ver que la línea del WP 0.2 ya traía `0011-region-us-east-2.md`.

**Qué se hizo.** Renumerar, no borrar. Cada ADR nuevo declara `Reemplaza a:` y el viejo pasa a
`Estado: reemplazada por NNNN` conservando su texto: [0007](adr/0007-yt-dlp-videos.md) por el
0015 y [0010](adr/0010-power-bi-desktop.md) por el 0016. El 0022 anota su número anterior.

**Qué evita que vuelva a pasar.** Antes de numerar un ADR hay que hacer `git pull origin main`
y mirar `docs/adr/`. Una rama que vive semanas sin rebasarse numera sobre una foto vieja del
repositorio, y git no avisa porque no hay conflicto de archivos.

### 2 · Glue no admite reintentos con la cola de corridas (25/11/2026)

El despliegue falló con *«Maximum retries was set to 1, must be set to 0 with job run queuing
enabled»* y CloudFormation revirtió solo. Se eligió conservar la cola y renunciar al reintento:
perder un disparo es peor que no reintentar. La recuperación queda en el aviso por SNS y en la
corrida siguiente. Detalle en el [ADR 0017](adr/0017-cola-de-corridas-maxretries-0.md) y en la
[evidencia del 25/11](evidencias/despliegue_2026-11-25.md).

### 3 · Un parámetro de CloudFormation conservó su valor anterior (26/11/2026)

La plantilla traía 3 008 MB para la Lambda de limpieza desde el WP 0.2, pero el despliegue del
25/11 la dejó en 1 024 MB porque `aws cloudformation deploy` **conserva el valor anterior de un
parámetro** si no se le pasa de nuevo. Se corrigió el 26/11 con el change set
`memoria-lambda-3008`. La lección: cambiar un valor por defecto en la plantilla no llega solo a
la cuenta; hay que verificarlo en el recurso después de desplegar.
[ADR 0021](adr/0021-lambda-limpieza-3008-mb.md) y [evidencia del 26/11](evidencias/ajustes_aws_2026-11-26.md).

### 4 · Silver publicaba RUC de personas naturales (27/11/2026)

**Qué pasó.** La prueba de privacidad del A12 encontró que
`src/bronze_to_silver/handler.py` conservaba **todos** los RUC válidos:

```python
df["ruc"] = df["documento_norm"].where(df["clase_documento"] == "RUC")
```

Un RUC que empieza en 10, 15 o 17 es de **persona natural**. En la tabla
`red_02_distribuidores` había 33 de ellos publicados en Silver.

**Por qué importa.** Con la muestra sintética no expone a nadie, pero con los 35 archivos reales
sí, y va contra la regla de `CLAUDE.md` de no publicar RUC de personas naturales. No fue un
descuido de redacción: la condición filtraba por *clase de documento*, que era la pregunta
equivocada; la correcta es *de quién es ese documento*.

**Cómo se cerró.** Ahora solo pasa el RUC de persona jurídica y el documento completo se queda en
`documento_hash` (`fa5ec36`, con su prueba en `616e47f`). Verificado sobre el parquet regenerado:
0 RUC de persona natural, los 34 de empresa intactos y las 125 filas conservadas. La prueba se
amplió después a las alertas y a las ocho vistas de Athena (`140f124`), porque la bandeja de
alertas es lo que de verdad mira una persona cada día.

**La lección.** Una regla de privacidad escrita en `CLAUDE.md` no se cumple sola: se cumple
cuando hay una prueba que falla si alguien la rompe.

### 5 · Dos catálogos de señales decían cosas distintas (26/11/2026)

**Qué pasó.** Las señales existían dos veces, en Spark y en pandas, cada una con su propio
catálogo, con descripciones y grados de evidencia distintos para la misma señal. El tablero, el
modelo y el informe podían afirmar cosas diferentes de S1-S12 sin que nada fallara.

**Cómo se cerró.** Un solo catálogo (`src/signals/catalogo.yaml`), un solo contrato de alertas
(`fact_alerta_base`) y las interfaces del WP 0.8 como única declaración de las entradas, con
pruebas que comparan las dos implementaciones sobre los mismos datos
([ADR 0030](adr/0030-un-esquema-por-tabla.md), commits `31fb9b3` y `950537b`).

### 6 · Las pruebas de Spark no corrían en ninguna máquina del equipo (27/11/2026)

**Qué pasó.** Spark en Windows necesita `winutils.exe` hasta para leer un archivo local, así que
las pruebas de PySpark e Iceberg se **omitían** en las máquinas del equipo. Omitidas se ven
verdes: durante semanas nadie las ejecutó de verdad.

**Cómo se cerró.** El `ci.yml` las corre en Ubuntu y, además, **falla a propósito** si alguna
queda omitida por Spark: una prueba que no corre no puede acreditar nada. El motivo de cada
omisión local se informa (`-rs`) en lugar de quedar en silencio.

## Lo que queda abierto

| Tema | Estado | Quién decide |
|---|---|---|
| **Merma técnica.** 0.5 % de lo comprado: pérdida de masa con buena instrumentación en balances de hidrocarburos, menor que 0.5 % (Emerson, 2019), y tope del índice Solomon. Osinergmin no publica una tolerancia de merma para plantas envasadoras. Está declarada como supuesto en `.env.example` (`MERMA_TECNICA_ES_SUPUESTO=si`) y no se presenta como medición ([ADR 0027](adr/0027-merma-tecnica-referencia-de-mercado.md)) | Resuelto con referencia de mercado | Análisis y modelado |
| **Stock físico.** El balance de planta necesita el stock medido físicamente; con los archivos actuales los cierres de stock no son mediciones físicas | Sin cubrir | Coordinación, con la empresa |
| **EMR y la evidencia de Hadoop Streaming.** El v16 descarta EMR y hace MapReduce con Spark, pero `CLAUDE.md` todavía cita la excepción del [ADR 0014](adr/0014-emr-transitorio-reglas-v6.md) y exige Hadoop Streaming. Es un requisito del curso | Anotado en el ADR 0014 | Coordinación con Ingeniería de datos |
| **Roles de la Semana 8.** [`docs/equipo.md`](equipo.md) rotó los roles en sentido contrario al del informe v16 (0.1) y al reparto real del trabajo. Ya está corregido en el `README.md` | Sin corregir en `equipo.md` | Coordinación |
| **Stock diario.** Buscado en las 199 hojas del inventario de encabezados: ninguna tiene stock por día, así que S11 no tiene fuente en esta entrega y el KPI 1 toma la variación de stock en 0, marcada con `stock_es_supuesto`. No es un pendiente: es un resultado, y así se publica | No cubierto, con evidencia | Calidad y documentación |
| **MFA y rotación de claves.** Ningún usuario de IAM tiene MFA, el usuario raíz tampoco, y las claves son del 11/10/2026 | Pendiente desde el 26/11 | Titular de la cuenta |

## Lo que esta bitácora deja dicho

Seis riesgos se materializaron y los seis están arriba con su fecha, su causa y cómo se cerraron.
Tres de ellos no eran fallas de código, y conviene no perderlos de vista, porque son los que se
repiten:

1. **Una rama sin rebasar** duplicó la numeración de los ADR. El código no dio conflicto porque
   eran archivos distintos; el conflicto era de significado.
2. **Un valor por defecto cambiado en la plantilla no llega solo a la cuenta.** Hay que verificarlo
   en el recurso después de desplegar.
3. **Una prueba omitida se ve igual que una prueba que pasa.** Por eso la integración continua
   falla si una prueba de Spark queda omitida.

Las decisiones de diseño, con sus alternativas y sus fuentes, están cada una en su ADR; esta
bitácora solo guarda la fecha, el porqué y lo que costó.
