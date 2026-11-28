-- Una fila por factura del cruce tesoreria x logistica (`senales_spark.cruce_s12`), que es la
-- tabla de modelado de S12 y la fuente del KPI 3. F07 y F17 le agregan sus columnas de
-- atributos y de probabilidad en el mismo cambio que las empiecen a escribir.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.modelo_factura (
  factura_id string COMMENT 'proveedor, serie y numero',
  unidad_id string,
  codigo_scop string,
  kg_logistica double COMMENT 'kg de compras_glp',
  kg_tesoreria double COMMENT 'kg de pedidos_proveedor',
  fecha_pago date,
  fecha_vence date,
  clase_s12 string COMMENT 'coincide, kg_distinto, kg_desconocido, solo_logistica o solo_tesoreria',
  fecha date COMMENT 'la de logistica; si falta, la de pago o la de vencimiento',
  anio int,
  mes int)
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/modelo_factura/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
