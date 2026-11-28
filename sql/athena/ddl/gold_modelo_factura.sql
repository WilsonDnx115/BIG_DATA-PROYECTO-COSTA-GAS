-- Una fila por factura del cruce tesoreria x logistica (`senales_spark.cruce_s12`) con la
-- etiqueta S12, la madurez y las variables de la Tabla 4.6: la tabla de modelado de S12
-- y la fuente del KPI 3. Columnas en el orden de `modelo_factura.COLUMNAS` (F07).
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.modelo_factura (
  factura_id string COMMENT 'proveedor, serie y numero',
  proveedor_id string,
  unidad_id string,
  codigo_scop string,
  fecha date COMMENT 'la de logistica; si falta, la de pago o la de vencimiento',
  clase_s12 string COMMENT 'coincide, kg_distinto, kg_desconocido, solo_logistica o solo_tesoreria',
  etiqueta_s12 double COMMENT '1 descuadre, 0 coincide, nulo sin kg',
  kg double,
  kg_logistica double COMMENT 'kg de compras_glp',
  kg_tesoreria double COMMENT 'kg de pedidos_proveedor',
  precio_usd_kg double,
  usd_kg_vs_mediana double COMMENT 'frente a la mediana de 90 dias previos del proveedor',
  desvio_tc double,
  flag_scop_duplicado int,
  ratio_carga_capacidad double,
  fecha_pago date,
  fecha_vence date,
  vence_estimado boolean COMMENT 'vencimiento estimado con el plazo de pago medido',
  fecha_madurez date,
  madura boolean,
  anio int,
  mes int)
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/modelo_factura/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
