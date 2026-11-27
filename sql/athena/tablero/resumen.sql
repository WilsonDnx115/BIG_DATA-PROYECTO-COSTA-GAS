-- Página Resumen del tablero (dashboards/grafana/01_resumen.json, B03).
-- Informe, Tabla 4.11 (página 1) y Tabla 4.10 (los cinco KPI). Usuario: gerencia de planta.
--
-- UNA sola consulta por refresco (ADR 0016): los paneles comparten este resultado y cada uno se
-- queda con su bloque ('kpi' o 'calidad') mediante una transformación de Grafana.
--
-- Variables de Grafana (dashboards/grafana/_variables.json y la constante de la página):
--   ${anio}, ${mes}          mes elegido; la ventana es ese mes y los 11 anteriores
--   ${producto:sqlstring}    'GLP-E','GLP-G' o '__all'
--   ${rol:sqlstring}         'reparto','transporte' o '__all'
--   ${umbral_kpi1}           referencia del KPI 1 = UMBRAL_KPI_DIF de src/common/config.py (0.02)
-- Para correrla a mano en Athena, reemplaza las variables, por ejemplo:
--   ${anio} -> 2020, ${mes} -> 12, ${producto:sqlstring} -> '__all', ${rol:sqlstring} -> '__all',
--   ${umbral_kpi1} -> 0.02
--
-- Costo: toda lectura de una vista de KPI filtra por anio y mes (las vistas leen hechos de Gold
-- particionados por anio/mes, y Athena empuja el filtro hasta las particiones). El filtro
-- `anio BETWEEN` es el que poda particiones; el de `anio * 12 + mes` recorta la ventana exacta.
-- dim_tiempo (108 filas) y calidad_silver (una fila por tabla, dimensión y control) no están
-- particionadas y pesan kilobytes. Objetivo: menos de 1 GB escaneado (en la práctica, el mínimo
-- facturable de 10 MB).
--
-- Meses sin cobertura: la ventana sale de dim_tiempo y los KPI se unen con LEFT JOIN, así que un
-- mes sin datos queda en NULL (el tablero muestra «sin dato»), nunca en cero.
--
-- INTERFAZ QUE ESTA CONSULTA ESPERA DE F06 (vistas v_kpi_1 a v_kpi_5) y de A10 (calidad_silver).
-- Pendiente de confirmar: esas vistas aún no están en el repositorio. Las vistas exponen
-- componentes sumables y el cociente se calcula aquí, para que el filtro de producto o de rol
-- dé el KPI correcto y no un promedio de porcentajes.
--   v_kpi_1  anio, mes, producto, kg_comprados, kg_vendidos, merma_tecnica_pct (0.5 %, referencia
--            de mercado adoptada por el equipo; fact_balance_planta)
--   v_kpi_2  anio, mes, producto, valor_diferencia_soles (fact_balance_planta)
--   v_kpi_3  anio, mes, n_compras, n_con_segundo_registro (modelo_factura)
--   v_kpi_4  anio, mes, rol, combustible_soles, kg (kg vendidos en reparto, transportados en
--            transporte; fact_unidad_mes)
--   v_kpi_5  anio, mes, n_revisadas, n_confirmadas (v_alerta y revision_alerta)
--   calidad_silver  tabla, dimension, valor, meta, cumple, fecha_control
--
-- Fórmulas (frecuencia mensual):
--   KPI 1 sin merma = (kg_comprados - kg_vendidos) / kg_comprados          (diferencia bruta)
--   KPI 1 con merma = KPI 1 sin merma - merma_tecnica_pct  (merma: referencia de mercado)
--   KPI 2 = suma de valor_diferencia_soles                                  (S/)
--   KPI 3 = n_con_segundo_registro / n_compras                              (%)
--   KPI 4 = combustible_soles / (kg / 1000)                                 (S/ por t)
--   KPI 5 = n_confirmadas / n_revisadas                                     (%)
-- Un divisor en cero o nulo da NULL, nunca infinito ni cero.

