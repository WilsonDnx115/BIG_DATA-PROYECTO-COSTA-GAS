# Producción diaria: sí existe en la entrega, y dónde está

- **Fecha:** 2026-11-27
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** verificación directa sobre los 35 archivos de la entrega (diccionario v3.0),
  hecha fuera del repositorio. **De aquí no sale ningún valor de celda**: solo nombres de hoja,
  etiquetas de concepto, conteos y fechas límite.
- **Corrige** la versión anterior de este documento (`produccion_no_cubierta.md`, PR #21), que
  declaraba el stock diario como no cubierto apoyándose en la búsqueda del inventario.

## La corrección, en una línea

**El stock por día existe.** Está en
`Reporte de Produccion CGT 2018.xlsx` → hoja **`ProduccionReal-Cap Efec (Octub)`**, con **una
fila por día y los 31 días de octubre de 2018**.

## Qué se encontró, exactamente

| Dónde | Qué hay |
|---|---|
| Columna A | **31 fechas, 31 días distintos, del 2018-10-01 al 2018-10-31**: el mes completo, sin huecos |
| Fila 1, columna 2 | `STOCK INICIAL` |
| Fila 1, columna 9 | `VENTAS` |
| Fila 1, columna 16 | `BONIFICACIONES` |
| Fila 1, columna 23 | `STOCK FINAL(PLAT. + UNID)` |
| Fila 1, columna 30 | `PRODUCCION` |
| Fila 2 | Subencabezado de cada bloque: la marca y una columna `TOTAL` |

Son **los cinco conceptos de la interfaz `produccion` del WP 0.8**
([`src/signals/contratos.py`](../../src/signals/contratos.py)), con el grano que S11 necesita.

## Por qué la búsqueda anterior no la encontró

No fue un descuido. La hoja tiene **encabezado en dos niveles**: el concepto en la fila 1 y la
subdivisión por marca en la fila 2, con los bloques separados cada siete columnas. La heurística
de [`encabezados.py`](../../src/ingest/encabezados.py) busca **una** fila de encabezado y, al no
reconocer ninguna, clasificó la hoja como dudosa por `tipo_de_celda`, que es el motivo que el
propio inventario describe como «puede que los nombres estén ahí y no se reconozcan»
([`hojas_sin_encabezado.md`](hojas_sin_encabezado.md), sección 1). Estaba en las 13 hojas de ese
grupo.

La lección vale para el resto del inventario: **`tipo_de_celda` no significa «no hay
encabezado»**, significa «la heurística no lo reconoció». Las 13 hojas de ese grupo merecen una
mirada con el archivo delante, como esta.

## Qué cambia y qué no

| | Antes | Ahora |
|---|---|---|
| **S11** (cierre de planta sin medición física) | Sin fuente en la entrega | **Tiene fuente**: los 31 días de oct-2018, que es justo su ventana en el catálogo |
| **La cita del informe** («residuo cero en 31 de 31 días, oct-2018») | No se sostenía con el inventario | **Se sostiene**: hay 31 días y los cinco conceptos. La fuente F36 es esta hoja |
| **KPI 1 en 2020** | Variación de stock en 0, marcada | **Igual**: esta hoja es de 2018. Para el piloto 2020 sigue sin haber stock diario, así que `delta_stock_kg` queda nulo y la vista publica `stock_es_supuesto` |
| **`fact_balance_planta`** | Se construye sin la fuente de producción | **Igual**, por lo mismo |

Dicho de otra manera: **se recupera la validación de S11, no el KPI 1 del piloto.**

## Qué falta para cargarla

Lo mismo que bloquea a los contratos de gastos y de PRIMAX, más una cosa propia:

1. **Lectura por posición** en `src/silver/contratos.py`, que hoy empareja por nombre de
   encabezado normalizado de una sola fila. Aquí el encabezado son dos filas y bloques repetidos
   cada siete columnas: hay que tomar la columna `TOTAL` de cada bloque
   ([`gastos_posiciones.md`](gastos_posiciones.md), sección 4, propone el formato).
2. **Decidir qué columna del bloque entra**. Cada concepto está abierto por marca y cierra con un
   `TOTAL`. Para la interfaz `produccion`, que es de planta, corresponde el `TOTAL`; las columnas
   por marca son un desglose que hoy no se usa.
3. **`stock_final_es_calculado`**. La interfaz lo pide y la hoja no lo trae. Con lo que el informe
   ya dice —que el inventario final no se contabiliza físicamente sino que se calcula para que el
   balance cuadre— ese campo sale **verdadero** para todas las filas, y así hay que declararlo, no
   dejarlo nulo.

Mientras eso no esté, `contracts/produccion_diaria.yaml` no se escribe: un contrato que no se
puede leer es una promesa, no un contrato. Lo que sí queda es **dónde está la fuente y con qué
grano**, que era lo que faltaba.
