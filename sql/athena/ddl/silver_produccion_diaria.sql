-- Generado desde contracts/produccion_diaria.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.produccion_diaria (
  origen string COMMENT 'id de la fuente del contrato',
  hoja string COMMENT 'hoja de Excel de origen',
  fila bigint COMMENT 'fila de Excel de origen',
  fecha date COMMENT 'dia del balance; lo no convertible pasa a nulo y se cuenta',
  stock_inicial double COMMENT 'kg en planta al abrir el dia, TOTAL del bloque',
  produccion double COMMENT 'kg envasados en el dia, TOTAL del bloque',
  ventas double COMMENT 'kg vendidos en el dia, TOTAL del bloque',
  bonificaciones double COMMENT 'kg entregados sin venta, TOTAL del bloque',
  stock_final double COMMENT 'kg en planta al cerrar el dia, TOTAL del bloque',
  stock_final_es_calculado boolean COMMENT 'verdadero siempre: la planta no contabiliza su inventario fisico, lo calcula para que el balance diario cuadre (informe v17, 1.1 y cierres_medidos_fisicamente: 0). Sin esta marca el stock se leeria co',
  llave_repetida boolean COMMENT 'la llave natural aparece en mas de una fila; se conserva y se marca')
COMMENT 'Balance diario de planta con stock inicial, produccion, ventas, bonificaciones y stock final'
STORED AS PARQUET
LOCATION '${LAKE}/silver/produccion/produccion_diaria/';
