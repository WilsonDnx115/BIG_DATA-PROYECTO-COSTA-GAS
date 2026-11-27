-- Serie del detector de desvios persistentes (`src/models/detector.py`, F14). Una fila por
-- entidad y periodo, con el CUSUM y el EWMA. La lee v_semaforo_unidades.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.fact_serie (
  entidad_id string COMMENT 'placa de la unidad',
  entidad_tipo string COMMENT 'unidad por ahora',
  granularidad string COMMENT 'semana o mes',
  periodo string,
  periodo_inicio string COMMENT 'periodo estimado de inicio del desvio; nulo sin alarma',
  estado string COMMENT 'verde, ambar, rojo o no_evaluable',
  valor_esperado double,
  residuo double COMMENT 'real menos esperado, en kg',
  z double COMMENT 'desvio relativo sobre la escala robusta del grupo',
  cusum double,
  ewma double,
  kg_acumulados double COMMENT 'faltante neto desde el inicio estimado',
  soles_acumulados double COMMENT 'kg acumulados por el precio de referencia')
LOCATION '${LAKE}/gold/fact_serie/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
