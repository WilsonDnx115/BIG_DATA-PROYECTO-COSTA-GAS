# Diccionario de datos de Gold

- **Fecha:** 2026-11-27
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Procedencia:** los DDL versionados de [`sql/athena/ddl/gold_*.sql`](../sql/athena/ddl) (W09).
  No está escrito a mano a partir de otra lista: cada tabla, cada columna y cada partición de
  este documento sale de su DDL, que es la fuente de verdad del esquema.

Trece tablas en **Iceberg**, formato Parquet, en la base `costagas_gold`. Se despliegan con
`python -m sql.athena.crear_tablas --solo gold`.

## Cómo leer este documento

- **Grano** es qué representa una fila. Es lo primero que hay que mirar antes de sumar una
  columna: sumar kilos sobre una tabla cuyo grano no es el que uno cree es la forma más fácil de
  publicar una cifra inflada.
- **Llave** es lo que identifica una fila sin repetirse. Donde el productor ya la declara en el
  código, es además la llave del `MERGE INTO` de Iceberg, y por eso reprocesar un mes actualiza
  sus filas en vez de duplicarlas. Hoy la declaran `fact_balance_planta`
  (`balance.LLAVE`), `mercado_mes` (`externos_job.LLAVE_MERCADO`) y las seis dimensiones
  (`dimensiones.LLAVES`); en las demás la fila se identifica por las columnas que se indican y la
  llave del `MERGE` se fija cuando se escriba su paso.
- **Partición**: solo `anio` y `mes`, nunca por placa, RUC ni documento (`CLAUDE.md`). Una
  consulta que filtra por año y mes lee solo esos archivos y por eso cuesta céntimos.

## Hechos

### `fact_balance_planta`

| | |
|---|---|
| **Grano** | un producto y un mes |
| **Llave** | `producto`, `anio`, `mes` |
| **Partición** | `anio`, `mes` |
| **Lo escribe** | [`src/glue/balance.py`](../src/glue/balance.py) (W06) |
| **Fuente Silver** | `compras_glp` y `ventas_detalle` |
| **Técnica** | agregación por producto y mes, y `MERGE INTO` de Iceberg por la llave |
| **Quién lo lee** | `v_kpi_1` y `v_kpi_2` |

Columnas: `producto`, `anio`, `mes`, `kg_comprados`, `kg_vendidos`, `diferencia_bruta_kg`,
`delta_stock_kg`, `merma_tecnica_kg`, `merma_es_supuesto`, `kg_no_explicados`,
`pct_no_explicado`, `valor_soles`, `mes_completo`.

Dos columnas que hay que leer con cuidado, porque son supuestos declarados y no mediciones:

- **`delta_stock_kg` es nulo**, no cero, mientras la entrega no traiga cierres físicos. Un cero
  afirmaría que el stock no se movió, y eso nadie lo midió
  ([produccion_diaria_en_la_entrega.md](evidencias/produccion_diaria_en_la_entrega.md)). La vista `v_kpi_1` lo
  convierte en 0 para poder calcular, y publica `stock_es_supuesto` junto al número.
- **`merma_tecnica_kg`** es el 0.5 % del [ADR 0027](adr/0027-merma-tecnica-referencia-de-mercado.md),
  una referencia de mercado, y `merma_es_supuesto` lo dice en la propia fila.

### `fact_alerta`

| | |
|---|---|
| **Grano** | una alerta: una señal que se dispara sobre una entidad en una fecha |
| **Identifica una fila** | `id_alerta`, un SHA-256 de señal, tipo, resolución, fecha, unidad, factura y motivo. La llave del `MERGE` la fijará el paso que escriba la tabla (W12) |
| **Partición** | `anio`, `mes` |
| **Lo escribe** | [`src/glue/senales_spark.py`](../src/glue/senales_spark.py) y el modelo S12 (W12) |
| **Fuente Silver** | `compras_glp`, `scop`, `ventas_detalle`, `ventas_unidad_mes`, `unidades` |
| **Técnica** | señales S1-S12 sobre las interfaces del WP 0.8; contrato `fact_alerta_base` ([ADR 0030](adr/0030-un-esquema-por-tabla.md)) |
| **Quién lo lee** | `v_alerta`, y a través de ella `v_kpi_5` |

Columnas: `id_alerta`, `senal`, `tipo`, `resolucion`, `fecha`, `unidad_id`, `rol`, `factura_id`,
`codigo_scop`, `kg`, `valor_soles`, `puntaje`, `probabilidad`, `grado_evidencia`,
`estado_revision`, `motivo`, `fuentes`, `anio`, `mes`.

**`valor_soles` queda nulo a propósito** salvo que la señal cuantifique soles (el sobrecobro del
F08). Unos kg señalados son un desvío por explicar, no una pérdida medida: valorizarlos habría
inflado el KPI 2 con algo que nadie midió. `probabilidad` es nula en una alerta de regla.

