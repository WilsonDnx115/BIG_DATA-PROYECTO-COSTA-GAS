# Protocolo de la validación documental ciega

Proyecto Costa Gas Trujillo · responsable: Coordinación (Bruno Ordóñez Gonzales).
Referencias: informe v16, sección 4.3 (validación documental ciega y KPI 5) y Tabla 4.11 (página
«Revisión ciega»); [ADR 0013](../adr/0013-modelo-base-v6-evidencia-documental.md) y
[ADR 0019](../adr/0019-revision-alerta-solo-inserciones.md); reglas de `CLAUDE.md`
(«Conciliación, señales y modelos»).

## 1. Propósito

Una alerta del sistema es un caso para revisar, **no un robo confirmado**. Este protocolo
establece cómo se comprueba con documentos si cada alerta señala una discrepancia real, sin que el
revisor sepa cuánto «confía» el modelo en ella. De esa revisión salen el KPI 5, la precisión
documental y la etiqueta positiva del siguiente reentrenamiento de S12.

## 2. Quién revisa

| Papel | Quién | Condición |
|---|---|---|
| Revisor principal | Coordinación (Bruno) | No es autor del modelo ni de las señales que se revisan |
| Segundo revisor | Un integrante distinto del autor del modelo y del revisor principal | Solo para la doble revisión y las discrepancias (sección 8) |
| Autor del modelo y de las señales | Análisis y modelado | **No revisa** sus propias alertas; puede responder dudas técnicas sobre la fuente, no sobre el caso |

Cada revisor entra al portal con su propio usuario de Cognito. El revisor **no se escribe en el
formulario**: la función `revision` lo toma del token (`cognito:username`), así que cada decisión es
atribuible a una persona.

## 3. Con qué documentos

Una alerta solo se confirma con un **segundo registro** independiente del que la generó:

| Documento | Uso |
|---|---|
| Orden SCOP | Placa cargada, volumen y fecha del despacho (S1, S2) |
| Factura o comprobante | Kg, precio, tipo de cambio y placa facturada (S2, S3, S4, S6, S10, S12) |
| Registro de tesorería (`1. PEDIDOS GLP`) | Fecha de pago y vencimiento de la factura (S12) |
| Guía de remisión | Unidad, fecha y cantidad trasladada |
| Nota de crédito | Corrección posterior de una factura |
| Parte de producción o cierre diario | Residuo y ajustes de planta (S11) |

El revisor trabaja con la **muestra real enmascarada** o con Silver/Gold, con los identificadores
seudonimizados que ya trae el expediente. Nunca abre `data/raw/` ni copia al portal, a las notas o
al chat nombres, DNI ni RUC de personas naturales. Las notas describen el documento («factura
F001-123 con 2 000 kg»), no a la persona.

## 4. Qué ve el revisor (ceguera)

- La lista sale de la vista `costagas_gold.v_revision_ciega` (B08), que **no tiene** las columnas
  de probabilidad, puntaje ni grado de evidencia del modelo.
- El orden es aleatorio y estable durante la semana (`xxhash64(id_alerta || semana)`): la posición
  no revela si la alerta vino del top o del control aleatorio.
- El expediente muestra solo los hechos: orden SCOP, volumen, fecha, unidad declarada, comprobante
  y la señal que disparó.
- Durante la revisión, el revisor no abre la página «Bandeja de alertas» ni consultas que muestren
  el puntaje. Con el perfil `costagas` puede leer Gold, así que esta condición es **de
  procedimiento**: se declara al cerrar cada semana (sección 9).

## 5. Tamaño de la muestra por semana

Cada lunes se arma la muestra con las alertas abiertas de la semana anterior:

1. **Top 20:** las 20 alertas de mayor prioridad del modelo (por evidencia y percentil dentro de
   cada señal; los puntajes de señales distintas no se comparan entre sí).
2. **Control aleatorio: 10 alertas** elegidas al azar entre las restantes, con la semilla de la
   semana. Sirven para estimar la tasa base.
3. Las 30 se mezclan y se presentan en el orden aleatorio de la vista. El revisor no sabe a qué
   grupo pertenece cada una; el grupo queda registrado aparte para el cálculo (sección 7).

Si hay menos de 30 alertas abiertas, se revisan todas y se informa el tamaño real. Si en la semana
no hay alertas, la semana se registra como «sin muestra», **no como 0 %**.

