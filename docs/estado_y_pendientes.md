# Costa Gas Trujillo · dónde estamos y qué falta

**Fecha:** 27/11/2026 (actualizado tras el merge de los PR #13 y #16) · **Escribe:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación, Semanas 8-14)

Este documento resume lo que llevo hecho y, sobre todo, **qué necesito de cada uno para poder seguir**. Las secciones de Wilson, Frank y Bruno están escritas para que puedan pasárselas directamente a su asistente.

Repositorio: `WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS`

## Lo que falta, en corto

| Quién | Qué | Desbloquea |
|---|---|---|
| **Wilson** | Publicar los encabezados de `CO01. GASTOS` y `GASTOS FLOTA` en `encabezados_raw.md` | Mi A06 |
| **Wilson** | Decir de qué archivo y hoja sale el stock diario, o confirmar que no existe | La mitad de mi A08 |
| **Wilson** | Publicar los encabezados de la hoja `PRIMAX` | El cuarto proveedor de mi A07 |
| **Frank** | Escribir `detector.calibrar_h` (su F14) | Mi A18 |
| **Bruno** | Corregir los roles de la Semana 8 en `docs/equipo.md` | Coherencia con el v16 |
| **Bruno y Wilson** | Decidir qué pasa con el ADR 0014 de EMR y la evidencia de Hadoop Streaming | Un requisito del curso |
| **Titular de AWS** | MFA del usuario raíz y de los cuatro usuarios de IAM | Seguridad de la cuenta |

Lo mío que ya no depende de nadie está hecho. Con el #13 mergeado me quedan desbloqueados el A11, el A13 y el A19, que hago yo en cuanto el PR #17 entre.

El detalle de cada punto está abajo, con el archivo y la hoja exactos.

---

## 1. Estado de los pull requests

| PR | Autor | Estado | Qué trae |
|---|---|---|---|
| [#15](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/15) | Anghelo | **Mergeado** 27/11 | A01-A05: README y PLAN al v16, ADR 0015-0021, bitácora |
| [#17](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/17) | Anghelo | **Abierto** | A07, A08, A10, A12, A14-A17 y medio A11, más un arreglo de privacidad |
| [#13](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/13) | Wilson | **Mergeado** | W01-W05, W08, W13, W23: ingesta, job de Gold, dimensiones, CD y el `ci.yml` |
| [#16](https://github.com/WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS/pull/16) | Bruno | **Mergeado** | Coordinación, tablero, portal, validación ciega y controles |

Los PR #13 y #16 entraron a `main` mientras el mío estaba abierto. El único choque fue `tests/conftest.py`, que tocamos Wilson y yo: lo resolví quedándome con su sesión de Iceberg y añadiéndole mis dos arreglos de Windows. Suite en verde con todo integrado, y ahora **el `ci.yml` de Wilson ya corre sobre mi PR**, que es la primera verificación real de las pruebas de Spark.

---

## 2. Lo que llevo hecho

### Mergeado en `main` (PR #15)

| Commit | Qué |
|---|---|
| `e28b910` | **A01** README con el flujo real del v16, señales S1-S12, `us-east-2`, costo de US$ 0.89, sin Power BI, y la tabla de quién cuida qué carpeta |
| `17a9a3f` | **A02** PLAN con `us-east-2`, el paso 4.4.4 con Grafana Cloud y sus 6 páginas, y la sección «Fase 6» con las 96 casillas del equipo |
| `7c68c98` | **A03** ADR 0015 YouTube Data API y 0016 Grafana Cloud |
| `a1b3901` | **A04** ADR 0017 cola de corridas con `MaxRetries` 0 y 0018 lago `op/` |
| `8f17fae` | **A05** ADR 0019 `revision_alerta`, 0020 regla de Gold y 0021 memoria de la Lambda |
| `6bae64c` | Renumeración del `0011` duplicado a `0022` y anotación del `0014` de EMR |
| `4b2ccf1` | `docs/bitacora.md` y `PLAN.md` sin `yt-dlp` |

### En el PR #17, esperando revisión

| Commit | Qué |
|---|---|
| `fa5ec36` | **Arreglo de privacidad** (ver sección 3) |
| `616e47f` | **A12** prueba de privacidad en tres frentes |
| `f88153a` | **A10** `calidad_silver.py` |
| `280e8e5` | **A14** compensación de pares redigitados |
| `e61c3eb` | **A15** PSI de deriva |
| `454c823` | **A16** escenario A sin robos |
| `db40cf2` | **A17** inyección ciega del escenario B |
| `5826f56` | **A11 parcial** `--validar` de contratos |
| `57b5037` | Pruebas de Spark y encoding arregladas en Windows |
| `153cf8a` | **A07** contrato `pedidos_proveedor` |
| `a0a79fc` | **A08 parcial** maestros de distribuidores y clientes |
| merge | Integra `main` con los PR #13 y #16, resolviendo el conflicto de `conftest.py` |

Las pruebas quedan en **verde, 0 fallos**, ya con el trabajo de Wilson y de Bruno dentro. Las de Spark se omiten en mi máquina por falta de winutils; ahora las corre la CI en Ubuntu sobre este mismo PR.

---

## 3. El hallazgo que más importa: una fuga de datos personales

Mi prueba del A12 encontró esto en `src/bronze_to_silver/handler.py`:

```python
df["ruc"] = df["documento_norm"].where(df["clase_documento"] == "RUC")
```

Conservaba **todos** los RUC válidos, incluidos los de prefijo 10, 15 y 17, que son de persona natural. En la tabla `red_02_distribuidores` había **33 RUC de personas publicados en Silver**.

Con la muestra sintética no expone a nadie, pero con los 35 archivos reales sí lo haría, y va contra la regla de `CLAUDE.md` de no publicar RUC de personas naturales.

Ya está arreglado: ahora solo pasa el RUC de persona jurídica y el documento completo sigue en `documento_hash`. Verificado sobre el parquet regenerado: **0 RUC de persona natural**, los 34 de empresa intactos, las 125 filas conservadas.

Wilson, toqué tu handler por esto. Es una línea y lo dejé en un commit aparte de su prueba para que lo veas suelto.

---

## 4. Wilson · Ingeniería de datos

### Lo que me tiene bloqueado

**4.1 · Encabezados de gastos.** Bloquea mi **A06** entero.

`docs/evidencias/encabezados_raw.md` dice literalmente «Sin encabezado claro» para:

- `CO01. GASTOS DETALLADO POR PROYECTO X RANGO DE FECHA.xls`, hoja `Sheet1` (encabezado en la fila 3): **8 columnas `A`-`H`, nombres no publicados**
- `GASTOS 2020.xls`, hoja `GASTOS FLOTA` (fila 3): **15 columnas `A`-`O`, nombres no publicados**

Un contrato empareja **encabezado original → nombre estándar**, así que sin los nombres originales no puedo escribir `contracts/gastos.yaml`. Yo no puedo abrir `data/raw/`; tú sí tienes el rol. Lo que necesito es que publiques esos nombres en `encabezados_raw.md` con el mismo formato de tabla que el resto del inventario.

El `contracts/README.md` ya lo tenía anotado como pendiente desde antes.

**4.2 · De dónde sale el stock diario.** Bloquea la mitad que falta de mi **A08**.

Busqué `STOCK`, `SALDO`, `RESIDUO`, `INICIAL` y `FINAL` en las 3 172 líneas del inventario: **no hay ninguna hoja con stock por día**. Las de `Reporte de Produccion CGT 2018.xlsx` son resúmenes por mes o no publican encabezados.

Existe el contrato Python `pro_01` en `src/common/schemas.py` con los conceptos correctos (fecha, stock inicial, producción, ventas, bonificaciones, stock final), pero `FuenteInterna` no guarda patrón de archivo, así que no sé de qué Excel y hoja salen. Necesito el archivo, la hoja y la fila del encabezado.

Si resulta que ese dato **no existe** en la entrega, dímelo igual: lo anoto como no cubierto y cerramos el tema. Coincide con lo que ya dice la bitácora y con el `cierres_medidos_fisicamente: 0` del v16.

**4.3 · Encabezados de PRIMAX.** Completa mi A07.

Hoja `PRIMAX` de `1. PEDIDOS GLP.xlsx` (fila 3): 25 columnas `A`-`Y` sin nombres. Con eso añado el cuarto proveedor a `pedidos_proveedor`. No es urgente, las otras tres ya están.

**4.4 · El #13 ya entró, gracias.** Con eso me quedan desbloqueados tres commits y los hago yo:

- **A11**: le agrego el paso `--validar` a tu `ci.yml`
- **A13**: la prueba de integridad referencial contra tu `dimensiones.py` del W08
- **A19**: la ficha de cada versión del modelo contra tu registro del W13

### Lo que te dejo listo

- `contracts/pedidos_proveedor.yaml` con su DDL generado, para que lo despliegues
- `contracts/distribuidores.yaml` y `contracts/clientes.yaml`, ídem
- `python -m src.silver.contratos --validar`, que revisa los 8 contratos y sus DDL y sale con código 1 si algo falla. Mételo en el `ci.yml` cuando quieras
- El archivo sellado del escenario B, para que lo subas a `sim/_spec/` (tu W19). **No se lo pases a Frank.** Su huella SHA-256 está publicada en `docs/modelos/formato_spec_b.md`

### Un aviso sobre tu `externos_job.py`

Revisé tu W21 y ya cubre entero lo que era mi A09, siguiendo mi ADR 0015. Por eso **no voy a escribir** los contratos del entorno: duplicarlos sería mantener dos esquemas de la misma tabla, que `CLAUDE.md` prohíbe. Tu ADR 0023 ya descarta además lo de meter `landing/externo/` en `_archivos.yaml`, así que tampoco lo toco. Estamos alineados.

---

## 5. Frank · Análisis y modelado

### Lo que me tiene bloqueado

**5.1 · `detector.calibrar_h`.** Bloquea mi **A18**, la validación con 100 semillas.

`src/models/detector.py` no existe todavía, ni en `main` ni en ninguna rama. Mi A18 necesita llamar a `detector.calibrar_h` para fijar el umbral con el escenario A y después medir la detección sobre el escenario B **sin volver a tocar el umbral**. Esa es la Tabla 4.8h.

### Lo que ya tienes listo de mi lado

**`src/quality/redigitados.py`** para tu F13:

```python
from src.quality.redigitados import compensar
df = compensar(movimientos, entidad="placa_norm", valor="kg_error", periodo="fecha", ventana=2)
```

Añade `redigitado` y `<valor>_compensado`. Dos avisos importantes:

- Se aplica sobre el **desvío con signo**, no sobre los kg absolutos. Un par +X/−X solo se cancela en el desvío; sobre los kg cada semana parte de una base distinta. En la serie del escenario A esa columna se llama `kg_error`.
- **Los errores sin corregir no se tocan.** Un +500 suelto sigue visible, porque puede ser justo lo que hay que detectar.

**`src/models/deriva.py`** para el control de deriva:

```python
cortes = deriva.deciles_entrenamiento(pdf_entrenamiento, VARIABLES)  # se guarda con el modelo
resultado = deriva.evaluar(pdf_nuevas, cortes)
if deriva.requiere_reentreno(resultado): ...
```

Dos cuidados que están en el módulo y conviene que conozcas:

- Los cortes son **los del entrenamiento**. Si se recalculan con los datos nuevos, el PSI sale casi cero siempre y no mide nada.
- Con menos de `PSI_MIN_OBS` (100) facturas devuelve `"insuficiente"` en vez de un número. Y «insuficiente» **no** dispara reentrenamiento: no saber si hay deriva no es lo mismo que saber que la hay.

**`src/sim/escenario_a.py`**, la serie sin robos para calibrar tu umbral. Está calibrada contra los agregados publicados, no a ojo: 5.013 M kg de envasado en 2020 frente a los 5.0 de la Tabla 1.5, Spearman de 0.68 frente al 0.66 medido, y merma de 0.5 % exacta. Trae estacionalidad de invierno, la caída de la cuarentena, 15 eventos legítimos documentados y errores de digitación corregidos y sin corregir. Todo eso lo tiene que tolerar el detector sin confundirlo con un robo.

### Lo que te pido expresamente

**No abras `escenario_b_spec.yaml`.** No está en el repositorio justo por eso. Si sabes dónde están los robos, terminarás ajustando el detector a esos casos y la precisión que reportemos en la Tabla 4.8h no medirá nada. Lo tengo sellado con su SHA-256 publicado, así que después se puede demostrar contra qué archivo se midió.

Te adelanto solo lo que necesitas para diseñar: son **seis robos**, uno de ellos de un tipo que el detector no contempla por diseño, y otro que por construcción **no se puede detectar** comparando unidades entre sí (tiene que salir en el balance de planta, KPI 1). Ese segundo está ahí para que el límite del método quede medido y escrito, no para castigar al detector.

---

## 6. Bruno · Coordinación

**6.1 · `docs/equipo.md` tiene los roles al revés.**

La rotación de la Semana 8 está invertida respecto al informe v16 (sección 0.1):

| Semanas 8-14 | `docs/equipo.md` dice | El v16 dice |
|---|---|---|
| Frank | Coordinación | **Análisis y modelado** |
| Anghelo | Análisis y modelado | **Calidad y documentación** |
| Wilson | Calidad y documentación | **Ingeniería de datos** |
| Bruno | Ingeniería de datos | **Coordinación** |

El v16 coincide con lo que cada uno está haciendo de verdad. Lo corregí en el `README.md`, pero `equipo.md` es tuyo. Vi que tu PR #16 no lo toca.

**6.2 · El ADR 0014 de EMR, contigo y con Wilson.**

Lo dejé **anotado, no reemplazado**, porque la decisión no me toca. El problema son dos cosas encadenadas:

- El v16 ya descarta EMR («corre sobre instancias EC2 que cobran por hora y la política base las deniega») y su módulo M5 hace MapReduce con **Spark**. El W05 de Wilson está hecho así.
- Pero `CLAUDE.md:53` todavía cita el ADR 0014 como excepción viva, y además exige que «Hadoop MapReduce se ejecuta con Hadoop Streaming» y que «una operación sobre RDD de Spark **no sustituye** esa evidencia».

Eso choca de frente con el v16 y con el W05, y **es un requisito del curso, no una preferencia nuestra**. Hay que decidirlo antes del hito final. Si cerramos la ruta EMR, hay que marcar el ADR **y** quitar la excepción de `CLAUDE.md` en el mismo cambio, si no queda apuntando a una decisión muerta.

**6.3 · Tu `protocolo_ciego.md` encaja con mi escenario B.**

Vi que tu PR #16 trae `docs/validacion/protocolo_ciego.md`. Mi A17 implementa la inyección ciega y el sellado por SHA-256; convendría que el protocolo que escribes y el mecanismo que programé digan lo mismo. Cuando lo revises, mira `docs/modelos/formato_spec_b.md`.

---

## 7. Titular de la cuenta AWS

Sigue pendiente desde la auditoría del 26/11:

- **El usuario raíz no tiene MFA.** Es lo más urgente.
- Ninguno de los cuatro usuarios de IAM tiene MFA.
- Las claves de todos son del 11/10/2026: falta la rotación de la Semana 8.
- Quedan 2 suscripciones de SNS sin confirmar.
- `svc-dashboard` todavía no tiene clave, así que Grafana no se puede conectar.

---

## 8. Lo que me queda a mí, en orden

| Commit | Lo hago cuando |
|---|---|
| **A06** contrato de gastos | Wilson publique los encabezados (4.1) |
| **A08** producción diaria | Wilson diga de dónde sale el stock (4.2) |
| **A11** paso en el `ci.yml` | **Ya puedo**, el #13 entró |
| **A13** integridad referencial de Gold | **Ya puedo**, el #13 entró |
| **A18** validación con 100 semillas | Frank tenga `detector.calibrar_h` (5.1) |
| **A19** ficha de cada versión del modelo | **Ya puedo**, el #13 entró |
| **A20** técnicas del curso con archivo y línea | Estén W05-W21 |
| **A21** plan de pruebas ejecutado | Estén W11 y W16-W22, y tenga acceso de lectura |
| **A22** diccionario de Gold | Esté W09 |
| **A23** bitácora al cierre | Al final; ya existe el archivo |
| **A24** insumos del informe v17 | Estén F24, W24 y mi A21 |

**A09 no lo voy a hacer**: ya lo cubre el W21 de Wilson y duplicarlo rompería la regla de no mantener dos esquemas de la misma tabla.

---

## 9. Una cosa que no está verificada y conviene saber

Las 2 pruebas con Spark de mi A10 **se omiten** en mi máquina, porque Spark en Windows necesita `winutils.exe` hasta para leer un archivo. No es un problema del código, es que no tengo dónde correrlo.

Con el #13 ya mergeado, el `ci.yml` corre en Ubuntu sobre mi PR y esa es la primera vez que alguien las ejecuta de verdad. **Hasta que ese check pase en verde, el A10 no se puede dar por probado.**
