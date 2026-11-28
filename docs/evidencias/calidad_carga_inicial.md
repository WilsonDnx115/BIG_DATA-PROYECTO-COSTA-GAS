# Calidad de la carga inicial (WR09), medida sobre la corrida real

- **Fecha:** 2026-11-28
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** los 26 archivos de control que la Lambda de limpieza dejó en
  `s3://costagas-trujillo-lake-upao-g4-2026/silver/_control/` durante la **primera corrida sobre
  los datos reales**, entre las **02:24 y las 02:38 UTC del 28/11/2026**. Leídos con el perfil de
  gobierno, que es de solo lectura. **De aquí no sale ningún valor de celda**: los controles solo
  publican conteos y tasas.
- **Cumple** AR16. Las metas son las de la **Tabla 3.7** y están en `src/common/config.py`; las
  fórmulas de completitud, unicidad y metas incumplidas son las de
  [`src/quality/calidad_silver.py`](../../src/quality/calidad_silver.py).

## Cómo se reproduce

```powershell
aws s3 cp s3://costagas-trujillo-lake-upao-g4-2026/silver/_control/ .\_control\ --recursive --profile costagas-gobierno
```

Sobre esa carpeta, `calidad_silver.construir` da la tabla de abajo. La completitud es la fracción
de celdas con dato sobre las declaradas por el contrato; la unicidad es `1 − repetidas / salida`;
una meta solo se evalúa si la corrida midió su métrica.

**No se usó Athena.** Con el perfil de gobierno, `StartQueryExecution` termina en
`INSUFFICIENT_PERMISSIONS: Unable to verify/create output bucket
costagas-trujillo-lake-upao-g4-2026`, porque el usuario no tiene `s3:PutObject` sobre
`athena-results/`. Es un hecho de esta medición, no un pendiente: `silver/_control/` es la fuente
oficial de las filas efectivas según [`contracts/README.md`](../../contracts/README.md), y la
consulta de Athena se agregará como segunda evidencia cuando exista el permiso.

## Resultado por tabla

| Tabla | Fuentes | Leídas | Efectivas | Salida | Completitud | Unicidad | Descartes | Metas incumplidas |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `clientes` | 3 | 66 991 | 66 991 | 66 984 | 1.0000 | 1.0000 | 7 | — |
| `compras_glp` | 2 | 2 987 | 1 604 | 1 495 | 0.7643 | 0.9712 | 109 | — |
| `distribuidores` | 4 | 2 172 | 1 286 | 1 285 | 0.8544 | 0.9268 | 1 | — |
| `gastos` | 3 | 16 428 | 16 428 | 16 322 | 0.9888 | 1.0000 | 106 | `META_PLACA_VALIDA` |
| `pedidos_proveedor` | 4 | 1 054 091 | 1 050 223 | 1 150 | 0.0775 | 0.9887 | 1 049 073 | `META_KG_EN_RANGO` |
| `produccion_diaria` | 1 | 81 | 39 | 32 | 0.8590 | 1.0000 | 7 | — |
| `scop` | 1 | 77 | 29 | 29 | 0.8391 | 0.9310 | 0 | — |
| `unidades` | 4 | 2 074 | 285 | 281 | 0.9734 | 1.0000 | 4 | `META_PLACA_VALIDA` |
| `ventas_detalle` | 2 | 12 011 | 12 011 | 12 011 | 0.9696 | 1.0000 | 0 | — |
| `ventas_unidad_mes` | 2 | 4 160 | 1 159 | 1 159 | 1.0000 | 0.3762 | 0 | `META_PLACA_VALIDA` |

Las diez tablas tienen estado `ok`: ninguna fuente quedó sin leer.

## Resultado por fuente

