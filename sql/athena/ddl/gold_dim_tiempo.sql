-- Un mes por fila, generada por `dimensiones.dim_tiempo`. No se lee de ninguna fuente.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.dim_tiempo (
  id_tiempo int COMMENT 'anio * 100 + mes',
  anio int,
  mes int,
  trimestre int,
  en_ventana_analisis boolean COMMENT 'el anio cae entre ANIO_INI y ANIO_FIN',
  pandemia_2020 boolean COMMENT 'el anio es el del piloto')
LOCATION '${LAKE}/gold/dim_tiempo/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
