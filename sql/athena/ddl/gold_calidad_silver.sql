-- Una fila por tabla y corrida de Silver (`src/quality/calidad_silver.py`, A10). Sale de los
-- JSON de `silver/_control/`; es lo que mira la funcion `estado` del portal.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.calidad_silver (
  tabla string,
  fuente string COMMENT 'id de la fuente del contrato',
  familia string,
  generado_utc string,
  estado string,
  filas_leidas bigint,
  filas_efectivas bigint,
  filas_salida bigint,
  filas_con_llave_repetida bigint,
  columnas_declaradas int,
  completitud double COMMENT 'celdas con dato sobre celdas posibles',
  unicidad double COMMENT '1 menos la proporcion de llaves repetidas',
  filas_descartadas bigint,
  filas_corregidas bigint,
  placa_valida double,
  kg_con_placa_valida double,
  kg_positivo double,
  scop_presente double,
  fecha_valida double,
  documento_presente double,
  mes_reconocido double,
  entidad_id_presente double,
  metas_incumplidas array<string> COMMENT 'metas del contrato que no se cumplen',
  cumple boolean)
LOCATION '${LAKE}/gold/calidad_silver/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
