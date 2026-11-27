# Seguimiento de los commits de Bruno (B01-B24)

Coordinación, tablero y validación ciega · rama `dev-bruno` · revisa los PR: Anghelo.

**Última actualización:** 26/11/2026 · `dev-bruno` en `25a697b` (subida a `origin`) · `main` en `6f636c1`.

Este archivo se actualiza en el mismo commit de cada cambio. Solo dice «hecho» lo que está en un
commit de `dev-bruno`; «integrado» exige que el PR esté fusionado en `main`. Las casillas de
`PLAN.md` (Fase 6) se marcan `[x]` cuando el commit entra a `main` y su prueba está verificada.

## Resumen

| Estado | Commits |
|---|---|
| Integrado en `main` | — |
| Hecho en `dev-bruno` (sin PR) | B01, B02, B03, B10, B11, B15, B17, B18, B19 |
| Bloqueado por otro integrante | B04, B05, B06, B07, B08, B09, B12, B13, B16 |
| Pendiente de lo anterior | B14, B20, B21, B22, B23, B24 |

**Avance:** 9 de 24 hechos en rama · 0 de 24 integrados.

## Estado por commit

| ID | Asunto | Estado | Commit | Prueba | Requiere / bloqueo |
|---|---|---|---|---|---|
| B01 | CODEOWNERS, plantilla de PR y flujo de Git | hecho | `ace192a` | — (sin pruebas) | — |
| B02 | Base del tablero en Grafana y variables | hecho | `74aa582` + fix `1edbe88` | JSON válido | Columnas de las dimensiones por confirmar con el DDL de W09 |
| B03 | Página Resumen (5 KPI, semáforo, calidad) | hecho, **sin probar en Athena** | `8190855` | JSON válido; 1 consulta por refresco | F06 (`v_kpi_1` a `v_kpi_5`) y A10 (`calidad_silver`); W11 |
| B04 | Página Balance y unidades | bloqueado | — | — | `fact_balance_planta` y `fact_unidad_mes` (W06, W07, W09) |
| B05 | Página Bandeja de alertas | bloqueado | — | — | `v_alerta` (W09); datos con W12 |
| B06 | Página Mercado | bloqueado | — | — | `mercado_mes` (W09); datos con W21 |
| B07 | Página Semáforo de unidades | bloqueado | — | — | `v_semaforo_unidades` (F06, W09); colores con F15 |
| B08 | Vista `v_revision_ciega` | bloqueado | — | — | DDL de `fact_alerta` y `v_alerta` (W09) |
| B09 | Página Revisión ciega | bloqueado | — | — | B08 |
| B10 | Estructura y estilos del portal | hecho | `6822599` | sin prueba en navegador | — |
| B11 | Inicio de sesión SRP con Cognito | hecho, **sin probar con Cognito real** | `e7a8a52` | `node --check` sin errores | `config.js` desplegado (W22) para probarlo |
| B12 | Subida prefirmada y estado por capa | bloqueado | — | — | W22 en `main` (funciones `firmar` y `estado`) |
| B13 | Resumen de KPI y formulario de revisión | bloqueado | — | — | B12; funciones `kpis` y `revision` (W22) |
| B14 | Guía de uso del portal y del tablero | pendiente | — | — | B03-B13 |
| B15 | Protocolo de la validación ciega | hecho | `9e7982f` | — (documento) | — |
| B16 | Seguimiento semanal del KPI 5 | bloqueado | — | — | F06 (`v_kpi_5`) |
| B17 | Plantilla del correo del semáforo | hecho | `2715086` | 16 pruebas pasan | — (W17 la llamará) |
| B18 | Acuerdo de los tres puntos de control | hecho, **falta conformidad de gerencia** | `efb4614` | — (documento) | Firma de la gerencia y umbrales en blanco |
| B19 | Actas y cronograma del cierre | hecho, **faltan fechas objetivo** | `25a697b` | — (documento) | Fecha de la sustentación |
| B20 | Pruebas del portal publicado | pendiente | — | — | W22, B13 |
| B21 | Capturas del tablero | pendiente | — | — | B03-B09 con datos reales |
| B22 | Guion de la demostración | pendiente | — | — | B20, B21 |
| B23 | Estructura de la presentación | pendiente | — | — | F24, A24 |
| B24 | Revisión final y plan de desmontaje | pendiente | — | — | Todo lo anterior |

## Pull requests hacia `main`

| Punto de integración | Commits | Estado |
|---|---|---|
| Después de B02 | B01, B02 | por abrir |
| Después de B09 | B03-B09 | B03 listo; B04-B09 bloqueados |
| Después de B17 | B10-B17 | B10, B11, B15 y B17 listos; B12, B13, B14 y B16 bloqueados |
| Después de B21 | B18-B21 | B18 y B19 listos |
| Después de B24 | B22-B24 | pendiente |

## Avisos a otros integrantes

| Para | Tema | Estado |
|---|---|---|
| Frank (F06) | Interfaz que espera la página Resumen de `v_kpi_1` a `v_kpi_5`: componentes sumables (ver encabezado de `sql/athena/tablero/resumen.sql`) | entregada en F06 (`sql/athena/vistas/`, comprobada por `tests/test_vistas_sql.py`) |
| Anghelo (A10) | Columnas esperadas de `calidad_silver`: `tabla`, `dimension`, `valor`, `meta`, `cumple`, `fecha_control` | por enviar |
| Wilson (W09) | Confirmar `dim_tiempo.anio/mes`, `dim_producto.producto` y `dim_unidad.rol` en el DDL de Gold | por enviar |
| Wilson o Anghelo | Agregar `portal/config.js` a `.gitignore` (lo genera `deploy.sh`) | por enviar |
| Anghelo | `tests/test_linea_base.py` falla en Windows: lee sin `encoding="utf-8"` (pasa con `PYTHONUTF8=1`) | por enviar |

## Decisiones propias

- Refresco del tablero cada 5 min, no cada minuto (costo de Athena; README de `dashboards/grafana/`).
- Protocolo ciego: 5 alertas con doble revisión por semana; niveles de evidencia `documental` y
  `parcial`; «sustracción confirmada» exige evidencia documental y conformidad de la gerencia.
- Responsables de cada KPI en la página Resumen, tomados de la Tabla 4.10: gerencia (KPI 1 y 2), administración (KPI 3), operaciones (KPI 4) y control interno (KPI 5).

## Registro de cambios

| Fecha | Commit | Cambio |
|---|---|---|
| 26/11/2026 | `ace192a` | B01 · CODEOWNERS, plantilla de PR y `docs/flujo_git.md` |
| 26/11/2026 | `74aa582` | B02 · README de Grafana y `_variables.json` |
| 26/11/2026 | `1edbe88` | Fix de B02 · variable `producto` según `dim_producto`; «All» como `__all` |
| 26/11/2026 | `8190855` | B03 · página Resumen y `sql/athena/tablero/resumen.sql` |
| 26/11/2026 | `6822599` | B10 · `portal/index.html` y `portal/estilos.css` |
| 26/11/2026 | `e7a8a52` | B11 · `portal/app.js` con inicio de sesión SRP |
| 26/11/2026 | `9e7982f` | B15 · `docs/validacion/protocolo_ciego.md` |
| 26/11/2026 | `2715086` | B17 · plantilla del semáforo y sus pruebas |
| 26/11/2026 | `efb4614` | B18 · `docs/coordinacion/puntos_de_control.md` |
| 26/11/2026 | `25a697b` | B19 · actas y cronograma del cierre |
