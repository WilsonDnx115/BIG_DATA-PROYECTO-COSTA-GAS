# Gastos: qué mide cada posición de las hojas sin encabezado

- **Fecha:** 2026-11-27
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** perfilado estructural de los 35 archivos de la entrega (diccionario v3.0),
  hechos fuera del repositorio. **De aquí no sale ningún valor de celda**: lo que se publica es
  qué fracción de cada posición es número, fecha o texto, cuántos valores distintos tiene y si
  encaja con un patrón conocido. Ningún nombre, DNI, RUC ni placa.
- **Responde a** la sección 2 de [`hojas_sin_encabezado.md`](hojas_sin_encabezado.md), donde
  Ingeniería de datos dejó dicho que en estas hojas **los nombres de columna no existen**: las
  tres empiezan en datos.

## Por qué hace falta este documento

Un contrato empareja encabezado original con nombre estándar. Cuando la hoja no tiene encabezado,
lo único que queda es decir **qué mide cada posición**, y decirlo con algo más que una impresión:
cada fila de las tablas de abajo se sostiene en una medida reproducible sobre la hoja.

## 1 · `GASTOS 2020.xls` → `GASTOS FLOTA` (fila 3, 15 columnas, 13 599 filas de datos)

| Posición | Qué mide | En qué se sostiene |
|---|---|---|
| **A** | Mes, como texto | 12 valores distintos, 100 % texto, todos empiezan por un nombre de mes |
| **B** | Fecha del gasto | 100 % convertible a fecha, todas de 2020, 363 distintas |
| **C** | **Placa de la unidad** | 94 % encaja con la forma de placa peruana; 26 placas distintas en 35 valores |
| **D** | Agrupador de flota (área o tipo de unidad) | 4 valores distintos, texto de 10 a 16 caracteres, 100 % lleno |
| **E** | **Categoría del gasto** | 13 categorías; **una de ellas es combustible** y cubre el 15.6 % de las filas |
| **F** | Descripción libre del gasto | 1 245 valores distintos, texto de 4 a 58 caracteres; el 15.8 % nombra combustible, coherente con E |
| **G** | **Monto en soles** | 100 % numérico, de 1 a 5 dígitos, 61 % con decimales, sin negativos y sin ceros |
| **H** | Proveedor (razón social) | 558 distintos, texto de 21 a 76 caracteres |
| **I** | Planta | 1 solo valor, que coincide al 100 % con la columna `PLANTA` de `OTROS GASTOS` |
| **J**, **K** | — | **No cubiertas: completamente vacías** |
| **L**, **M**, **N**, **O** | — | **No cubiertas: menos del 0.05 % de las filas tienen dato** (1 o 2 valores distintos en 13 599 filas) |

**La columna que necesita Ingeniería de datos es la E.** De ahí sale `es_combustible` para
`fact_unidad_mes`, y con él el KPI 4 y la señal S9. No hace falta interpretar el texto libre de
la F: la categoría de la E ya lo clasifica, y la F confirma la proporción (15.6 % frente a
15.8 %).

## 2 · `CO01. GASTOS DETALLADO POR PROYECTO X RANGO DE FECHA.xls` → `Sheet1` (fila 3, 8 columnas, 1 784 filas)

| Posición | Qué mide | En qué se sostiene |
|---|---|---|
| **A** | Fecha del gasto | 94 % convertible a fecha, **todas de 2019**, 34 distintas |
| **B** | — | **No cubierta: completamente vacía** |
| **C** | Proyecto o centro de costo | 107 distintos, 97 % texto de 2 a 19 caracteres |
| **D** | Documento del gasto | 1 341 distintos, texto de 8 a 17 caracteres, 92 % lleno |
| **E** | Categoría del gasto | 71 categorías; el 15.1 % de las filas cae en las de combustible |
| **F** | Descripción libre | 324 distintos, de 4 a 86 caracteres |
| **G** | **Monto en soles** | 100 % numérico, hasta 4 dígitos, 59 % con decimales |
| **H** | Proveedor (razón social) | 234 distintos, de 24 a 74 caracteres |

**Esta hoja no se puede atribuir a una unidad.** Ninguna de sus ocho posiciones supera el 1 % de
valores con forma de placa: es gasto por **proyecto**, no por vehículo. Además es de **2019**, un
año fuera del piloto 2020. Sirve para el gasto de planta; no alimenta `fact_unidad_mes`.

