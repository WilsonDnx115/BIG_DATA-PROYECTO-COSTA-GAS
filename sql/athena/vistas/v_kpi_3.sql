-- KPI 3 · Compras con segundo registro coincidente, por mes (Tabla 4.10).
-- modelo_factura trae una fila por factura del cruce tesorería × logística (clase_s12 de
-- cruce_s12). Las «solo_tesoreria» no son compras registradas en logística y no entran al
-- denominador; kg_desconocido cuenta como compra sin confirmar.
CREATE OR REPLACE VIEW costagas_gold.v_kpi_3 AS
SELECT anio, mes,
       count(*)                                                       AS n_compras,
       count_if(clase_s12 = 'coincide')                               AS n_con_segundo_registro,
       count_if(clase_s12 = 'coincide') * 1.0 / NULLIF(count(*), 0)   AS kpi3_pct,
       count_if(clase_s12 = 'solo_logistica')                         AS n_solo_logistica,
       count_if(clase_s12 = 'kg_distinto')                            AS n_kg_distinto,
       count_if(clase_s12 = 'kg_desconocido')                         AS n_kg_desconocido
FROM costagas_gold.modelo_factura
WHERE clase_s12 <> 'solo_tesoreria'
GROUP BY anio, mes
