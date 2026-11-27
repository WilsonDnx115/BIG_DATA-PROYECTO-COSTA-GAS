# Las 32 hojas sin encabezado claro: por qué no hay nombres y qué hacer con cada una

- **Fecha:** 2026-11-27
- **Responsable:** Wilson Mirano Ríos (Ingeniería de datos)
- **Procedencia:** derivado de [`encabezados_raw.json`](encabezados_raw.json), generado el
  2026-10-08T05:46:28Z desde `../DATASETS` (los 35 archivos del diccionario v3.0, 199 hojas).
  Ese JSON está versionado y no contiene ningún valor de celda de datos.
- **Reproducible sin acceso a `data/raw/`:**

  ```powershell
  python -m src.ingest.encabezados --dudosas docs/evidencias/encabezados_raw.json
  ```

Responde a los puntos 4.1, 4.2 y 4.3 de [`estado_y_pendientes.md`](../estado_y_pendientes.md)
de Anghelo. La respuesta corta es la que menos esperábamos: **en las tres hojas que pedía, los
nombres de columna no existen en el archivo.** No es que alguien no los haya publicado.

## 1. Por qué una hoja queda sin nombres

`src/ingest/encabezados.py` tiene dos barreras, y la salida dice cuál actuó:

| `motivo_dudoso` | Qué pasó | Cuántas hojas |
|---|---|---|
| `identificador_en_la_fila` | La fila que mejor puntúa como encabezado **trae un documento, una razón social o una placa**. Si eso está en la fila, la fila es un registro de datos: la hoja empieza en datos y no tiene encabezado. | **19** |
| `tipo_de_celda` | Ninguna de las primeras 20 filas puntúa como encabezado: todas son del mismo tipo que los datos. Puede ser un cuadro de totales, o un encabezado que la heurística no reconoce. | **13** |

La diferencia importa para quien escribe un contrato. `identificador_en_la_fila` es un **hecho
sobre el archivo**: no hay nombres que publicar. `tipo_de_celda` es un **límite de la heurística**:
puede que los nombres estén ahí y no se reconozcan.

Para el segundo caso agregué `--encabezado ARCHIVO:HOJA:FILA`, que deja declarar la fila a quien
sí abrió la hoja. Lo que **no** levanta es la criba de datos personales: la fila declarada sigue
pasando celda por celda, y si trae un RUC la hoja se sigue tratando como dudosa. Está probado en
`tests/test_encabezados.py::test_encabezado_forzado_no_levanta_la_criba_de_datos_personales`.

## 2. Las tres hojas que pedía Anghelo

### 4.1 · `CO01. GASTOS DETALLADO POR PROYECTO X RANGO DE FECHA.xls`, hoja `Sheet1`

Fila 3, 8 columnas (`A`-`H`), 1 784 filas de datos. Motivo: **`identificador_en_la_fila`**.

La tabla empieza en la fila 3 **con datos**. No hay fila de encabezado. Los nombres originales
que el contrato debería emparejar no existen en el archivo.

### 4.1 · `GASTOS 2020.xls`, hoja `GASTOS FLOTA`

Fila 3, 15 columnas (`A`-`O`), 13 599 filas de datos. Motivo: **`identificador_en_la_fila`**.

Mismo caso. Y aquí sabemos qué trae esa fila, porque es el caso que rompió la primera versión del
inventario y quedó fijado como prueba en
`tests/test_encabezados.py::test_fila_con_ruc_invalida_la_hoja_completa`: mes, placa, concepto de
gasto, proveedor con su RUC pegado al nombre, y planta. Es una fila de gasto, no un encabezado.

### 4.3 · `1. PEDIDOS GLP.xlsx`, hoja `PRIMAX`

Fila 3, 25 columnas (`A`-`Y`). Motivo: **`identificador_en_la_fila`**.

Igual que las otras dos: la hoja arranca en datos. Las otras tres hojas del mismo libro
(`PETROPERU`, `SOLGAS`, `PLUSPETROL`) sí tienen encabezado y ya están en
[`contracts/pedidos_proveedor.yaml`](../../contracts/pedidos_proveedor.yaml).

