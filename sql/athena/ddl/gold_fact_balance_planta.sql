-- KPI 1 y 2: balance de planta por producto y mes (`src/glue/balance.py`, W06).
-- `delta_stock_kg` es nulo mientras la entrega no traiga cierres fisicos, y `merma_tecnica_kg`
-- es el supuesto declarado del ADR 0027. Las vistas v_kpi_1 y v_kpi_2 leen de aqui.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.fact_balance_planta (
  producto string COMMENT 'GLP-E, GLP-G o SIN_CLASIFICAR',
  anio int,
  mes int,
  kg_comprados double,
  kg_vendidos double,
  diferencia_bruta_kg double COMMENT 'kg_comprados - kg_vendidos',
  delta_stock_kg double COMMENT 'nulo sin cierre fisico; un cero afirmaria que no se movio',
  merma_tecnica_kg double COMMENT 'nulo si no se descuenta merma',
  merma_es_supuesto boolean COMMENT 'la merma es un supuesto declarado, no una medicion',
  kg_no_explicados double COMMENT 'diferencia bruta menos stock y merma',
  pct_no_explicado double COMMENT 'kg_no_explicados / kg_comprados',
  valor_soles double COMMENT 'kg no explicados al precio de compra del mes; nulo sin TC valido',
  mes_completo boolean COMMENT 'el mes tiene compras y ventas registradas')
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/fact_balance_planta/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
