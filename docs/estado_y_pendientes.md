# Costa Gas Trujillo · estado al 28/11/2026, tarde

**Escribe:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación) · Repositorio:
`WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS`, `main` en el merge del PR #31.

**Cambió lo principal desde la versión de esta madrugada: la carga inicial ya ocurrió.** Silver
está cargada en S3 con los datos reales de la empresa y `main` volvió a verde. Gold sigue sin
correr, y eso es ahora el único cuello de botella.

## Lo que cambió respecto de la versión anterior

**`main` ya no está en rojo.** El `cd` fallaba en su séptimo paso porque el rol
`costagas-github-deploy` no existía. Lo resolvió Frank en `9a2125d` (OIDC con el `sub` inmutable de
GitHub y la plantilla desde S3 por su tamaño), que entró en el PR #31: el `cd` de `main` del 28/11
a las 07:04 UTC terminó en success, igual que el `ci`.

**Los 35 archivos están cargados y Silver corrió.** En
`s3://costagas-trujillo-lake-upao-g4-2026/silver/` hay 26 Parquet y sus 26 archivos de control,
4.4 MB, las diez tablas, con marca del 28/11 entre las 02:24 y las 02:38 UTC. Las diez tablas están
registradas en el catálogo Glue `costagas_silver`.

**Las cuatro ramas están fusionadas en `main` y no hay pull requests abiertos.** La frase anterior
sobre los commits de Frank sin fusionar ya no aplica.

## Lo que falta, que es Gold

**`fact_unidad_mes` ya existe.** Entró con el PR #32 (`gold_fact_unidad_mes.sql`,
`src/glue/unidad_mes.py` y su integración al job), está catalogada en `costagas_gold` y con ella se
catalogaron las tres vistas que faltaban: `v_kpi_4`, `v_cubo_unidad` y `v_semaforo_unidades`. El
catálogo de Gold tiene hoy sus **quince tablas y ocho vistas**.

**El job de Gold está en pruebas, no cerrado.** `costagas-gold-conciliacion` registra cinco
ejecuciones el 28/11 entre las 03:27 y las 03:45: cuatro fallaron y la quinta estaba corriendo al
escribir esto. Los cuatro fallos, por si ayudan a Ingeniería de datos:

| Hora | Error |
|---|---|
| 03:27 | `NotADirectoryError` al leer `src/signals/catalogo.yaml` dentro de `costagas_src.zip` |
| 03:30 | `ValueError: fact_unidad_mes: hay placas sin rol en dim_unidad; se cancela para no inventar el rol` |
| 03:37 | `PATH_NOT_FOUND` de `data/lake/silver/_control/*/*.json` dentro del zip, en vez de la ruta de S3 |
| 03:40 | `INCONSISTENT_BEHAVIOR_CROSS_VERSION.READ_ANCIENT_DATETIME` al leer fechas anteriores a 1900 con Spark ≥ 3.0 |

El tercero y el cuarto son de empaquetado y de lectura de fechas antiguas. El segundo es el
interesante para calidad: el job **se niega a inventar el rol** de una placa que `dim_unidad` no
declara, que es exactamente lo que pide `CLAUDE.md`. Las placas sin rol salen de que
`relacion_unidades` tiene 80.1 % de placas válidas y `soat_2020` 83.7 %
([medición](evidencias/calidad_carga_inicial.md)).

Mientras ese job no termine en `SUCCEEDED`, **ninguna cifra de KPI, señal o semáforo puede
presentarse como resultado de la empresa**.

La regla `costagas-silver-actualizado` sigue en **DISABLED**, como manda el
[ADR 0020](adr/0020-regla-gold-prefijos-internos.md), y `costagas-glue-fallido` en ENABLED.

## Qué necesito de cada uno

