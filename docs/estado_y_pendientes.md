# Costa Gas Trujillo · dónde estamos y qué falta

**Fecha:** 27/11/2026 · **Escribe:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación,
Semanas 8-14) · Repositorio: `WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS`

Al día con los PR #21, #22 y #23 ya en `main`. Este documento dice **qué quedó hecho**, **qué
falta y de quién depende** y **por qué `main` aparece con un check en rojo**. Cada sección está
escrita para que se la puedan pasar directamente a su asistente.

## Resumen en una tabla

| Quién | Qué falta | Qué desbloquea |
|---|---|---|
| **Wilson** | **Lectura por posición** en `src/silver/contratos.py` y la entrada `gastos` en `transformar.TRANSFORMACIONES` | Tres contratos que ya tienen sus posiciones medidas: gastos, PRIMAX y producción diaria |
| **Wilson + titular de AWS** | El rol de despliegue por OIDC: **el workflow `cd` falla en todos los merges** (sección 5) | Que `main` deje de estar en rojo y que WR07-WR10 puedan desplegar |
| **Wilson** | WR07-WR10: despliegue, carga inicial a S3 y primera corrida | **AR16, AR17, AR21 y AR22**, y todas las cifras reales del informe |
| **Wilson** | Subir la especificación sellada del escenario B a `sim/_spec/` y correr la Lambda | **AR18 y AR19**, la medición ciega del detector |
| **Frank** | Fusionar `dev-frank`: **10 commits sin entrar a `main`** | El ADR 0028, las métricas con bootstrap y las columnas de `modelo_factura` |
| **Frank** | Revisar S11 y F36 con la corrección de la sección 3 | Que el informe v17 cite bien la fuente |
| **Bruno** | Roles de la Semana 8 en `docs/equipo.md`; protocolo ciego alineado con `revision.py` | Coherencia con el v16 y la revisión ciega real |
| **Bruno o Wilson** | Proteger la rama `main` (sección 6.3) | Que CODEOWNERS sirva de algo y que no se pueda fusionar en rojo |
| **Titular de AWS** | MFA del usuario raíz y de los cuatro usuarios de IAM, y rotar claves | La seguridad de la cuenta |

**De mis 24 commits hay 17 hechos.** Los 7 que faltan esperan alguna fila de arriba. No me queda
nada que dependa solo de mí, con una excepción que dejo a decisión del equipo en la sección 7.

---

## 1. Lo que hice

### En `main`

| Commit | Qué |
|---|---|
| **AR01** | `contracts/gastos.yaml` con su DDL y su prueba, y las posiciones de las tres hojas de gasto medidas sobre la entrega |
| **AR02** | La producción diaria, verificada contra los archivos (sección 3) |
| **AR03** | El `ci.yml` valida los contratos con `python -m src.silver.contratos --validar` |
| **AR04** | `pytest.importorskip("pyspark")` en la prueba que rompía el workflow `cd` |
| **AR05** | `tests/test_integridad_gold.py`: `left_anti` de cada hecho contra cada dimensión, 0 filas huérfanas |
| **AR06** | `src/sim/validacion.py`: validación del detector con 100 semillas en lotes de 10 |
| **AR07** | `src/models/ficha.py`: la ficha de cada versión del modelo se genera del registro |
| **AR08** | `deriva.a_dict()` y `desde_dict()`: los cortes del PSI se guardan con el modelo |
| **AR09** | `calidad_silver.bloqueos()`: qué KPI no se publica si su Silver incumple la Tabla 3.7 |
| **AR10** | `CLAUDE.md` alineado al informe **v17** |
| **AR11** | ADR 0030: un solo esquema por tabla |
| **AR12** | `tests/test_sin_pendientes.py`: falla si aparece una fórmula que anuncia un valor ausente |
| **AR13** | Privacidad en las alertas y en las ocho vistas de Athena |
| **AR14** | `docs/diccionario_gold.md`: las 13 tablas de Gold desde sus DDL |
| **AR15** | `docs/tecnicas_curso.md`: diez técnicas más, cada una con archivo y línea |
| **AR20** | Anexo A con el uso de IA |
| **AR23** | Bitácora al cierre: decisiones 0015-0030 y seis riesgos materializados |

**Pruebas: 600 en local (0 fallos, 82 omitidas por Spark en Windows) y `ci` en verde en Ubuntu**,
donde las de Spark sí corren: el workflow falla a propósito si alguna queda omitida por Spark.

### Lo que me queda, y de qué depende

