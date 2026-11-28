-- Serie del detector de desvios persistentes (`src/glue/fact_serie.py`, FR05 y FR26). Una
-- fila por entidad y periodo, con el valor esperado de la regresion de pares, el CUSUM y
-- el EWMA. La lee v_semaforo_unidades. Columnas de `fact_serie.ESQUEMA`.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.fact_serie (
  entidad_tipo string COMMENT 'unidad, vendedor, cliente o proveedor',
  entidad_id string COMMENT 'placa o id seudonimizado',
  grupo string COMMENT 'grupo de pares',
  granularidad string COMMENT 'semana o mes',
  periodo date,
  valor_real double,
  valor_esperado double,
  residuo double COMMENT 'real menos esperado, en kg',
  z double COMMENT 'desvio relativo sobre la escala robusta del grupo',
  cusum double,
  ewma double,
  estado string COMMENT 'verde, ambar, rojo o no_evaluable',
  periodo_inicio date COMMENT 'periodo estimado de inicio del desvio; nulo sin alarma',
  kg_acumulados double COMMENT 'faltante neto desde el inicio estimado',
  soles_acumulados double COMMENT 'kg acumulados por el precio de referencia',
  anio int,
  mes int)
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/fact_serie/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
