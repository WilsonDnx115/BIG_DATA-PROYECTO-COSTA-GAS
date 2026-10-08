# Reglas del proyecto para Claude Code (paso 0.1.3)

Proyecto: Big Data para detección de anomalías y prevención de pérdidas de GLP — Grupo Costa Gas, planta Trujillo, 2016–2024. Ruta B (AWS), tope de costo **US$ 1**. El plan está en `PLAN.md`: ejecutar **un paso por sesión** y marcarlo `[x]` en el mismo commit.

## Datos
- **Nunca** leer, imprimir ni commitear archivos de `data/raw/`. Trabajar sobre `data/sample/` (sintética, `python -m src.common.muestra`).
- Ningún nombre, DNI ni RUC de persona natural en Silver/Gold, el tablero, los logs o el chat. Seudonimizar con `limpieza.seudonimizar` (sal en `.env` o SSM).
- Ninguna regla de limpieza inventa datos: lo no convertible pasa a nulo y se cuenta.

## Código
- Toda ruta se arma con `src/common/rutas.py` desde `LAKE_URI`; ningún módulo escribe rutas fijas.
- Todo umbral o parámetro vive en `src/common/config.py` (leído de `.env`).
- Esquemas declarados en `src/common/schemas.py`. En Spark se lee con `.schema(...)`, nunca con `inferSchema`.
- En Spark: **no usar `collect()`**; inspeccionar con `show()`/`take()`. Tablas pequeñas con `broadcast()`.
- Capas `bronze/`, `silver/`, `gold/`. Particionar solo por `anio`/`mes`, nunca por placa, RUC o documento.
- Nombres en snake_case, sin tildes. Toda función nueva con prueba en `tests/` (`python -m pytest -q`).
- Cada técnica nueva del curso se registra en `docs/tecnicas_curso.md` con archivo y línea.
- Cada decisión de diseño nueva: ADR en `docs/adr/` a partir de `0000-plantilla.md`.

## AWS
- Región **us-east-1**. No crear recursos fuera de `infra/cloudformation/stack.yaml`.
- Prohibido: EC2, EMR, NAT Gateway, QuickSight, KMS propio, Glue crawlers.
- Glue: máximo 2 trabajadores (5 solo en la prueba de escalabilidad), FLEX, timeout 15 min.
- Antes de proponer un comando AWS que cree recursos o ejecute jobs, indicar su **costo estimado**.
- Al terminar: `infra/scripts/teardown.sh`.
