-- KPI 1 · Diferencia no explicada (%) y KPI 2 · Valor de la diferencia (S/). Tabla 4.10.
-- Merma técnica parametrizada (MERMA_TECNICA en .env; 0.5 % hasta que la empresa la confirme).
CREATE OR REPLACE VIEW costagas_gold.v_kpi_diferencia AS
SELECT anio, mes,
       SUM(kg_comprados)                                        AS kg_comprados,
       SUM(kg_vendidos)                                         AS kg_vendidos,
       (SUM(kg_comprados) - SUM(kg_vendidos) - 0.005 * SUM(kg_comprados))
         / NULLIF(SUM(kg_comprados), 0)                         AS pct_diferencia_no_explicada,
       SUM(valor_ref_soles)                                     AS valor_diferencia_soles
FROM costagas_gold.fact_conciliacion_unidad
GROUP BY anio, mes;