### `revision_alerta`

| | |
|---|---|
| **Grano** | una revisión de una alerta. **Una alerta puede tener varias filas** |
| **Identifica una fila** | `id_alerta` + `revisado_en`. No hay `MERGE`: la tabla es de solo inserciones |
| **Partición** | ninguna |
| **Lo escribe** | [`src/portal/revision.py`](../src/portal/revision.py) (W22) |
| **Fuente Silver** | ninguna: la escribe una persona al revisar |
| **Técnica** | **solo inserciones** ([ADR 0019](adr/0019-revision-alerta-solo-inserciones.md)); `v_alerta` se queda con la más reciente |

Columnas: `id_alerta`, `estado`, `causa`, `nivel_evidencia`, `nota`, `revisor_hash`,
`revisado_en`.

`revisor_hash` es el **único dato de persona de todo Gold**, y va seudonimizado con sal
(`tests/test_privacidad.py` lo comprueba sobre el contrato y sobre las ocho vistas). Que la tabla
sea de solo inserciones no es un detalle técnico: es lo que permite auditar quién revisó qué y
cuándo, sin que una segunda revisión borre la primera.

### `modelo_factura`

| | |
|---|---|
| **Grano** | una factura del cruce tesorería × logística |
| **Identifica una fila** | `factura_id`. La llave del `MERGE` la fijará el paso que escriba la tabla |
| **Partición** | `anio`, `mes` |
| **Lo escribe** | `senales_spark.cruce_s12` |
| **Fuente Silver** | `compras_glp` (logística) y `pedidos_proveedor` (tesorería) |
| **Técnica** | unión externa de los dos registros por documento, con `TOL_KG_S12` de 1 kg |
| **Quién lo lee** | `v_kpi_3`, y es la tabla de modelado de S12 |

Columnas: `factura_id`, `unidad_id`, `codigo_scop`, `kg_logistica`, `kg_tesoreria`, `fecha_pago`,
`fecha_vence`, `clase_s12`, `fecha`, `anio`, `mes`.

`clase_s12` es la etiqueta del cruce: `coincide`, `solo_logistica`, `solo_tesoreria`,
`kg_distinto` o `kg_desconocido`. El KPI 3 deja fuera `solo_tesoreria`, porque una factura que
logística no registró no es una compra registrada y no puede estar en el denominador.

### `fact_serie`

| | |
|---|---|
| **Grano** | una entidad y un periodo (semana o mes) |
| **Identifica una fila** | `entidad_id`, `entidad_tipo`, `granularidad` y `periodo`. La llave del `MERGE` la fijará el paso que escriba la tabla |
| **Partición** | ninguna |
| **Lo escribe** | [`src/models/detector.py`](../src/models/detector.py) (F14) a través del job de Gold |
| **Fuente Silver** | `ventas_unidad_mes` y `unidades`, por `fact_unidad_mes` |
| **Técnica** | CUSUM y EWMA sobre el desvío estandarizado por rol; los parámetros y su fuente están en el ADR 0028, escrito en la rama `dev-frank` |
| **Quién lo lee** | `v_semaforo_unidades` |

Columnas: `entidad_id`, `entidad_tipo`, `granularidad`, `periodo`, `periodo_inicio`, `estado`,
`valor_esperado`, `residuo`, `z`, `cusum`, `ewma`, `kg_acumulados`, `soles_acumulados`.

`estado` es `verde`, `ambar`, `rojo` o **`no_evaluable`**. El último no es un verde: significa que
la unidad no tiene volumen o combustible válidos, o que su MAD es cero, y por eso no se la puede
comparar. Contarlo como verde diría que esa unidad está bien.

### `mercado_mes`

| | |
|---|---|
| **Grano** | un mes |
| **Llave** | `anio`, `mes` |
| **Partición** | `anio`, `mes` |
| **Lo escribe** | [`src/glue/externos_job.py`](../src/glue/externos_job.py) (W21) |
| **Fuente Silver** | ninguna: fuentes externas (GDELT, Facilito de Osinergmin, BCRP) |
| **Técnica** | agregación mensual y LDA sobre el texto de las noticias |

Columnas: `anio`, `mes`, `n_eventos_gdelt`, `tono_promedio`, `precio_mediano_plaza`,
`n_establecimientos`, `tipo_cambio_promedio`, `n_temas`.

**No es una medición de la empresa.** Son precios de la plaza, tipo de cambio y volumen de
noticias: sirven para descartar que un desvío se explique por el entorno, no para atribuirle nada
a la planta. Lo que no tiene fuente queda nulo.

### `calidad_silver`

