-- B05 · Bandeja de alertas del mes elegido, desde v_alerta (fact_alerta + su ultima revision).
-- Una sola consulta por refresco (ADR 0016). Filtra por anio y mes: v_alerta lee un hecho particionado.
-- Sin nombres, DNI ni RUC: unidad_id es la placa normalizada y revisor_hash va seudonimizado.
SELECT id_alerta,
       senal,
       tipo,
       resolucion,
       fecha,
       unidad_id,
       rol,
       factura_id,
       codigo_scop,
       kg,
       puntaje,
       probabilidad,
       grado_evidencia,
       estado_revision,
       nivel_evidencia,
       revisado_en,
       motivo,
       fuentes,
       anio,
       mes
  FROM costagas_gold.v_alerta
 WHERE anio = ${anio}
   AND mes = ${mes}
   AND ('__all' IN (${rol:sqlstring}) OR rol IN (${rol:sqlstring}))
 ORDER BY puntaje DESC NULLS LAST, id_alerta
