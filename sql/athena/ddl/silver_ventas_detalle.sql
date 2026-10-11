-- Generado desde contracts/ventas_detalle.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.ventas_detalle (
  origen string,
  hoja string,
  fila bigint,
  anio bigint COMMENT 'año de la fecha del documento',
  mes bigint,
  fecha date,
  proyecto string,
  placa_norm string,
  centro_costo string,
  linea bigint,
  articulo_codigo string,
  articulo string,
  es_glp boolean COMMENT 'el artículo es GLP; la planta también vende abarrotes',
  unidad_medida string,
  cantidad double,
  precio_unitario double,
  importe double,
  kg double COMMENT 'solo GLP: KILOS si viene; si no, unidades por presentación, galones por 2.04, litros por 0.54',
  kg_origen string COMMENT 'registrado, derivado, sin_conversion o no_glp',
  cliente_id string COMMENT 'SHA-256 con sal del código de cliente',
  indicador string,
  documento string,
  vendedor_hash string COMMENT 'SHA-256 con sal',
  llave_repetida boolean COMMENT 'la llave natural aparece en más de una fila; se conserva y se marca')
COMMENT 'Líneas de venta del ERP. Por ahora las dos fuentes con encabezado; faltan los reportes mensuales de 2019'
STORED AS PARQUET
LOCATION '${LAKE}/silver/ventas/ventas_detalle/';
