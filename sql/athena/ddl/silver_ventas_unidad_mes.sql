-- Generado desde contracts/ventas_unidad_mes.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.ventas_unidad_mes (
  origen string,
  hoja string,
  fila bigint,
  anio bigint,
  mes bigint COMMENT 'desde el nombre del mes',
  proyecto string COMMENT 'valor original de la columna Proyecto',
  placa_norm string COMMENT 'placa extraída de Proyecto',
  centro_costo string COMMENT 'Proyecto cuando no es una placa',
  articulo string,
  tipo string,
  unidad_negocio string,
  unidad_medida string,
  cantidad double,
  precio_promedio double,
  vendedor_hash string COMMENT 'SHA-256 con sal',
  kg double,
  balones_galones double)
COMMENT 'Ventas por unidad de reparto, mes y presentación, 2020 y 2021'
STORED AS PARQUET
LOCATION '${LAKE}/silver/ventas_unidad/ventas_unidad_mes/';
