-- Semáforo de unidades antes del despacho (Tabla 4.8i, carril 2).
-- rojo:  desvío persistente confirmado por el CUSUM (estado 'rojo' en fact_serie), o combustible
--        sin volumen o atípico (S9) junto con otra señal en el último mes de la unidad;
-- ambar: el desvío empieza (el EWMA pasó su límite y el CUSUM aún no cruza el umbral);
-- verde: sin señales.
-- Se toma el periodo más reciente de cada unidad, con la granularidad semanal si existe.
CREATE OR REPLACE VIEW costagas_gold.v_semaforo_unidades AS
WITH serie AS (
  SELECT entidad_id AS unidad_id, granularidad, periodo, estado, periodo_inicio, kg_acumulados,
         soles_acumulados,
         row_number() OVER (PARTITION BY entidad_id
                            ORDER BY CASE granularidad WHEN 'semana' THEN 0 ELSE 1 END, periodo DESC) AS orden
  FROM costagas_gold.fact_serie
  WHERE entidad_tipo = 'unidad'
),
ultimo_mes AS (
  SELECT unidad_id, rol, senales, n_senales,
         row_number() OVER (PARTITION BY unidad_id ORDER BY anio DESC, mes DESC) AS orden
  FROM costagas_gold.fact_unidad_mes
)
SELECT s.unidad_id, u.rol, s.granularidad, s.periodo, s.periodo_inicio, s.kg_acumulados,
       s.soles_acumulados, u.senales,
       CASE
         WHEN s.estado = 'rojo' OR (contains(u.senales, 'S9') AND u.n_senales >= 2) THEN 'rojo'
         WHEN s.estado = 'ambar' THEN 'ambar'
         ELSE 'verde'
       END AS semaforo
FROM serie s
LEFT JOIN ultimo_mes u ON u.unidad_id = s.unidad_id AND u.orden = 1
WHERE s.orden = 1