| Commit | Espera |
|---|---|
| **AR16** calidad de la carga inicial | La carga a S3 (WR09) |
| **AR17** plan de pruebas ejecutado | WR09-WR16 |
| **AR18** entrega sellada del escenario B | Que Wilson suba el archivo a `sim/_spec/` |
| **AR19** cierre de la medición ciega | AR18 y la corrida de la Lambda |
| **AR21** contratos al día con filas efectivas | La carga a S3: las filas efectivas salen de `silver/_control/` |
| **AR22** README con el estado real | La carga a S3 |
| **AR24** insumos del informe v17 | FR24, WR21 y mi AR17 |

---

## 2. Lo que encontré en los 35 archivos, sin copiar ningún valor

Ya tengo la entrega. **No entra al repositorio** y de ella no sale ningún valor de celda: lo que
publico es qué mide cada posición, medido con descriptores de estructura (qué fracción es número,
fecha o texto, cuántos valores distintos hay, con qué patrón encaja). 35 archivos, 115 MB, que es
lo que esperaba el diccionario v3.0.

### 2.1 · La columna `PLACA` de `OTROS GASTOS` no contiene placas

| Medida | Valor |
|---|---|
| Filas con dato | 1 043 de 1 043 |
| Valores distintos | 29 |
| Con forma de placa peruana | **0 %** |
| Numéricos | 12 % |
| Coincidencia con las 26 placas de `GASTOS FLOTA` | **ninguna** |

29 valores distintos se parece al tamaño de la flota, así que probablemente es un **código interno
de unidad**, pero sin una tabla que lo traduzca **no se puede unir con `dim_unidad`**. El contrato
lo guarda como `unidad_codigo`, no como `placa_norm`. El mapeo que todos dábamos por hecho no se
sostiene.

### 2.2 · Lo que Wilson necesita de `GASTOS FLOTA`

Está completo en [`evidencias/gastos_posiciones.md`](evidencias/gastos_posiciones.md):

| Posición | Qué mide | Medida que lo sostiene |
|---|---|---|
| A | mes como texto | 12 valores, todos empiezan por un nombre de mes |
| B | fecha | 100 % convertible, todas de 2020 |
| **C** | **placa** | **94 % con forma de placa; 26 placas distintas** |
| D | agrupador de flota | 4 valores |
| **E** | **categoría del gasto** | **13 categorías; una es combustible, 15.6 % de las filas** |
| F | descripción libre | 1 245 distintos; 15.8 % nombra combustible, coherente con E |
| G | **monto en soles** | 100 % numérico, 61 % con decimales, sin negativos ni ceros |
| H | proveedor | 558 distintos |
| I | planta | 1 valor, coincide al 100 % con `PLANTA` de `OTROS GASTOS` |
| J-O | — | no cubiertas: vacías o con menos del 0.05 % de dato |

**`es_combustible` sale de la posición E.** `CO01/Sheet1` es gasto por proyecto y de 2019:
ninguna de sus posiciones supera el 1 % de valores con forma de placa, así que no alimenta
`fact_unidad_mes`.

### 2.3 · PRIMAX

524 filas de 2021-2023 y 26 columnas con dato
([`evidencias/primax_posiciones.md`](evidencias/primax_posiciones.md)). Determinadas: **B** fecha,
**E** producto, **G** importe, **H** documento (97 % con forma `SERIE-NUMERO`), **Q** fecha de
pago, **R** banco.

**La cantidad en kg no se puede determinar desde la estructura.** La posición D es la única
candidata —100 % enteros, mediana de 5 dígitos, rango muy estrecho: la forma de una carga
estándar— pero solo el 27 % de las filas la trae. No la declaro, y el motivo importa: el cruce
S12 compara kg con 1 kg de tolerancia, así que una columna equivocada no daría un error, daría
**descuadres falsos en el KPI 3**, que es justo la señal que queremos medir. Quien abra la hoja lo
resuelve en un minuto.

---

## 3. La corrección más importante: el stock diario sí existe

En el PR #21 declaré la producción diaria como **no cubierta**, apoyándome en la búsqueda sobre el
inventario. **Con los archivos delante, esa conclusión era falsa.**

`Reporte de Produccion CGT 2018.xlsx` → hoja **`ProduccionReal-Cap Efec (Octub)`**:

| Dónde | Qué hay |
|---|---|
| Columna A | **31 fechas, 31 días distintos, del 2018-10-01 al 2018-10-31** |
| Fila 1, columnas 2, 9, 16, 23 y 30 | `STOCK INICIAL`, `VENTAS`, `BONIFICACIONES`, `STOCK FINAL(PLAT. + UNID)`, `PRODUCCION` |
| Fila 2 | subencabezado por marca, con una columna `TOTAL` en cada bloque |

Son los cinco conceptos de la interfaz `produccion` del WP 0.8, con el grano que S11 necesita.

