-- Hecho unidad-mes (W07): columnas de la interfaz `unidad_mes` y las que agrega kpi4.
-- El volumen transportado queda nulo mientras no exista una fuente por unidad que lo mida.
CREATE TABLE IF NOT EXISTS costagas_gold.fact_unidad_mes (
  unidad_id string,
  rol string COMMENT 'reparto o transporte, desde el maestro de unidades',
  anio int,
  mes int,
  kg_vendidos double,
  kg_transportados double COMMENT 'nulo: no hay fuente de volumen transportado por unidad',
  gasto_combustible double COMMENT 'soles; nulo cuando la categoría de gasto es desconocida',
  gasto_total double,
  kg_base_rol double,
  soles_comb_por_t double,
  z double,
  puntaje double,
  alerta_base boolean,
  estado_puntaje string,
  senales array<string>,
  n_senales int)
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/fact_unidad_mes/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
