# Ingeniería de datos · dónde estoy y qué necesito

**Fecha:** 2026-11-27 · **Escribe:** Wilson Mirano Ríos (Ingeniería de datos, Semanas 8-14)

El equivalente de [`estado_y_pendientes.md`](estado_y_pendientes.md) desde mi lado. Las secciones de
Anghelo, Frank y Bruno están escritas para que puedan pasárselas directamente a su asistente.

Estado del repositorio: los PR #13 a #21 están en `main`. El
[PR #22](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/22) está abierto con seis
commits míos y espera revisión; lo que diga de él este documento es «implementado y probado», no
«mergeado».

## Lo que falta, en corto

| Quién | Qué | Desbloquea |
|---|---|---|
| **Anghelo** | `contracts/gastos.yaml` (su AR01/A06) | Mi **WR02**, y con él S7, S9, el KPI 3 y el semáforo |
| **Frank** | `puntuar_s12` (su FR12) | Mi **WR11**, y detrás WR12, WR13, WR14 y WR16 |
| **Frank** | Fusionar sus commits de `dev-frank`, que siguen sin mergear | Que lo anterior se pueda usar |
| **Anghelo** | Revisar el PR #22: `src/sim/validacion.py` y `docs/adr/` son suyos | Que entre a `main` |
| **Bruno** | Confirmar el ADR 0029, que cierra la ruta EMR y cambia `CLAUDE.md` | Un requisito del curso |
| **Titular de AWS** | Subir los 35 archivos a `landing/interno/`; MFA, rotación de claves y la clave de `svc-dashboard` | **Todas las cifras reales** |
| **Titular de AWS** | Subir a `sim/_spec/` la especificación sellada del escenario B, sin abrirla | La validación del detector |
| **El dueño de la máquina** | La carpeta `../DATASETS` otra vez accesible | Cualquier relectura de `data/raw/` |

**Nadie espera un contrato mío.** Lo único que tenía bloqueado a Anghelo quedó respondido y está en
el punto 3.

## 1. Lo que llevo hecho

| Commit | Qué | Estado |
|---|---|---|
| **W01-W02** | Lago, prefijos y Lambda de ingesta con manifiesto y SHA-256 | Implementado y probado |
| **W03** | Bases de AWS en `stack.yaml`, `us-east-2` | Implementado |
| **W04** | Bronze → Silver con los cinco contratos | Implementado y probado |
| **W05** | Patrón MapReduce en Spark SQL hacia `gold/mr/` | Implementado y probado |
| **W08** | Las seis dimensiones del modelo estrella, con `dim_senal` desde la Tabla 4.9 | Implementado y probado |
| **W13** | Registro de modelos en `gold/_modelos/` | Implementado y probado |
| **W20** | Los cinco extractores externos en Lambda | Implementado y probado |
| **W21** | Job de fuentes externas: GDELT, LDA de temas, `mercado_mes` | Implementado y probado |
| **W22** | Las cuatro funciones del portal, con JWT de Cognito verificado en código | Implementado y probado |
| **W23** | Despliegue continuo con OIDC y el `ci.yml` | Implementado y corriendo |
| **W24** | Prueba de escalabilidad, Tabla 3.11 | Medido en local; **las filas de AWS siguen pendientes** |
| **WR01** (W06) | `fact_balance_planta`, el balance de planta (KPI 1 y 2) | Implementado y probado |
| **WR04-WR05** (W09) | DDL de Gold en Iceberg: **13 de las 15 tablas** | Implementado y probado |
| **WR17** (W19) | Lambda `costagas-validacion-detector` y rol `costagas-sim-role`, solo `sim/` | Implementado y probado |

Y lo que va en el PR #22, de hoy:

| Commit | Qué | Estado |
|---|---|---|
| **WR19** | `PYSPARK_PYTHON` y `PYSPARK_DRIVER_PYTHON` a `sys.executable` en la fixture `spark` | Implementado y probado |
| **WR03** | `src/glue/interfaces.py`: las interfaces `compras`, `unidades` y `tc` del WP 0.8 en Spark | Implementado y probado |
| **WR20** | ADR 0029: el patrón MapReduce corre con Spark SQL; el 0014 queda reemplazado | Implementado |
| **WR06** | `paso_senales`: S2, S3, S6 y S12 hacia `fact_alerta` por MERGE sobre `id_alerta` | Implementado y probado |
| **WR07** | El trabajo de Glue apunta a `gold_job.py`, con `--modo evento` y `scikit-learn==1.5.2` | Implementado; **sin desplegar** |

Más los ADR 0023 a 0027 y el 0029, que documentan las decisiones de alcance que tomé por el camino.

### Las tablas de Gold, que es lo que al resto le sirve

El mapa completo está en [`contexto_modelo.md`](contexto_modelo.md). En corto, hoy se escriben:

| Tabla | Grano | Quién la escribe | Quién la lee |
|---|---|---|---|
| `fact_balance_planta` | producto, año, mes | mi `src/glue/balance.py` | `v_kpi_1`, `v_kpi_2` |
| `fact_alerta` | `id_alerta` | mi `paso_senales` (S2, S3, S6, S12) | `v_alerta`, el portal |
| las seis `dim_*` | su llave natural | mi `src/glue/dimensiones.py` | todas las vistas |
| `gold/mr/balance` | producto, año, mes | `mapreduce_sql.py` (evidencia de la técnica S3) | el informe |

Faltan por escribir `fact_unidad_mes` (espera el contrato de gastos) y `fact_operacion` (WR16). De
las 15 tablas del modelo, las dos que **no** tienen DDL son justo esas: un DDL inventado es peor que
un DDL ausente, porque parece acordado.

### Lo que NO está desplegado, y conviene no confundir

El stack sí está en la cuenta: el titular lo aplicó el 25/11 y quedó en `UPDATE_COMPLETE` con 36
recursos ([evidencia](evidencias/despliegue_2026-11-25.md)). Lo que **no** está en la nube es todo
lo que le agregué después: los cinco extractores del W20, el job de externos del W21, las cuatro
funciones del portal del W22, el cambio de los programas a `AWS::Scheduler::Schedule`, la Lambda de
validación del WR17 y el cambio de script del WR07. Hoy la plantilla declara 78 recursos.

Pasa `cfn-lint` sobre `us-east-2` sin hallazgos, pero
[`despliegue_ingesta.md`](evidencias/despliegue_ingesta.md) sigue diciendo «pendiente de ejecución»
y las filas de AWS de la Tabla 3.11 están marcadas una por una. Tampoco se ha lanzado **ninguna
corrida de Glue**, y la regla `costagas-silver-actualizado` sigue `DISABLED` a propósito, para la
carga inicial. Implementado, probado, desplegado y corrido son cuatro cosas distintas, y el informe
tiene que decirlo así.

Al volver a desplegar hay que acordarse del [ADR 0021](adr/0021-lambda-limpieza-3008-mb.md):
`aws cloudformation deploy` conserva el valor anterior de un parámetro si no se lo vuelves a pasar,
así que el `MemorySize` se verifica en el recurso, no en el comando.

## 2. Lo que me queda, en orden

| Commit | Lo hago cuando |
|---|---|
| **WR08** desplegar y llenar las evidencias | Entre el PR #22. Cuesta **US$ 0** y no depende de nadie más |
| **WR09** carga inicial y primera corrida de Gold | El titular suba los 35 archivos. FLEX, ≈ US$ 0.03 |
| **WR10** tablas y vistas creadas en Athena | Esté WR09. Las 8 vistas de Frank ya están en `main` |
| **WR02** `fact_unidad_mes` | Anghelo cierre `contracts/gastos.yaml`. **Es el único contrato que falta** |
| **WR05** completo | Esté WR02; hoy faltan `fact_unidad_mes` y `fact_operacion` |
| **WR11** `fact_alerta` con la probabilidad del modelo y aviso SNS | Frank entregue `puntuar_s12` |
| **WR12** lectura incremental · **WR13** mantenimiento de Iceberg | Esté WR11 |
| **WR14** control previo al pago · **WR15** semáforo de las 6:30 · **WR16** entregas mensuales | Esté la cadena anterior |
| **WR18** evidencia del portal publicado | Esté WR08 |
| **WR21** filas de AWS de la Tabla 3.11 · **WR25** ADR 0031 | Esté WR09. ≈ US$ 0.10 a 0.15 |
| **WR22** costo real · **WR23** primera corrida del CD · **WR24** desmontaje | Al final, en ese orden |

Lo único que podría adelantar sin esperar a nadie es el **WR14**: su lógica de rojo, ámbar y verde
sale de la Tabla 4.8i y de `config.py`, y `fact_alerta` ya existe. Quedaría sin probar contra la
probabilidad del modelo hasta que llegue `puntuar_s12`.

## 3. Anghelo · lo que me pediste, respondido

El detalle está en [`evidencias/hojas_sin_encabezado.md`](evidencias/hojas_sin_encabezado.md), con
la tabla de las 32 hojas y el comando que la regenera. En resumen:

**Los encabezados de gastos y de PRIMAX no existen.** No es que no los haya publicado: en las tres
hojas (`CO01. GASTOS` → `Sheet1`, `GASTOS 2020.xls` → `GASTOS FLOTA`, y `1. PEDIDOS GLP.xlsx` →
`PRIMAX`) el motivo es `identificador_en_la_fila`, que significa que la fila que mejor puntúa como
encabezado **trae un documento, una razón social o una placa**. Esas hojas empiezan en datos, sin
fila de nombres.

Lo que te propongo para A06: declarar como fuente con nombres la hoja hermana **`OTROS GASTOS`** del
mismo libro, que sí tiene encabezado (`MES, FECHA, PLACA, ÁREA, DESCRIPCIÓN, COMENTARIOS, MONTO,
PROVEEDOR, PLANTA`, 1 043 filas), y `GASTOS FLOTA` como fuente **por posición**, con lo que no se
pueda nombrar en la sección `pendiente:` del contrato. Es el patrón que ya usan tus `clientes.yaml`
y `distribuidores.yaml`.

Lo que sigo debiéndote y hoy no puedo entregar: la descripción en prosa de qué mide cada posición de
`GASTOS FLOTA` y de `CO01/Sheet1` —sobre todo **qué columna dice si el gasto es de combustible**, que
es lo que necesita `gasto_combustible`—. La escribo sin volcar un solo valor en cuanto tenga la
carpeta a mano.

**El stock diario no existe en la entrega.** Busqué en las 199 hojas las columnas con `STOCK`,
`SALDO`, `INICIAL`, `FINAL`, `RESIDUO`, `INVENTARIO` y `EXISTENC`, y además las hojas con 300 filas o
más que tengan columna de fecha. Lo único que sale son saldos de **factura** de proveedor y cuadros
cruzados **por mes**; el `Reporte de Produccion CGT 2018.xlsx` es mensual y de 2018, fuera del
piloto. El `pro_01` de `schemas.py` tiene los conceptos correctos y **ningún archivo detrás**.
Anótalo como no cubierto: coincide con el `cierres_medidos_fisicamente: 0` del informe.

La consecuencia práctica, por si sirve para tu contrato: en `fact_balance_planta` el
`delta_stock_kg` queda **nulo**, no en cero, y la señal **S11** se declara sin fuente en el log del
job. Un cero ahí se leería como un cierre medido.

**Una herramienta para los otros 13 casos.** Las 13 hojas con motivo `tipo_de_celda` son distintas:
ahí puede que los nombres estén y la heurística no los reconozca (las seis `VENTAS *.xls` con 26
columnas son el caso típico). Para eso le agregué a `src/ingest/encabezados.py` la opción
`--encabezado ARCHIVO:HOJA:FILA`, que deja que quien abrió la hoja declare la fila y entonces se
publican sus nombres. La criba de datos personales **no** se levanta: si la fila declarada trae un
RUC, la hoja se sigue tratando como dudosa. Está probado.

**Lo del `pyspark` en Windows, resuelto por los dos.** Tu `test_calidad_silver.py` ya lleva el
`importorskip` del PR #21, gracias. Y el fallo de `test_dimensiones.py` que me reportaste («Python
worker failed to connect back») era otra cosa: la JVM lanzaba el worker con el `python` del PATH y no
con el de la suite. Está arreglado en el WR19 del PR #22, en `tests/conftest.py`.

