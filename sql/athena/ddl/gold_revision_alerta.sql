-- Revision documental de una alerta. **Solo inserciones** (ADR 0019): cada revision es una
-- fila nueva y la vista v_alerta se queda con la mas reciente. Lo escribe la funcion
-- `revision` del portal (W22).
-- Generado por W09. Esta es la fuente de verdad del esquema de la tabla:
-- si cambia lo que escribe su productor, se regenera el DDL en el mismo cambio.
CREATE TABLE IF NOT EXISTS costagas_gold.revision_alerta (
  id_alerta string COMMENT 'la alerta revisada, de fact_alerta',
  estado string COMMENT 'confirmada, descartada o sin_concluir',
  causa string COMMENT 'digitacion, pago_tardio, entrega_parcial, nota_credito, sustraccion_confirmada o sin_explicar',
  nivel_evidencia int COMMENT '1, 2 o 3; la sustraccion confirmada exige 3',
  nota string COMMENT 'texto libre del revisor, sin datos personales',
  revisor_hash string COMMENT 'SHA-256 con sal del usuario de Cognito; no el nombre',
  revisado_en timestamp)
LOCATION '${LAKE}/gold/revision_alerta/'
TBLPROPERTIES ('table_type'='ICEBERG', 'format'='parquet',
               'vacuum_max_snapshot_age_seconds'='604800');
