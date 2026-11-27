-- Generado desde contracts/distribuidores.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.distribuidores (
  origen string COMMENT 'id de la fuente del contrato',
  hoja string COMMENT 'hoja de Excel de origen; identifica la envasadora',
  fila bigint COMMENT 'fila de Excel de origen',
  entidad_id string COMMENT 'RUC si es empresa; si no, el hash del documento, o del nombre cuando no hay documento',
  tipo_persona string COMMENT 'JURIDICA, NATURAL, INVALIDO o VACIO',
  ruc string COMMENT 'solo RUC válido de persona jurídica (prefijo 20); se conserva para cruzar con SUNAT',
  documento_hash string COMMENT 'SHA-256 con sal del DNI o del RUC 10; el número no pasa a Silver',
  razon_social string COMMENT 'solo de persona jurídica; en persona natural queda nulo',
  nombre_hash string COMMENT 'SHA-256 con sal del nombre cuando el titular es persona natural',
  departamento string,
  provincia string,
  distrito string,
  direccion string COMMENT 'ubicación del establecimiento; nula si el titular es persona natural',
  capacidad_kg double COMMENT 'capacidad de almacenamiento declarada, en kg',
  empresa_envasadora string,
  tipo string COMMENT 'solo lo trae la hoja DISTRIBUIDORES',
  uit double,
  item bigint COMMENT 'número de orden dentro de la hoja',
  llave_repetida boolean COMMENT 'la llave natural aparece en más de una fila; se conserva y se marca')
COMMENT 'Maestro de distribuidores y sus almacenes, con capacidad declarada en kg'
STORED AS PARQUET
LOCATION '${LAKE}/silver/maestros/distribuidores/';
