# Costa Gas Trujillo · dónde estamos y qué falta

**Fecha:** 27/11/2026 · **Escribe:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación,
Semanas 8-14) · Repositorio: `WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS`

Actualizado tras los merges de los PR #18 (Wilson), #19 (Frank) y #20 (mío), y con el PR #21
abierto. Resume **qué hice**, **qué me queda** y, sobre todo, **qué necesito de cada uno**. Las
secciones de Wilson, Frank y Bruno están escritas para que puedan pasárselas directamente a su
asistente.

## Lo que falta, en corto

| Quién | Qué necesito | Qué desbloquea |
|---|---|---|
| **Wilson o quien tenga los archivos** | La carpeta `DATASETS` con los 35 Excel (hoy **no está en ninguna de nuestras máquinas**, ver 4.1), y describir en prosa qué mide cada posición de `GASTOS FLOTA` y de `CO01/Sheet1` | **AR01** (contrato de gastos) y con él **AR21**, el `fact_unidad_mes` del W07 y el combustible del KPI 4 |
| **Wilson** | WR07-WR10: despliegue, carga inicial a S3 y primera corrida | **AR16, AR17 y AR22**, y todas las cifras reales del informe |
| **Wilson** | WR17: la Lambda del detector | **AR18 y AR19** (la medición ciega) |
| **Frank** | Fusionar `dev-frank`: tiene **10 commits sin entrar a `main`** | El ADR 0028, las métricas con bootstrap y las columnas de `modelo_factura` |
| **Frank** | Revisar la cita de S11 y F36 (abajo, punto 5.1) | Que el informe v17 no publique una cifra que los archivos no sostienen |
| **Bruno y Wilson** | Decidir el ADR 0014 de EMR y la evidencia de Hadoop Streaming | **AR10** y un requisito del curso |
| **Bruno** | Corregir los roles de la Semana 8 en `docs/equipo.md` | Coherencia con el informe v16 |
| **Bruno o Wilson** | Proteger la rama `main` (abajo, punto 6.3) | Que CODEOWNERS sirva de algo y que no se pueda fusionar en rojo |
| **Titular de AWS** | MFA del usuario raíz y de los cuatro usuarios de IAM, y rotar claves | La seguridad de la cuenta |

**Lo único que me queda por mi cuenta es el AR15**, y ya no está bloqueado: las diez técnicas que
tiene que documentar están en `main` desde los merges del 27/11 (punto 1.3). Los otros 8 commits
esperan alguna de las filas de arriba.

---

## 1. Lo que hice

### En `main` (PR #15, #17 y #20)

| Commit | Qué |
|---|---|
| **AR06** | `src/sim/validacion.py`: validación del detector con 100 semillas en lotes de 10. Calibra con el escenario A y mide con el B **sin volver a tocar el umbral**; cada lote deja su JSON en `sim/resultados/lote=<n>.json` con las cifras de la Tabla 4.8h y su meta al lado |
| **AR07** | `src/models/ficha.py`: la ficha de cada versión del modelo se genera del registro de W13, no se escribe a mano |
| **AR08** | `deriva.a_dict()` y `desde_dict()`: los cortes del PSI se guardan con el modelo en JSON válido |
| **AR09** | `calidad_silver.bloqueos()`: qué KPI no se publica si su tabla Silver incumple las metas de la Tabla 3.7 |
| **AR11** | ADR 0030: un solo esquema por tabla (catálogo S1-S12, `fact_alerta_base`, interfaces del WP 0.8 y `COLUMNAS_GOLD`) |
| **AR13** | Privacidad en las alertas y en las ocho vistas de Athena |
| **AR20** | Anexo A con el uso de IA |
| **AR23** | Bitácora al cierre: decisiones 0015-0027 y 0030, y seis riesgos materializados |
| **AR03** | El `ci.yml` valida los contratos con `python -m src.silver.contratos --validar` |
| **AR12** | `tests/test_sin_pendientes.py`: falla si vuelve a aparecer una de las fórmulas que prohíbe la regla 2 del equipo |

### En el PR #21, esperando revisión

