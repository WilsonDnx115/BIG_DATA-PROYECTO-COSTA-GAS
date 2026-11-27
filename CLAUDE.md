# Reglas del proyecto para Claude Code · WP 0.1, B2

Proyecto: Big Data para detección de anomalías y prevención de pérdidas de GLP,
Grupo Costa Gas, planta Trujillo. Alcance 2016–2024, piloto 2020, sujeto a la
cobertura real de cada fuente. Ruta B (AWS), tope de costo total **US$ 1**.

## Referencias y entregas

- Aplicar el **informe v17** y [el Plan de Corrección](docs/guias/Correcciones_CostaGas_v6.pdf), que sigue vigente salvo donde el v17 lo reemplaza. Las excepciones documentadas en `docs/adr/` forman parte de las reglas; la región vigente es `us-east-2` (ADR 0011).
- Trabajar por paquete WP y por la tarea solicitada. Registrar avances en `PLAN.md`: marcar `[x]` solo lo verificado y documentar dependencias, bloqueos y aceptación pendiente.
- Usar una rama por paquete y PR revisado por el integrante de apoyo. No trabajar directamente en `main`. Mensajes: `tipo(alcance): WP x.y descripción`.
- Registrar decisiones de diseño en `docs/adr/` usando `0000-plantilla.md` y técnicas del curso en `docs/tecnicas_curso.md`, con archivo y línea.
- **Ningún valor sin fuente.** Todo parámetro, umbral o cifra lleva su origen: una tabla del informe v17, un dato medido con la consulta o el script que lo reproduce, o una referencia externa citada en un ADR. Las fórmulas que anuncian un valor que no está no se escriben en ninguna parte: la lista exacta la tiene `tests/test_sin_pendientes.py`, que recorre `docs/`, `sql/`, `dashboards/`, `contracts/` y `src/common/config.py` y falla si alguna aparece.
- **Si un dato no existe en la entrega, se dice como hecho**: «no cubierto», con la evidencia de la búsqueda y su consecuencia. Eso es un resultado, no un pendiente; el ejemplo es el gasto atribuible a una unidad, declarado como no cubierto en [`contracts/gastos.yaml`](contracts/gastos.yaml) con la medición que lo sostiene ([gastos_posiciones.md](docs/evidencias/gastos_posiciones.md)).

## Datos y privacidad

- El análisis, los modelos, el tablero y las evidencias usan datos reales. Para reproducción local, usar la **muestra sintética** que genera `python -m src.common.muestra --unidades 25 --semilla 42`: tiene el mismo formato que las fuentes internas e inyecta a propósito los problemas de la Tabla 3.5, así que el pipeline corre entero sin datos reales. No representa a ninguna persona ni unidad real y **sus cifras no son resultados del negocio**.
- Datos sintéticos solo en pruebas y `scaletest/`; el generador anterior queda como fixture. No publicar sus cifras en `docs/evidencias/` ni usarlas como resultados del negocio.
- El acceso a `data/raw/` y Bronze interno corresponde al rol autorizado de ingeniería. En tareas de análisis, calidad y documentación, trabajar con Silver/Gold o la muestra enmascarada; nunca imprimir ni versionar archivos crudos.
- No publicar nombres, DNI ni RUC de personas naturales en Silver/Gold, muestras, tableros, logs, evidencias o chat. Usar IDs seudonimizados de forma consistente entre tablas; la sal va en `.env` o SSM, nunca en Git.
- No inventar datos al limpiar: valores no convertibles pasan a nulo y se cuentan. No completar períodos sin cobertura ni presentar ceros como mediciones cuando falten fuentes.
- El universo interno es la entrega de 35 archivos del diccionario v3.0. Distinguir duplicados y filas efectivas mediante el manifiesto; el informe es referencia, no una certificación de la corrida.
- No hay data interna no estructurada. La externa opera a nivel de marca, mes y mercado, sin señalar personas o vehículos. TikTok y Facebook quedan fuera del alcance corregido; YouTube es opcional.

## Contratos y capas

- Mantener `src/` y sus imports; contratos YAML en `contracts/` y la muestra de pruebas en `src/common/muestra.py`. El patrón MapReduce vive en `src/glue/mapreduce_sql.py`; no hay módulos de Hadoop Streaming ([ADR 0029](docs/adr/0029-mapreduce-con-spark-sin-emr.md)).
- Para las tablas migradas, `contracts/*.yaml` es la fuente de verdad: columnas, tipos, grano, claves, reglas y marcas de datos personales. Lectura, Parquet y DDL se derivan del mismo contrato; regenerar el DDL en el mismo cambio.
- **Un solo esquema por tabla** ([ADR 0030](docs/adr/0030-un-esquema-por-tabla.md)): las entradas de las señales usan las interfaces del WP 0.8 (`src/signals/contratos.py`); las alertas, el contrato `fact_alerta_base` de `src/common/schemas.py`; las señales S1-S12, `src/signals/catalogo.yaml`; y las columnas de Gold, `COLUMNAS_GOLD` de `tests/test_vistas_sql.py`. Declarar lo mismo en dos sitios es un defecto, aunque los dos coincidan hoy.
- Los contratos Python existentes solo cubren módulos aún no migrados. No mantener dos esquemas independientes de la misma tabla ni inferir encabezados ausentes: documentar el pendiente del inventario.
- Toda ruta del lago se construye con `src/common/rutas.py` desde `LAKE_URI`. Umbrales y parámetros viven en `src/common/config.py`, leídos de `.env`.
- Capas `bronze/`, `silver/`, `gold/`. Bronze es inmutable y conserva manifiesto y hash. Reprocesar no debe duplicar filas ni borrar aportes de otras fuentes.
- Silver pequeña: Parquet por fuente, sin particiones, con salida determinística. Particionar hechos Gold por `anio`/`mes`; nunca por placa, RUC o documento.
- Medir calidad por tabla y dimensión en `silver/_control/`. No publicar una métrica Gold cuando sus fuentes Silver incumplan las metas del contrato; informar el bloqueo.

