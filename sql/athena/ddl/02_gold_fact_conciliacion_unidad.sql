CREATE EXTERNAL TABLE IF NOT EXISTS costagas_gold.fact_conciliacion_unidad (
  placa_norm string, fecha date, id_producto string,
  kg_comprados double, kg_despachados double, kg_vendidos double,
  n_operaciones bigint, kg_diferencia double, pct_diferencia double,
  valor_ref_soles double, capacidad_kg double, habilitada boolean)
PARTITIONED BY (anio int, mes int)
STORED AS PARQUET
LOCATION '${LAKE}/gold/fact_conciliacion_unidad/'
TBLPROPERTIES ('projection.enabled'='true',
  'projection.anio.type'='integer', 'projection.anio.range'='2016,2024',
  'projection.mes.type'='integer',  'projection.mes.range'='1,12',
  'storage.location.template'='${LAKE}/gold/fact_conciliacion_unidad/anio=${anio}/mes=${mes}/');