| Commit | Qué |
|---|---|
| **AR04** | `pytest.importorskip("pyspark")` en la prueba que rompía el workflow `cd` (punto 4.1) |
| **AR02** | La producción diaria, declarada **no cubierta** con la búsqueda que lo sostiene |
| **AR05** | `tests/test_integridad_gold.py`: `left_anti` de cada hecho contra cada dimensión |
| **AR14** | `docs/diccionario_gold.md`: las 13 tablas de Gold desde sus DDL |

**Pruebas: 563 en local (0 fallos, 72 omitidas por Spark en Windows) y CI en verde en Ubuntu**,
donde las de Spark sí corren: el `ci.yml` falla a propósito si alguna queda omitida por Spark.

### Lo que me queda, y de qué depende cada uno

| Commit | Espera |
|---|---|
| **AR01** contrato de gastos | Los 35 Excel (4.1) |
| **AR21** estado de los contratos | AR01 |
| **AR10** CLAUDE.md al v16 | La decisión sobre EMR (6.2) |
| **AR16, AR17, AR22** | La carga inicial (WR09) |
| **AR18, AR19** | La Lambda del detector (WR17) |
| **AR24** insumos del informe v17 | FR24, WR21 y mi AR17 |

### 1.3 · Lo siguiente que hago, y no necesito a nadie

**AR15 · técnicas de ingeniería con archivo y línea.** El plan lo daba como bloqueado por WR06 y
WR12, y eso ya no es cierto: las diez técnicas que faltaba documentar están en `main`.

| Técnica | Dónde está |
|---|---|
| MapReduce SQL | `src/glue/mapreduce_sql.py:62` (`mapear`) y `:71` (`reducir`) |
| MapReduce sobre RDD | `src/silver_to_gold/mapreduce.py:53` (`reduceByKey`) y `:59` (`groupByKey`) |
| `MERGE` de Iceberg | `src/glue/iceberg.py:70` (`escribir_merge`) |
| Lectura incremental | `infra/cloudformation/stack.yaml:360` y `:1002` (`job-bookmark-enable`) |
| AQE y `broadcast()` | ya están en la tabla de `docs/tecnicas_curso.md` |
| EventBridge Events | `infra/cloudformation/stack.yaml:515` y `:562` |
| EventBridge Scheduler | `infra/cloudformation/stack.yaml:877` |
| Flujos de Glue | `infra/cloudformation/stack.yaml` |
| LDA | `src/glue/externos_job.py:248` (`temas`) |
| pdfplumber | `src/extractores/resoluciones.py` |

Hoy [`docs/tecnicas_curso.md`](tecnicas_curso.md) cubre S1-S5 con 27 filas, todas con su archivo y
su línea. Faltan estas diez, que entraron después.

---

## 2. Estado de las ramas y los pull requests