**Dos cosas del PR #22 que son tuyas y necesitan tu visto bueno.** En `src/sim/validacion.py` solo
**agrego** al final el punto de entrada en Lambda (`lambda_handler` y `descargar_spec`);
`ejecutar_lote` y `medir_semilla` quedan intactos. Y en el ADR 0014 tu nota del 26/11 se conserva
textual: la decisión se escribe encima, no en su lugar.

## 4. Frank · lo que necesito de ti

**4.1 · `puntuar_s12` (tu FR12).** Es lo único que me falta de tu lado y bloquea cuatro commits
míos: sin ella `fact_alerta` se escribe con `probabilidad` nula y no hay WR11, ni WR12, ni el control
previo al pago, ni las entregas mensuales. No está en ninguna rama, `dev-frank` incluida.

**4.2 · Fusionar `dev-frank`.** Tienes commits sin mergear. Mientras no entren, lo que esté ahí no
lo puedo llamar desde el job.

**4.3 · Las vistas ya están, gracias.** Las ocho (`v_kpi_1` a `v_kpi_5`, `v_alerta`,
`v_cubo_unidad`, `v_semaforo_unidades`) están en `main` y la lista blanca de `src/portal/kpis.py`
apunta a ellas. Mientras las tablas no existan en Athena el portal responde `estado: "sin_vista"`, y
es correcto que lo haga: eso se cierra con mi WR10.

