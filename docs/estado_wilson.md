# Ingeniería de datos · dónde estoy y qué necesito

**Fecha:** 2026-11-27 (tras el merge de los PR #15, #16 y #17) · **Escribe:** Wilson Mirano Ríos
(Ingeniería de datos, Semanas 8-14)

El equivalente de [`estado_y_pendientes.md`](estado_y_pendientes.md) desde mi lado. Las secciones
de Anghelo, Frank y Bruno están escritas para que puedan pasárselas directamente a su asistente.

Mi paquete son 24 commits, W01 a W24. **Llevo 15.**

## Lo que falta, en corto

| Quién | Qué | Desbloquea |
|---|---|---|
| **Anghelo** | `contracts/gastos.yaml` (su A06), ya sin el bloqueo del encabezado | Mi **W07**, y con él toda la cadena de alertas |
| **Frank** | `src/models/detector.py` con `calibrar_h` (su F14) | El A18 de Anghelo, y con él mi **W19** |
| **Frank** | Las vistas `v_kpi_1` a `v_kpi_5` y `v_semaforo_unidades` en `sql/athena/vistas/` | Mi **W17**, y que el portal devuelva algo |
| **Bruno** | Su `formatear_resumen()` (B17) ya está; falta el tema de negocio confirmado en SNS | Mi **W17** |
| **Bruno y yo** | Decidir el ADR 0014 de EMR y la evidencia de Hadoop Streaming | Un requisito del curso |
| **Titular de AWS** | MFA, rotación de claves y la clave de `svc-dashboard` | El despliegue y Grafana |
| **El dueño de la máquina** | La carpeta `../DATASETS` otra vez accesible | Cualquier relectura de `data/raw/` |

**Nadie espera un contrato mío.** Lo que tenía bloqueado a Anghelo quedó respondido hoy, y lo
explico en el punto 3.

## 1. Lo que llevo hecho

Todo mergeado en `main` por los PR [#13](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/13)
y [#14](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/14).

| Commit | Qué | Estado |
|---|---|---|
| **W01-W02** | Lago, prefijos y Lambda de ingesta con manifiesto y SHA-256 | Implementado y probado |
| **W03** | Bases de AWS en `stack.yaml`, `us-east-2` | Implementado |
| **W04** | Bronze → Silver con los cinco contratos | Implementado y probado |
| **W05** | Job de Gold en Spark SQL (el M5 del v16) | Implementado y probado |
| **W08** | Las seis dimensiones del modelo estrella, con `dim_senal` desde la Tabla 4.9 | Implementado y probado |
| **W13** | Registro de modelos en `gold/_modelos/` | Implementado y probado |
| **W20** | Los cinco extractores externos en Lambda | Implementado y probado |
| **W21** | Job de fuentes externas: GDELT, LDA de temas, `mercado_mes` | Implementado y probado |
| **W22** | Las cuatro funciones del portal, con JWT de Cognito verificado en código | Implementado y probado |
| **W23** | Despliegue continuo con OIDC y el `ci.yml` | Implementado y corriendo |
| **W24** | Prueba de escalabilidad, Tabla 3.11 | Medido en local; **las filas de AWS siguen pendientes** |
| **W06** | `fact_balance_planta`, el balance de planta (KPI 1 y 2) | Implementado y probado |
| **W09** | DDL de Gold en Iceberg: 13 de las 15 tablas | Implementado y probado |

Y los ADR 0023 a 0026, que documentan las cuatro decisiones de alcance que tomé por el camino.

**Lo que NO está desplegado y conviene no confundir.** El stack sí está en la cuenta: el titular lo
aplicó el 25/11 y quedó en `UPDATE_COMPLETE` con 36 recursos
([evidencia](evidencias/despliegue_2026-11-25.md)). Lo que **no** está en la nube es todo lo que le
agregué después de esa fecha: los cinco extractores del W20, el job de externos del W21, las cuatro
funciones del portal del W22 y el cambio de los programas a `AWS::Scheduler::Schedule`. Pasa
`cfn-lint` sin hallazgos, pero
[`docs/evidencias/despliegue_ingesta.md`](evidencias/despliegue_ingesta.md) sigue diciendo
«pendiente de ejecución» y las filas de AWS de la Tabla 3.11 están marcadas `pendiente` una por
una. Tampoco se ha lanzado **ninguna corrida de Glue**, y la regla `costagas-silver-actualizado`
sigue `DISABLED` a propósito, para la carga inicial. Implementación, despliegue y corrida son tres
cosas distintas y el informe tiene que decirlo así.

Al volver a desplegar hay que acordarse del [ADR 0021](adr/0021-lambda-limpieza-3008-mb.md):
`aws cloudformation deploy` conserva el valor anterior de un parámetro si no se lo vuelves a pasar,
así que hay que verificar el `MemorySize` en el recurso después, no en el comando.

## 2. Lo que me queda, en orden

| Commit | Lo hago cuando |
|---|---|
| **W07** `fact_unidad_mes` | Anghelo cierre `contracts/gastos.yaml`. **Es el único contrato que falta y es la llave de toda la cadena** |
| **W09** completo | Esté W07; hoy faltan solo `fact_unidad_mes` y `fact_operacion` |
| **W10**, **W11** | Esté W09 completo y los contratos de A06 en `main` |
| **W12** `fact_alerta`, **W14**, **W15**, **W18** | Esté la cadena anterior |
| **W16** control previo al pago | Esté W12. El lado de tesorería ya lo tengo: `pedidos_proveedor.yaml` |
| **W17** semáforo de las 6:30 | Esté W16, y Frank publique `v_semaforo_unidades` |
| **W19** validación del detector | Anghelo cierre A18, que espera a Frank |
| Filas de AWS de la **Tabla 3.11** | Esté W11 y se haya desplegado |
| **Desplegar** y llenar las evidencias | Tenga la aprobación del change set |

## 3. Anghelo · lo que me pediste, respondido

El detalle está en [`evidencias/hojas_sin_encabezado.md`](evidencias/hojas_sin_encabezado.md), con
la tabla de las 32 hojas y el comando que la regenera. En resumen:

**4.1 y 4.3 · Los encabezados de gastos y de PRIMAX no existen.** No es que no los haya publicado:
en las tres hojas (`CO01. GASTOS` → `Sheet1`, `GASTOS 2020.xls` → `GASTOS FLOTA`, y
`1. PEDIDOS GLP.xlsx` → `PRIMAX`) el motivo es `identificador_en_la_fila`, que significa que la
fila que mejor puntúa como encabezado **trae un documento, una razón social o una placa**. Esas
hojas empiezan en datos, sin fila de nombres.

Lo que te propongo para A06: declarar como fuente con nombres la hoja hermana **`OTROS GASTOS`**
del mismo libro, que sí tiene encabezado (`MES, FECHA, PLACA, ÁREA, DESCRIPCIÓN, COMENTARIOS,
MONTO, PROVEEDOR, PLANTA`, 1 043 filas), y `GASTOS FLOTA` como fuente **por posición**, con lo que
no se pueda nombrar en la sección `pendiente:` del contrato. Es el patrón que ya usan tus
`clientes.yaml` y `distribuidores.yaml`.

Si para cerrar el mapeo necesitas saber qué mide cada posición, dímelo: lo describo en prosa
(«la F es un monto en soles») sin volcar un solo valor, en cuanto tenga la carpeta a mano.

**4.2 · El stock diario no existe en la entrega.** Busqué en las 199 hojas las columnas con
`STOCK`, `SALDO`, `INICIAL`, `FINAL`, `RESIDUO`, `INVENTARIO` y `EXISTENC`, y además las hojas con
300 filas o más que tengan columna de fecha. Lo único que sale son saldos de **factura** de
proveedor y cuadros cruzados **por mes**; el `Reporte de Produccion CGT 2018.xlsx` es mensual y de
2018, fuera del piloto. El `pro_01` de `schemas.py` tiene los conceptos correctos y **ningún
archivo detrás**. Anótalo como no cubierto: coincide con el `cierres_medidos_fisicamente: 0`
del v16.

**Además, una herramienta nueva para los otros 13 casos.** Las 13 hojas con motivo
`tipo_de_celda` son distintas: ahí puede que los nombres estén y la heurística no los reconozca
(las seis `VENTAS *.xls` con 26 columnas son el caso típico). Para eso le agregué a
`src/ingest/encabezados.py` la opción `--encabezado ARCHIVO:HOJA:FILA`, que deja que quien abrió
la hoja declare la fila y entonces se publican sus nombres. La criba de datos personales **no** se
levanta: si la fila declarada trae un RUC, la hoja se sigue tratando como dudosa. Está probado.

**Una cosa tuya que falla en Windows.** `tests/test_calidad_silver.py::test_el_esquema_declara_lo_que_escribe_procesar`
importa `pyspark` sin la guarda de `skipif` que llevan las demás pruebas de Spark, así que revienta
en mi máquina con `ModuleNotFoundError`. En la CI de Ubuntu pasa, por eso no lo viste. Es una
línea; dime si lo arreglo yo o lo tomas tú.

**Gracias por el arreglo de privacidad.** El `ruc` de `transformar_red_02` era mío y conservaba los
RUC de prefijo 10, 15 y 17. Lo revisé y tu corrección está bien.

## 4. Frank · lo que necesito de ti

**4.1 · `src/models/detector.py` con `calibrar_h`.** No existe en ninguna rama. Bloquea el A18 de
Anghelo y, a través suyo, mi W19, que es la Lambda que corre esa validación en `sim/`.

**4.2 · Las vistas de Athena.** `sql/athena/vistas/` no existe en ninguna rama. Necesito:

- `v_kpi_1` a `v_kpi_5`, porque la función `kpis` del portal tiene su lista blanca apuntando ahí
  (`src/portal/kpis.py`, constante `VISTAS`). Hoy responde `estado: "sin_vista"` y es correcto que
  lo haga, pero el tablero no muestra nada;
- `v_semaforo_unidades`, que es lo que consulta mi W17.

Mientras no estén, el portal está implementado y probado pero no tiene qué devolver. Si los
nombres que quieres usar son otros, dímelos y cambio la lista blanca: es una constante.

**Lo que ya tienes de mi lado:** las seis dimensiones del W08 con `dim_senal` completa (resolución,
ventana, estado y grado de evidencia desde `src/signals/catalogo.yaml`), el registro de modelos del
W13, y el job de Gold del W05 donde enganchan tus `kpi4()` y `agregar_senales()`.

## 5. Bruno · lo que necesito de ti

**5.1 · El tema de SNS del negocio.** Mi W17 publica ahí el correo de las 6:30 armado con tu
`formatear_resumen()`. La auditoría del 26/11 dice que quedan 2 suscripciones sin confirmar; hasta
que lo estén, el semáforo se puede desplegar pero no llega a nadie.

**5.2 · El ADR 0014 de EMR, contigo.** Es lo único abierto que no puede esperar al final, porque es
requisito del curso y no una preferencia nuestra. El choque, en dos líneas:

- `CLAUDE.md` exige que «Hadoop MapReduce se ejecuta con Hadoop Streaming, mapper, reducer y
  combiner» y dice que «una operación sobre RDD de Spark **no sustituye** esa evidencia».
- El informe v16 descarta EMR por costo y su módulo M5 hace MapReduce con Spark. **Mi W05 está
  hecho así**, con Spark SQL, y está mergeado.

O conseguimos la evidencia de Hadoop Streaming —y entonces el ADR 0014 sigue vivo y hay que
habilitar EMR con el administrador—, o cerramos la ruta y hay que **marcar el ADR como reemplazado
y quitar la excepción de `CLAUDE.md` en el mismo cambio**. Lo que no se puede es dejarlo apuntando a
una decisión muerta, que es como está hoy.

**5.3 · Tu página del portal (B13) ya está** en `portal/`, gracias. El bloque de publicación de
`infra/scripts/deploy.sh` ya la sube a S3 y invalida CloudFront; falta correrlo.

## 6. El titular de la cuenta AWS

Repito lo de la auditoría del 26/11 porque me bloquea el despliegue:

- el usuario raíz **sin MFA**, y ninguno de los cuatro usuarios de IAM con MFA;
- claves del 11/10/2026, sin la rotación de la Semana 8;
- `svc-dashboard` sin clave, así que Grafana no se puede conectar.

El tope de costo sigue siendo **US$ 1** y lo gastado hasta ahora es **US$ 0.00**, porque no se ha
corrido nada. El despliegue del stack no cuesta; lo que cuesta son las corridas de Glue del W11 y
la prueba de escala del W24, y ambas están presupuestadas.

## 7. Dos cosas que conviene saber y no están verificadas

**7.1 · `../DATASETS` no está en esta máquina.** El inventario de encabezados se generó el
2026-10-08 desde esa carpeta y el JSON quedó versionado, así que todo lo de este documento se
sostiene sobre él. Pero **hoy no puedo volver a leer `data/raw/`**: la carpeta no está en el disco.
Cualquier pregunta nueva sobre los archivos crudos espera a que vuelva a estar.

**7.2 · La suite pasa en verde salvo ese `pyspark` de Windows.** Corrí `python -m pytest -q` con los
tres PR integrados: un solo fallo, el del punto 3, que no es de mi código. Las pruebas de Spark se
omiten en Windows por falta de `winutils.exe`; las que valen son las de la CI en Ubuntu.
