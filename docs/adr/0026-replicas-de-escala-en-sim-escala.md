# 0026 · Las réplicas de la prueba de escalabilidad van a `sim/escala/`, no a Silver

- **Fecha:** 2026-11-27
- **Estado:** aceptada
- **Responsable:** Wilson Mirano Ríos (Ingeniería de datos)

## Contexto
La prueba de escalabilidad de la Tabla 3.11 (W24) necesita el mismo universo multiplicado por 1,
10 y 100 para ver dónde se agota una sola máquina (Lambda) y qué gana el escalado horizontal
(Glue con 2 y con 5 trabajadores). Esas réplicas son **datos sintéticos**: cada copia desplaza
placas y documentos para que las uniones sigan siendo válidas, así que hay cien veces más placas
y facturas que en la realidad.

El riesgo es obvio y es de interpretación, no técnico: si esas filas quedan en `silver/` o en
`gold/`, cualquier consulta posterior las suma. Un KPI de diferencia de planta calculado sobre
un Silver contaminado daría cien veces los kilos reales, y el proyecto prohíbe presentar cifras
sintéticas como resultados del negocio.

El lago ya tenía dos prefijos candidatos: `scaletest/`, que usaba la versión anterior del script,
y `sim/`, el de la validación del detector con datos sintéticos (escenarios A y B, W19).

## Alternativas evaluadas
1. **Dejarlas en `silver/` con una columna que marque la réplica.** Descartada: hace falta que
   todas las consultas recuerden filtrar esa columna, y la primera que lo olvide publica cifras
   infladas. Es exactamente el fallo que no se puede permitir.
2. **Mantener `scaletest/`,** el prefijo de la versión anterior del script. Descartada: deja dos
   prefijos de datos sintéticos con reglas distintas, y el `commits_wilson.md` de este paquete
   pide `sim/escala/`.
3. **`sim/escala/xN/`, dentro del prefijo que ya es de datos sintéticos.** Elegida.

## Criterio
- **Un solo lugar para lo sintético.** `sim/` ya es, por el diseño de W19, el prefijo de los
  datos que solo validan el método; `escala/` es un subprefijo suyo. Una sola regla que recordar:
  nada de `sim/` entra al análisis.
- **Ninguna lectura del pipeline apunta ahí.** Ni el job de Gold ni el de externos leen `sim/`, y
  la regla `costagas-silver-actualizado` filtra por los siete prefijos internos de Silver
  ([ADR 0020](0020-regla-gold-prefijos-internos.md)), así que escribir réplicas no dispara
  ninguna corrida.
- **Se borran al terminar,** como pide la sección 3.7 del informe, y el borrado es el
  comportamiento por defecto del script, no un paso que alguien deba acordarse de hacer.

## Consecuencia
- [`src/scaletest/replicar.py`](../../src/scaletest/replicar.py) escribe en
  `sim/escala/x{factor}/` y borra ese prefijo al terminar salvo que se le pase `--conservar`,
  que es lo que se usa cuando hay que medir en AWS después de replicar.
- La copia 0 es la muestra intacta; de la 1 en adelante se desplazan `placa`, `placa_norm`,
  `documento`, `ruc`, `comprobante` y `nro_scop`. Hay una prueba que lo comprueba y otra que
  verifica que la copia 0 es idéntica a la muestra.
- `scaletest/` sigue declarado en [`src/common/rutas.py`](../../src/common/rutas.py) por
  compatibilidad, pero la prueba de escalabilidad ya no lo usa.
- [`docs/evidencias/escalabilidad.md`](../evidencias/escalabilidad.md) separa lo medido en local
  (fechado) de las filas de AWS, que siguen **pendientes de ejecución** hasta W11, y dice
  explícitamente que el 1× local es la muestra de 0.66 MB y no la entrega real de 114 MB.
- **Las cifras de las réplicas no se publican** en `docs/evidencias/` como resultados del
  negocio ni entran en el informe: lo único que miden es el motor.
