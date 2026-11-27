-- Solo el hash y el tipo. Ninguna columna de nombre ni de documento (CLAUDE.md, privacidad).
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.dim_persona (
  persona_hash string COMMENT 'SHA-256 con sal; el nombre no pasa a Gold',
  tipo string COMMENT 'conductor o vendedor')
LOCATION '${LAKE}/gold/dim_persona/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
