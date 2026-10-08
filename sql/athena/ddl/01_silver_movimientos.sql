-- Paso 3.5.1. Proyección de particiones: sin crawlers ni MSCK REPAIR.
-- ${LAKE} se reemplaza por s3://costagas-trujillo-lake-<sufijo> en crear_tablas.py
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.movimientos (
  tipo_mov string, documento string, linea int, placa_norm string, fecha date,
  id_producto string, kg_comprados double, kg_despachados double, kg_vendidos double,
  codigo_scop string, card_code string, precio double, canal string)
PARTITIONED BY (anio int, mes int)
STORED AS PARQUET
LOCATION '${LAKE}/silver/movimientos/'
TBLPROPERTIES ('projection.enabled'='true',
  'projection.anio.type'='integer', 'projection.anio.range'='2016,2024',
  'projection.mes.type'='integer',  'projection.mes.range'='1,12',
  'storage.location.template'='${LAKE}/silver/movimientos/anio=${anio}/mes=${mes}/');
