-- Generado desde contracts/scop.yaml. No editar a mano: python -m src.silver.contratos --ddl
CREATE EXTERNAL TABLE IF NOT EXISTS costagas_silver.scop (
  origen string,
  hoja string,
  fila bigint,
  fecha date COMMENT 'la columna llega como texto dd/mm/aaaa',
  nro_scop string COMMENT 'solo dígitos',
  producto string,
  proveedor string,
  lugar_origen string,
  placa_cargada string COMMENT 'placa normalizada',
  placa_facturada string COMMENT 'placa normalizada; la celda puede traer una fecha',
  fecha_en_placa string COMMENT 'fecha escrita junto a la placa facturada',
  flag_placa_divergente boolean COMMENT 'ambas placas válidas y distintas (S1)',
  factura string,
  estado string COMMENT 'texto original en mayúsculas',
  llave_repetida boolean COMMENT 'la llave natural aparece en más de una fila; se conserva y se marca')
COMMENT 'Órdenes SCOP con placa cargada y placa facturada (base de la señal S1)'
STORED AS PARQUET
LOCATION '${LAKE}/silver/compras/scop/';
