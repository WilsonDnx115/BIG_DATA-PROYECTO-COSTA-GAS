# 0028 · Parámetros del detector de desvíos persistentes

- **Fecha:** 2026-11-27
- **Estado:** aceptada
- **Responsable:** Frank Trelles Díaz (análisis y modelado)

## Contexto

El detector (`src/models/detector.py`, informe v16, 4.3 y Figura 4.5) busca faltantes pequeños que se repiten hacia el mismo lado. Un faltante de 2 % en un periodo se confunde con el ruido, pero acumulado semana tras semana se separa de él. Para eso usa un CUSUM de un solo lado y un EWMA sobre el desvío de cada entidad frente a sus pares. Cada uno tiene parámetros, y ninguno puede quedar sin fuente.

## Alternativas evaluadas

1. **Comparar cada unidad con su propio pasado.** Descartada: un solo año no basta para estimar la estacionalidad, y la cuarentena de 2020 bajó a todas las unidades a la vez (informe, 4.3).
2. **Umbral fijo por unidad.** Descartado: con muchas entidades vigiladas, las falsas alarmas se suman y llenan la bandeja.
3. **Comparación con los pares, parámetros de la literatura de control estadístico y umbral calibrado para todo el sistema.** Elegida.

## Criterio

| Parámetro | Valor | Fuente |
|---|---|---|
| `DETECTOR_K` | 0.5 | Montgomery: el CUSUM tabular con k = δ/2 detecta un corrimiento de δ desviaciones; con δ = 1, k = 0.5 |
| `DETECTOR_H` | 5.0 inicial | Montgomery: h = 4 o 5 con k = 0.5 tiene un buen ARL ante un corrimiento de 1 desviación; con h = 5 el ARL en control ronda los 465 periodos. Es solo el valor de partida: el que se usa sale de `calibrar_h` |
| `DETECTOR_LAMBDA` | 0.2 | Montgomery: λ entre 0.05 y 0.25 funciona bien; 0.2 detecta antes que 0.05 sin volverse tan nervioso como 0.25 |
| `DETECTOR_L` | 3.0 | Montgomery: L = 3 es el límite habitual del EWMA |
| `DETECTOR_PERIODOS_BASE` | 4 | Decisión de diseño: con 4 periodos propios, la participación de la entidad frente a sus pares sale de una mediana y no de un solo periodo. En la serie mensual de 14 meses (ene-2020 a feb-2021) quedan 10 meses evaluables |
| `FALSAS_ALARMAS_ANIO` | 12 | Informe v16, Tabla 4.8h: como máximo 12 al año en todo el sistema y en cada granularidad, una por mes |

**Cómo se calcula el desvío.** El valor esperado de cada entidad es su participación histórica por la mediana de sus pares en el mismo periodo. La participación usa solo periodos anteriores, sin mirar el futuro. El desvío relativo se divide por una escala robusta, σ = 1.4826 × MAD del grupo. Si un grupo no tiene variación (MAD = 0), sus entidades quedan «no_evaluable» y no se inventa una escala.

**Cómo se calibra h.** `calibrar_h` busca el menor h, de 0.5 en adelante y de 0.1 en 0.1, que deja como máximo 12 falsas alarmas al año sumando todas las entidades de una serie sin robos (escenario A). Cada vez que el CUSUM cruza h cuenta como una alarma y se reinicia, que es la práctica habitual tras una señal.

**Resultado con el escenario A** de `src/sim/escenario_a.py` (12 unidades, 2020-2022, semilla 42; `detector.calibrar_con_escenario_a()`):

| Granularidad | h calibrado | Falsas alarmas al año | σ reparto | σ transporte |
|---|---|---|---|---|
| Semana | 2.3 | 11.3 (34 en 3 años) | 0.109 | 0.127 |
| Mes | 1.0 | 12.0 (36 en 3 años) | 0.059 | 0.057 |

El h calibrado queda por debajo del 5 inicial: el presupuesto de 12 alarmas se reparte entre solo 12 unidades, y la serie semanal tiene más ruido relativo que la mensual. Con más entidades vigiladas el h sube, porque el presupuesto es del sistema (`tests/test_detector.py`).

**Errores de digitación.** Antes de acumular, los pares +X/−X que alguien corrigió se neutralizan con `src/quality/redigitados.compensar`, sobre el desvío con signo. Los errores sueltos se dejan, porque pueden ser lo que hay que detectar. En la prueba, el par corregido deja el CUSUM en 2.0; sin neutralizarlo sube a 39.5 y la unidad pasa a rojo.

## Consecuencia

- `src/common/config.py` y `.env.example` tienen los cinco parámetros con esta fuente.
- El umbral calibrado y la σ de cada rol se guardan en `gold/_modelos/detector/umbral.json`, y el detector los reutiliza al puntuar (`detectar(..., h=cal["h"], sigma=cal["sigma"])`).
- La validación con el escenario B (AR06, Tabla 4.8h) usa el h calibrado aquí **sin volver a tocarlo**: así se mide cuántos robos detecta el detector y no cuánto se ajustó a ellos.
- Si la planta empieza a cargar ventas por documento cada semana, se recalibra con esa serie y se actualiza esta tabla.

## Fuentes

- Montgomery, D. C. *Introduction to Statistical Quality Control*, 8.ª ed., Wiley. Capítulo 9: CUSUM tabular (secc. 9.1) y EWMA (secc. 9.2).
- Informe v16, sección 4.3 («Detector de desvíos persistentes») y Tabla 4.8h.
- Commits `e1be9d2` (detector) y `8caa9d9` (calibración) en `dev-frank`.