**Por qué el inventario no la encontró, y no fue un descuido:** la hoja tiene el encabezado en
**dos filas** —concepto arriba, marca abajo— con bloques cada siete columnas. La heurística busca
una sola fila y la clasificó como dudosa por `tipo_de_celda`, que es el motivo que el propio
inventario describe como «puede que los nombres estén ahí y no se reconozcan». **La lección vale
para las otras 12 hojas de ese grupo:** `tipo_de_celda` no significa «no hay encabezado».

**Qué cambia y qué no.** S11 recupera su fuente y la cita del informe («residuo cero en 31 de 31
días, oct-2018») **se sostiene**: F36 es esa hoja. Pero es de **2018**: para el piloto 2020 sigue
sin haber stock diario, así que `delta_stock_kg` queda nulo y el KPI 1 mantiene
`stock_es_supuesto`. **Se recupera la validación de S11, no el KPI 1 del piloto.**

Todo está en [`evidencias/produccion_diaria_en_la_entrega.md`](evidencias/produccion_diaria_en_la_entrega.md).

---

## 4. Wilson · lo que te toca

### 4.1 · Lectura por posición: un solo cambio desbloquea tres contratos

`src/silver/contratos.py` empareja **por nombre de encabezado normalizado**, y las tres hojas
—`GASTOS FLOTA`, `CO01/Sheet1` y `PRIMAX`— empiezan en datos. Apuntar `fila_encabezado` a la
primera fila de datos sería peor que no leerlas: los nombres de columna saldrían de una fila que
trae una placa y un proveedor con su RUC.

Lo que hace falta, con las descripciones ya medidas:

```yaml
  - id: gastos_flota_2020
    archivo: '^GASTOS 2020\.xls$'
    hojas: '^GASTOS FLOTA$'
    primera_fila: 3          # la hoja empieza en datos
    posiciones:              # letra de columna → nombre estándar
      A: mes_texto
      B: fecha
      C: placa_norm
      D: area
      E: categoria
      F: descripcion
      G: monto_soles
      H: proveedor
      I: planta
```

Y `transformar.TRANSFORMACIONES` necesita su entrada `gastos`. Hay una prueba que deja ese estado
escrito: si agregas la transformación y no la actualizas, te enteras ahí.

La producción diaria necesita además poder tomar **la columna `TOTAL` de cada bloque**, porque su
encabezado son dos filas con bloques repetidos cada siete columnas.

### 4.2 · La carga inicial (WR07-WR10)

De ahí salen **todas** las cifras reales: mis AR16, AR17, AR21 y AR22, tu WR21 y los FR19-FR24.
Antes de subir, confirmar que la regla `costagas-silver-actualizado` siga en **DISABLED**
([ADR 0020](adr/0020-regla-gold-prefijos-internos.md)). La entrega son 35 archivos y 115 MB: menos
de US$ 0.01. Mi perfil de AWS es de solo lectura, así que la carga la haces tú o el titular.

### 4.3 · El escenario B

La Lambda `costagas-validacion-detector` ya está declarada (tu WP 0.11) y corre mi
`src/sim/validacion.py`. Falta que **subas el archivo sellado a `sim/_spec/`**. Verifiqué hoy que
la huella SHA-256 publicada en [`modelos/formato_spec_b.md`](modelos/formato_spec_b.md) coincide
exactamente con el archivo que tengo: el sello está intacto y se puede demostrar.

---

## 5. Por qué `main` sale en rojo, y de quién es

En cada merge aparece **1 check fallando de 3**. No es de las pruebas y **no lo causó ningún
commit nuestro de código**:

| Check | Resultado |
|---|---|
| `ci / Pruebas, plantilla y contratos` | ✅ **success** |
| `cd / Change set (sin ejecutar)` | ❌ **failure** |
| `cd / Ejecutar el change set` | ⏭️ skipped, porque el anterior falló |

El paso que falla es el **séptimo** del job, y los seis anteriores pasan (pruebas incluidas):

```
7. Run aws-actions/configure-aws-credentials@v4: failure
   Credentials could not be loaded, please check your action inputs:
   Could not load credentials from any providers
```

Es el **rol de despliegue por OIDC**. El workflow pide un token a GitHub y asume
`costagas-github-deploy`, cuya confianza se declara en `infra/cloudformation/stack.yaml`. Ese rol
todavía no existe en la cuenta, o su política de confianza no acepta a este repositorio: hasta que
el stack se despliegue una primera vez, no hay credenciales que cargar.

**No es normal en el sentido de «está bien»**, pero sí es esperable mientras WR07 no se haya
ejecutado. Lo resuelve Wilson con el titular de la cuenta. Dos formas:

1. Desplegar el stack una primera vez a mano, con el perfil de ingeniería, para que el rol exista.
2. O condicionar el job de `cd` a que el secreto/rol esté configurado, para que no marque en rojo
   lo que todavía no se puede hacer.

