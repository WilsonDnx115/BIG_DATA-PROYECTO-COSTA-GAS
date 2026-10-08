CREATE EXTERNAL TABLE IF NOT EXISTS costagas_gold.fact_alerta (
  id_alerta string, senal string, tipo string, fecha date, placa_norm string,
  documento string, kg double, valor_soles double, puntaje double,
  grado_evidencia string, estado_revision string)
PARTITIONED BY (anio int, mes int)
STORED AS PARQUET
LOCATION '${LAKE}/gold/fact_alerta/'
TBLPROPERTIES ('projection.enabled'='true',
  'projection.anio.type'='integer', 'projection.anio.range'='2016,2024',
  'projection.mes.type'='integer',  'projection.mes.range'='1,12',
  'storage.location.template'='${LAKE}/gold/fact_alerta/anio=${anio}/mes=${mes}/');
