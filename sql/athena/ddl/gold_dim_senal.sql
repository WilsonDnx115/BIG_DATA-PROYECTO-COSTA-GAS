-- Catalogo S1-S12 (Tabla 4.9). La descripcion y el grado salen de `senales_spark.CATALOGO`;
-- la resolucion, la ventana y el estado, de `src/signals/catalogo.yaml`.
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.dim_senal (
  id_senal string COMMENT 'S1 a S12',
  descripcion string,
  resolucion string COMMENT 'evento, unidad-mes, planta-mes o factura',
  ventana string COMMENT 'periodo con cobertura para evaluarla',
  estado string COMMENT 'resoluble o no resoluble',
  grado_evidencia string COMMENT 'alta, media o baja')
LOCATION '${LAKE}/gold/dim_senal/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
