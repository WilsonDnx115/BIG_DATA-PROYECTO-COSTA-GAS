-- Medidas de la operacion con entregas mensuales (Tabla 4.8e; `src/glue/operacion.py`, FR14).
-- Grano mes x tramo x medida; lo escribe `gold_job --modo operacion` por MERGE.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.fact_operacion (
  tramo string COMMENT 'unidades, facturas o clientes',
  medida string,
  valor double COMMENT 'nulo si la entrada no permite medirla; la causa va en nota',
  numerador double,
  denominador double,
  ic_inferior double COMMENT 'intervalo bootstrap del 95 %',
  ic_superior double,
  nota string,
  anio int,
  mes int)
PARTITIONED BY (anio, mes)
LOCATION '${LAKE}/gold/fact_operacion/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
