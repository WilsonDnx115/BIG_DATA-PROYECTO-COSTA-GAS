# WP 0.8 · Catálogo, señales y modelo base

Responsable del paquete según la asignación: Wilson Mirano, análisis y modelado.
Base: informe v6, tablas 4.3 y 4.4; `docs/guias/Correcciones_CostaGas_v6.pdf`, M1–M3.

## Estado verificable

| Paso | Implementación | Resultado real |
|---|---|---|
| 3.1.3 | Catálogo S1–S12 con resolución, ventana, familias fuente, evidencia y estado | No requiere ejecutar el lago. |
| 4.2.1 | S2, S3, S6, S7, S9 y S11, cada una en su módulo; pruebas de reglas y persistencia | Pendiente de tablas Silver/Gold v6. S12 corresponde al WP 0.11. |
| 4.2.2 | MAD de log(S/ combustible por tonelada), por rol y en ambas colas | Pendiente de Gold real. La referencia 0/82 no es resultado del entorno. |
| 4.2.3 | Exportador de top, expedientes y control aleatorio sin puntajes | Pendiente de alertas reales; el CSV versionado está vacío, con encabezado. |
| 4.2.4 | Métricas documentales y cobertura con trazabilidad | Pendiente de entradas reales, revisión independiente, casos conocidos y diferencias atribuibles. |

`linea_base_tecnica.json` es un registro de estado con métricas `null`, no una
corrida medida. Se retiraron del top y de la línea base técnica las evidencias
sintéticas anteriores. Las pruebas se escriben en temporales; la compatibilidad
v2 usa módulos `*_fixture.py` y nombres de evidencia `*_fixture`, sin certificar
el modelo v6.

La ejecución del comando real en el lago configurado detectó cuatro faltantes:
`silver/compras_glp`, `silver/unidades`, `gold/fact_unidad_mes` y
`silver/produccion_diaria`. El tipo de cambio del lago existe, pero no se ha
certificado su procedencia real. No se usaron tablas v2 para fabricar datos v6,
ni se consultó `data/raw/` ni se crearon recursos AWS.

## Interfaz esperada de WP 0.2 y Gold

Las entradas normalizadas están declaradas en `src/signals/contratos.py`. Los
nombres constituyen una interfaz de integración; no son encabezados reales
inferidos ni una certificación del inventario de los 35 archivos.

| Nombre | Ruta | Columnas obligatorias |
|---|---|---|
| compras | `silver/compras_glp` | factura_id, fecha, proveedor_id, codigo_scop, kg, precio_usd_kg, tipo_cambio |
| unidades | `silver/unidades` | unidad_id, habilitada |
| unidad_mes | `gold/fact_unidad_mes` | unidad_id, rol, anio, mes, kg_vendidos, kg_transportados, gasto_combustible, gasto_total |
| produccion | `silver/produccion_diaria` | fecha, stock_inicial, produccion, ventas, bonificaciones, stock_final, stock_final_es_calculado |
| tc | `silver/referencia/tipo_cambio` | fecha, tc_oficial |

Compras admite opcionalmente `unidad_id`, `rol` y `precio_pactado_usd_kg`.
`silver/control_sobrecobros` es una entrada opcional F08 con `factura_id`, `fecha`,
`monto_facturado_soles` y `monto_pactado_soles`; si falta, se informa.

IDs de contraparte/unidad deben venir enmascarados por el proceso autorizado.
La validación publica solo las columnas del contrato y no exporta columnas
extra de nombres ni documentos personales. Exige una fila por factura, unidad,
unidad-mes o fecha según la fuente. No elimina silenciosamente claves repetidas.
Fechas, meses, roles y booleanos inválidos producen errores de contrato.

Roles: `reparto` o `transporte`. `habilitada` y `stock_final_es_calculado` son
booleanos o nulos; un nulo expresa desconocimiento, no false. La entrega se
presupone limitada a Trujillo. Todas las rutas se construyen desde `LAKE_URI`.

## Reglas y límites

- **S2:** SCOP ausente o repetido en facturas, en 2020 y feb-2022–ago-2023. Marca
  todas las facturas afectadas por un código repetido; no confundir el número de
  alertas con el número de códigos distintos repetidos.
- **S3:** desviación absoluta superior a `TOL_PRECIO_COMPRA` (5 %) respecto del
  precio pactado en US$/kg; si no existe un pactado positivo, usa la mediana por
  proveedor y mes, con esa misma moneda/unidad. El control F08 en soles se evalúa
  aparte, por diferencia positiva entre monto facturado y pactado. Una mediana
  con una sola factura no aporta contraste; la regla no prueba sobrecobro.
- **S6:** desviación relativa superior a `TOL_TIPO_CAMBIO` (1 %) en 2022–23. La
  referencia oficial se une por fecha exacta, sin completar días faltantes ni
  usar tipos de cambio de otros períodos. Ausencia de referencia no produce
  una alerta de contraste y se cuenta en la evaluabilidad.
- **S7:** actividad en 2020 de una unidad declarada no habilitada, incluyendo
  gastos aunque no haya ventas. Habilitación desconocida se informa aparte.
- **S9:** combustible con volumen cero del rol, o valor atípico de combustible
  por tonelada en 2020. Reparto usa venta; transporte usa carga. Volumen nulo
  no se interpreta como cero. Los puntajes MAD se calculan por rol.
- **S11:** cierre con residuo cero en octubre de 2018 y procedencia expresamente
  calculada del stock final. Un cierre cuadrado por sí solo no prueba ausencia
  de medición física. Se identifica además un ajuste negativo que anula el
  stock inicial; no se interpreta como producción física ni como robo.