Un aviso sobre `v_kpi_1` y `v_kpi_2`: leen `merma_es_supuesto` de `fact_balance_planta`. La columna
existe y sale de `MERMA_TECNICA_ES_SUPUESTO`, así que el tablero puede decir que ese 0.5 % es una
referencia de mercado ([ADR 0027](adr/0027-merma-tecnica-referencia-de-mercado.md)) y no una medición
de la planta.

**Lo que ya tienes de mi lado:** las seis dimensiones del W08 con `dim_senal` completa, el registro
de modelos del W13, el job de Gold donde enganchan tus `kpi4()` y `agregar_senales()`, las
interfaces del WP 0.8 en Spark (WR03) y `fact_alerta` escribiéndose con las alertas de regla (WR06).

## 5. Bruno · lo que necesito de ti

**5.1 · El ADR 0029, contigo.** Lo escribí y cierra lo que quedaba abierto del 0014: el patrón
MapReduce corre con Spark SQL, el 0014 pasa a reemplazado y `CLAUDE.md` pierde la excepción de EMR y
el requisito de Hadoop Streaming. El razonamiento es del informe, no mío: su Tabla 2.6b descarta
«Amazon EMR, EMR Serverless o Databricks» porque «EMR corre sobre instancias EC2 que cobran por hora
y la política base las deniega», su Tabla 2.2c define el módulo M5 como Spark 3.5 en Glue, y su Tabla
2.8 mapea la técnica S3 —«Map, Shuffle y Reduce; Combiner»— a PySpark en Glue.

