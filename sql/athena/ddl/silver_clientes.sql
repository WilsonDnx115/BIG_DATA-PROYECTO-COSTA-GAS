-- Generado desde contracts/clientes.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.clientes (
  origen string COMMENT 'id de la fuente del contrato',
  hoja string COMMENT 'hoja de Excel de origen',
  fila bigint COMMENT 'fila de Excel de origen',
  entidad_id string COMMENT 'RUC si es empresa; si no, el hash del documento, el Código SN o el hash del nombre',
  tipo_persona string COMMENT 'JURIDICA, NATURAL, INVALIDO o VACIO',
  ruc string COMMENT 'solo RUC válido de persona jurídica (prefijo 20); se conserva para cruzar con SUNAT',
  documento_hash string COMMENT 'SHA-256 con sal del DNI o del RUC 10; el número no pasa a Silver',
  razon_social string COMMENT 'solo de persona jurídica; en persona natural queda nulo',
  nombre_hash string COMMENT 'SHA-256 con sal del nombre cuando el titular es persona natural',
  codigo_sn string COMMENT 'código del socio de negocio en el sistema; solo la hoja Hoja2',
  llave_repetida boolean COMMENT 'la llave natural aparece en más de una fila; se conserva y se marca')
COMMENT 'Maestro de clientes con su documento y su razon social'
STORED AS PARQUET
LOCATION '${LAKE}/silver/maestros/clientes/';
