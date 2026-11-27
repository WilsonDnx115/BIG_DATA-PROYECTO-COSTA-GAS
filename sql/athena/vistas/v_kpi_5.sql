-- KPI 5 · Confirmación documental de alertas, por señal y mes (Tabla 4.10).
-- confirmadas ÷ (confirmadas + descartadas), con la última revisión de cada alerta
-- (docs/validacion/protocolo_ciego.md, sección 7). Las pendientes no entran al denominador.
-- Los indicios (S1, S4 y S7, muestra mínima) no entran: no sostienen la precisión del modelo.
CREATE OR REPLACE VIEW costagas_gold.v_kpi_5 AS
SELECT senal, anio, mes,
       count_if(estado_revision IN ('confirmada', 'descartada'))                AS n_revisadas,
       count_if(estado_revision = 'confirmada')                                 AS n_confirmadas,
       count_if(estado_revision = 'confirmada') * 1.0
         / NULLIF(count_if(estado_revision IN ('confirmada', 'descartada')), 0) AS kpi5_pct,
       count_if(estado_revision = 'pendiente')                                  AS n_pendientes
FROM costagas_gold.v_alerta
WHERE grado_evidencia <> 'indicio'
GROUP BY senal, anio, mes
