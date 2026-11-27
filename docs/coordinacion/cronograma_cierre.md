# Cronograma del cierre (Fase 6 · implementación del informe v16)

Proyecto Costa Gas Trujillo · mantiene: Coordinación.

**Fuente del estado:** las casillas de la Fase 6 de [`PLAN.md`](../../PLAN.md) en `main`. Aquí no se marca nada como hecho: el estado se copia de `PLAN.md`, donde cada dueño marca `[x]` su propia casilla en el commit que la cumple. Para actualizar esta tabla se vuelve a leer `PLAN.md`.

**Corte:** 26/11/2026 (main en 6f636c1) · **avance:** 2 de 96 commits marcados `[x]` en `PLAN.md`.

**Fechas objetivo:** por fase, dentro de la Semana 14 del informe (23/11 - 27/11/2026, hito final y sustentación). Una fase empieza cuando su fase previa entregó lo que la siguiente necesita; el campo «Requiere» de cada commit está en el plan de cada integrante.

| Fase | Wilson | Frank | Anghelo | Bruno | Fecha objetivo | Estado |
|---|---|---|---|---|---|---|
| 1 · Base | W01-W03 | F01-F04 | A01-A09 | B01-B02 | 26/11/2026 | 2 de 18 |
| 2 · Gold y demostración | W04-W11 | F05-F07 | A10-A13 | B03-B09 | 27/11/2026 | 0 de 22 |
| 3 · Aprendizaje automático | W12-W15 | F08-F17 | A14-A19 | - | 27/11/2026 | 0 de 20 |
| 4 · Controles y operación | W16-W19 | F18 | - | B10-B17 | 27/11/2026 | 0 de 13 |
| 5 · Externos, portal y CD | W20-W23 | - | A20-A22 | B18-B21 | 27/11/2026 | 0 de 11 |
| 6 · Resultados y cierre | W24 | F19-F24 | A23-A24 | B22-B24 | 27/11/2026 | 0 de 12 |

## Detalle por commit

Estado: `hecho` = `[x]` en `PLAN.md`; `pendiente` = casilla sin marcar. «Fecha objetivo» la completa Coordinación; «Observación» registra dependencias o bloqueos.

### Fase 1 · Base

| Commit | Responsable | Asunto | Fecha objetivo | Estado | Observación |
|---|---|---|---|---|---|
| W01 | Wilson | crear_tablas solo con los DDL vigentes | | pendiente |  |
| W02 | Wilson | Lambda de ingesta de landing a Bronze | | pendiente |  |
| W03 | Wilson | funcion de ingesta en el stack | | pendiente |  |
| F01 | Frank | — | | pendiente |  |
| F02 | Frank | — | | pendiente |  |
| F03 | Frank | — | | pendiente |  |
| F04 | Frank | — | | pendiente |  |
| A01 | Anghelo | docs: README alineado con el informe v16 | | hecho |  |
| A02 | Anghelo | docs: PLAN con us-east-2, Grafana y la fase de implementacion del v16 | | hecho |  |
| A03 | Anghelo | docs(adr): 0015 YouTube Data API y 0016 Grafana Cloud | | pendiente |  |
| A04 | Anghelo | docs(adr): 0017 cola de corridas y 0018 lago op/ | | pendiente |  |
| A05 | Anghelo | docs(adr): 0019 revisiones, 0020 regla de Gold y 0021 memoria de Lambda | | pendiente |  |
| A06 | Anghelo | feat(contratos): contrato de gastos con conductor seudonimizado | | pendiente |  |
| A07 | Anghelo | feat(contratos): contrato de tesoreria con fecha de pago y vencimiento | | pendiente |  |
| A08 | Anghelo | feat(contratos): produccion diaria, distribuidores y clientes | | pendiente |  |
| A09 | Anghelo | feat(contratos): BCRP, Facilito y YouTube hacia silver/entorno | | pendiente |  |
| B01 | Bruno | chore(equipo): CODEOWNERS por area, plantilla de PR y flujo de Git | | pendiente | commit en dev-bruno; falta el PR hacia main |
| B02 | Bruno | feat(tablero): base del tablero en Grafana con variables comunes | | pendiente | commit en dev-bruno; falta el PR hacia main |

