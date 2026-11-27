# 0023 · La Lambda de ingesta ignora `landing/externo/` en vez de rechazarlo

- **Fecha:** 2026-11-27
- **Estado:** aceptada
- **Responsable:** Wilson Mirano Ríos (Ingeniería de datos)

## Contexto
La Lambda `costagas-ingesta` (W02) se dispara con cada objeto que llega a `landing/` y a
`op/landing/`. Su trabajo es la entrega interna: calcula el SHA-256, consulta el manifiesto para
no contar dos veces la misma fuente y copia el archivo sin transformar a
`bronze/interno/estructurado/<dominio>/…`, donde el dominio lo resuelve
[`contracts/_archivos.yaml`](../../contracts/_archivos.yaml). Un archivo con una extensión que el
contrato no admite levanta excepción y el evento termina en `costagas-eventos-fallidos`.

El problema es que los extractores de W20 escriben en `landing/externo/<fuente>/`, que cae dentro
del prefijo `landing/` que vigila esa notificación. Y lo que dejan ahí no es la entrega interna:
son JSON del BCRP, de Facilito y de YouTube, PDF de resoluciones y bloques `.csv.gz` de GDELT.
Ninguna de esas extensiones está en `_archivos.yaml`, ni debería estarlo: ese contrato describe
los 35 archivos del diccionario v3.0, no las fuentes del entorno.

Sin una decisión explícita, cada corrida de un extractor mandaría su archivo a la cola de fallas:
el extractor de GDELT, con un bloque por cada ~128 MB, llenaría la cola él solo y dispararía
`costagas-eventos-fallidos` y su alarma sin que nada esté roto.

## Alternativas evaluadas
1. **Agregar las extensiones externas a `_archivos.yaml`.** Descartada: mezcla dos universos.
   Ese contrato es la fuente de verdad del dominio de cada archivo interno, y meterle `.json`,
   `.pdf` y `.gz` lo volvería ambiguo justo donde el proyecto exige distinguir duplicados y filas
   efectivas de la entrega de 35 archivos.
2. **Restringir la notificación de S3 al prefijo `landing/interno/`.** Descartada por frágil: un
   archivo cargado a mano en la raíz de `landing/` —como se cargó la entrega hasta ahora— dejaría
   de ingresar, sin aviso. La ingesta perdería cargas en silencio, que es el peor fallo posible
   en esta capa.
3. **Que la Lambda reconozca `landing/externo/` y lo deje pasar sin tocarlo.** Elegida.

## Criterio
- **Una sola puerta, dos caminos declarados.** La notificación sigue cubriendo todo `landing/`,
  así que ninguna carga se pierde, y el código dice en una constante
  (`PREFIJO_EXTERNO = "landing/externo/"`) qué no le corresponde.
- **La cola de fallas sigue significando algo.** Si entra ruido previsible, el equipo deja de
  mirar la alarma. Una extensión no admitida en la entrega interna sigue siendo un fallo real.
- **Cada capa con su dueño.** Lo externo lo tipa el job de externos (W21) hacia
  `silver/entorno/`, con su propio contrato; Bronze interno no lo recibe porque no es una entrega
  de la empresa y no tiene manifiesto de 35 archivos que cuadrar.

## Consecuencia
- [`src/ingest/lambda_ingesta.py`](../../src/ingest/lambda_ingesta.py) declara `PREFIJO_EXTERNO` y
  omite esas claves: no las copia, no las anota en el manifiesto y no levanta excepción.
- La notificación del bucket en
  [`infra/cloudformation/stack.yaml`](../../infra/cloudformation/stack.yaml) se queda con los
  prefijos `landing/` y `op/landing/`, sin filtros por sufijo.
- `landing/externo/` no llega a Bronze interno. Su camino es el del ADR 0015 y el job de externos:
  `landing/externo/<fuente>/` → `silver/entorno/<fuente>/`.
- **Riesgo aceptado:** un archivo interno que alguien suba por error dentro de `landing/externo/`
  no se ingiere y no avisa. Se acota con la función `firmar` del portal (W22), que solo emite URL
  prefirmadas hacia `landing/interno/`, de modo que la carga normal no puede equivocarse de
  prefijo.
- El informe debe decir, en la fila de M1, que la ingesta atiende la entrega interna y que las
  fuentes del entorno entran por el job de externos, no por Bronze interno.