`cd.yml` es tuyo según CODEOWNERS, así que la decisión es tuya. Lo que sí quedó arreglado es lo
que **sí** era nuestro: ese mismo workflow fallaba antes en el paso 5 por un
`ModuleNotFoundError: No module named 'pyspark'`, y hoy el paso 5 pasa en verde (AR04).

---

## 6. Bruno · lo que te toca

### 6.1 · Los roles de la Semana 8 siguen al revés en `docs/equipo.md`

| Semanas 8-14 | `docs/equipo.md` dice | El informe dice |
|---|---|---|
| Frank | Coordinación | **Análisis y modelado** |
| Anghelo | Análisis y modelado | **Calidad y documentación** |
| Wilson | Calidad y documentación | **Ingeniería de datos** |
| Bruno | Ingeniería de datos | **Coordinación** |

### 6.2 · El ADR 0014 de EMR: cerrado, y conviene saberlo

Wilson lo resolvió con el [ADR 0029](adr/0029-mapreduce-con-spark-sin-emr.md), que reemplaza al
0014: el patrón MapReduce se ejecuta con Spark SQL en Glue y EMR queda fuera. Ya ajusté `CLAUDE.md`
al informe v17 en consecuencia. **Este punto ya no bloquea a nadie.**

### 6.3 · `main` no tiene protección de rama

- La API de protección de `main` responde **404** y los *rulesets* están **vacíos**.
- Resultado: los PR #18, #19, #20, #22 y #23 se fusionaron **con 0 revisiones** y con `cd` en rojo.

`.github/CODEOWNERS` está bien escrito y dice en su cabecera que «quien es dueño de un archivo no
aprueba su propio pull request», pero **CODEOWNERS no hace nada por sí solo**: solo tiene efecto
con la rama protegida. Lo que pediría, en Settings → Branches sobre `main`:

1. Require a pull request before merging, con **1 aprobación**.
2. Require review from Code Owners.
3. Require status checks to pass: **`ci`** (no `cd`, hasta que 5 esté resuelto).

### 6.4 · El protocolo ciego y `revision.py`

Tu `docs/validacion/protocolo_ciego.md` usa niveles «documental» y «parcial»; `revision.py` usa 1
a 3. Conviene alinearlos **antes** de la medición real, no después.

---

## 7. La única decisión que queda abierta de mi lado

**La medición ciega del detector (AR19) se puede correr hoy, en local, sin AWS.** Los escenarios A
y B son sintéticos, viven en `sim/` y `src/sim/validacion.py` ya está probado: `--lotes 10` daría
las 100 semillas y la Tabla 4.8h completa.

No lo hice por mi cuenta por una razón de método, no técnica: **la medición cierra el protocolo
ciego**, y cerrarlo implica revelar la especificación del escenario B. Eso debería ocurrir cuando
el equipo lo dé por cerrado, y con la corrida oficial de la Lambda si vamos a reportarla como
corrida en AWS. Una corrida local es una **prueba local**, y en este proyecto implementado,
probado, desplegado y corrido son cuatro cosas distintas.

Si el equipo prefiere tener ya la cifra del método, la corro y la publico marcada como medición
local, con la huella del archivo sellado para que se pueda repetir en AWS y comparar.

---

## 8. Titular de la cuenta AWS

Sigue pendiente desde la auditoría del 26/11, y es lo único de toda la lista que es un riesgo de
seguridad y no de avance:

- **El usuario raíz no tiene MFA.** Es lo más urgente.
- Ninguno de los cuatro usuarios de IAM tiene MFA.
- Las claves de todos son del 11/10/2026: falta la rotación de la Semana 8.
- Quedan 2 suscripciones de SNS sin confirmar.
- `svc-dashboard` todavía no tiene clave, así que Grafana no se puede conectar.
- Y lo de la sección 5: sin el rol de despliegue, `cd` seguirá en rojo en cada merge.

---

## 9. Dos cosas que conviene no perder de vista

**Una prueba omitida se ve igual que una prueba que pasa.** Las de Spark se omiten en Windows por
falta de `winutils.exe`. Por eso `ci` las corre en Ubuntu y **falla a propósito** si alguna queda
omitida por Spark. Las 11 pruebas de integridad de Gold del AR05 son el primer caso verificado
así: en mi máquina se omiten, en CI corrieron y dieron 0 filas huérfanas.

**Implementado, probado, desplegado y corrido son cuatro cosas distintas.** Casi todo está
implementado y probado; **nada está corrido sobre los datos reales** hasta la carga inicial.
Ninguna cifra de este repositorio puede presentarse como resultado de la empresa hasta entonces.