### Fase 2 · Gold y demostración

| Commit | Responsable | Asunto | Fecha objetivo | Estado | Observación |
|---|---|---|---|---|---|
| W04 | Wilson | esqueleto del job de Gold con MERGE en Iceberg | | pendiente |  |
| W05 | Wilson | patron MapReduce en Spark SQL hacia gold/mr | | pendiente |  |
| W06 | Wilson | — | | pendiente |  |
| W07 | Wilson | — | | pendiente |  |
| W08 | Wilson | dimensiones del modelo estrella | | pendiente |  |
| W09 | Wilson | — | | pendiente |  |
| W10 | Wilson | — | | pendiente |  |
| W11 | Wilson | — | | pendiente |  |
| F05 | Frank | — | | pendiente |  |
| F06 | Frank | — | | pendiente |  |
| F07 | Frank | — | | pendiente |  |
| A10 | Anghelo | feat(calidad): tabla calidad_silver desde silver/_control | | pendiente |  |
| A11 | Anghelo | ci: pytest con PySpark local, cfn-lint y validacion de contratos | | pendiente |  |
| A12 | Anghelo | test(privacidad): sin nombres, DNI ni RUC de persona natural | | pendiente |  |
| A13 | Anghelo | test(gold): integridad referencial de hechos contra dimensiones | | pendiente |  |
| B03 | Bruno | feat(tablero): pagina Resumen con 5 KPI, semaforo y calidad | | pendiente | commit en dev-bruno; espera F06 (vistas v_kpi_1 a v_kpi_5) y A10 (calidad_silver) para probarse en Athena |
| B04 | Bruno | feat(tablero): pagina Balance y unidades con Pareto por rol | | pendiente |  |
| B05 | Bruno | feat(tablero): pagina Bandeja de alertas con expediente | | pendiente |  |
| B06 | Bruno | feat(tablero): pagina Mercado con precios, tipo de cambio y eventos | | pendiente |  |
| B07 | Bruno | feat(tablero): pagina Semaforo de unidades | | pendiente |  |
| B08 | Bruno | feat(athena): vista de revision ciega sin puntaje ni probabilidad | | pendiente |  |
| B09 | Bruno | feat(tablero): pagina Revision ciega con enlace al formulario | | pendiente |  |

### Fase 3 · Aprendizaje automático

| Commit | Responsable | Asunto | Fecha objetivo | Estado | Observación |
|---|---|---|---|---|---|
| W12 | Wilson | — | | pendiente |  |
| W13 | Wilson | registro de modelos S12 con vigente.json | | pendiente |  |
| W14 | Wilson | — | | pendiente |  |
| W15 | Wilson | — | | pendiente |  |
| F08 | Frank | — | | pendiente |  |
| F09 | Frank | — | | pendiente |  |
| F10 | Frank | — | | pendiente |  |
| F11 | Frank | — | | pendiente |  |
| F12 | Frank | — | | pendiente |  |
| F13 | Frank | — | | pendiente |  |
| F14 | Frank | — | | pendiente |  |
| F15 | Frank | — | | pendiente |  |
| F16 | Frank | — | | pendiente |  |
| F17 | Frank | — | | pendiente |  |
| A14 | Anghelo | feat(calidad): compensacion de pares redigitados para el detector | | pendiente |  |
| A15 | Anghelo | feat(deriva): PSI con deciles del entrenamiento y minimo de 100 | | pendiente |  |
| A16 | Anghelo | feat(sim): escenario A calibrado con agregados de 2020 | | pendiente |  |
| A17 | Anghelo | feat(sim): inyeccion ciega del escenario B con especificacion sellada | | pendiente |  |
| A18 | Anghelo | feat(sim): validacion del detector con escenarios A y B en lotes | | pendiente |  |
| A19 | Anghelo | docs(modelos): ficha automatica de cada version del modelo | | pendiente |  |