La evidencia que queda en su lugar son las cuatro etapas en el plan físico, con una prueba que las
exige: dos `HashAggregate` alrededor de un `Exchange hashpartitioning` por `(producto, anio, mes)`,
que es el combiner que Catalyst agrega sin que nadie lo escriba. Más la igualdad de totales entre la
versión SQL y la de RDD sobre el mismo universo.

**Lo que decides tú, y es la razón de que te lo pase:** si la evaluación del curso exige el binario
de Hadoop y no el patrón, la ruta se reabre con el administrador y el 0029 se reemplaza a su vez.
Eso está escrito en el propio ADR para que no se pierda.

**5.2 · El tema de SNS del negocio.** Mi WR15 publica ahí el correo de las 6:30 armado con tu
`formatear_resumen()`. La auditoría del 26/11 anotó 2 suscripciones no confirmadas; hasta que lo
estén, el semáforo se puede desplegar pero no llega a nadie. No lo he vuelto a verificar.

**5.3 · Tu página del portal (B13) ya está** en `portal/`, gracias. El bloque de publicación de
`infra/scripts/deploy.sh` ya la sube a S3 e invalida CloudFront; falta correrlo, y eso es mi WR18.

## 6. El titular de la cuenta AWS

- **Subir los 35 archivos a `landing/interno/`.** Es lo que me bloquea la primera corrida y, con
  ella, todas las cifras reales del informe. Son 34 distintos: `COMPRAS MENSUALES (1).xlsx` es un
  duplicado y la ingesta lo rechaza por SHA-256, que es el comportamiento correcto.
