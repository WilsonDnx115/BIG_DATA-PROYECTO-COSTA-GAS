# Plantilla de la ficha de un modelo

**No se rellena a mano.** La ficha de cada versión del modelo S12 la genera
[`src/models/ficha.py`](../../src/models/ficha.py) desde el registro de W13:

```powershell
python -m src.models.ficha --destino docs/modelos/ficha_s12.md
```

Lo que publica sale de `gold/_modelos/s12/vigente.json`, que es la corrida **promovida**
(`registro.promover_si_mejora`), no la última entrenada. Una ficha escrita a mano envejece en
silencio: queda describiendo un umbral que el modelo ya no usa. El umbral que aparece aquí es el
que está en el registro, o no aparece ninguno.

## Qué secciones trae y de dónde sale cada una

| Sección | Clave en `vigente.json` | Quién la escribe |
|---|---|---|
| Versión, corrida y artefacto | `version`, `corrida`, `ruta` | `registro.guardar` (W13) |
| Umbral de decisión | `umbral` | el entrenamiento, al fijar el punto de corte |
| Datos de entrenamiento | `metricas.datos` | el entrenamiento (filas, periodo, positivos) |
| Variables | `metricas.variables` | el entrenamiento |
| Métricas con IC 95 % | `metricas.precision`, `recall`, `pr_auc`, `f1` y `metricas.ic` | la evaluación con bootstrap (`BOOTSTRAP_REMUESTREOS`, informe v16, Tabla 4.8b) |
| Deriva (PSI) | `metricas.psi` | [`src/models/deriva.py`](../../src/models/deriva.py), con los cortes del entrenamiento |
| Sesgos | `metricas.sesgos.por_rol`, `.por_producto`, `.por_canal` | paso 5.3 del [PLAN](../../PLAN.md): tipo de unidad, producto y canal |

## Lo que falta se escribe como falta

Si una de esas claves no está en el registro, la ficha publica **«no cubierto»** con el motivo y
dónde se escribiría ese dato. Nunca queda en blanco y nunca dice «por confirmar» (regla 2 del
equipo, y la prueba `tests/test_sin_pendientes.py` la hace cumplir).

El motivo es de lectura, no de forma: un hueco en la sección de sesgos de una ficha de modelo se
lee como «este modelo no tiene sesgos», que es muy distinto de «nadie los ha medido todavía».

## Estructura que genera

```markdown
# Ficha del modelo s12-<AAAA-MM-DD>

- **Corrida:** <AAAA-MM-DD>
- **Artefacto:** `gold/_modelos/s12/corrida=<AAAA-MM-DD>/modelo`
- **Umbral de decision:** <0.0000>

## Datos de entrenamiento
## Variables
## Metricas          <- tabla: métrica, valor, IC 95 %
## Deriva (PSI)
## Sesgos (paso 5.3 del PLAN)
### Por tipo de unidad (rol)
### Por producto
### Por canal
```

Sin ningún modelo promovido, la ficha es una sola línea que lo dice: **«Sin modelo vigente»** con
el motivo. Eso también es un resultado, y es el estado correcto mientras el registro esté vacío.
