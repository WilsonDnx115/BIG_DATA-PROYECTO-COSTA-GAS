# 0024 · Facilito y Osinergmin: endpoint configurable y sin corrida programada hasta confirmarlo

- **Fecha:** 2026-11-27
- **Estado:** aceptada
- **Responsable:** Wilson Mirano Ríos (Ingeniería de datos)

## Contexto
De las cinco fuentes externas de W20, tres tienen un contrato de API publicado y estable:

- **BCRP**, serie `PD04640PD` por `/estadisticas/series/api/<serie>/json/<desde>/<hasta>`;
- **YouTube Data API v3**, documentada y con cuota declarada ([ADR 0015](0015-youtube-data-api.md));
- **GDELT**, con su lista maestra de archivos (`masterfilelist.txt`).

Las otras dos, no. **Facilito** es el comparador público de precios de Osinergmin y su portal
consume un servicio interno que la entidad no publica como API con versión ni compromiso de
estabilidad. Las **resoluciones** se descargan desde el buscador de Osinergmin, que entrega los
PDF pero tampoco expone un listado consultable por programa.

Escribir esas dos URL fijas en el código las volvería una afirmación del proyecto: diría que el
endpoint es ese y que la corrida programada funciona. No lo he comprobado contra el servicio real,
y el presupuesto y los permisos actuales no permiten dejar corriendo un extractor cada semana
contra una URL que puede cambiar o no existir: cada corrida fallida va a la cola de fallas y
dispara su alarma.

## Alternativas evaluadas
1. **Dejar las URL fijas en el código y programar las dos funciones.** Descartada: presenta como
   verificado algo que no se probó, y mete ruido previsible en la cola de fallas, que es
   justamente lo que el [ADR 0023](0023-landing-externo-ignorado-por-la-ingesta.md) intenta
   evitar.
2. **No implementar los dos extractores hasta tener el endpoint confirmado.** Descartada: dejaría
   sin código la mitad del paquete y bloquearía el job de externos (W21), que sí puede probarse
   con los archivos que esos extractores producen.
3. **Implementarlos con el endpoint como constante sustituible por variable de entorno, y dejar
   la lista de resoluciones en el evento.** Elegida.

## Criterio
- **Separar lo probado de lo supuesto.** El código, el parseo y la escritura en
  `landing/externo/` están implementados y probados con respuestas HTTP simuladas; lo único no
  verificado es la dirección del servicio, y eso queda dicho en el módulo y aquí.
- **Barato de corregir.** Cuando se confirme la URL, se cambia una variable de entorno de la
  función en el stack; no hay que tocar la lógica ni volver a probarla.
- **Sin datos inventados.** Si el servicio responde vacío o con otra forma, el extractor levanta
  `RespuestaInvalida` en lugar de escribir un archivo que luego pase por precio de mercado.

## Consecuencia
- [`src/extractores/facilito.py`](../../src/extractores/facilito.py) toma su URL de `FACILITO_URL`
  y su departamento de `FACILITO_DEPARTAMENTO`, con los valores por defecto documentados en el
  módulo como **pendientes de confirmar**.
- [`src/extractores/resoluciones.py`](../../src/extractores/resoluciones.py) no descubre las URL:
  las recibe en el evento o en `RESOLUCIONES_URLS`. Sin lista, no escribe nada y lo dice; además
  comprueba la cabecera `%PDF-` antes de guardar, para no versionar una página de error.
- Los programas `costagas-facilito-semanal` y `costagas-resoluciones-mensual` quedan creados en
  [`infra/cloudformation/stack.yaml`](../../infra/cloudformation/stack.yaml), **pero su primera
  corrida debe hacerse a mano** y dejar su evidencia en `docs/evidencias/` antes de confiar en la
  programación. Si el endpoint resulta inválido, el programa se desactiva en el stack hasta
  corregirlo.
- El informe no puede afirmar que estas dos fuentes están cargadas mientras no exista esa
  evidencia. Lo implementado es el extractor; lo medido, ninguna corrida todavía.
- Pendiente de decidir por Calidad y documentación: si Facilito no expone un servicio usable, la
  alternativa es el archivo de precios de referencia que Osinergmin publica como descarga, que
  cubre la misma necesidad de contexto de la señal S10 con otra forma de acceso.