| Tabla | Fuente | Familia | Leídas | Efectivas | Salida | Completitud | Unicidad | Metas incumplidas |
|---|---|---|---:|---:|---:|---:|---:|---|
| `clientes` | `clientes_codigo_sn` | F35 | 2 571 | 2 571 | 2 564 | 0.9986 | 1.0000 | — |
| `clientes` | `clientes_razon_social` | F34 | 63 298 | 63 298 | 63 298 | 1.0000 | 1.0000 | — |
| `clientes` | `clientes_ruc_cliente` | F33 | 1 122 | 1 122 | 1 122 | 1.0000 | 1.0000 | — |
| `compras_glp` | `compras_mensuales_2022_2023` | F06 | 2 251 | 1 145 | 1 066 | 0.7033 | 0.9634 | — |
| `compras_glp` | `compras_total_2020` | F07 | 736 | 459 | 429 | 0.9441 | 0.9907 | — |
| `distribuidores` | `distribuidores_hoja_maestra` | F29 | 588 | 588 | 587 | 0.8180 | 0.9250 | — |
| `distribuidores` | `distribuidores_por_envasadora` | F30 | 457 | 456 | 456 | 0.8592 | 0.9254 | — |
| `distribuidores` | `distribuidores_mega_gas_almacenes` | F31 | 131 | 131 | 131 | 0.8985 | 0.9237 | — |
| `distribuidores` | `distribuidores_mega_gas_relacion` | F32 | 996 | 111 | 111 | 0.9946 | 0.9459 | — |
| `gastos` | `otros_gastos_2020` | F26 | 1 043 | 1 043 | 1 043 | 0.8884 | 1.0000 | `META_PLACA_VALIDA` |
| `gastos` | `gastos_flota_2020` | F27 | 13 600 | 13 600 | 13 600 | 1.0000 | 1.0000 | `META_PLACA_VALIDA` |
| `gastos` | `gastos_proyecto_2019` | F28 | 1 785 | 1 785 | 1 679 | 0.9550 | 1.0000 | `META_PLACA_VALIDA` |
| `pedidos_proveedor` | `pedidos_petroperu` | F01 | 997 | 129 | 108 | 0.7103 | 0.9815 | `META_KG_EN_RANGO` |
| `pedidos_proveedor` | `pedidos_solgas` | F02 | 998 | 998 | 474 | 0.4259 | 1.0000 | `META_KG_EN_RANGO` |
| `pedidos_proveedor` | `pedidos_pluspetrol` | F03 | 1 048 572 | 1 048 572 | 45 | 0.0770 | 1.0000 | — |
| `pedidos_proveedor` | `pedidos_primax` | F04 | 3 524 | 524 | 523 | 0.7415 | 0.9790 | `META_KG_EN_RANGO` |
| `produccion_diaria` | `produccion_octubre_2018` | F36 | 81 | 39 | 32 | 0.8590 | 1.0000 | — |
| `scop` | `scops_generados` | F05 | 77 | 29 | 29 | 0.8391 | 0.9310 | — |
| `unidades` | `relacion_unidades` | F22 | 1 015 | 196 | 196 | 0.9959 | 1.0000 | `META_PLACA_VALIDA` |
| `unidades` | `relacion_unidades_otras` | F22 | 11 | 3 | 2 | 1.0000 | 1.0000 | — |
| `unidades` | `control_flota` | F24 | 52 | 37 | 34 | 0.8581 | 1.0000 | — |
| `unidades` | `soat_2020` | F26 | 996 | 49 | 49 | 1.0000 | 1.0000 | `META_PLACA_VALIDA` |
| `ventas_detalle` | `ventas_por_proyecto` | F09 | 7 579 | 7 579 | 7 579 | 1.0000 | 1.0000 | — |
| `ventas_detalle` | `ventas_mayo_2020` | F18 | 4 432 | 4 432 | 4 432 | 0.8889 | 1.0000 | — |
| `ventas_unidad_mes` | `ventas_flota_2020` | F17 | 993 | 992 | 992 | 1.0000 | 0.3790 | — |
| `ventas_unidad_mes` | `ventas_flota_2021` | F19 | 3 167 | 167 | 167 | 1.0000 | 0.3593 | `META_PLACA_VALIDA` |

## Los contratos coinciden con la corrida real

