# 0015 · YouTube Data API v3 en lugar de yt-dlp

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Reemplaza a:** [0007 · yt-dlp para videos públicos](0007-yt-dlp-videos.md)

## Contexto
Las fuentes no estructuradas NE-01 y NE-06 del informe necesitan los títulos, las descripciones
y los comentarios de videos públicos sobre GLP y sobre el sector, para la página «Mercado» del
tablero. El [ADR 0007](0007-yt-dlp-videos.md) resolvió obtenerlos con `yt-dlp`, una herramienta
que automatiza la descarga desde el propio sitio de YouTube. La bitácora del informe v16 ya
registra la API oficial como la opción elegida desde el 07/10/2026, pero el ADR 0007 conservó la
redacción anterior y `PLAN.md` todavía describe `yt-dlp` en los pasos 3.2.7 y 3.2.8. Esta
decisión cierra esa diferencia.

El motivo del cambio no es técnico sino de condiciones de uso: la descarga automatizada va
contra los términos de servicio de YouTube, y el proyecto no puede sostener una fuente obtenida
de esa forma en un informe académico ni en una entrega a la empresa.

## Alternativas evaluadas
1. **`yt-dlp` sin descargar el video** (`--skip-download --write-info-json --write-comments`).
   Descartada: la descarga automatizada va contra las condiciones de uso de YouTube, aunque solo
   se tomen los metadatos.
2. **TikTok Research API y Meta Content Library.** Descartadas: exigen aprobación institucional,
   que el equipo no tiene y no puede conseguir dentro del semestre. TikTok y Facebook quedan
   además fuera del alcance corregido.
3. **YouTube Data API v3.** Elegida.

## Criterio
- Es gratuita con una clave y una cuota diaria, así que no consume el tope de US$ 1.
- Respeta las condiciones de uso de YouTube y entrega lo que el proyecto necesita: metadatos,
  descripciones y comentarios de videos **públicos**, sin descargar el video.
- No añade un servicio que administrar: la consume una Lambda extractora ya prevista.
- La clave es un `SecureString` en AWS Systems Manager Parameter Store, que solo lee la función
  `costagas-extractor-youtube`. No entra al repositorio ni a `.env` versionado.

## Consecuencia
- La fuente de videos pasa a `costagas-extractor-youtube`, una Lambda programada con EventBridge
  Scheduler en cadencia semanal, que escribe en `landing/externo/`.
- El contrato `contracts/entorno_youtube.yaml` declara id del video, fecha, canal, título y
  descripción, y su destino es `silver/entorno/youtube/`. **No se guarda ningún dato de quien
  comenta**: los comentarios se usan agregados por marca y tema, nunca por persona (5.1).
- `yt-dlp` sale de `requirements.txt`.
- `PLAN.md` debe reescribir los pasos 3.2.7 y 3.2.8 con la API; el 3.2.8 (TikTok y Facebook)
  queda fuera del alcance corregido.
- El informe mantiene la fila de la bitácora del 07/10/2026; este ADR es su respaldo en el
  repositorio.