## 3 · Un hallazgo que cambia el mapeo previsto: `OTROS GASTOS` no trae placas

La hoja `OTROS GASTOS` sí tiene encabezado (fila 1, 9 columnas, 1 043 filas) y su columna se
llama `PLACA`. Pero **ninguno de sus valores tiene forma de placa**:

| Medida sobre `OTROS GASTOS.PLACA` | Valor |
|---|---|
| Filas con dato | 1 043 de 1 043 |
| Valores distintos | 29 |
| Con forma de placa peruana | **0 %** |
| Numéricos | 12 % |
| Largo | de 2 a 20 caracteres |
| Coincidencia con las 26 placas de `GASTOS FLOTA` | **ninguna** |

29 valores distintos se parece al tamaño de la flota, así que lo más probable es que sea un
**código interno de unidad**. Pero eso no se puede afirmar desde la estructura, y sin una tabla
que traduzca ese código a placa **no se puede unir con `dim_unidad`**. Por eso el contrato no
mapea esa columna a `placa_norm`: lo guarda como `unidad_codigo`, un atributo, y declara que no
es una llave.

El mapeo que suponía la guía (`PLACA` → `placa_norm`) no se sostiene con los archivos. La única
fuente de gasto atribuible a una unidad es `GASTOS FLOTA`.

## 4 · Resultado de leerlas: las tres hojas ya entran a Silver

El lector de contratos admite ahora fuentes **por posición** (`primera_fila` y `posiciones`), y
las tres hojas de gasto están declaradas en [`contracts/gastos.yaml`](../../contracts/gastos.yaml).
Esto es lo que devuelve el pipeline sobre los archivos reales, **sin escribir nada y sin publicar
ningún valor**: solo conteos y tasas.

```powershell
python -c "from src.silver import procesar; procesar.procesar_archivo('<ruta>/GASTOS 2020.xls', escribir=False)"
```

| Fuente | Filas de salida | Placa válida | Monto válido | Con categoría | Filas de combustible |
|---|---|---|---|---|---|
| `otros_gastos_2020` | 1 043 de 1 043 leídas | 0 % | 100 % | 0 % | 0 |
| `gastos_flota_2020` | 13 600 de 13 600 | **94.7 %** | 100 % | **100 %** | **2 126** |
| `gastos_proyecto_2019` | 1 679 de 1 785 | 0 % | 100 % | 100 % | 253 |

Tres cosas que esta corrida confirma, y que antes eran una previsión:

- **`GASTOS FLOTA` es la fuente del combustible por unidad.** 2 126 filas de combustible con
  94.7 % de placas válidas: eso es lo que agrega `gasto_combustible` en `fact_unidad_mes`.
- **`OTROS GASTOS` no aporta ni placa ni categoría**, tal como decía el perfilado: su
  `es_combustible` queda **nulo**, nunca falso.
- **`CO01` descarta 106 filas** por no traer monto, y no tiene ni una placa válida: su gasto es de
  planta, no de unidad.

## 5 · Cómo se declara una hoja que empieza en datos

El lector de contratos ([`src/silver/contratos.py`](../../src/silver/contratos.py)) empareja
**por nombre de encabezado normalizado**: cada fuente declara `fila_encabezado` y un mapa
`encabezado: nombre_estandar`. En una hoja que empieza en datos no hay encabezado que emparejar,
y apuntar `fila_encabezado` a la primera fila de datos sería peor que no leerla: los nombres de
columna saldrían de una fila que trae una placa y un proveedor con su RUC.

El modo por posición se agregó de forma **aditiva**: las fuentes con nombre no cambian en nada, y
hay una prueba que lo comprueba. Una fuente se declara así:

```yaml
  - id: gastos_flota_2020
    archivo: '^GASTOS 2020\.xls$'
    hojas: '^GASTOS FLOTA$'
    primera_fila: 3          # la hoja empieza en datos: no hay encabezado
    posiciones:              # letra de columna → nombre estándar
      A: mes
      B: fecha
      C: placa_norm
      ...
```

Una fuente declara sus columnas **por nombre o por posición**, nunca las dos: el lector lo
rechaza al cargar el contrato. Y en una fuente por posición no se busca el encabezado repetido en
medio de los datos, porque no hay título con el que comparar.