| Quién | Qué | Desbloquea |
|---|---|---|
| **Wilson** | Que `costagas-gold-conciliacion` termine en `SUCCEEDED` | **AR17 completo y AR24**, y todas las cifras de Gold del informe |
| **Wilson** | Las placas sin rol en `dim_unidad`, que cancelan `fact_unidad_mes` | El KPI 4 y el semáforo |
| **Wilson** | Subir el escenario B sellado a `sim/_spec/` y correr `costagas-validacion-detector` | **AR18 y AR19** |
| **Wilson o el titular** | En mi política: `s3:ListBucket` sobre el bucket y `s3:PutObject`/`GetObject` sobre `athena-results/*` | Poder citar consultas de Athena como evidencia |
| **Bruno** | Roles de la Semana 8 en `equipo.md`; protocolo ciego alineado con `revision.py`; proteger `main` | Coherencia con el informe y la revisión ciega real |
| **Titular AWS** | MFA del raíz y de los cuatro usuarios de IAM, y rotar claves | La seguridad de la cuenta |

## Lo que hice

**Los diez contratos tienen fuente declarada y leída, y ahora están contrastados contra la corrida
real.** Las filas efectivas de [`contracts/README.md`](../contracts/README.md) ya no vienen de la
corrida local en pandas, sino de `silver/_control/`, que es la fuente oficial.

| Commit | Qué |
|---|---|
| AR01 | Contrato de gastos: **16 322 filas**, con **2 126 de combustible** y 94.7 % de placas válidas en `GASTOS FLOTA` |
| AR02 | Producción diaria: **31 días de oct-2018, los 31 con residuo cero**. Confirma la cita de S11 del informe |
| AR03 · AR04 | `--validar` de contratos en el `ci.yml`; `pyspark` opcional, que arreglaba el paso 5 de `cd` |
| AR05 · AR12 · AR13 | Integridad referencial de Gold, sin valores sin resolver, privacidad en alertas y vistas |
| AR06 · AR07 · AR08 · AR09 | Validación del detector con 100 semillas, ficha del modelo, cortes del PSI, bloqueo de KPI por calidad |
| AR10 · AR11 · AR14 · AR15 | `CLAUDE.md` al v17, ADR 0030, diccionario de Gold, técnicas con archivo y línea |
| **AR16** | **Calidad de la carga inicial**, medida sobre los 26 controles de la corrida real ([evidencia](evidencias/calidad_carga_inicial.md)) |
| AR20 · AR21 · AR23 | Anexo A de uso de IA, estado de los contratos con las filas de S3, bitácora al cierre |
| — | **Lectura por posición** en el lector de contratos: lo que desbloqueó las tres hojas que empiezan en datos, y con ellas el `fact_unidad_mes` de Wilson |

**La verificación que dejó la carga:** nueve de las diez tablas coinciden al dígito entre la corrida
local y la de producción. La décima, `distribuidores`, estaba mal en el README con 2 244 filas: era
un conteo del orden de las leídas, y las efectivas son 1 285. Corregido en AR21, con la explicación
en la evidencia de AR16.

## Lo que me queda

| Commit | Espera |
|---|---|
| AR17 completo | La corrida de Gold; la parte de ingesta, Silver y contratos ya está medida |
| AR18 · AR19 | Que el escenario B sellado esté en `sim/_spec/` y corra su Lambda |
| AR24 | AR17 y los resultados de Frank y Wilson |

## Cuatro cosas que conviene no perder de vista

**Implementado, probado, desplegado y corrido son cuatro cosas distintas.** Hoy el sistema está
corrido **hasta Silver** sobre datos reales. Gold no. Ninguna cifra de KPI, señal o semáforo puede
presentarse todavía como resultado de la empresa.

**Las cifras de la muestra sintética no son resultados del negocio.** El pipeline completo corre en
local con `python -m src.pipeline --regenerar-muestra`, y sirve para desarrollar y probar, pero sus
números no se publican: `CLAUDE.md` lo prohíbe y `docs/evidencias/linea_base.md` lo declara en su
cabecera.

**Una prueba omitida se ve igual que una que pasa.** Las de Spark se omiten en Windows; por eso `ci`
las corre en Ubuntu y falla a propósito si alguna queda omitida.

**Con el perfil de gobierno no se puede consultar Athena.** `StartQueryExecution` termina en
`INSUFFICIENT_PERMISSIONS` porque falta `s3:PutObject` sobre `athena-results/`. Las métricas de
AR16 se tomaron de `silver/_control/`, que es la fuente oficial de todos modos.
