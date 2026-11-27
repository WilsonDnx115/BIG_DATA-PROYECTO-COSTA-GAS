# Contexto del modelo de datos: el lago, las tablas y quién escribe cada una

- **Fecha:** 2026-11-27
- **Responsable:** Wilson Mirano Ríos (Ingeniería de datos)
- **Para qué sirve:** es el mapa. Antes de tocar una tabla, de escribir una vista o de pedirle
  una columna a alguien, aquí está quién la produce, quién la consume, cuál es su llave y si
  existe de verdad o todavía es un pendiente.

Lo que dice este documento sale del código y de los contratos, no de memoria. Cuando algo
discrepe, manda el código: `contracts/*.yaml` para Silver y `sql/athena/ddl/gold_*.sql` para Gold.

---

## 1. El lago, de una punta a la otra

Un solo bucket, `costagas-trujillo-lake-<sufijo>`, en **us-east-2**. Toda ruta se construye con
`src/common/rutas.py` desde `LAKE_URI`; nunca se escribe un prefijo a mano.

```
landing/   interno/   los 35 archivos de la entrega, tal como llegan
           externo/   BCRP, Facilito, YouTube, GDELT y resoluciones (W20)
bronze/    interno/estructurado/<dominio>/   copia inmutable, con hash y manifiesto
silver/    <dominio>/<tabla>/   Parquet por fuente, sin particionar
           entorno/   lo externo ya tipado (textos, temas, youtube)
           _control/  un JSON de calidad por tabla y corrida
gold/      <tabla>/   hechos y dimensiones en Iceberg
           mr/        salida del patrón MapReduce (W05) y eventos de GDELT
           _modelos/  modelos registrados y el umbral del detector
op/        el mismo lago, mes a mes, para la medición de la operación (W18)
sim/       datos sintéticos: escenarios A y B (W19) y réplicas de escala (W24)
```

Dos reglas que no se negocian y que ya costaron una decisión escrita:

- **Nada de `sim/` entra al análisis.** Son datos sintéticos; sus cifras no se publican como
  resultados del negocio ([ADR 0026](adr/0026-replicas-de-escala-en-sim-escala.md)).
- **`landing/externo/` no pasa por la ingesta interna.** La Lambda lo reconoce y lo deja pasar sin
  tocarlo; su camino es el job de externos ([ADR 0023](adr/0023-landing-externo-ignorado-por-la-ingesta.md)).

### Cómo se mueve un dato

```
archivo a landing/  →  Lambda costagas-ingesta (W02): SHA-256, manifiesto, copia a bronze/
bronze/             →  Lambda de limpieza: aplica contracts/*.yaml y escribe silver/ + _control/
silver/             →  evento EventBridge costagas-silver-actualizado (7 prefijos internos)
                    →  job Glue costagas-gold-conciliacion (src/glue/gold_job.py)
                       └ MapReduce SQL (W05) · dimensiones (W08) · balance (W06)
                         · unidad-mes (W07, falta) · alertas (W12, falta)
gold/               →  vistas de Athena (F06) →  tablero Grafana y portal
landing/externo/    →  job Glue costagas-externos (W21) → silver/entorno/ y gold/mercado_mes
```

La regla de Gold filtra por los **siete prefijos internos** de Silver, así que escribir en
`silver/entorno/` no dispara una corrida ([ADR 0020](adr/0020-regla-gold-prefijos-internos.md)).

---

## 2. Silver: ocho tablas, una por contrato

`contracts/*.yaml` es la **fuente de verdad**: columnas, tipos, grano, llaves, reglas y marcas de
dato personal. La lectura, el Parquet y el DDL se derivan del mismo contrato, y
`python -m src.silver.contratos --validar` comprueba que los ocho y sus DDL estén al día.

| Tabla | Grano | Dominio en el lago | Dueño |
|---|---|---|---|
| `compras_glp` | factura de compra | `silver/compras/` | Wilson (W04) |
| `pedidos_proveedor` | factura registrada por tesorería | `silver/compras/` | Anghelo (A07) |
| `scop` | orden SCOP | `silver/compras/` | Wilson (W04) |
| `ventas_detalle` | línea de comprobante | `silver/ventas/` | Wilson (W04) |
| `ventas_unidad_mes` | unidad × mes × artículo × vendedor | `silver/ventas_unidad/` | Wilson (W04) |
| `unidades` | fila de cada maestro de vehículos | `silver/flota/` | Wilson (W04) |
| `clientes` | cliente | `silver/maestros/` | Anghelo (A08) |
| `distribuidores` | establecimiento de un distribuidor | `silver/maestros/` | Anghelo (A08) |

