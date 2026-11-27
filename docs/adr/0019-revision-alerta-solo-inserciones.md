# 0019 · `revision_alerta` de solo inserciones y `v_alerta` con la última fila

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)

## Contexto
La validación documental ciega la conduce el rol de Coordinación desde un formulario del portal
web: para cada alerta marca «confirmada» o «descartada» y registra la causa, el nivel de
evidencia, el revisor y la fecha. Esa decisión alimenta el KPI 5 y entra como etiqueta positiva
en el siguiente reentrenamiento del modelo S12.

Una revisión puede cambiar: lo que se descartó en noviembre puede confirmarse en diciembre
cuando aparece el documento que faltaba. Si la tabla se actualizara en su sitio, ese cambio
borraría la decisión anterior, y con ella la fecha, el revisor y la causa originales. Se
perdería justamente lo que hace auditable a la revisión ciega: poder demostrar quién decidió
qué, cuándo y con qué evidencia.

## Alternativas evaluadas
1. **`MERGE`/`UPDATE` sobre `revision_alerta`, una fila por alerta.** Descartada: la tabla
   quedaría más simple, pero cada corrección destruye el historial y el procedimiento deja de
   ser auditable. Además da permiso de actualización a una función expuesta en internet.
2. **Tabla de revisiones vigentes más una tabla de historial.** Descartada: dos tablas que hay
   que mantener en coherencia, y la fuente de verdad queda ambigua.
3. **Solo INSERT, con una vista que resuelve la última fila.** Elegida.

## Criterio
- El historial completo se conserva sin esfuerzo: cada decisión es una fila nueva.
- Encaja con Iceberg, que resuelve bien el patrón de solo anexar, y evita conflictos de
  escritura con el job de Gold, que corre a la vez.
- **Mínimo privilegio.** `costagas-portal-revision` es una Lambda con URL de función, alcanzable
  desde internet. Que solo pueda insertar acota el daño si alguien supera el control del token:
  puede añadir una revisión falsa, que queda registrada y es rastreable, pero **no puede borrar
  ni alterar** ninguna decisión anterior.
- Reconstruir el estado vigente es una consulta, no un proceso.

## Consecuencia
- `gold/revision_alerta` recibe **únicamente INSERT**. Nunca `UPDATE` ni `DELETE`.
- Cada fila lleva estado, causa, nivel de evidencia, revisor y fecha.
- La vista `v_alerta` une cada alerta con **su última revisión** y es la que consultan el
  tablero y las métricas. Nada lee `revision_alerta` en crudo salvo una auditoría del historial.
- El KPI 5 (confirmación de alertas) y la etiqueta de reentrenamiento salen de `v_alerta`, no de
  la tabla base, para no contar dos veces una alerta revisada dos veces.
- La política de `costagas-portal-revision` permite insertar en `gold/revision_alerta/` y
  actualizar esa tabla en el catálogo; nada más.
- La corrección de una revisión es una fila nueva, no una edición. Quien audite ve las dos.
