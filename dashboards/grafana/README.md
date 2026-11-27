# Tablero en Grafana Cloud

Tablero de Costa Gas Trujillo sobre la capa Gold, consultada con Amazon Athena (paso 1.7 del
`docs/Plan_Implementacion_Codigo_v15.md`; informe, sección 4.4 y Tabla 4.11).
Cada página se versiona como un JSON exportado de Grafana en esta carpeta.

| Archivo | Página | Commit |
|---|---|---|
| `_variables.json` | Variables comunes (no es una página) | B02 |
| `01_resumen.json` | Resumen: 5 KPI, semáforo y calidad | B03 |
| `02_balance_unidades.json` | Balance y unidades | B04 |
| `03_bandeja.json` | Bandeja de alertas | B05 |
| `04_mercado.json` | Mercado | B06 |
| `05_semaforo.json` | Semáforo de unidades | B07 |
| `06_revision_ciega.json` | Revisión ciega | B09 |

Las consultas de cada página están también en `sql/athena/tablero/`, para correrlas y medirlas en Athena.

## Origen de datos Athena

Lo crea **el titular** una sola vez, como indica `docs/guias/Guia_Equipo_Avisos_y_Grafana.md`
(pasos 2 a 4). La clave de `svc-dashboard` solo vive en Grafana: nunca en este repositorio, en un
JSON exportado ni en el chat.

| Campo | Valor |
|---|---|
| Tipo | Amazon Athena (`grafana-athena-datasource`) |
| Authentication Provider | *Access & secret key* de `svc-dashboard` |
| Default Region | `us-east-2` |
| Data Source | `AwsDataCatalog` |
| Database | `costagas_gold` |
| Workgroup | `costagas-wg` |
| Output Location | vacío (lo define el workgroup) |

`svc-dashboard` solo lee Gold y consulta en `costagas-wg`. Si una consulta pide `silver` o `bronze`, fallará: es lo esperado.

## Variables comunes (`_variables.json`)

Todas las páginas usan las mismas variables, en este orden:

| Variable | Origen | Selección | Uso en el SQL |
|---|---|---|---|
| `ds_athena` | Origen de datos Athena | una | `"datasource": {"type": "grafana-athena-datasource", "uid": "${ds_athena}"}` |
| `anio` | `dim_tiempo` | una (el más reciente por defecto) | `anio = ${anio}` |
| `mes` | `dim_tiempo` del año elegido | una (el más reciente por defecto) | `mes = ${mes}` |
| `producto` | `dim_producto` (`GLP-E`, `GLP-G`) | varias o «All» | `('__all' IN (${producto:sqlstring}) OR producto IN (${producto:sqlstring}))` |
| `rol` | `dim_unidad` (`reparto`, `transporte`) | varias o «All» | `('__all' IN (${rol:sqlstring}) OR rol IN (${rol:sqlstring}))` |

«All» vale `__all` en lugar de la lista de valores: así no se pierden las filas que no están en
la dimensión (el balance de 2020 trae productos sin clasificar y hay placas sin rol en el maestro).

Columnas de las dimensiones según `src/glue/dimensiones.py` (W08, rama `dev-wilson`):
`dim_tiempo.anio` y `mes`; `dim_producto.producto` (`GLP-E` o `GLP-G`); `dim_unidad.rol`.
**Pendiente:** confirmarlas con el DDL de Gold (`sql/athena/ddl/gold_*.sql`, W09). Si cambian,
se corrige este archivo y las páginas en el mismo pull request.

`dim_tiempo` es un calendario completo (todos los meses de 2016 a 2024), así que un mes elegido
puede no tener cobertura en alguna fuente. Las páginas muestran «sin dato» o un hueco en ese caso,
nunca un cero como si fuera una medición.

## Regla de costo: filtrar siempre por `anio` y `mes`

Los hechos de Gold están particionados por `anio`/`mes`. **Toda consulta a un hecho filtra por
`anio` y `mes`**, para que Athena lea solo las particiones necesarias y no pase de **1 GB escaneado**
por consulta (a US$ 5 por TB, menos de US$ 0.005).

- Mes elegido: `WHERE anio = ${anio} AND mes = ${mes}`.
- Tendencia de 12 meses: una ventana explícita sobre `anio * 12 + mes`, por ejemplo
  `WHERE (anio * 12 + mes) BETWEEN (${anio} * 12 + ${mes} - 11) AND (${anio} * 12 + ${mes})`,
  más `anio BETWEEN ${anio} - 1 AND ${anio}`, para que la poda de particiones funcione.
- Las variables leen las dimensiones, que no están particionadas y pesan kilobytes; la de `mes` ya filtra por `anio`.
- Nunca `SELECT *` sobre un hecho; solo las columnas del panel.
- Una sola consulta por página y refresco (ADR 0016); los demás paneles la reutilizan con el
  origen `-- Dashboard --`. Refresco automático cada **5 min**: Athena cobra como mínimo 10 MB por
  consulta, así que una página abierta 8 h al día cuesta unos US$ 0.005 diarios; con 1 min, cinco veces más.
- Antes de subir una página, cada consulta se prueba en Athena y se anota el dato escaneado
  («Data scanned») en el pull request.

## Datos personales

El tablero solo muestra identificadores seudonimizados (por ejemplo, `placa_norm` o los hash de
conductor y cliente). Nunca nombres, DNI ni RUC de personas naturales. La página de revisión ciega
no muestra probabilidad, puntaje ni grado de evidencia.

## Cómo importar una página

1. En Grafana: **Dashboards → New → Import**.
2. **Upload dashboard JSON file** y elige el archivo de esta carpeta (por ejemplo, `01_resumen.json`).
3. En **Folder** elige `Costa Gas` (créala la primera vez). Si Grafana pide el origen de datos, elige el Athena del paso anterior.
4. **Import**. En la parte superior aparecen `anio`, `mes`, `producto` y `rol`.
5. Revisa que cada panel cargue. Un panel vacío mientras Gold no tenga datos es normal.

`_variables.json` no se importa solo: es el bloque `templating` que se copia en cada página.
Para agregarlo a una página nueva, reemplaza su `"templating"` por el de este archivo.

## Cómo actualizar una página en el repositorio

1. Edita la página en Grafana y guárdala.
2. **Share → Export → Export for sharing externally** y descarga el JSON.
3. Revisa que el JSON no tenga claves, datos de filas ni nombres de personas, y reemplaza el archivo de esta carpeta.
4. Abre el pull request con el dato escaneado de cada consulta nueva.
