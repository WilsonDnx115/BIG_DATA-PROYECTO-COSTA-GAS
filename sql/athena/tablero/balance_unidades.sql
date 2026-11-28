-- B04 · Balance de planta y unidades, 12 meses hasta el mes elegido.
-- Una sola consulta por refresco (ADR 0016): los demas paneles reusan este resultado.
-- Filtra por anio y mes en los dos hechos para que Athena pode particiones.
WITH balance AS (
    SELECT anio, mes,
           SUM(kg_comprados)              AS kg_comprados,
           SUM(kg_vendidos)               AS kg_vendidos,
           SUM(delta_stock_kg)            AS delta_stock_kg,
           SUM(merma_tecnica_kg)          AS merma_tecnica_kg,
           MAX(stock_es_supuesto)         AS stock_es_supuesto,
           MAX(merma_es_supuesto)         AS merma_es_supuesto,
           MIN(mes_completo)              AS mes_completo
      FROM costagas_gold.v_kpi_1
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
       AND ('__all' IN (${producto:sqlstring}) OR producto IN (${producto:sqlstring}))
     GROUP BY anio, mes
),
valor AS (
    SELECT anio, mes,
           SUM(kg_no_explicados)          AS kg_no_explicados,
           SUM(valor_diferencia_soles)    AS valor_diferencia_soles
      FROM costagas_gold.v_kpi_2
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
       AND ('__all' IN (${producto:sqlstring}) OR producto IN (${producto:sqlstring}))
     GROUP BY anio, mes
),
unidades AS (
    SELECT anio, mes,
           SUM(unidades)                  AS unidades,
           SUM(kg)                        AS kg_unidades,
           SUM(combustible_soles)         AS combustible_soles,
           SUM(senales_disparadas)        AS senales_disparadas,
           SUM(unidades_mes_atipicas)     AS unidades_atipicas
      FROM costagas_gold.v_cubo_unidad
     WHERE nivel = 0
       AND anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
       AND ('__all' IN (${rol:sqlstring}) OR rol IN (${rol:sqlstring}))
     GROUP BY anio, mes
)
SELECT format('%04d-%02d', b.anio, b.mes)                       AS periodo,
       b.anio, b.mes,
       b.kg_comprados, b.kg_vendidos, b.delta_stock_kg, b.merma_tecnica_kg,
       v.kg_no_explicados, v.valor_diferencia_soles,
       (b.kg_comprados - b.kg_vendidos) / NULLIF(b.kg_comprados, 0)          AS kpi1_bruto,
       (b.kg_comprados - b.kg_vendidos - COALESCE(b.delta_stock_kg, 0) - b.merma_tecnica_kg)
           / NULLIF(b.kg_comprados, 0)                                       AS kpi1_neto,
       b.stock_es_supuesto, b.merma_es_supuesto, b.mes_completo,
       u.unidades, u.kg_unidades, u.combustible_soles, u.senales_disparadas, u.unidades_atipicas
  FROM balance b
  LEFT JOIN valor    v ON v.anio = b.anio AND v.mes = b.mes
  LEFT JOIN unidades u ON u.anio = b.anio AND u.mes = b.mes
 ORDER BY b.anio, b.mes