S8 está no resoluble por falta de ventanas coincidentes. S12 está declarada,
pero su cálculo pertenece a WP 0.11. El catálogo también conserva S1, S4, S5 y
S10 para su alcance correspondiente; no se sustituyen por reglas sintéticas.

El MAD no usa un epsilon artificial cuando la dispersión es cero. Tales grupos,
volúmenes/combustibles no positivos y entradas no finitas quedan sin puntaje.
Un resultado de cero alertas solo es interpretable junto con la cantidad de
filas evaluables. Una alerta nunca equivale a un caso confirmado de robo.

## Expedientes, revisión y métricas

La priorización conjunta es operativa: grado de evidencia, percentil del puntaje
**dentro de cada señal**, fecha descendente e ID estable. Evita comparar
directamente escalas incompatibles; no estima una probabilidad de robo.
`top20_base.csv` contiene hasta `TOP_K` alertas. Si hay menos, no se inventan
filas ni se presenta una precisión formal de 20 casos.

`expedientes_revision.csv` mezcla el top con hasta diez alertas aleatorias del
resto, usando `SEMILLA`. No muestra puntaje, grado, posición ni pertenencia al
top/control. Un integrante distinto del autor revisa los registros sin consultar
el top con sus puntajes y completa `confirmada`, `revisor_id` (ID del integrante,
no nombre personal) y `evidencia_ref`. `confirmada` debe ser booleana o 0/1; vacío
significa revisión pendiente. La referencia debe identificar un segundo
registro independiente. La interfaz exige esos metadatos; no puede certificar
por sí sola que la persona realmente revisó a ciegas.

- **Precisión documental:** confirmadas / 20, solo cuando hay veinte alertas y
  veinte decisiones. Antes: `null`. No se usa S1/S8 como etiqueta débil.
- **Tasa base:** confirmadas / 10 en el control aleatorio completamente revisado.
  Un control menor o incompleto no permite publicar esa tasa.
- **Recuperación:** casos conocidos alertados / casos conocidos confirmados por
  otro integrante, con evidencia. CSV: `caso_id`, `id_alerta`,
  `confirmado_documentalmente`, `revisor_id`, `evidencia_ref`. Las asociaciones a
  IDs deben verificarse documentalmente; el listado de expectativas del informe
  no reemplaza la lista de casos. S12 no debe declararse recuperada antes de WP 0.11.
- **Cobertura de kg:** diferencias positivas trazables asociadas a alertas / total
  de diferencias positivas del mismo universo. CSV: `caso_id`, `id_alerta`
  (puede estar vacío para casos no alertados), `kg_diferencia`, `evidencia_ref`.
  Una fila por caso evita doble conteo. El universo y las asociaciones deben
  provenir de mediciones verificadas, no del volumen de compra/venta ni de una
  resta entre cisterna y reparto. Sin esa atribución, la métrica queda `null`.
- **Alertas por mes:** IDs únicos por mes observado dentro de las ventanas del
  hito; incluye ceros en meses observados, sin rellenar años no cubiertos.

El campo `kg` de una alerta conserva volumen de contexto, **no pérdida**.
`valor_soles` queda nulo salvo sobrecobro F08 cuantificado en soles.

## Ejecución y pruebas

Desde la raíz del repositorio, con la venv activa y `LAKE_URI` apuntando al lago
real o a la muestra real enmascarada preparada por el proceso autorizado:

```bash
python -m src.models.evaluacion_base --tipo-datos muestra_enmascarada
```

Ese primer comando produce los expedientes cuando existen las tablas. Después
de la revisión independiente y preparación de casos/diferencias:

```bash
python -m src.models.evaluacion_base --tipo-datos muestra_enmascarada \
  --revisiones ruta/expedientes_revisados.csv \
  --autor-modelo WilsonDnx115 \
  --casos ruta/casos_conocidos.csv \
  --diferencias ruta/diferencias_atribuibles.csv
```

`--tipo-datos reales` también está disponible. La declaración del operador no
certifica la procedencia de los datos. `--salida` cambia el directorio de salida.
Datos `prueba` solo se pueden exportar fuera del checkout o bajo `.build/`.

El exportador escribe top, expediente ciego, JSON y puntajes unidad-mes. El
orquestador `python -m src.signals.senales` puede persistir las señales en
`gold/fact_alerta_base/` con contrato y particiones anio/mes; es una salida de
desarrollo, no el reemplazo del futuro hecho Iceberg. No se publican métricas
hasta completar cálculos y validaciones de entrada.

```bash
python -m pytest -o addopts='' -q tests/test_wp08.py
python -m pytest -o addopts='' -q
```

Las pruebas incluyen ambas colas del MAD, separación por rol, ceros/nulos,
procedencia de stock, coincidencia temporal, revisión independiente, universos
incompletos y exportación sin columnas personales. No requieren AWS.

Verificación local del 10/10/2026: **94 pruebas aprobadas y 1 omitida** por
ausencia de PySpark. El comando completo se ejecutó sobre Parquet de prueba en
un lago temporal, con `TOP_K=20` y `TOP_K=5`: produjo los cuatro artefactos y
mantuvo pendientes las métricas documentales. Los temporales no se versionan.
La ejecución con `--tipo-datos reales` terminó con código 2 por las cuatro
tablas faltantes indicadas arriba, antes de reemplazar evidencia. No se ha
validado una corrida real ni una corrida en S3.
