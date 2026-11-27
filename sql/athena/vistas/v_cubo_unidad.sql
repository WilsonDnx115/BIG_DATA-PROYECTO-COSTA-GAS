-- Cubo de unidades: totales por rol, año y mes y todas sus combinaciones (GROUP BY CUBE).
-- nivel = grouping(rol, anio, mes): 0 es el detalle y 7 el total general.
CREATE OR REPLACE VIEW costagas_gold.v_cubo_unidad AS
SELECT rol, anio, mes,
       grouping(rol, anio, mes)        AS nivel,
       count(DISTINCT unidad_id)       AS unidades,
       sum(kg_base_rol)                AS kg,
       sum(gasto_combustible)          AS combustible_soles,
       sum(n_senales)                  AS senales_disparadas,
       count_if(alerta_base)           AS unidades_mes_atipicas
FROM costagas_gold.fact_unidad_mes
GROUP BY CUBE (rol, anio, mes)
