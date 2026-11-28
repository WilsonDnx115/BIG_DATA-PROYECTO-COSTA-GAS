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

## La posición D es la cantidad en kg

Ayer quedó sin declarar porque la estructura sola no alcanzaba. Se resuelve comparando la
**forma** de cada columna numérica con la de `CANTIDAD` en las tres hojas que sí tienen
encabezado. Solo estadísticos de forma; ningún valor:

| Columna | Mediana (log10) | Enteros | Rango p10-p90 |
|---|---|---|---|
| `PETROPERU.CANTIDAD` | 4.35 | 100 % | 4.34–4.37 |
| `SOLGAS.CANTIDAD` | 4.36 | 100 % | 4.35–4.38 |
| `PLUSPETROL.CANTIDAD CARGADA` | 4.37 | 100 % | 4.35–4.38 |
| **PRIMAX, posición D** | **4.36** | **100 %** | **4.34–4.38** |
| PRIMAX, F · G · K · L · M | 4.75 a 4.92 | 1 a 2 % | ancho |
| PRIMAX, N · O · P | 4.83 a 4.96 | 41 a 86 % | muy ancho |

La firma de una carga de cisterna es inconfundible: **enteros y un rango muy estrecho** alrededor
de las 22-24 toneladas. Las demás columnas numéricas son importes (casi todos con decimales) o
tienen una dispersión que ninguna carga tiene. La D es la única que encaja.

**La D trae dato en el 27 % de las filas.** Las demás entran al cruce S12 como
`kg_desconocido`, que es una de las clases que `cruce_s12` ya contempla: se cuentan como compra
sin confirmar, no se descartan ni se inventan.

## Resultado: PRIMAX ya entra a Silver

Corrida sobre el archivo real, sin escribir nada y sin publicar ningún valor:

| Fuente | Filas de salida | Fecha válida | Con kg positivo |
|---|---|---|---|
| `pedidos_primax` | **523** de 3 524 leídas | 99.8 % | 23.5 % |

Una sola fila se descartó por no traer factura. Con esto el cruce tesorería × logística tiene sus
**cuatro** proveedores.

## Lo que sigue sin cubrirse



**La fecha de vencimiento.** Las otras tres hojas traen `VENCIMIENTO` o `VENCE`; PRIMAX solo
tiene dos columnas de fecha, la B y la Q, y la Q está en la misma posición relativa que la
«fecha de pago» de SOLGAS, justo antes del banco. Así que `fecha_vence` queda **no cubierta**
para este proveedor: el cruce S12 usa la fecha de pago cuando falta, que es lo que ya hace con
PETROPERU.

**Las columnas F, K, L, M, N, O y P**, importes parciales: no se declaran mientras ninguna
métrica las necesite, igual que los desgloses de PLUSPETROL.
