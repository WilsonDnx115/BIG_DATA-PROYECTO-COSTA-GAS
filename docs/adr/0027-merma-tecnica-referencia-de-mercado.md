# 0027 · Merma técnica de 0.5 % como referencia de mercado

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Frank Trelles Díaz (análisis y modelado)

## Contexto

El KPI 1 resta a la diferencia de planta una merma técnica: el GLP que se pierde en la operación normal por trasvase, venteo y gas residual en cilindros (hipótesis H5). La planta no mide su stock físico (`cierres_medidos_fisicamente: 0`) ni tiene registrada una tolerancia de merma, y **Osinergmin no publica un porcentaje de merma permitida para plantas envasadoras**: sus normas controlan el peso neto de cada cilindro, no la pérdida de la planta. Sin un valor, el KPI 1 con merma no se puede calcular y la hipótesis H5 no deja evidencia.

## Alternativas evaluadas

1. **Dejar la merma vacía.** Descartada: el KPI 1 neto y H5 quedan sin cálculo.
2. **Tomar el 4 % de pérdidas reconocidas de la CREG (Colombia).** Descartada: al revisar la fuente, ese tope es para gas natural por red en áreas de servicio exclusivo, no para GLP en cilindros, e incluye pérdidas no técnicas.
3. **Usar la referencia de pérdidas de masa en balances de hidrocarburos.** Elegida.

## Criterio

La referencia publicada más usada para pérdidas de masa en la industria de hidrocarburos clasifica las pérdidas según la calidad de la medición (Emerson, 2019):

| Instrumentación y procedimientos | Pérdida de masa |
|---|---|
| Buenos | menos de 0.5 % |
| Medios | 0.7 % a 1.5 % |
| Deficientes | 1.5 % a 2.5 % |

El índice Solomon exige pérdidas menores que 0.5 % para reportar. Se adopta **0.5 %**, el valor de buena práctica, porque una merma más alta absorbería como «normal» lo que podría ser pérdida, y el proyecto existe para detectarla.

La misma referencia sirve para leer el resultado: la diferencia bruta de mayo de 2020 (1.7 % a 2.0 %) cae en el rango de **instrumentación deficiente**, lo que coincide con que la planta no mide su stock físico.

Una advertencia de la propia industria: ningún porcentaje fijo es «la merma normal» sin conocer las condiciones de operación; lo correcto es un balance de masa de la operación concreta (Mizanest). Por eso el valor queda declarado como supuesto y el tablero muestra el KPI 1 con y sin merma.

## Consecuencia

- `src/common/config.py` y `.env.example`: `MERMA_TECNICA_PCT=0.005`, `MERMA_TECNICA_FUENTE` cita esta referencia y `MERMA_TECNICA_ES_SUPUESTO=si`.
- `sql/athena/vistas/v_kpi_1.sql` entrega `kpi1_bruto`, `kpi1_neto` y `merma_es_supuesto`; el tablero (`dashboards/grafana/01_resumen.json`) etiqueta la merma como referencia de mercado.
- `docs/coordinacion/puntos_de_control.md` y `docs/bitacora.md` usan el mismo valor y la misma fuente.
- Si la planta empieza a medir su stock físico, la merma se recalcula con su propio balance de masa y se cambia en `.env`, sin tocar código.

## Fuentes

- Emerson Automation Solutions (2019). *Lost with Losses: The Hidden Impact of Measurement Technology in Closing Mass Balances.* Sección «Typical Refinery Losses». https://www.sigmafine.com/wp-content/uploads/2019/10/Lost-with-Losses-The-Hidden-Impact-of-Measurement-Technology-in-Closing-Mass-Balances-Emerson-Milan.pdf
- Mizanest. *LPG Loss During Transfer: Causes, Measurement Differences and Best Practices.* https://mizanest.com/lpg-loss-during-transfer-en/
- CREG, Concepto 5149 de 2014 (revisado y descartado: aplica a gas natural por red). https://gestornormativo.creg.gov.co/gestor/entorno/docs/concepto_creg_0005149_2014.htm
