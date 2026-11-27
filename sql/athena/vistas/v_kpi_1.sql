-- KPI 1 · Diferencia no explicada de planta, por producto y mes (Tabla 4.10).
-- Expone componentes sumables para que el tablero (sql/athena/tablero/resumen.sql) calcule el
-- cociente después de filtrar por producto, más el KPI de la fila para el portal.
--   kpi1_bruto: (kg comprados − kg vendidos) ÷ kg comprados.
--   kpi1_neto:  además resta la variación de stock y la merma técnica.
-- Supuestos declarados: sin stock físico medido (delta_stock_kg nulo) la variación se toma como 0 y
-- stock_es_supuesto es verdadero; la merma es MERMA_TECNICA_PCT de config.py (0.5 %, supuesto del
-- equipo) y merma_es_supuesto lo indica. El tablero etiqueta ambos.
CREATE OR REPLACE VIEW costagas_gold.v_kpi_1 AS
SELECT producto, anio, mes,
       kg_comprados,
       kg_vendidos,
       COALESCE(delta_stock_kg, 0)                                   AS delta_stock_kg,
       delta_stock_kg IS NULL                                        AS stock_es_supuesto,
       merma_tecnica_kg,
       merma_tecnica_kg / NULLIF(kg_comprados, 0)                    AS merma_tecnica_pct,
       merma_es_supuesto,
       (kg_comprados - kg_vendidos) / NULLIF(kg_comprados, 0)        AS kpi1_bruto,
       (kg_comprados - kg_vendidos - COALESCE(delta_stock_kg, 0) - merma_tecnica_kg)
         / NULLIF(kg_comprados, 0)                                   AS kpi1_neto,
       mes_completo
FROM costagas_gold.fact_balance_planta
