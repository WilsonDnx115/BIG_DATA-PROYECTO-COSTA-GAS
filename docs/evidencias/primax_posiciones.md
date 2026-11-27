# PRIMAX: qué mide cada posición de la hoja sin encabezado

- **Fecha:** 2026-11-27
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** perfilado estructural de `1. PEDIDOS GLP.xlsx` → hoja `PRIMAX`, hecho fuera del
  repositorio. **De aquí no sale ningún valor de celda**: solo qué fracción de cada posición es
  número, fecha o texto, cuántos valores distintos tiene y con qué patrón encaja.
- **Completa** el cuarto proveedor de [`contracts/pedidos_proveedor.yaml`](../../contracts/pedidos_proveedor.yaml).
  Las otras tres hojas del libro (`PETROPERU`, `SOLGAS` y `PLUSPETROL`) sí tienen encabezado y ya
  están declaradas.

## Forma de la hoja

Desde la fila 3 y sin contar las filas vacías: **524 filas de datos y 26 columnas con dato**
(`A` a `Z`), de **2021 a 2023**. El inventario la contaba con 25 columnas; la diferencia es una
columna que solo tiene dato en el 0.2 % de las filas.

## Lo que cada posición mide

| Posición | Qué mide | En qué se sostiene |
|---|---|---|
| **B** | **Fecha de la factura** | 100 % de las filas, 308 fechas distintas, todas de 2021-2023 |
| **E** | **Producto** | 98 % lleno, 6 valores distintos, texto de 3 a 8 caracteres |
| **G** | Importe de la factura | 84 % lleno, 427 distintos, numérico de 5 dígitos con decimales en el 98 % |
| **H** | **Documento, con forma SERIE-NUMERO** | 100 % de las filas, 513 distintos, **97 % encaja con el patrón `SERIE-NUMERO`** |
| **Q** | **Fecha de pago** | 56 % lleno, 238 fechas distintas de 2021-2023; la misma proporción que la columna de pagos |
| **R** | Banco | 54 % lleno, 8 valores distintos |
| **A**, **U**, **X**, **Z** | — | **No cubiertas: vacías** |
| **C**, **I**, **J**, **V**, **W**, **Y** | — | **No cubiertas: menos del 20 % de las filas con dato y 1 a 4 valores distintos** |
| **D** | Candidata a cantidad, sin confirmar con la estructura | 100 % enteros, mediana de 5 dígitos y rango muy estrecho (del percentil 10 al 90 varía menos de un 10 %), que es la forma de una carga estándar. Pero **solo el 27 % de las filas la trae**: no alcanza para declararla como los kg de la factura |
| **F**, **K**, **L**, **M**, **N**, **O**, **P** | Importes parciales | numéricos de 4 a 6 dígitos con dato en el 11 % al 56 % de las filas; por su forma son desgloses de importe (percepción, saldo, pagos), no cantidades |
| **S**, **T** | — | **No cubiertas: 7 % de las filas, valores de 0 a 1 dígito** |

## Qué falta para que PRIMAX entre al contrato

Dos cosas, y ninguna es mía:

1. **Lectura por posición en el lector de contratos.** `src/silver/contratos.py` empareja por
   nombre de encabezado normalizado, y esta hoja empieza en datos. Es el mismo bloqueo que tiene
   el contrato de gastos, y está descrito con el formato propuesto en
   [`gastos_posiciones.md`](gastos_posiciones.md), sección 4.
2. **Confirmar cuál es la cantidad en kg.** El cruce S12 compara los kg de tesorería contra los
   de logística con una tolerancia de 1 kg (`TOL_KG_S12`), así que declarar la columna
   equivocada no daría un error: daría descuadres falsos en el KPI 3. Con la estructura sola, la
   posición D es la única candidata y no alcanza. Quien abra la hoja lo resuelve en un minuto
   mirando el encabezado visual del libro.

Mientras tanto, el contrato declara las tres hojas con encabezado y deja PRIMAX como no cubierta,
con este documento como evidencia. **No se inventa una cuarta fuente**: una fuente de tesorería
mal mapeada se vería en el KPI 3 como descuadres entre tesorería y logística, que es justamente
la señal que el proyecto quiere medir.
