# 0020 · La regla de Gold escucha solo los prefijos internos de Silver

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)

## Contexto
Gold se reescribe por eventos: cuando Silver cambia, EventBridge agrupa los cambios en lotes de
10 eventos o 60 segundos y lanza el flujo `costagas-flujo-gold`, que corre el job de Glue.

El problema es que **el job también escribe en el lago**: deja Gold en `gold/`, la salida del
patrón MapReduce en `gold/mr/` y las fuentes del entorno en `silver/entorno/`. Si la regla
escuchara «cualquier objeto creado bajo `silver/`», la escritura de `silver/entorno/` al final
de una corrida dispararía la corrida siguiente, que volvería a escribirlo, y así
indefinidamente. Un bucle de corridas de Glue contra un tope de US$ 1 vacía el presupuesto en
una tarde y nadie se entera hasta que llega el aviso del presupuesto.

## Alternativas evaluadas
1. **Escuchar todo `silver/` y cortar el bucle dentro del job** (por ejemplo, detectando que
   nada cambió y saliendo pronto). Descartada: la corrida igual arranca y se cobra. El freno
   llega tarde y depende de una comprobación que alguien puede romper al editar el job.
2. **Un prefijo aparte fuera de `silver/` para lo que escribe Glue.** Descartada: rompe la
   organización por capas; `silver/entorno/` es Silver y debe vivir ahí.
3. **Enumerar en la regla los prefijos de las entregas internas.** Elegida.

## Criterio
- El corte está en el disparador, no en el job: la corrida que no debe ocurrir **no empieza**, y
  no cuesta nada.
- La lista es explícita y se lee en la plantilla: quien añada un dominio nuevo a Silver ve que
  tiene que añadirlo también aquí.
- Separa con claridad quién dispara Gold (una entrega de la empresa) de quién no (el propio
  pipeline).

## Consecuencia
- `costagas-silver-actualizado` filtra por estos **7 prefijos**, los de las entregas internas
  ([`infra/cloudformation/stack.yaml`](../../infra/cloudformation/stack.yaml)):

  `silver/compras/` · `silver/ventas/` · `silver/ventas_unidad/` · `silver/gastos/` ·
  `silver/flota/` · `silver/maestros/` · `silver/produccion/`

- Lo que escriben los jobs de Glue (`gold/`, `gold/mr/` y `silver/entorno/`) **no cae en esos
  prefijos**, así que ninguna corrida lanza otra.
- Las fuentes del entorno (BCRP, Facilito y YouTube) no disparan Gold: entran con la corrida
  siguiente o con la mensual de externos en clase FLEX.
- **Al añadir un dominio nuevo a Silver hay que añadir su prefijo a esta regla**, o sus entregas
  no actualizarán Gold. Es el riesgo que acepta esta decisión, a cambio de no poder entrar en
  bucle.
- La misma lista, bajo `op/silver/`, gobierna la regla `costagas-op-actualizado` del lago de la
  operación mensual ([ADR 0018](0018-lago-op-operacion-mensual.md)).