**Plazo:** la muestra de la semana se revisa a más tardar el viernes. Lo que quede sin revisar
pasa a la semana siguiente y se informa como pendiente.

## 6. Cómo se registra cada revisión

En el portal, desde la página «Revisión ciega» de Grafana (enlace `#revision/<id_alerta>`):

| Campo | Valores |
|---|---|
| Estado | `confirmada` (el segundo registro muestra la discrepancia que señala la alerta) o `descartada` (los documentos coinciden y no hay discrepancia) |
| Causa | digitación · pago tardío · entrega parcial · nota de crédito · sustracción confirmada · sin explicar |
| Nivel de evidencia | `1` indicio: lo marcó el sistema (no lo registra el revisor) · `2` descuadre confirmado: la factura, el pago y la orden SCOP confirman la diferencia · `3` pérdida atribuida: la causa se verificó en campo con pesaje, SCOP y ruta (Tabla 4.8f; `src/portal/revision.py` solo acepta 1, 2 o 3) |
| Nota | Texto breve: qué documentos se compararon y qué mostraron. Sin datos personales |

Reglas:

- **Solo inserción** (ADR 0019): cada decisión es una fila nueva en `gold/revision_alerta`. Nunca
  se edita ni se borra una revisión. Una corrección es otra fila, con su propia fecha y revisor.
- La decisión vigente de cada alerta es su **última fila**, que resuelve la vista `v_alerta`.
- **Sin segundo registro no hay confirmación.** Si falta el documento, la alerta no se registra:
  queda pendiente y se informa como «pendiente por falta de documento».
- «Sustracción confirmada» exige nivel `3` (verificación en campo) y la conformidad de la gerencia;
  `revision.py` rechaza esa causa en otro nivel y el sistema no la declara por sí solo.
- Las señales S1 y S8 no se usan como etiqueta débil: una alerta solo cuenta como confirmada por
  esta revisión documental. S8 es no resoluble y no entra a la muestra.

## 7. Cálculo del KPI 5 y métricas asociadas

Con la última revisión de cada alerta (`v_alerta`), por semana y por mes:

| Métrica | Fórmula |
|---|---|
| **KPI 5 · confirmación documental de alertas** | confirmadas / (confirmadas + descartadas) de la muestra |
| Precisión documental del top 20 | confirmadas del top 20 / revisadas del top 20 |
| Tasa base | confirmadas del control aleatorio / revisadas del control aleatorio |
| Recuperación de casos conocidos | casos conocidos que el sistema alertó / casos conocidos (`null` si no hay casos conocidos documentados) |
| Pendientes | alertas de la muestra sin revisión al cierre (incluye las que no tienen documento) |

- Las alertas pendientes **no** entran al denominador del KPI 5 y se informan aparte.
- Si una métrica no puede medirse (sin muestra, sin casos conocidos), se registra `null` con su
  causa; nunca 0.
- El seguimiento semanal lo genera `src/reportes/kpi5.py` (B16) en `docs/evidencias/kpi5/`.

## 8. Doble revisión y discrepancias

1. **Doble revisión:** 5 alertas de cada muestra semanal (elegidas al azar) las revisa también el
   segundo revisor, sin ver la decisión del primero.
2. **Acuerdo:** se informa el porcentaje de alertas de doble revisión con el mismo estado.
3. **Discrepancia** (estado distinto entre revisores):
   - Ambos revisores comparan los documentos y anotan qué vio cada uno.
   - Si llegan a un acuerdo, el revisor principal registra la decisión final como una fila nueva,
     con una nota que cita la discrepancia.
   - Si no hay acuerdo, decide un tercer integrante distinto del autor del modelo, y su decisión se
     registra como la última fila.
   - Si la discrepancia nace de que falta un documento, la alerta queda pendiente hasta tenerlo.
4. Las discrepancias y su resolución se anotan en el acta de la semana (`docs/coordinacion/actas.md`).

## 9. Cierre semanal

Cada viernes, el revisor principal deja constancia en el acta:

- tamaño de la muestra (top 20, control aleatorio y doble revisión) y cuántas se revisaron;
- KPI 5, precisión del top 20, tasa base, acuerdo entre revisores y pendientes;
- declaración: «durante la revisión no se consultó el puntaje ni la probabilidad de las alertas».

Las pruebas automáticas del código no cierran esta validación: la aceptación exige datos reales y
la revisión independiente descrita aquí.
