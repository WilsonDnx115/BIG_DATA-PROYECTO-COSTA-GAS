-- KPI 2 · Valor de la diferencia (S/), por producto y mes (Tabla 4.10).
-- kg no explicados × precio de compra del mes (columna valor_soles de fact_balance_planta).
-- Hereda los supuestos del KPI 1; el tablero suma valor_diferencia_soles después de filtrar.
CREATE OR REPLACE VIEW costagas_gold.v_kpi_2 AS
SELECT producto, anio, mes,
       kg_no_explicados,
       valor_soles                AS valor_diferencia_soles,
       delta_stock_kg IS NULL     AS stock_es_supuesto,
       merma_es_supuesto
FROM costagas_gold.fact_balance_planta
