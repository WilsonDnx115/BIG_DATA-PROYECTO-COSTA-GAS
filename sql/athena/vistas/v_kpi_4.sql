-- KPI 4 · Combustible por tonelada (S/ por t), por rol y mes (Tabla 4.10).
-- Solo suma las unidades-mes evaluables (soles_comb_por_t no nulo: volumen y gasto positivos),
-- así una unidad con gasto y sin volumen no infla el cociente; esas se cuentan aparte y salen en S9.
-- kg es el volumen de su rol: kg vendidos en reparto y transportados en transporte (kg_base_rol).
CREATE OR REPLACE VIEW costagas_gold.v_kpi_4 AS
SELECT rol, anio, mes,
       sum(CASE WHEN soles_comb_por_t IS NOT NULL THEN gasto_combustible END)   AS combustible_soles,
       sum(CASE WHEN soles_comb_por_t IS NOT NULL THEN kg_base_rol END)         AS kg,
       count(*)                                                                 AS unidades_mes,
       count_if(soles_comb_por_t IS NOT NULL)                                   AS unidades_evaluables,
       approx_percentile(soles_comb_por_t, 0.5)                                 AS mediana_soles_por_t,
       count_if(contains(senales, 'S9'))                                        AS unidades_con_s9
FROM costagas_gold.fact_unidad_mes
GROUP BY rol, anio, mes