| Rama | Estado |
|---|---|
| `dev-wilson` | **Todo en `main`** (PR #18) |
| `dev-bruno` | **Todo en `main`** |
| `dev-frank` | **10 commits sin fusionar**, el último `624d56e` |
| `dev-anghelo` | PR #21 abierto, CI en verde |

| PR | Autor | Estado |
|---|---|---|
| #15, #17, #20 | Anghelo | Mergeados |
| #13, #18 | Wilson | Mergeados |
| #16 | Bruno | Mergeado |
| #19 | Frank | Mergeado, pero su rama siguió avanzando |
| **#21** | Anghelo | **Abierto**: AR04, AR02, AR05 y AR14 |

---

## 3. Lo que ya no me bloquea, porque ustedes lo resolvieron

Vale la pena dejarlo escrito, porque tres cosas que estaban en la versión anterior de este
documento ya están cerradas:

- **`detector.calibrar_h` existe** (`src/models/detector.py:226`, PR #19 de Frank). Con eso el
  AR06 dejó de estar bloqueado y ya está hecho.
- **Los 13 DDL de Gold entraron** con el PR #18 de Wilson. Eso desbloqueó el AR05 y el AR14, los
  dos hechos y en el PR #21.
- **Wilson firmó que el stock diario no existe** en la entrega
  ([`hojas_sin_encabezado.md`](evidencias/hojas_sin_encabezado.md), sección 4). Con esa evidencia
  el AR02 quedó escrito como resultado, no como pendiente.

---

## 4. Wilson · Ingeniería de datos

### 4.1 · Lo único que me bloquea del todo: los 35 Excel

Tu respuesta sobre los encabezados cerró la duda y fue la que menos esperábamos: en `GASTOS
FLOTA`, `CO01/Sheet1` y `PRIMAX` **los nombres de columna no existen en el archivo**, las tres
hojas empiezan en datos. No es que nadie los haya publicado.

Tu recomendación y la mía coinciden: `OTROS GASTOS` como fuente **con nombres** (MES, FECHA,
PLACA, ÁREA, DESCRIPCIÓN, COMENTARIOS, MONTO, PROVEEDOR, PLANTA) y `GASTOS FLOTA` y
`CO01/Sheet1` **por posición**. Para escribir eso necesito una sola cosa:

> **Qué mide cada posición, en prosa y sin ningún valor.** «A: mes como texto», «C: placa»,
> «F: monto en soles», «H: texto libre del concepto». Y sobre todo **cuál columna dice si el
> gasto es combustible**, que es la que necesita `gasto_combustible` de `fact_unidad_mes`.

**Dónde están los archivos hoy: en ninguna de nuestras dos máquinas.** Los busqué en la mía por
nombre de libro (`GASTOS 2020.xls`, `1. PEDIDOS GLP.xlsx`, `COMPRAS TOTAL 2020.xlsx`,
`Reporte de Produccion CGT 2018.xlsx`) y por carpeta, y no aparecen; `C:\BIG DATA\DATASETS` no
existe. Lo único que tengo son los Excel sintéticos de los escenarios A y B, que son míos. Tú
escribiste que lo harías cuando tengas `../DATASETS` otra vez a mano. Así que el primer paso de
todo esto es que alguien recupere la entrega y la ponga en `C:\BIG DATA\DATASETS`, fuera del
repositorio, y por un canal privado: nunca por WhatsApp ni por correo.

Es el cuello de botella real del proyecto: sin eso no hay AR01, y sin AR01 no hay `fact_unidad_mes` (tu W07), ni
combustible en el KPI 4, ni señal S9 sobre datos reales, ni AR21.

Lo que **no** hace falta: que publiques los valores de la primera fila. Tienes razón en no
hacerlo, esas filas traen placas y el RUC del proveedor pegado a la razón social.

### 4.2 · La carga inicial (WR07-WR10)

Es lo segundo más importante, porque de ahí salen **todas** las cifras reales del informe: mis
AR16, AR17 y AR22, tus WR21 y los FR19-FR24 de Frank.

Antes de subir, dos cosas que ya acordamos y conviene no saltarse:

1. Confirmar que la regla `costagas-silver-actualizado` sigue en **DISABLED**, para que Gold no
   corra con la carga a medias ([ADR 0020](adr/0020-regla-gold-prefijos-internos.md)).
2. La Lambda de ingesta rechaza sola la copia repetida por su huella SHA-256:
   `COMPRAS MENSUALES (1).xlsx` es copia de `COMPRAS MENSUALES.xlsx`. 35 archivos, 34 únicos,
   unos 114 MB, menos de US$ 0.01 de subida.

Mi perfil de AWS es de solo lectura (gobierno): la carga la haces tú o el titular desde
CloudShell.

### 4.3 · `fact_unidad_mes` sigue sin DDL, y está bien así

Lo dejaste explicado en `tests/test_ddl_gold.py` y lo recogí en el diccionario de Gold: es el W07
y espera `contracts/gastos.yaml`. No se declara una tabla cuyo esquema no esté definido. Lo
desbloquea 4.1.

### 4.4 · Un aviso: te toqué dos archivos

- **`.github/workflows/ci.yml`** (AR03). Según CODEOWNERS ese archivo es mío y `cd.yml` es tuyo,
  así que estaba en mi área, pero el paso que cambié lo habías escrito tú: reemplacé el script en
  línea de 22 líneas por `python -m src.silver.contratos --validar`, que hace lo mismo y además
  revisa llave, dominio, fuentes, tipos y tablas duplicadas. Si prefieres el script anterior,
  dímelo y lo revierto.
- **La prueba de `calidad_silver`** (AR04), que rompía tu workflow `cd`. Detalle abajo.

### 4.5 · El workflow `cd` llevaba roto desde el 27/11 a las 05:13

No era de nadie en particular y conviene que se sepa por qué, porque el patrón se puede repetir:

```
FAILED tests/test_calidad_silver.py::test_el_esquema_declara_lo_que_escribe_procesar
ModuleNotFoundError: No module named 'pyspark'
```

`ci` instala `requirements-spark.txt` y `cd` instala `requirements.txt`, que no trae pyspark. Esa
prueba llama a `calidad_silver.esquema()`, que construye un `StructType` y por eso importa pyspark
**aunque no abra ninguna sesión de Spark**; como no pide el fixture `spark`, nadie la omitía.
Arreglado en el PR #21 con `pytest.importorskip`.

Ojo con esto: `cd` solo se dispara con cambios en `infra/`, `src/`, `contracts/` o su propio
workflow, así que el arreglo **no lo va a disparar al entrar**. Se verá en verde con el siguiente
cambio de `src/` que llegue a `main`.

---

## 5. Frank · Análisis y modelado

### 5.1 · La cita de S11 y F36 no se sostiene con los archivos

Es lo que más me importa de tu lado, porque va al informe v17.

El catálogo ([`src/signals/catalogo.yaml`](../src/signals/catalogo.yaml), S11) le da a la señal la
fuente **F36**, la ventana **oct-2018** y la referencia «residuo cero en 31 días; un ajuste de
producción de −9 095». Esa referencia solo puede salir de una tabla **con una fila por día**,
porque cuenta 31 días de un mes de 31.

Lo que el inventario muestra de 2018 es `Reporte de Produccion CGT 2018.xlsx`, y sus hojas son
cuadros **cruzados por mes**. Son dos afirmaciones que no encajan, y la que está verificada contra
los archivos es la del inventario. La búsqueda completa está en
[`evidencias/produccion_diaria_en_la_entrega.md`](evidencias/produccion_diaria_en_la_entrega.md).

Lo que propongo, y que decides tú:

1. **Decir de qué hoja exacta del diccionario v3.0 salió F36.**
2. **Marcar S11 como no evaluable en esta entrega.** Hoy está como `resoluble` con
   `evidencia: alta`, y eso ya no describe la situación.
3. **No presentar la cifra de oct-2018 como resultado de esta corrida.**

### 5.2 · Tienes 10 commits sin fusionar

`dev-frank` va 10 commits por delante de `main`, con el ADR 0028 (parámetros del detector con su
fuente), las métricas con bootstrap, el PR-AUC con MLlib y las columnas de `modelo_factura`. El
diccionario de Gold cita ese ADR como «escrito en la rama `dev-frank`» justamente porque todavía
no está. Abre el PR cuando quieras y lo reviso.

### 5.3 · Lo que ya tienes de mi lado

- **`src/sim/validacion.py`** (AR06). Corre con `python -m src.sim.validacion --lotes 10`. El
  umbral sale **solo** del escenario A y el B no lo recalibra: hay una prueba que lo comprueba
  recalibrando por su cuenta y comparando. Dos cosas que corregí al medir y que cambian el
  resultado: la alarma se cuenta **desde la semana en que empieza el robo** (si no, una falsa
  alarma anterior daba retardo negativo y contaba como detección), y los kg se comparan **en la
  misma ventana**, lo acumulado hasta la alarma contra lo robado hasta esa semana.
- **El robo de canal no entra al denominador.** Un robo que baja a toda la flota a la vez no lo
  ve un detector que compara unidades entre sí: está en el escenario para medir ese límite, sale
  en `robos_no_detectables_por_diseno` y lo tiene que ver el balance de planta (KPI 1).
- **`src/models/ficha.py`** (AR07) genera la ficha de cada versión desde `vigente.json`. Si tus
  métricas traen `ic`, `datos`, `variables`, `psi` y `sesgos`, la ficha los publica; lo que no
  esté sale como «no cubierto» con su motivo, nunca en blanco.
- **`deriva.a_dict()`** (AR08) para guardar los cortes del PSI junto al modelo. Acuérdate de que
  los cortes son **los del entrenamiento**: si se recalculan con los datos nuevos, el PSI sale
  casi cero siempre y no mide nada.
- **No abras `escenario_b_spec.yaml`.** Sigue fuera del repositorio y su huella SHA-256 queda en
  cada resultado, para poder demostrar después contra qué archivo se midió.

---

## 6. Bruno · Coordinación

### 6.1 · Los roles de la Semana 8 siguen al revés en `docs/equipo.md`

La rotación está invertida respecto al informe v16 (sección 0.1) y al reparto real del trabajo. Lo
corregí en el `README.md`, pero `equipo.md` es tuyo.

| Semanas 8-14 | `docs/equipo.md` dice | El v16 dice |
|---|---|---|
| Frank | Coordinación | **Análisis y modelado** |
| Anghelo | Análisis y modelado | **Calidad y documentación** |
| Wilson | Calidad y documentación | **Ingeniería de datos** |
| Bruno | Ingeniería de datos | **Coordinación** |

### 6.2 · El ADR 0014 de EMR, contigo y con Wilson

Sigue abierto y bloquea mi AR10. El v16 descarta EMR y hace MapReduce con Spark, pero
`CLAUDE.md:53` todavía cita el ADR 0014 como excepción viva y exige Hadoop Streaming, diciendo que
una operación sobre RDD de Spark **no sustituye** esa evidencia. Es un requisito del curso, no una
preferencia nuestra. Si se cierra la ruta EMR, hay que marcar el ADR **y** quitar la excepción de
`CLAUDE.md` en el mismo cambio.

### 6.3 · `main` no tiene protección de rama

Esto lo encontré al revisar por qué los merges salían con un check en rojo, y conviene arreglarlo
antes del hito final:

- `repos/.../branches/main/protection` responde **404**: no hay protección.
- `rulesets` está **vacío**.
- Resultado: los PR #18, #19 y #20 se fusionaron **con 0 revisiones** y con el `cd` en rojo.

`.github/CODEOWNERS` está bien escrito y hasta dice en su cabecera que «quien es dueño de un
archivo no aprueba su propio pull request», pero **CODEOWNERS no hace nada por sí solo**: solo
tiene efecto si la rama está protegida con «Require review from Code Owners». Lo mismo con los
checks: sin «Require status checks to pass» nada impide fusionar en rojo.

Lo que pediría, en Settings → Branches → Add rule sobre `main`:

1. Require a pull request before merging, con **1 aprobación**.
2. Require review from Code Owners.
3. Require status checks to pass: **`ci`**.

Lo configura quien sea dueño del repositorio (Wilson) o tú como coordinación. Yo no tengo ese
permiso, y tampoco debería tenerlo.

### 6.4 · El protocolo ciego y `revision.py`

Tu `docs/validacion/protocolo_ciego.md` usa niveles «documental» y «parcial»; `src/portal/revision.py`
usa 1 a 3. Mi AR17 implementa la inyección ciega y el sellado por SHA-256, y conviene que el
protocolo y el mecanismo digan lo mismo antes de la medición real. Mira
[`docs/modelos/formato_spec_b.md`](modelos/formato_spec_b.md).

---

## 7. Titular de la cuenta AWS

Sigue pendiente desde la auditoría del 26/11, y es lo único de la lista que es un riesgo de
seguridad y no de avance:

- **El usuario raíz no tiene MFA.** Es lo más urgente.
- Ninguno de los cuatro usuarios de IAM tiene MFA.
- Las claves de todos son del 11/10/2026: falta la rotación de la Semana 8.
- Quedan 2 suscripciones de SNS sin confirmar.
- `svc-dashboard` todavía no tiene clave, así que Grafana no se puede conectar.

---

## 8. Dos cosas que conviene no perder de vista

**Una prueba omitida se ve igual que una prueba que pasa.** Las de Spark se omiten en Windows por
falta de `winutils.exe`, así que durante semanas nadie las ejecutó de verdad. Por eso el `ci.yml`
las corre en Ubuntu y **falla a propósito** si alguna queda omitida por Spark. Las 11 pruebas de
integridad del AR05 son el primer caso que se verificó así: en mi máquina se omiten, en CI
corrieron y dieron 0 filas huérfanas.

**Implementado, probado, desplegado y corrido son cuatro cosas distintas.** Casi todo lo que
tenemos está implementado y probado; **nada está corrido sobre los datos reales** hasta la carga
inicial (4.2). Ninguna cifra de este repositorio puede presentarse como resultado de la empresa
hasta entonces.