| | |
|---|---|
| **Grano** | una tabla Silver y una corrida |
| **Identifica una fila** | `tabla`, `fuente` y `generado_utc`: una corrida de una fuente |
| **Partición** | ninguna |
| **Lo escribe** | [`src/quality/calidad_silver.py`](../src/quality/calidad_silver.py) (A10) |
| **Fuente Silver** | los JSON de control de `silver/_control/` |
| **Técnica** | lectura con esquema declarado y agregación de mapas sin traer nada al driver |

Columnas: `tabla`, `fuente`, `familia`, `generado_utc`, `estado`, `filas_leidas`,
`filas_efectivas`, `filas_salida`, `filas_con_llave_repetida`, `columnas_declaradas`,
`completitud`, `unicidad`, `filas_descartadas`, `filas_corregidas`, `placa_valida`,
`kg_con_placa_valida`, `kg_positivo`, `scop_presente`, `fecha_valida`, `documento_presente`,
`mes_reconocido`, `entidad_id_presente`, `metas_incumplidas`, `cumple`.

`cumple` es la columna que permite ver un bloqueo: `CLAUDE.md` prohíbe publicar una métrica de
Gold cuando sus fuentes Silver incumplen las metas de la Tabla 3.7. Qué KPI queda bloqueado por
cada incumplimiento lo resuelve `calidad_silver.bloqueos()`.

## Dimensiones

Ninguna se particiona: son tablas chicas y el particionado solo tendría sentido en los hechos.

| Tabla | Grano | Llave | Columnas | De dónde sale |
|---|---|---|---|---|
| `dim_tiempo` | un mes | `id_tiempo` (`anio × 100 + mes`) | `id_tiempo`, `anio`, `mes`, `trimestre`, `en_ventana_analisis`, `pandemia_2020` | **generada**, no se lee de ninguna fuente |
| `dim_unidad` | una placa | `placa_norm` | `placa_norm`, `empresa`, `marca`, `clase`, `capacidad_kg`, `habilitada_glp`, `rol`, `presente_en_maestro` | placas vistas en compras y ventas, más el maestro de vehículos |
| `dim_persona` | una persona y su tipo | `persona_hash`, `tipo` | `persona_hash`, `tipo` | hash que ya trae Silver (conductor o vendedor) |
| `dim_producto` | un artículo | `articulo_codigo` | `articulo_codigo`, `articulo`, `presentacion_kg`, `producto`, `marca` | artículos de GLP de `ventas_detalle` |
| `dim_contraparte` | un cliente o distribuidor | `documento_hash` | `documento_hash`, `tipo`, `ruc_valido`, `capacidad_kg` | maestros de clientes y distribuidores |
| `dim_senal` | una señal S1-S12 | `id_senal` | `id_senal`, `descripcion`, `resolucion`, `ventana`, `estado`, `grado_evidencia` | [`src/signals/catalogo.yaml`](../src/signals/catalogo.yaml), el catálogo único |

Tres cosas de privacidad que valen para todas:

- **`dim_persona` solo guarda el hash y el tipo.** Ni nombre, ni DNI, ni documento.
- **`dim_contraparte` no publica el RUC**, solo si es válido. El RUC de persona natural no llega
  a Silver desde el arreglo del 27/11, y hay una prueba que lo verifica.
- **`dim_producto.marca` es siempre nula**: la entrega no trae la marca comercial. Está declarada
  en el esquema para no cambiar la tabla cuando aparezca, y se lee como «sin fuente», no como
  «sin marca».

La integridad entre hechos y dimensiones la comprueba
[`tests/test_integridad_gold.py`](../tests/test_integridad_gold.py): un `left_anti` de cada hecho
contra cada dimensión tiene que dar 0 filas.

## Dos tablas que todavía no tienen DDL, y por qué

No se declara una tabla cuyo esquema no esté definido: un DDL inventado es peor que uno ausente,
porque parece acordado.

| Tabla | Por qué no está | Qué la desbloquea |
|---|---|---|
| `fact_unidad_mes` | Es el W07 y necesita el gasto de combustible por unidad, que sale de `contracts/gastos.yaml`. Hoy solo se conocen las columnas que consume `v_semaforo_unidades` | El contrato de gastos (AR01), y ese necesita los 35 archivos de la entrega |
| `fact_operacion` | Es el W18 y todavía no tiene columnas definidas en ninguna parte | Su propio paquete |

`fact_unidad_mes` sí tiene su interfaz declarada en
[`src/signals/contratos.py`](../src/signals/contratos.py) y sus columnas en `COLUMNAS_GOLD`
([`tests/test_vistas_sql.py`](../tests/test_vistas_sql.py)), que es lo que las vistas `v_kpi_4` y
`v_cubo_unidad` esperan encontrar. Lo que falta es el DDL, no el acuerdo sobre los nombres.
