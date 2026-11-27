-- Bandeja de alertas: cada alerta de fact_alerta con su ÚLTIMA revisión (informe v16, Tabla 4.9; ADR 0019).
-- revision_alerta es de solo inserciones (src/portal/revision.py escribe una fila por revisión);
-- aquí se toma la más reciente de cada alerta. Sin revisión, estado_revision = 'pendiente'.
-- La vista expone el puntaje y la probabilidad: la revisión ciega usa otra vista, sin ellos.
CREATE OR REPLACE VIEW costagas_gold.v_alerta AS
WITH ultima AS (
  SELECT id_alerta, estado, causa, nivel_evidencia, nota, revisor_hash, revisado_en,
         row_number() OVER (PARTITION BY id_alerta ORDER BY revisado_en DESC) AS orden
  FROM costagas_gold.revision_alerta
)
SELECT a.id_alerta, a.senal, a.tipo, a.resolucion, a.fecha, a.unidad_id, a.rol, a.factura_id,
       a.codigo_scop, a.kg, a.puntaje, a.probabilidad, a.grado_evidencia, a.motivo, a.fuentes,
       a.anio, a.mes,
       COALESCE(r.estado, 'pendiente') AS estado_revision,
       r.causa, r.nivel_evidencia, r.nota, r.revisor_hash, r.revisado_en
FROM costagas_gold.fact_alerta a
LEFT JOIN ultima r ON r.id_alerta = a.id_alerta AND r.orden = 1
