# Anexo A · Uso de inteligencia artificial

Lo exige `CLAUDE.md` («Evidencias e informe»: *declarar el uso de IA en el Anexo A*) y la sección
0.4 del informe v16. Este anexo dice **qué se hizo con asistencia de IA, en qué archivos y quién
revisó cada cambio**. No es una lista de herramientas: es la trazabilidad de los cambios.

## Cómo se usó

La asistencia de IA se usó como **par de programación y de redacción**, dentro de tres reglas que
el equipo fijó y que se pueden verificar en el repositorio:

1. **Una sesión por commit.** Cada sesión recibe las reglas del repositorio (`CLAUDE.md`) y el
   plan del integrante, y produce **un solo** commit con su prueba. Los planes de trabajo de cada
   integrante viven fuera del repositorio y no se suben.
2. **Ningún dato real entra a la sesión.** No se pegan celdas de los 35 archivos de la entrega, ni
   nombres, DNI, RUC ni placas. Cuando hay que describir una hoja sin encabezado, se describe en
   prosa qué mide cada posición. El acceso a `data/raw/` corresponde al rol de ingeniería.
3. **Nada se da por bueno sin ejecutarlo.** El commit solo se hace si `python -m pytest -q` pasa
   en la máquina del integrante, y la integración continua (`.github/workflows/ci.yml`) lo vuelve
   a correr en Ubuntu, donde además sí se ejecutan las pruebas de Spark e Iceberg.

Lo que **no** se delegó: las decisiones. Cada decisión de diseño se discutió y quedó escrita por
su responsable en un ADR de [`docs/adr/`](../adr/), con sus alternativas y su fuente. Una
propuesta de la IA sin fuente verificable no entró al repositorio: la regla «ningún valor sin
fuente» aplica igual a lo que escribe una persona y a lo que escribe una herramienta.

## Declaración por área

Cada integrante declara su propia área. A la fecha de este anexo está declarada el área de
Calidad y documentación; las otras tres las completa su titular en este mismo archivo, con el
mismo formato y citando sus commits.

### Calidad y documentación · Oftcher Anghelo Alcántara Pérez

| Qué se hizo con asistencia de IA | Archivos | Revisión |
|---|---|---|
| Contratos de datos y su DDL derivado | [`contracts/`](../../contracts/), [`sql/athena/ddl/`](../../sql/athena/ddl/) | La revisión la hace la propia herramienta de contratos: `python -m src.silver.contratos --validar` falla si un DDL no coincide con su contrato, y el paso corre en la CI |
| Pruebas de calidad, privacidad y contratos | [`tests/test_privacidad.py`](../../tests/test_privacidad.py), [`tests/test_calidad_silver.py`](../../tests/test_calidad_silver.py), [`tests/test_contratos_validar.py`](../../tests/test_contratos_validar.py) | Ejecutadas en local y en la CI; la de privacidad se verificó además contra un caso construido a propósito con DNI y RUC de persona natural |
| Métrica de calidad de Silver y bloqueo de KPI | [`src/quality/calidad_silver.py`](../../src/quality/calidad_silver.py) | Pull request revisado por Ingeniería de datos (PR #17) |
| Escenarios A y B de la validación del detector, y la validación con 100 semillas | [`src/sim/`](../../src/sim/) | El escenario A se calibró contra los agregados publicados (Tabla 1.5) y eso es lo que se revisó: 5.013 M kg frente a 5.0, Spearman 0.68 frente a 0.66 medida. La especificación del escenario B **no está en el repositorio** y su huella SHA-256 se publicó antes de medir |
| Control de deriva (PSI) y ficha del modelo | [`src/models/deriva.py`](../../src/models/deriva.py), [`src/models/ficha.py`](../../src/models/ficha.py) | Pruebas con distribuciones desplazadas a propósito; la ficha se genera del registro, no se escribe a mano |
| ADR, bitácora, README y este anexo | [`docs/adr/`](../adr/), [`docs/bitacora.md`](../bitacora.md), [`README.md`](../../README.md) | Cada ADR lo revisa Coordinación; las referencias externas se verificaron una por una en su fuente |

**Lo que se corrigió a la herramienta.** Vale la pena dejarlo escrito, porque es la parte que
sostiene que la revisión existió:

- Una primera versión del control de deriva recalculaba los deciles con los datos nuevos. Así el
  PSI sale casi cero siempre y no mide nada. Se cambió para que los cortes sean **los del
  entrenamiento** y se guarden junto al modelo.
- La compensación de pares redigitados se aplicaba sobre los kg absolutos. Un par +X/−X solo se
  cancela sobre el **desvío con signo**: sobre los kg, cada semana parte de una base distinta.
- La valorización de los kg señalados en soles se quitó de las alertas: un kilo señalado es un
  desvío por explicar, no una pérdida medida, y valorizarlo habría inflado el KPI 2.
- Al medir el escenario B, la primera versión tomaba la primera alarma de la unidad en toda la
  serie. Si esa unidad ya tenía una falsa alarma anterior al robo, el retardo salía negativo y la
  detección contaba un robo que nadie había visto. Se corrigió para contar solo desde la semana en
  que empieza el robo.

## Lo que la IA no escribió

- **Los datos.** Ninguna cifra del informe la produjo una herramienta: salen de las corridas sobre
  los archivos de la empresa, con su consulta o su script reproducible.
- **La especificación del escenario B.** La define una persona, desde Calidad y documentación, y
  no se revela a quien ajusta el detector hasta cerrar la medición
  ([`docs/validacion/protocolo_ciego.md`](../validacion/protocolo_ciego.md)).
- **Las credenciales y el despliegue en AWS.** Los hace el titular de la cuenta y el rol de
  ingeniería, con sus propias identidades.
