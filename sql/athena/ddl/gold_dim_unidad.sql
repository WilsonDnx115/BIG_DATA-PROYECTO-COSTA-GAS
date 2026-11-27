-- Una fila por placa: las vistas en compras y ventas mas las del maestro de vehiculos.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.dim_unidad (
  placa_norm string COMMENT '6 caracteres sin guion ni sufijo',
  empresa string,
  marca string,
  clase string,
  capacidad_kg double COMMENT 'capacidad autorizada de GLP, del maestro',
  habilitada_glp boolean COMMENT 'la unidad puede trasladar gas; lo miran S4 y S7',
  rol string COMMENT 'transporte o reparto, deducido de clase y uso',
  presente_en_maestro boolean COMMENT 'la placa figura en el maestro de vehiculos')
LOCATION '${LAKE}/gold/dim_unidad/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
