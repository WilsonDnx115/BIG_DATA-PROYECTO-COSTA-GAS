-- Generado desde contracts/unidades.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.unidades (
  origen string,
  hoja string,
  fila bigint,
  empresa string COMMENT 'nombre de la hoja o columna EMPRESA',
  zonal string,
  placa_texto string COMMENT 'valor original de la columna PLACA, en mayúsculas',
  placa_norm string COMMENT '6 caracteres; nulo si el valor no es una placa',
  clase string,
  marca string,
  modelo string,
  anio_fabricacion bigint,
  capacidad_glp_kg double COMMENT 'capacidad autorizada; base de S4',
  cert_mercancias_peligrosas string,
  uso string,
  estado_soat string,
  traslada_gas boolean COMMENT 'SI/NO; base de S7',
  llave_repetida boolean COMMENT 'la llave natural aparece en más de una fila; se conserva y se marca')
COMMENT 'Vehículos según tres maestros (seguros, control de flota y SOAT). Una fila por placa y maestro'
STORED AS PARQUET
LOCATION '${LAKE}/silver/flota/unidades/';