**Falta uno: `gastos.yaml`** (A06). Es el único contrato pendiente y es la llave de media cadena:
sin él no hay `fact_unidad_mes`, y sin esa tabla no hay alertas, ni control de pago, ni semáforo.

> `pedidos_proveedor` es el lado de **tesorería** del cruce S12; `compras_glp` es el de
> **logística**. Comparar los dos es lo que mide el KPI 3.

### Privacidad, en una línea

Ni nombres, ni DNI, ni RUC de persona natural salen de Bronze. Lo que viaja es
`documento_hash` / `conductor_hash` / `vendedor_hash`, SHA-256 con sal en SSM. El RUC de persona
**jurídica** (prefijo 20) sí se conserva, para cruzar con SUNAT.

---

## 3. Gold: las quince tablas

Trece ya tienen DDL en `sql/athena/ddl/gold_*.sql` (W09). Todas son **Iceberg**, con
`vacuum_max_snapshot_age_seconds = 604800` (7 días) y escritura con `MERGE INTO` sobre la llave
del grano: una corrida que reprocesa un mes actualiza sus filas, no las duplica.

### 3.1 Dimensiones — ninguna se particiona

| Tabla | Llave | Qué tiene | La escribe |
|---|---|---|---|
| `dim_tiempo` | `id_tiempo` | un mes por fila, trimestre, si está en la ventana y si es 2020 | generada, W08 |
| `dim_unidad` | `placa_norm` | rol, capacidad, habilitación GLP, empresa, si está en el maestro | W08 |
| `dim_persona` | `persona_hash`, `tipo` | **solo el hash** y si es conductor o vendedor | W08 |
| `dim_producto` | `articulo_codigo` | presentación en kg, GLP-E o GLP-G; la marca queda nula | W08 |
| `dim_contraparte` | `documento_hash` | tipo de documento, si el RUC es válido, capacidad | W08 |
| `dim_senal` | `id_senal` | catálogo S1-S12 con resolución, ventana, estado y evidencia | W08 |

`dim_senal` junta dos fuentes: la descripción y el grado vienen de `senales_spark.CATALOGO`, que
es el que usa el detector, y la resolución, la ventana y el estado de `src/signals/catalogo.yaml`.
Si falta el YAML quedan **nulos**, no inventados.

`dim_contraparte` todavía no se escribe: el job no le pasa el maestro. Cuando se enganche hay que
agregarle `estado` y `canal` **en el mismo cambio** que empiece a escribirlos.

### 3.2 Hechos y tablas de apoyo

| Tabla | Llave / grano | Partición | La escribe | La leen |
|---|---|---|---|---|
| `fact_balance_planta` | producto × año × mes | `anio`, `mes` | W06 ✔ | `v_kpi_1`, `v_kpi_2` |
| `fact_unidad_mes` | placa × mes | `anio`, `mes` | **W07, falta** | `v_kpi_4`, `v_semaforo_unidades`, `v_cubo_unidad` |
| `fact_alerta` | `id_alerta` | `anio`, `mes` | **W12, falta** | `v_alerta` |
| `revision_alerta` | solo inserciones | — | portal (W22) ✔ | `v_alerta`, `v_kpi_5` |
| `modelo_factura` | factura | `anio`, `mes` | `cruce_s12` (F07) | `v_kpi_3` |
| `fact_serie` | entidad × periodo | — | detector (F14) | `v_semaforo_unidades` |
| `mercado_mes` | año × mes | `anio`, `mes` | W21 ✔ | contexto del tablero |
| `calidad_silver` | tabla × corrida | — | A10 ✔ | portal, tablero |
| `fact_operacion` | — | — | **W18, sin columnas aún** | — |

#### `fact_balance_planta` — el KPI 1 y el KPI 2

Es el primer nivel de conciliación: cuánto entró por compras, cuánto salió por ventas y qué parte
de la diferencia queda **sin explicar**.

```
diferencia_bruta_kg = kg_comprados - kg_vendidos
kg_no_explicados    = diferencia_bruta_kg - delta_stock_kg - merma_tecnica_kg
```

Las dos restas son opcionales y por motivos distintos, y esto es lo que hay que entender antes de
leer el KPI:

- **`delta_stock_kg` es nulo siempre, hoy.** La entrega no trae stock de planta de ningún grano;
  lo verifiqué sobre las 199 hojas del inventario y está en
  [`evidencias/hojas_sin_encabezado.md`](evidencias/hojas_sin_encabezado.md). Nulo, **no cero**: un
  cero afirmaría que el stock no se movió, y eso no se midió. Coincide con el
  `cierres_medidos_fisicamente: 0` del informe v16.
