-- Generado desde contracts/gastos.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.gastos (
  origen string COMMENT 'id de la fuente del contrato',
  hoja string COMMENT 'hoja de Excel de origen',
  fila bigint COMMENT 'fila de Excel de origen',
  mes_texto string COMMENT 'mes tal como lo escribe la hoja; de ahi sale anio y mes cuando la fecha falta',
  fecha date COMMENT 'fecha del gasto; lo no convertible pasa a nulo y se cuenta',
  anio bigint COMMENT 'anio de la fecha; nulo si la fecha no se pudo convertir',
  mes bigint COMMENT 'mes de la fecha; si falta, el que se reconozca de mes_texto',
  unidad_codigo string COMMENT 'identificador de unidad de OTROS GASTOS; NO es una placa y no une con dim_unidad (evidencia, seccion 3)',
  placa_norm string COMMENT 'placa normalizada de 6 caracteres; solo la trae GASTOS FLOTA. Nula en OTROS GASTOS y en CO01, que no traen placa',
  area string COMMENT 'area que asume el gasto',
  proyecto string COMMENT 'proyecto o centro de costo; solo la hoja CO01, que no tiene placa',
  documento_gasto string COMMENT 'documento del gasto; solo la hoja CO01',
  categoria string COMMENT 'categoria del gasto; la trae la posicion E de GASTOS FLOTA, hoy no cubierta',
  es_combustible boolean COMMENT 'verdadero si la categoria es de combustible; nulo mientras la categoria no este cubierta, nunca falso por defecto',
  descripcion string COMMENT 'texto libre del concepto',
  comentarios string COMMENT 'texto libre adicional de la hoja',
  monto_soles double COMMENT 'monto en soles; lo no convertible pasa a nulo y se cuenta',
  proveedor string COMMENT 'razon social del proveedor; el RUC no se publica aunque venga pegado al nombre',
  planta string COMMENT 'planta que registra el gasto',
  llave_repetida boolean COMMENT 'la llave natural aparece en mas de una fila; se conserva y se marca')
COMMENT 'Gastos de la operacion por mes, con su categoria, su monto y su proveedor'
STORED AS PARQUET
LOCATION '${LAKE}/silver/gastos/gastos/';
