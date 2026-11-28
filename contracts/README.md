# Contratos de las tablas Silver

Un archivo YAML por tabla. Es la única fuente de verdad del esquema (base B5 y hallazgo C5 del Plan de Corrección): de aquí salen las columnas que la Lambda lee de cada hoja, el esquema del Parquet que escribe y el DDL de Athena.

## Estado de cada contrato

**Diez contratos, todos con fuente declarada y leída.** Las filas de abajo salen de
`silver/_control/`, que es la fuente oficial: son las de la **carga inicial a S3** del 28/11/2026,
02:24–02:38 UTC, medidas en
[`calidad_carga_inicial.md`](../docs/evidencias/calidad_carga_inicial.md).

```powershell
aws s3 cp s3://costagas-trujillo-lake-upao-g4-2026/silver/_control/ .\_control\ --recursive --profile costagas-gobierno
```

Nueve de las diez tablas coinciden al dígito con la corrida local en pandas que publicaba este
cuadro antes de la carga. La décima, `distribuidores`, se corrigió: decía 2 244 filas en 6 hojas,
que era un conteo del orden de las **filas leídas**; las **efectivas** son 1 285 en 7 hojas. Las
cuatro fuentes leen 2 172 filas en bruto, y casi todo el hueco viene de `MEGA GAS` de relación,
que lee 996 filas y solo tiene 111 con dato: el resto son filas vacías por debajo del último
registro. No hay pérdida de datos.

| Tabla | Filas efectivas | Fuentes | Lo que no cubre |
|---|---|---|---|
| `clientes` | 66 984 | 3 hojas de `CLIENTES TOTAL.xlsx` | `CLIENTES AGOSTO.xls`: su hoja empieza en datos |
| `compras_glp` | 1 495 | `COMPRAS MENSUALES.xlsx` (1 066), `COMPRAS TOTAL 2020.xlsx` (429) | La hoja SETIEMBRE de 2020, sin encabezado |
| `distribuidores` | 1 285 | 7 hojas de los dos libros de distribuidores: maestra (587), por envasadora (456), MEGA GAS almacenes (131) y MEGA GAS relación (111) | — |
| `gastos` | 16 322 | `GASTOS FLOTA` (13 600), `OTROS GASTOS` (1 043), `CO01/Sheet1` (1 679) | El gasto por unidad de `OTROS GASTOS` y de `CO01`: no traen placa ([evidencia](../docs/evidencias/gastos_posiciones.md)) |
| `pedidos_proveedor` | 1 150 | PETROPERU (108), SOLGAS (474), **PRIMAX (523)**, PLUSPETROL (45) | `fecha_vence` de PRIMAX, que no tiene esa columna ([evidencia](../docs/evidencias/primax_posiciones.md)) |
| `produccion_diaria` | 32 | `ProduccionReal-Cap Efec (Octub)`, **31 días de oct-2018** | Los demás meses y el piloto 2020: la entrega no los trae ([evidencia](../docs/evidencias/produccion_diaria_en_la_entrega.md)) |
| `scop` | 29 | `1. PEDIDOS GLP.xlsx`, hoja SCOPS GENERADOS | — |
| `unidades` | 281 | Relación de unidades, control de flota y SOAT | — |
| `ventas_detalle` | 12 011 | `VENTAS MAYO 2020.xlsx` (4 432), `Ventas Por Proyecto.xlsx` (7 579) | Los reportes mensuales de 2019, sin encabezado |
| `ventas_unidad_mes` | 1 159 | `VENTAS FLOTA 2020.xlsx` (992) y `2021.xlsx` (167) | Las hojas MAYO, JUNIO y Hoja3 |

`COMPRAS MENSUALES (1).xlsx` es copia de `COMPRAS MENSUALES.xlsx` y no suma: el patrón del
contrato no la toma, y en AWS la Lambda de ingesta la rechaza sola por su huella SHA-256.

Cada contrato lista su propio pendiente en la clave `pendiente`.

Una tabla **no cubierta** y una tabla **pendiente** no son lo mismo, y conviene no confundirlas al
leer este cuadro: la pendiente espera un dato que existe; la no cubierta ya se buscó y no está, y
lo que falta queda declarado en las salidas en lugar de rellenarse.

### Las hojas que empiezan en datos

Tres hojas de la entrega no tienen fila de encabezado: `GASTOS FLOTA`, `CO01/Sheet1` y `PRIMAX`,
más la de producción, que lo tiene en dos filas. Se declaran **por posición**, con `primera_fila`
y `posiciones` (letra de columna → nombre estándar). Qué mide cada posición está medido sobre la
entrega, sin copiar ningún valor, en `docs/evidencias/`.

Una fuente declara sus columnas **por nombre o por posición, nunca las dos**: el lector lo rechaza
al cargar el contrato.

## Estructura de un contrato

- `tabla`, `dominio`, `grano`, `llave`: identidad de la tabla. Se escribe en `silver/<dominio>/<tabla>/`.
- `fuentes`: de dónde sale. Cada fuente declara el patrón del nombre del archivo, el patrón de las hojas, la fila del encabezado, las columnas que toma (encabezado original → nombre estándar) y los campos que exige no vacíos.
- `columnas`: el esquema de salida, con tipo, rol, regla y marca `personal` para los datos seudonimizados.
- `valor_esperado`: el conteo del diccionario v3.0, para comparar tras cada corrida.

Los encabezados se emparejan sin tildes, signos ni mayúsculas: `GLP-E (Kilogramos)` y `glp e kilogramos` son el mismo.

## Cómo se usan

```bash
python -m src.silver.contratos           # lista los contratos
python -m src.silver.contratos --ddl     # regenera sql/athena/ddl/silver_<tabla>.sql
python -m src.silver.verificar --origen "C:/ruta/a/los/excel"     # corre en local y muestra solo conteos
python -m src.ingest.entrega --origen "C:/ruta/a/los/excel" --simular
```

Al cambiar un contrato hay que regenerar el DDL en el mismo commit: una prueba compara ambos.

## Reglas

- Ningún nombre de persona entra al esquema de salida. Conductor, vendedor y cliente se guardan solo como hash con sal.
- Las tablas Silver son pequeñas: un Parquet por fuente, sin particiones. Reprocesar un archivo reemplaza solo su Parquet.
- `_archivos.yaml` asigna cada archivo de la entrega a su dominio de Bronze.