WITH ventana AS (
    SELECT anio, mes
      FROM costagas_gold.dim_tiempo
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
),
k1 AS (
    SELECT anio, mes,
           SUM(kg_comprados)      AS kg_comprados,
           SUM(kg_vendidos)       AS kg_vendidos,
           MAX(merma_tecnica_pct) AS merma_tecnica_pct
      FROM costagas_gold.v_kpi_1
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
       AND ('__all' IN (${producto:sqlstring}) OR producto IN (${producto:sqlstring}))
     GROUP BY anio, mes
),
k2 AS (
    SELECT anio, mes, SUM(valor_diferencia_soles) AS valor_diferencia_soles
      FROM costagas_gold.v_kpi_2
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
       AND ('__all' IN (${producto:sqlstring}) OR producto IN (${producto:sqlstring}))
     GROUP BY anio, mes
),
k3 AS (
    SELECT anio, mes,
           SUM(n_compras)              AS n_compras,
           SUM(n_con_segundo_registro) AS n_con_segundo_registro
      FROM costagas_gold.v_kpi_3
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
     GROUP BY anio, mes
),
k4 AS (
    SELECT anio, mes,
           SUM(combustible_soles) AS combustible_soles,
           SUM(kg)                AS kg
      FROM costagas_gold.v_kpi_4
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
       AND ('__all' IN (${rol:sqlstring}) OR rol IN (${rol:sqlstring}))
     GROUP BY anio, mes
),
k5 AS (
    SELECT anio, mes,
           SUM(n_revisadas)   AS n_revisadas,
           SUM(n_confirmadas) AS n_confirmadas
      FROM costagas_gold.v_kpi_5
     WHERE anio BETWEEN ${anio} - 1 AND ${anio}
       AND anio * 12 + mes BETWEEN ${anio} * 12 + ${mes} - 11 AND ${anio} * 12 + ${mes}
     GROUP BY anio, mes
),
kpi AS (
    SELECT 'kpi' AS bloque,
           format('%04d-%02d', v.anio, v.mes) AS periodo,
           v.anio, v.mes,
           CAST(k1.kg_comprados - k1.kg_vendidos AS double)
               / NULLIF(k1.kg_comprados, 0)                                AS kpi1_sin_merma,
           CAST(k1.kg_comprados - k1.kg_vendidos AS double)
               / NULLIF(k1.kg_comprados, 0) - k1.merma_tecnica_pct          AS kpi1_con_merma,
           CAST(k1.merma_tecnica_pct AS double)                             AS merma_tecnica_pct,
           CAST(${umbral_kpi1} AS double)                                   AS umbral_kpi1,
           CAST(k2.valor_diferencia_soles AS double)                        AS kpi2_soles,
           CAST(k3.n_con_segundo_registro AS double) / NULLIF(k3.n_compras, 0) AS kpi3_pct,
           CAST(k4.combustible_soles AS double) / NULLIF(k4.kg / 1000.0, 0) AS kpi4_soles_por_t,
           CAST(k5.n_confirmadas AS double) / NULLIF(k5.n_revisadas, 0)     AS kpi5_pct,
           CAST(k5.n_revisadas AS bigint)                                   AS kpi5_n_revisadas,
           CAST(NULL AS varchar) AS tabla,
           CAST(NULL AS varchar) AS dimension,
           CAST(NULL AS double)  AS valor,
           CAST(NULL AS double)  AS meta,
           CAST(NULL AS boolean) AS cumple,
           CAST(NULL AS varchar) AS fecha_control
      FROM ventana v
      LEFT JOIN k1 ON k1.anio = v.anio AND k1.mes = v.mes
      LEFT JOIN k2 ON k2.anio = v.anio AND k2.mes = v.mes
      LEFT JOIN k3 ON k3.anio = v.anio AND k3.mes = v.mes
      LEFT JOIN k4 ON k4.anio = v.anio AND k4.mes = v.mes
      LEFT JOIN k5 ON k5.anio = v.anio AND k5.mes = v.mes
),
-- calidad_silver guarda un control por corrida, no por mes del dato: no tiene anio/mes que
-- filtrar. Se toma el último control de cada tabla y dimensión.
calidad AS (
    SELECT 'calidad' AS bloque,
           CAST(NULL AS varchar) AS periodo,
           CAST(NULL AS integer) AS anio,
           CAST(NULL AS integer) AS mes,
           CAST(NULL AS double)  AS kpi1_sin_merma,
           CAST(NULL AS double)  AS kpi1_con_merma,
           CAST(NULL AS double)  AS merma_tecnica_pct,
           CAST(NULL AS double)  AS umbral_kpi1,
           CAST(NULL AS double)  AS kpi2_soles,
           CAST(NULL AS double)  AS kpi3_pct,
           CAST(NULL AS double)  AS kpi4_soles_por_t,
           CAST(NULL AS double)  AS kpi5_pct,
           CAST(NULL AS bigint)  AS kpi5_n_revisadas,
           tabla, dimension,
           CAST(valor AS double) AS valor,
           CAST(meta AS double)  AS meta,
           cumple,
           CAST(fecha_control AS varchar) AS fecha_control
      FROM (
            SELECT tabla, dimension, valor, meta, cumple, fecha_control,
                   row_number() OVER (PARTITION BY tabla, dimension
                                      ORDER BY fecha_control DESC) AS orden
              FROM costagas_gold.calidad_silver
           )
     WHERE orden = 1
)
SELECT * FROM kpi
UNION ALL
SELECT * FROM calidad
ORDER BY bloque DESC, periodo, tabla, dimension
