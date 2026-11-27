-- Clientes y distribuidores por su hash. El RUC no se publica, solo si es valido.
-- Cuando se enganche el maestro de `clientes.yaml` y `distribuidores.yaml` hay que
-- agregar aqui `estado` y `canal` en el mismo cambio que los empiece a escribir.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.dim_contraparte (
  documento_hash string COMMENT 'SHA-256 con sal del DNI o del RUC de persona natural',
  tipo string COMMENT 'clase del documento: RUC, DNI, INVALIDO o VACIO',
  ruc_valido boolean,
  capacidad_kg double COMMENT 'capacidad de almacenamiento declarada')
LOCATION '${LAKE}/gold/dim_contraparte/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
