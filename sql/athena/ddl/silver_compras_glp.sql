-- Generado desde contracts/compras_glp.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.compras_glp (
  origen string COMMENT 'id de la fuente del contrato',
  hoja string COMMENT 'hoja de Excel de origen',
  fila bigint COMMENT 'fila de Excel de origen',
  anio bigint COMMENT 'año de la hoja',
  mes bigint COMMENT 'mes de la hoja',
  proveedor string COMMENT 'mayúsculas, sin espacios dobles',
  codigo_osinergmin string,
  nro_scop string COMMENT 'solo dígitos; 11 dígitos es válido',
  fecha_factura date COMMENT 'se invierte día y mes si así cae en el mes de la hoja',
  estado_fecha string COMMENT 'ok, invertida, discrepa o sin_fecha',
  serie string,
  numero string,
  tipo string COMMENT 'producto declarado en 2020',
  kg_glp_e double COMMENT 'GLP envasado, en kg',
  kg_glp_g double COMMENT 'GLP a granel, en kg',
  kg double COMMENT 'kg_glp_e + kg_glp_g, o CANTIDAD en 2020',
  placa_norm string COMMENT '6 caracteres sin guion ni sufijo',
  centro_costo string COMMENT 'valor de PLACA cuando no es una placa',
  guia string,
  monto_usd double,
  tipo_cambio double,
  tc_valido boolean COMMENT 'tipo de cambio entre TC_MIN y TC_MAX',
  monto_pagado double,
  precio_unitario double,
  total double,
  estado string COMMENT 'catálogo cerrado',
  conductor_hash string COMMENT 'SHA-256 con sal; el nombre no pasa a Silver')
COMMENT 'Facturas de compra de GLP a proveedores, 2020 y feb-2022 a ago-2023'
STORED AS PARQUET
LOCATION '${LAKE}/silver/compras/compras_glp/';