## 3. Entonces, ¿cómo se escribe el contrato de gastos?

No por nombre de columna, porque no lo hay. Hay dos caminos y el primero es mucho mejor:

**a) Partir de la hoja hermana que sí tiene encabezado.** El mismo libro `GASTOS 2020.xls` trae
`OTROS GASTOS`, con encabezado en la fila 1, 9 columnas y 1 043 filas:

```
MES · FECHA · PLACA · ÁREA · DESCRIPCIÓN · COMENTARIOS · MONTO · PROVEEDOR · PLANTA
```

Ese es el vocabulario del dominio de gastos de flota, publicado por la propia entrega. `GASTOS
FLOTA` es la misma materia con más columnas (15 frente a 9) y mucho más volumen (13 599 frente a
1 043), y las cinco primeras posiciones de su fila de datos encajan con `MES`, `PLACA`, `ÁREA`,
`PROVEEDOR` y `PLANTA`. Mi recomendación es que **A06 declare `OTROS GASTOS` como fuente con
nombres** y `GASTOS FLOTA` como fuente **por posición**, con las columnas que no se puedan nombrar
anotadas en la sección `pendiente:` del contrato, como ya hacen `clientes.yaml` y
`distribuidores.yaml`.

**b) Que yo publique los valores de la primera fila.** No lo voy a hacer, y conviene dejar escrito
por qué: esas filas traen placas y el RUC del proveedor pegado a su razón social.
`CLAUDE.md` prohíbe que un RUC o una placa salgan en cualquier salida, evidencias incluidas. Lo
que sí puedo hacer, cuando tenga la carpeta `../DATASETS` otra vez a mano, es describir en prosa
qué mide cada posición —«la columna F es un monto en soles», «la H es un texto libre»— sin volcar
ningún valor. Si A06 lo necesita para cerrar el mapeo, pídemelo y lo agrego a este archivo.

El libro también tiene `GASTOS FLOTA 2020` (fila 5, 15 columnas, 289 filas), que **sí** tiene
nombres: `ÁREA`, los doce meses y `Total general`. Es un cuadro cruzado de totales por mes, no el
detalle. Útil para cuadrar, no como fuente del contrato.

## 4. El stock diario (4.2): no existe en la entrega

Esto lo puedo firmar, y es la respuesta que cierra el tema. Busqué en las 199 hojas del inventario
las columnas con `STOCK`, `SALDO`, `INICIAL`, `FINAL`, `RESIDUO`, `INVENTARIO` y `EXISTENC`, y
aparte las hojas con 300 filas o más que tengan una columna de fecha. Resultado:

| Lo único que aparece | Qué es en realidad |
|---|---|
| `1. PEDIDOS GLP.xlsx` → `PLUSPETROL`, columna `SALDO` | Saldo de la **factura** del proveedor, no stock de planta |
| `COMPRAS MENSUALES.xlsx` → `Junio 2023` y `Julio 2023`, columna `SALDO EN CONTRA` | Saldo de compra, el mismo caso |
| `Reporte de Produccion CGT 2018.xlsx` | Cuadros **cruzados por mes** (las columnas son los nombres de los meses), y de **2018**, fuera del piloto 2020 |
| `GASTOS 2020.xls` → `PRODUCCIÓN` | 8 columnas, de las que 6 son `ENERO`…`JUNIO`, y 43 filas: un cuadro **mensual** de medio año |

**No hay ninguna hoja con stock por día, ni con stock de planta de ningún grano.** El contrato
Python `pro_01` de `src/common/schemas.py` declara los conceptos correctos (fecha, stock inicial,
producción, ventas, bonificaciones, stock final), pero **no tiene archivo detrás en esta entrega**:
`FuenteInterna` no guarda patrón de archivo justamente porque nunca se encontró la fuente.

Coincide con el `cierres_medidos_fisicamente: 0` del informe v16 y con la bitácora. Anghelo: anótalo
como **no cubierto** y cerramos el punto.

### Lo que eso decide en mi lado

