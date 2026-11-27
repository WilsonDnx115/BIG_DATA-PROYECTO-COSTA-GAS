-- Alertas de las senales S1-S12 (`src/glue/senales_spark.py`) y del modelo S12.
-- `valor_soles` queda nulo a proposito: unos kg senalados no son una perdida.
-- `probabilidad` la escribe W12 a partir del modelo; en una alerta de regla es nula.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.fact_alerta (
  id_alerta string COMMENT 'SHA-256 de senal, tipo, resolucion, fecha, unidad, factura y motivo',
  senal string COMMENT 'S1 a S12',
  tipo string COMMENT 'regla o modelo',
  resolucion string COMMENT 'evento, unidad-mes, planta-mes o factura',
  fecha date,
  unidad_id string COMMENT 'placa normalizada',
  rol string COMMENT 'transporte o reparto',
  factura_id string,
  codigo_scop string,
  kg double,
  valor_soles double COMMENT 'nulo salvo que la senal cuantifique soles (sobrecobro F08)',
  puntaje double,
  probabilidad double COMMENT 'probabilidad del modelo S12; nula en una alerta de regla',
  grado_evidencia string COMMENT 'alta, media o baja',
  estado_revision string COMMENT 'pendiente al escribirse; la revision vive en revision_alerta',
  motivo string,
  fuentes string COMMENT 'tablas Silver que la sustentan, separadas por coma',
  anio int,
  mes int)
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/fact_alerta/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
