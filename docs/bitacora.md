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

## Lo que queda abierto

| Tema | Estado | Quién decide |
|---|---|---|
| **Merma técnica.** 0.5 % es un supuesto de trabajo del equipo, no un dato de la empresa. Está declarado así en `.env.example` (`MERMA_TECNICA_ES_SUPUESTO=si`) y no debe presentarse como medición | Sin fijar | Análisis y modelado, con la empresa |
| **Stock físico.** El balance de planta necesita el stock medido físicamente; con los archivos actuales los cierres de stock no son mediciones físicas | Sin cubrir | Coordinación, con la empresa |
| **EMR y la evidencia de Hadoop Streaming.** El v16 descarta EMR y hace MapReduce con Spark, pero `CLAUDE.md` todavía cita la excepción del [ADR 0014](adr/0014-emr-transitorio-reglas-v6.md) y exige Hadoop Streaming. Es un requisito del curso | Anotado en el ADR 0014 | Coordinación con Ingeniería de datos |
| **Roles de la Semana 8.** [`docs/equipo.md`](equipo.md) rotó los roles en sentido contrario al del informe v16 (0.1) y al reparto real del trabajo | Sin corregir | Coordinación |
| **MFA y rotación de claves.** Ningún usuario de IAM tiene MFA, el usuario raíz tampoco, y las claves son del 11/10/2026 | Pendiente desde el 26/11 | Titular de la cuenta |

> Esta bitácora se completa al cierre con las decisiones y los riesgos del resto de la
> implementación (commit A23).