W06 pide `construir(compras, ventas, produccion)` con `delta_stock_kg` «solo si el stock es físico;
si no, nulo». Con esto, **`delta_stock_kg` es nulo siempre** y `fact_balance_planta` se puede
construir sin la fuente de producción. Es decir, el W06 **ya no está bloqueado por A08**: queda
`kg_no_explicados == diferencia_bruta_kg` cuando no hay merma declarada, que es exactamente la
prueba que pide el paquete. Lo registro en un ADR antes de escribirlo, porque es una decisión de
alcance, no un detalle de implementación.

## 5. Las 32 hojas, con su razón

Hojas sin encabezado claro: 32 (identificador_en_la_fila: 19 · tipo_de_celda: 13)

| Archivo | Hoja | Fila | Cols. | Filas | Por qué no hay nombres |
|---|---|---|---|---|---|
| `1. PEDIDOS GLP.xlsx` | PRIMAX | 3 | 25 | ? | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `CLIENTES AGOSTO.xls` | Sheet1 | 1 | 8 | 293 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `CO01. GASTOS DETALLADO POR PROYECTO X RANGO DE FECHA.xls` | Sheet1 | 3 | 8 | 1784 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | TOTAL MARZO | 4 | 11 | 20 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `COMPRAS TOTAL 2020.xlsx` | TOTAL ABRIL | 9 | 7 | 8 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | TOTAL MAYO | 12 | 7 | 2 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | TOTAL JUNIO | 3 | 5 | 11 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | SETIEMBRE | 11 | 18 | 54 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | TOTAL OCT | 3 | 9 | 16 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `COMPRAS TOTAL 2020.xlsx` | TOTAL NOV | 12 | 8 | 6 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | FACT PENDIENTES | 4 | 16 | 45 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `COMPRAS TOTAL 2020.xlsx` | Hoja6 | 13 | 9 | 1 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `COMPRAS TOTAL 2020.xlsx` | Hoja3 | 4 | 3 | 32 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `Cuadro de Control de Flota.xlsx` | Master Doc. | 17 | 51 | 57 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `Cuadro de Control de Flota.xlsx` | Neumáticos | 7 | 29 | 140 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `GASTOS 2020.xls` | GASTOS FLOTA | 3 | 15 | 13599 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `GASTOS 2020.xls` | VENTAS "E" | 1 | 0 | 0 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `GASTOS 2020.xls` | VENTAS "G" | 1 | 0 | 0 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `RATIOS CORPORATIVOS.xlsx` | Conta 0620 | 5 | 8 | ? | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `RELACION DE DISTRIBUIDORES 2020-2021 Act 24092020.xlsx` | Hoja2 | 15 | 9 | ? | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `RELACION DE DISTRIBUIDORES ALMACENES 2020-2021.xlsx` | Hoja2 | 3 | 9 | 12 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `RELCION DE PLANTAS 2020-2021.xlsx` | CESIONES DE DERECHOS | 16 | 5 | 114 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `Reporte de Produccion CGT 2018.xlsx` | ProduccionReal-Cap Efec (Octub) | 3 | 95 | 80 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `Reporte de Produccion CGT 2018.xlsx` | REPORTE GENERAL | 3 | 11 | 12 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
| `ROTACION TANQUES.xlsx` | DATA | 1 | 40 | 64 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `ROTACION TANQUES.xlsx` | TANQUES CAPACIDAD | 1 | 6 | 59 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `VENTAR VENDEDOR AGOSTO.xls` | Sheet1 | 2 | 28 | 49 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `VENTAS ENERO.xls` | Sheet1 | 3 | 26 | 4750 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `VENTAS FEBRERO.xls` | Sheet1 | 3 | 26 | 4448 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `VENTAS MARZO (1).xls` | Sheet1 | 3 | 26 | 5136 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `VENTAS POR PRODUCTO Y VENDEDOR - SETIEMBRE.xls` | Sheet1 | 3 | 26 | 5012 | ninguna de las primeras filas puntúa como encabezado: son todas del mismo tipo que los datos |
| `VENTAS POR PRODUCTO Y VENDEDOR - SETIEMBRE.xls` | Hoja2 | 2 | 8 | 2041 | la fila que mejor puntúa trae un documento, una razón social o una placa, así que es una fila de datos: la hoja no tiene encabezado |