- **`merma_tecnica_kg` es un supuesto declarado**, 0.5 % de lo comprado, justificado como
  referencia de mercado en el [ADR 0027](adr/0027-merma-tecnica-referencia-de-mercado.md).
  `merma_es_supuesto` existe para que el tablero lo etiquete como tal.

`valor_soles` valoriza los kg no explicados al **precio de compra del propio mes**, medido de las
facturas (`monto_usd × tipo_cambio / kg`). Sin tipo de cambio válido queda nulo: no se usa un
precio de referencia.

#### `fact_alerta` y `revision_alerta` — y por qué están separadas

`fact_alerta` es lo que el sistema detecta; `revision_alerta` es lo que una persona concluyó. Son
tablas distintas a propósito ([ADR 0019](adr/0019-revision-alerta-solo-inserciones.md)):
`revision_alerta` es **de solo inserciones**, cada revisión es una fila nueva y nada se edita, así
que la secuencia de revisiones queda auditable. `v_alerta` se queda con la más reciente de cada
alerta.

Dos reglas que valen para todo el proyecto:

- **Una alerta no es un robo.** `estado_revision` nace en `pendiente` y solo una revisión
  documental con respaldo de un segundo registro la mueve.
- **Una alerta no valoriza kg.** `valor_soles` queda **nulo** salvo que la señal cuantifique un
  importe en soles, que hoy es solo el sobrecobro de F08. Multiplicar kg señalados por un precio
  de referencia convierte algo por revisar en una cifra de pérdida que nadie midió.

---

## 4. Las vistas de Athena (F06)

Ocho, en `sql/athena/vistas/`. Son la interfaz entre Gold y lo que ve la gente, y exponen
**componentes sumables** para que el tablero calcule el cociente después de filtrar: si no, un
filtro por producto daría un promedio de porcentajes en vez del KPI.

| Vista | Qué da | De dónde |
|---|---|---|
| `v_kpi_1` | diferencia no explicada de planta, bruta y neta | `fact_balance_planta` |
| `v_kpi_2` | valor en soles de esa diferencia | `fact_balance_planta` |
| `v_kpi_3` | compras con segundo registro coincidente | `modelo_factura` |
| `v_kpi_4` | combustible por tonelada, por rol | `fact_unidad_mes` |
| `v_kpi_5` | revisadas y confirmadas | `v_alerta` |
| `v_alerta` | bandeja: cada alerta con su última revisión | `fact_alerta` + `revision_alerta` |
| `v_cubo_unidad` | cubo por unidad | `fact_unidad_mes` |
| `v_semaforo_unidades` | rojo / ámbar / verde antes del despacho | `fact_serie` + `fact_unidad_mes` |

La función `kpis` del portal tiene su **lista blanca** apuntando a estos ocho nombres
(`src/portal/kpis.py`): nunca concatena un nombre de tabla que venga de afuera.

---

## 5. Quién cuida qué

| Área | Quién | Carpetas |
|---|---|---|
| Ingeniería de datos | Wilson | `src/ingest/`, `src/glue/`, `src/portal/`, `infra/`, `sql/athena/ddl/` |
| Análisis y modelado | Frank | `src/models/`, `src/signals/`, `sql/athena/vistas/` |
| Calidad y documentación | Anghelo | `contracts/`, `src/quality/`, `src/sim/`, `docs/adr/` |
| Coordinación | Bruno | `portal/`, `dashboards/`, `docs/coordinacion/` |

---

## 6. Qué falta, y de quién depende

| Bloqueo | Quién lo levanta | Qué destraba |
|---|---|---|
| `contracts/gastos.yaml` | Anghelo (A06) | `fact_unidad_mes` → `fact_alerta` → control de pago → semáforo |
| `src/sim/validacion.py` | Anghelo (A18), ya tiene `calibrar_h` | la Lambda de validación del detector |
| Desplegar el stack y correr Athena | el titular de la cuenta | que las 13 tablas existan de verdad y el portal devuelva datos |
| MFA y rotación de claves | el titular de la cuenta | seguridad, y la clave de `svc-dashboard` para Grafana |
| El ADR 0014 de EMR | Bruno y Wilson | la evidencia de Hadoop Streaming que pide el curso |

**Lo más importante de esta sección:** nada de Gold existe todavía en AWS. Los DDL están escritos
y probados, pero hasta que se corra `python -m sql.athena.crear_tablas --solo gold` las tablas no
están creadas. Implementación, despliegue y corrida son tres cosas distintas, y el informe tiene
que decirlo así.