Las filas efectivas que [`contracts/README.md`](../../contracts/README.md) publicaba venían de una
corrida local con pandas sobre los 35 archivos, antes de que existiera el lago. Esta carga permite
contrastarlas contra la corrida de producción, y **nueve de las diez tablas coinciden al dígito**:
`clientes` 66 984, `compras_glp` 1 495 (1 066 + 429), `gastos` 16 322 (13 600 + 1 043 + 1 679),
`pedidos_proveedor` 1 150 (108 + 474 + 523 + 45), `produccion_diaria` 32, `scop` 29, `unidades` 281,
`ventas_detalle` 12 011 (4 432 + 7 579) y `ventas_unidad_mes` 1 159 (992 + 167).

La única que no coincide es **`distribuidores`**: el README declaraba 2 244 filas en 6 hojas y la
corrida da **1 285 en 7 hojas**. La diferencia está explicada y no es una pérdida de datos: las
cuatro fuentes leyeron **2 172 filas en bruto** y dejaron **1 285 efectivas**, y casi todo el hueco
viene de `MEGA GAS` de relación, que lee 996 filas y solo tiene 111 con dato; el resto son filas
vacías por debajo del último registro. El 2 244 del README era un conteo del orden de las filas
leídas, no de las efectivas. **La cifra válida es 1 285**, y el README se corrige en AR21.

## Lo que mide cada meta incumplida

`META_PLACA_VALIDA` (0.98) la incumplen `gastos`, `unidades` y `ventas_unidad_mes`.
En `gastos` la tasa medida es 0.9469 en `GASTOS FLOTA`, y 0.0 en `OTROS GASTOS` y en `CO01`, que
sencillamente **no traen placa**: eso ya está declarado como no cubierto en
[`gastos_posiciones.md`](gastos_posiciones.md), y es la razón de que el gasto por unidad solo pueda
calcularse desde `GASTOS FLOTA`. En `unidades`, `relacion_unidades` da 0.8010 y `soat_2020` 0.8367.
En `ventas_unidad_mes`, `kg_con_placa_valida` es 0.9840 en 2020 y 0.7368 en 2021.

`META_KG_EN_RANGO` (0.99) la incumple `pedidos_proveedor`: `kg_positivo` es 0.2352 en PRIMAX,
0.5926 en PETROPERU y 0.9135 en SOLGAS. En esas hojas el kilaje no está en todas las filas de
factura, cosa ya declarada en [`primax_posiciones.md`](primax_posiciones.md).

Ninguna de estas tasas es un defecto del contrato: son propiedades de la entrega, medidas y
declaradas. Su efecto es el que fija `calidad_silver.bloqueos`, que decide qué KPI no se publica
mientras su tabla Silver incumpla una meta.

## Tres lecturas que conviene no malinterpretar

**La unicidad de `ventas_unidad_mes` es 0.3762** porque la llave se repite en 616 de las 992 filas
de 2020 y en 107 de las 167 de 2021. La hoja trae varias líneas por unidad y mes, y la agregación a
grano `unidad_mes` ocurre aguas abajo, en Gold. No es una carga duplicada.

**`pedidos_proveedor` lee 1 054 091 filas y deja 1 150.** El grueso es la hoja de PLUSPETROL, que
el motor de Excel devuelve con 1 048 572 filas por el formato del libro; 1 048 527 se descartan por
no tener ningún campo exigido. Por eso la completitud de la tabla cae a 0.0775: se calcula sobre
filas efectivas, que incluyen esas vacías. La cifra que importa en esa tabla es la de salida.

**La completitud baja de `compras_glp` (0.7643) y `scop` (0.8391)** viene de columnas opcionales del
contrato, no de filas rotas: por ejemplo, de las 1 066 filas de compras 2022-2023 solo 942 traen
tipo de cambio registrado.

## Estado

Implementado, probado, desplegado y **corrido**: esta es la primera medición de calidad sobre datos
reales de la empresa en el lago. Lo que sigue dependiendo de la corrida de Gold —los KPI, el
semáforo y la Tabla 2.9 completa— está declarado en
[`estado_y_pendientes.md`](../estado_y_pendientes.md).