### Fase 4 · Controles y operación

| Commit | Responsable | Asunto | Fecha objetivo | Estado | Observación |
|---|---|---|---|---|---|
| W16 | Wilson | — | | pendiente |  |
| W17 | Wilson | — | | pendiente |  |
| W18 | Wilson | — | | pendiente |  |
| W19 | Wilson | — | | pendiente |  |
| F18 | Frank | — | | pendiente |  |
| B10 | Bruno | feat(portal): estructura y estilos de la pagina del portal | | pendiente |  |
| B11 | Bruno | feat(portal): inicio de sesion SRP con Cognito | | pendiente |  |
| B12 | Bruno | feat(portal): subida con URL prefirmada y estado por capa | | pendiente |  |
| B13 | Bruno | feat(portal): resumen de KPI y formulario de revision | | pendiente |  |
| B14 | Bruno | docs(guias): guia de uso del portal y del tablero | | pendiente |  |
| B15 | Bruno | docs(validacion): protocolo de la validacion documental ciega | | pendiente |  |
| B16 | Bruno | feat(reportes): seguimiento semanal del KPI 5 | | pendiente |  |
| B17 | Bruno | feat(controles): plantilla del correo del semaforo diario | | pendiente |  |

### Fase 5 · Externos, portal y CD

| Commit | Responsable | Asunto | Fecha objetivo | Estado | Observación |
|---|---|---|---|---|---|
| W20 | Wilson | — | | pendiente |  |
| W21 | Wilson | — | | pendiente |  |
| W22 | Wilson | — | | pendiente |  |
| W23 | Wilson | despliegue continuo con OIDC y aprobacion | | pendiente |  |
| A20 | Anghelo | docs: tecnicas de ingenieria con archivo y linea | | pendiente |  |
| A21 | Anghelo | docs(evidencias): plan de pruebas del sistema ejecutado | | pendiente |  |
| A22 | Anghelo | docs: diccionario de datos de Gold | | pendiente |  |
| B18 | Bruno | docs(coordinacion): acuerdo de los tres puntos de control con gerencia | | pendiente |  |
| B19 | Bruno | docs(coordinacion): actas y cronograma del cierre | | pendiente |  |
| B20 | Bruno | test(portal): pruebas del portal publicado con capturas | | pendiente |  |
| B21 | Bruno | docs(evidencias): capturas del tablero con datos reales | | pendiente |  |

### Fase 6 · Resultados y cierre

| Commit | Responsable | Asunto | Fecha objetivo | Estado | Observación |
|---|---|---|---|---|---|
| W24 | Wilson | — | | pendiente |  |
| F19 | Frank | — | | pendiente |  |
| F20 | Frank | — | | pendiente |  |
| F21 | Frank | — | | pendiente |  |
| F22 | Frank | — | | pendiente |  |
| F23 | Frank | — | | pendiente |  |
| F24 | Frank | — | | pendiente |  |
| A23 | Anghelo | docs: bitacora de decisiones y riesgos al cierre | | pendiente |  |
| A24 | Anghelo | docs(resultados): insumos y cierre de hipotesis para el informe v17 | | pendiente |  |
| B22 | Bruno | docs(sustentacion): guion de la demostracion de extremo a extremo | | pendiente |  |
| B23 | Bruno | docs(sustentacion): estructura de la presentacion por integrante | | pendiente |  |
| B24 | Bruno | chore(entrega): revision final del repositorio y plan de desmontaje | | pendiente |  |

## Integración

| Rama | Pull request hacia `main` | Revisa |
|---|---|---|
| `dev-bruno` | después de B02, B09, B17, B21 y B24 | Anghelo |
| `dev-wilson`, `dev-frank`, `dev-anghelo` | al cerrar cada bloque de su fase | Coordinación y el integrante de apoyo |

Ver [`docs/flujo_git.md`](../flujo_git.md).