## Conciliación, señales y modelos

- Conciliar en dos niveles: `fact_balance_planta` por planta/mes/producto y `fact_unidad_mes` por unidad/mes y rol. No restar compras de cisternas contra ventas de reparto por la misma placa.
- Catálogo S1–S12 con resolución, fuente, ventana, estado y evidencia. S8 queda **no resoluble** por falta de ventana común; S12 pertenece al WP 0.11.
- Modelo base: z robusto de `log(S/ combustible por tonelada)`, separado por rol, con `abs(z) > 3.5`. Reparto usa kg vendidos; transporte usa kg transportados. Declarar no evaluables los casos sin volumen/combustible válido o con MAD cero.
- Validar documentalmente: top 20 y diez alertas aleatorias, revisión ciega por alguien distinto del autor, con respaldo de un segundo registro. No usar S1/S8 como etiqueta débil ni confundir alerta con robo confirmado.
- Reportar precisión documental, tasa base, recuperación de casos conocidos, cobertura de kg atribuibles y alertas por mes. Lo que no pueda medirse queda `null` con su causa; los kg de contexto no equivalen a pérdida.
- Apache Spark MLlib e Iceberg están permitidos. El estado de revisión de `fact_alerta` se persiste en Iceberg mediante `MERGE` cuando se implemente; una salida Parquet de desarrollo no acredita esa implementación.

## Código y verificación

- Nombres en snake_case, sin tildes. Toda función nueva lleva pruebas significativas en `tests/`; ejecutar los checks adecuados al cambio (`python -m pytest -q` para código).
- En Spark leer con esquema declarado, nunca con `inferSchema`. No usar `collect()`; inspeccionar muestras limitadas con `show()`/`take()`. Usar `broadcast()` para tablas pequeñas.
- Glue 5.0 usa Spark 3.5; mantener compatibilidad del motor local. Medir optimizaciones con planes físicos y tiempos, sin declarar que se ejecutaron servicios solo por tener el código.
- El patrón MapReduce se ejecuta con Spark SQL en Glue (módulo M5 del informe v17, Tabla 2.2c). La evidencia son las cuatro etapas en el plan físico —`Project`/`Filter`, `HashAggregate` parcial, `Exchange hashpartitioning` y `HashAggregate` final— y la igualdad de totales entre `mapreduce_sql.construir` y `mapear_reducir_rdd` sobre el mismo universo ([ADR 0029](docs/adr/0029-mapreduce-con-spark-sin-emr.md)).

## AWS y costo

- Región **us-east-2**, perfil CLI `costagas`, identidades individuales y permisos por función/prefijo (ADR 0011 y 0012). No compartir credenciales ni versionar `.env`, claves o sal.
- Recursos gestionados desde `infra/cloudformation/stack.yaml`, sin excepciones: no se crea nada por CLI ni por consola.
- EMR queda fuera de la arquitectura: corre sobre EC2 por hora y la política base lo deniega (informe v17, Tabla 2.6b; [ADR 0029](docs/adr/0029-mapreduce-con-spark-sin-emr.md), que reemplaza al 0014). B2 no cambia IAM ni el plan de la cuenta.
- Prohibidos: EC2 independiente, EMR en cualquier forma (transitorio, permanente o Serverless), NAT Gateway, QuickSight, KMS propio, Glue crawlers y servicios de texto por documento (Comprehend/Textract).
- Glue: G.1X × 2 para Silver→Gold; hasta 5 trabajadores para externos y escalabilidad, en corridas medidas. Usar FLEX donde sea compatible y timeout de 15 min. Lotes semanales, marcadores y ventana objetivo de 15 min; registrar el tiempo real.
- Antes de proponer creación de recursos o ejecución de jobs, indicar el costo estimado. Mantener el total dentro de US$ 1 y registrar el gasto real; las estimaciones del informe no son costos medidos.
- Comprimir GDELT y borrarlo después del filtrado; limitar la retención de réplicas y logs según el diseño. No dejar clústeres ni réplicas de escalabilidad activos tras las pruebas.
- Al terminar las corridas, limpiar los recursos creados con los scripts de infraestructura correspondientes, incluido `infra/scripts/teardown.sh` cuando proceda.

## Evidencias e informe

- Las evidencias medidas provienen de corridas reales y llevan fecha, procedencia, capa/tabla, resolución, ventana, fórmula y valor; enlazar la consulta o script reproducible. No copiar cifras del informe como resultados nuevos.
- Cuando corresponda, guardar consultas de métricas en `sql/athena/queries/` y conciliar sus valores con Python. Versionar agregados y referencias, sin datos personales ni secretos.
- Distinguir implementación, prueba local, corrida AWS y validación documental. Las pruebas no cierran una aceptación que exige datos reales o revisión independiente.
- Documentar resultados verificados en pasado, con capturas y planes físicos; el informe final tendrá hasta 35 páginas, cinco indicadores y la figura de la arquitectura que realmente corre. Declarar el uso de IA en el Anexo A.
