-- Articulos de GLP con su presentacion. La marca comercial queda nula: la entrega no la trae.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.dim_producto (
  articulo_codigo string,
  articulo string,
  presentacion_kg double COMMENT '5, 10, 15 o 45; nula en granel',
  producto string COMMENT 'GLP-E o GLP-G',
  marca string COMMENT 'sin fuente en la entrega: siempre nula')
LOCATION '${LAKE}/gold/dim_producto/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
