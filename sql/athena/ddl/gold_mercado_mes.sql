-- Contexto del entorno por mes (`src/glue/externos_job.py`, W21). No es una medicion de la
-- empresa: son precios de la plaza, tipo de cambio y volumen de noticias. Lo que no tiene
-- fuente queda nulo.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.mercado_mes (
  anio int,
  mes int,
  n_eventos_gdelt bigint COMMENT 'eventos de GDELT del mes para Peru',
  tono_promedio double COMMENT 'tono medio de esos eventos',
  precio_mediano_plaza double COMMENT 'precio mediano de Facilito en La Libertad',
  n_establecimientos bigint,
  tipo_cambio_promedio double COMMENT 'serie PD04640PD del BCRP',
  n_temas int COMMENT 'temas del LDA sobre resoluciones y texto del entorno')
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/mercado_mes/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
