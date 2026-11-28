# 0030 · Un solo esquema por tabla: catálogo, contrato de alertas e interfaces del WP 0.8

- **Fecha:** 2026-11-26
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)

## Contexto

Las señales S1-S12 se calculan en dos motores distintos y por buenas razones: el modelo base del
WP 0.8 corre en pandas, porque tiene que ser reproducible en una laptop y entrar en el informe; el
job de Glue corre en Spark, porque es el que atiende el volumen real. Además, el tablero las lee
desde la dimensión `dim_senal` de Gold.

Hasta el 26/11 cada uno de esos tres caminos traía su propia copia del esquema:

- había **dos catálogos de señales** con descripciones y grados de evidencia distintos para la
  misma señal;
- las alertas de Spark escribían sus columnas por su cuenta, sin pasar por el contrato que usa el
  modelo base;
- cada señal de Spark leía sus entradas con los nombres que le convenían, distintos de los que
  declara el WP 0.8.

El problema no es de estilo. Con dos esquemas, el tablero, el modelo y el informe pueden decir
cosas diferentes de la misma señal sin que nada falle, y no hay forma de demostrar cuál de los dos
resultados es el correcto. `CLAUDE.md` ya prohíbe mantener dos esquemas de lo mismo; lo que
faltaba era aplicarlo y dejar escrito dónde vive el esquema único de cada cosa.

## Alternativas evaluadas

1. **Dejar los dos catálogos y sincronizarlos a mano cuando alguien note una diferencia.**
   Descartada: es la situación que ya teníamos, y las diferencias aparecieron precisamente porque
   nadie puede notarlas todas. Un esquema que se sincroniza a mano son dos esquemas.
2. **Una sola implementación, solo Spark.** Descartada: el modelo base del WP 0.8 tiene que correr
   sin clúster y las cifras del informe salen de ahí. Dejaría el hito sin cumplir.
3. **Dos implementaciones, un solo esquema, y una prueba que las compare.** Elegida.

## Criterio

Cada cosa tiene **un** archivo que la define, y los demás lo leen:

| Qué | Dónde vive | Quién lo lee |
|---|---|---|
| Descripción, grado de evidencia e hipótesis de S1-S12 | [`src/signals/catalogo.yaml`](../../src/signals/catalogo.yaml) | las señales de pandas, las de Spark y `dim_senal` |
| Columnas de una alerta | el contrato `fact_alerta_base` de [`src/common/schemas.py`](../../src/common/schemas.py) | `src/signals/senales.py` y `src/glue/senales_spark.py` |
| Nombres y claves de las entradas (`compras`, `unidad_mes`, `unidades`, `produccion`, `tc`) | [`src/signals/contratos.py`](../../src/signals/contratos.py) | las dos implementaciones |
| Columnas de las tablas de Gold | `COLUMNAS_GOLD` de [`tests/test_vistas_sql.py`](../../tests/test_vistas_sql.py) | las vistas de Athena y el tablero |

Dos consecuencias del catálogo único que importan para leer los resultados:

- **S1, S4 y S7 llevan `muestra_minima: true`.** Tienen de 2 a 9 casos (informe v16, Tablas 4.3 y
  5.3): se calculan y abren revisión, pero su grado es «indicio» y **no entran a la precisión del
  modelo** ni a las conclusiones. Con dos catálogos, una de las copias podía contarlas y la otra
  no.
- **Una alerta no valoriza kg en soles.** Los kilos señalados son un desvío por explicar, no una
  pérdida medida; convertirlos a soles habría inflado el KPI 2 con algo que nadie midió.

Que las dos implementaciones coincidan no se declara: se prueba. Cada señal que tiene versión en
pandas se compara contra la de Spark sobre los mismos datos, y `tests/test_vistas_sql.py` toma las
columnas de Gold del propio repositorio, así que renombrar una columna rompe la prueba en lugar de
romper el tablero en silencio.

## Consecuencia

- Un solo catálogo S1-S12 en `src/signals/catalogo.yaml`, con `version: 6` y su fuente (informe,
  Tabla 4.3) declaradas en el propio archivo (commit `31fb9b3`).
- Las señales de Spark usan el contrato `fact_alerta_base` y las interfaces del WP 0.8;
  `normalizar_compras` arma la entrada `compras` desde Silver (commit `950537b`).
- El S9 y el KPI 4 calculan el z robusto sobre el **logaritmo** del combustible por tonelada y por
  rol; si la desviación es 0, la unidad queda «no evaluable» en lugar de salir con un z infinito.
- `COLUMNAS_GOLD` es el contrato que deben cumplir las tablas de Gold: lo que no esté ahí no lo
  puede leer una vista.
- Quien agregue una señal, una columna de alerta o una entrada nueva la declara en el archivo
  único correspondiente. Un esquema declarado dos veces es un defecto, y la revisión del pull
  request lo trata como tal.
