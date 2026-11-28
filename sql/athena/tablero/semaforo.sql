-- B07 · Semaforo de unidades antes del despacho (Tabla 4.8i, carril 2), desde v_semaforo_unidades.
-- Una sola consulta por refresco (ADR 0016). La vista ya toma el periodo mas reciente de cada unidad,
-- con granularidad semanal si existe, y cruza fact_serie con el ultimo mes de fact_unidad_mes.
SELECT unidad_id,
       rol,
       semaforo,
       granularidad,
       periodo,
       periodo_inicio,
       kg_acumulados,
       soles_acumulados,
       senales
  FROM costagas_gold.v_semaforo_unidades
 WHERE ('__all' IN (${rol:sqlstring}) OR rol IN (${rol:sqlstring}))
 ORDER BY CASE semaforo WHEN 'rojo' THEN 0 WHEN 'ambar' THEN 1 ELSE 2 END, unidad_id
