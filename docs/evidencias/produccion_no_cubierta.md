# Producción diaria: no cubierta por la entrega

- **Fecha:** 2026-11-27
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** inventario de encabezados
  [`encabezados_raw.json`](encabezados_raw.json), generado el 2026-10-08 desde los 35 archivos del
  diccionario v3.0 (199 hojas), y la búsqueda firmada por Ingeniería de datos en
  [`hojas_sin_encabezado.md`](hojas_sin_encabezado.md), sección 4.

**Esto no es un pendiente: es un resultado.** La interfaz `produccion` del WP 0.8 pide stock por
día y en la entrega no hay ninguna hoja que lo tenga. Se escribe aquí, con la búsqueda que lo
sostiene, y el sistema lo declara en sus salidas en lugar de rellenarlo.

## Qué se buscó y cómo

La búsqueda se hizo sobre el inventario versionado, no sobre los archivos: no hace falta abrir
`data/raw/` para reproducirla.

```powershell
python -m src.ingest.encabezados --dudosas docs/evidencias/encabezados_raw.json
```

Se recorrieron las **199 hojas** buscando dos cosas:

1. columnas con `STOCK`, `SALDO`, `INICIAL`, `FINAL`, `RESIDUO`, `INVENTARIO` y `EXISTENC`;
2. hojas de 300 filas o más que tuvieran alguna columna de fecha, por si el stock estuviera con
   otro nombre.

## Qué apareció, y por qué ninguna sirve

| Hoja | Qué es en realidad |
|---|---|
| `1. PEDIDOS GLP.xlsx` → `PLUSPETROL`, columna `SALDO` | Saldo de la **factura** del proveedor, no stock de planta |
| `COMPRAS MENSUALES.xlsx` → `Junio 2023` y `Julio 2023`, columna `SALDO EN CONTRA` | Saldo de compra: el mismo caso |
| `Reporte de Produccion CGT 2018.xlsx` | Cuadros **cruzados por mes** (las columnas son los nombres de los meses) y de **2018**, fuera del piloto 2020 |
| `GASTOS 2020.xls` → `PRODUCCIÓN` | 8 columnas, de las que 6 son `ENERO`…`JUNIO`, y 43 filas: un cuadro **mensual** de medio año |

**No hay ninguna hoja con stock por día, ni con stock de planta de ningún grano.** Las dos
primeras son saldos de dinero, no de producto; las dos últimas son cuadros cruzados por mes, que
sirven para cuadrar un total pero no dan una fila por día.

Coincide con dos cosas que el proyecto ya tenía escritas: el `cierres_medidos_fisicamente: 0` del
informe v16 y la frase de la sección 1.1, «el inventario final de planta no se contabiliza
físicamente, sino que se calcula para que el balance diario siempre cuadre».

## El contrato `pro_01` existe, pero no tiene archivo detrás

[`src/common/schemas.py`](../../src/common/schemas.py) declara `pro_01` con los conceptos
correctos —`fecha`, `stock_inicial`, `produccion`, `ventas`, `bonificaciones`, `stock_final`— y su
propio comentario dice que son «los conceptos de F36 del informe v6, no encabezados reales». Su
`FuenteInterna` **no guarda patrón de archivo**, y no es un olvido: nunca se encontró la fuente.

Por eso no se escribe `contracts/produccion_diaria.yaml`. Un contrato YAML empareja encabezado
original con nombre estándar; sin hoja de origen sería un esquema inventado, y `CLAUDE.md` prohíbe
exactamente eso: no completar períodos sin cobertura ni presentar ceros como mediciones.

## Qué consecuencia tiene, y dónde se ve

| Dónde | Consecuencia |
|---|---|
| **S11** (cierre de planta sin medición física) | Queda **sin fuente** en esta entrega. La señal está implementada en [`src/signals/s11.py`](../../src/signals/s11.py) y probada, pero no hay datos a los que aplicarla |
| **KPI 1** (diferencia no explicada) | La variación de stock se toma como **0** y la vista publica `stock_es_supuesto = true` cuando `delta_stock_kg` es nulo ([`v_kpi_1.sql`](../../sql/athena/vistas/v_kpi_1.sql)). El tablero lo etiqueta: no se presenta como medición |
| **KPI 2** | Hereda el mismo supuesto y lo declara igual |
| **`fact_balance_planta`** (W06) | `delta_stock_kg` es nulo siempre, así que la tabla se construye sin la fuente de producción: `kg_no_explicados` es la diferencia bruta cuando no hay merma declarada |

## La cita de S11 que el informe v17 tiene que corregir

El catálogo ([`src/signals/catalogo.yaml`](../../src/signals/catalogo.yaml), S11) le asigna a la
señal la fuente **F36**, la ventana **oct-2018** y la referencia «residuo cero en 31 días; un
ajuste de producción de −9 095». Esa referencia solo puede salir de una tabla **con una fila por
día**, porque cuenta 31 días de un mes de 31.

Lo que el inventario muestra de 2018 es `Reporte de Produccion CGT 2018.xlsx`, y sus hojas son
cuadros **cruzados por mes**. Son dos afirmaciones que no encajan, y la que está verificada contra
los archivos es la del inventario.

Para el informe v17, lo que hay que hacer con esa cita:

1. **Decir de qué hoja exacta del diccionario v3.0 salió F36.** Si esa hoja es una de las cuatro de
   la tabla de arriba, la referencia de 31 días no se sostiene y hay que quitarla o reescribirla.
2. **Marcar S11 como no evaluable en esta entrega**, igual que S8 está marcada como no resoluble.
   El catálogo hoy la da por `resoluble` con `evidencia: alta`, y eso ya no describe la situación.
3. **No presentar la cifra de oct-2018 como resultado de esta corrida.** `CLAUDE.md` lo dice:
   el informe es referencia, no una certificación de lo que corrió.

## Cómo se reabre

Si la empresa entrega el parte diario de planta —una fila por día con stock inicial, producción,
ventas, bonificaciones y stock final—, se escribe `contracts/produccion_diaria.yaml` con esas seis
columnas más `stock_final_es_calculado`, se regenera su DDL y S11 vuelve a tener fuente sin tocar
nada más: la interfaz `produccion` del WP 0.8 ya está declarada en
[`src/signals/contratos.py`](../../src/signals/contratos.py) y la señal ya está escrita.