- **Subir a `sim/_spec/` la especificación sellada del escenario B, un solo archivo y sin abrirlo.**
  No puede hacerlo quien valida el detector, porque entonces sabría dónde están los robos. La Lambda
  exige que haya exactamente uno bajo ese prefijo: la medición queda sellada contra su huella
  SHA-256.
- Lo de la auditoría del 26/11, que sigue igual: el usuario raíz **sin MFA** y ninguno de los cuatro
  usuarios de IAM con MFA; claves del 11/10/2026 sin la rotación de la Semana 8; `svc-dashboard` sin
  clave, así que Grafana no se puede conectar.

El tope de costo sigue siendo **US$ 1** y lo gastado hasta ahora es **US$ 0.00**, porque no se ha
corrido nada. El despliegue del stack no cuesta; lo que cuesta son la primera corrida de Glue
(≈ US$ 0.03 en FLEX) y la prueba de escala (≈ US$ 0.10 a 0.15), y las dos están presupuestadas.

## 7. Errores y cosas que no están verificadas

**7.1 · La suite pasa en verde, y lo que vale es la CI.** `python -m pytest -q` termina sin fallos
con los seis commits del PR #22. Pero en esta máquina **las pruebas de Spark se omiten**: hay Python
3.14 y Java 27, y pyspark 3.5 necesita Python 3.12 o menor y Java 17, además de `winutils.exe` para
que Hadoop lea el disco en Windows. Quien verifica de verdad es la CI (Ubuntu, temurin 17, Python
3.12). Si alguien ve una omisión en su máquina, es eso y no un fallo.

**7.2 · Nada de lo nuevo corrió en AWS.** Lo repito aquí porque es el error fácil al redactar el
informe: que una Lambda esté declarada en `stack.yaml` y pase `cfn-lint` no significa que exista en
la cuenta, y que exista no significa que haya corrido.

**7.3 · `../DATASETS` no está en esta máquina.** El inventario de encabezados se generó el
2026-10-08 desde esa carpeta y el JSON quedó versionado, así que todo lo de este documento se
sostiene sobre él. Pero hoy no puedo volver a leer `data/raw/`: la carpeta no está en el disco.
Cualquier pregunta nueva sobre los archivos crudos espera a que vuelva.

**7.4 · Lo que escribe `fact_alerta` hoy son cuatro señales, no doce.** S2, S3, S6 y S12. S7 y S9
esperan `fact_unidad_mes`; S11 no tiene fuente; S1, S4, S5, S8 y S10 leen la muestra sintética
antigua, y S8 quedó **no resoluble** por falta de ventana común. El job lo dice en el log por cada
señal que omite, con el motivo. Una alerta tampoco es un robo confirmado, y los kg de una alerta no
son una pérdida: `valor_soles` se escribe nulo a propósito.
