# Contratos de las tablas Silver

Un archivo YAML por tabla. Es la única fuente de verdad del esquema (base B5 y hallazgo C5 del Plan de Corrección): de aquí salen las columnas que la Lambda lee de cada hoja, el esquema del Parquet que escribe y el DDL de Athena.

## Estado

| Tabla | Fuentes declaradas | Pendiente |
|---|---|---|
| `compras_glp` | `COMPRAS MENSUALES.xlsx` (2022–2023), `COMPRAS TOTAL 2020.xlsx` | Hoja SETIEMBRE de 2020 (sin encabezado en el inventario) |
| `scop` | `1. PEDIDOS GLP.xlsx`, hoja SCOPS GENERADOS | — |
| `unidades` | Relación de unidades, control de flota y SOAT | Ubicar la cuarta familia del diccionario |
| `ventas_unidad_mes` | `VENTAS FLOTA 2020.xlsx` y `2021.xlsx`, hoja VENTAS | Confirmar las hojas MAYO, JUNIO y Hoja3 |
| `ventas_detalle` | `VENTAS MAYO 2020.xlsx`, `Ventas Por Proyecto.xlsx` | Reportes mensuales de 2019, sin encabezado |
| `gastos` | Sin contrato todavía | La hoja principal no publica sus encabezados en el inventario |

Cada contrato lista su propio pendiente en la clave `pendiente`.

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
