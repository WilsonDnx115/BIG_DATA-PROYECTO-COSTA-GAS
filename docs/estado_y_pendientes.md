# Costa Gas Trujillo · estado al 28/11/2026

**Escribe:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación) · Repositorio:
`WilsonDnx115/BIG_DATA-PROYECTO-COSTA-GAS`, `main` en el merge del PR #27.

**Mi parte está cerrada hasta donde se puede llegar sin la corrida en AWS.** 21 de mis 24
commits hechos; los 3 que faltan esperan la carga inicial o la Lambda del escenario B.

## Qué necesito de cada uno

| Quién | Qué | Desbloquea |
|---|---|---|
| **Wilson + titular** | El rol de despliegue por OIDC: **`cd` falla en todos los merges** (abajo) | Que `main` deje de estar en rojo y que se pueda desplegar |
| **Wilson** | WR07-WR10: despliegue, carga inicial a S3 y primera corrida | **AR16, AR17 y AR22**, y todas las cifras reales del informe |
| **Wilson** | Subir el escenario B sellado a `sim/_spec/` y correr su Lambda | **AR18 y AR19** |
| **Frank** | Fusionar `dev-frank`: **14 commits sin entrar a `main`** | Su propio AR24 y el ADR 0028 |
| **Bruno** | Roles de la Semana 8 en `equipo.md`; protocolo ciego alineado con `revision.py`; proteger `main` | Coherencia con el informe y la revisión ciega real |
| **Titular AWS** | MFA del raíz y de los cuatro usuarios de IAM, y rotar claves | La seguridad de la cuenta |

## Lo que hice

**Los diez contratos tienen fuente declarada y leída.** Filas efectivas medidas sobre los 35
archivos en [`contracts/README.md`](../contracts/README.md); los Excel nunca entran al
repositorio y de ellos no sale ningún valor de celda, solo conteos y tasas.

| Commit | Qué |
|---|---|
| AR01 | Contrato de gastos: **16 322 filas**, con **2 126 de combustible** y 94.7 % de placas válidas en `GASTOS FLOTA` |
| AR02 | Producción diaria: **31 días de oct-2018, los 31 con residuo cero**. Confirma la cita de S11 del informe |
| AR03 · AR04 | `--validar` de contratos en el `ci.yml`; `pyspark` opcional, que arreglaba el paso 5 de `cd` |
| AR05 · AR12 · AR13 | Integridad referencial de Gold, sin valores sin resolver, privacidad en alertas y vistas |
| AR06 · AR07 · AR08 · AR09 | Validación del detector con 100 semillas, ficha del modelo, cortes del PSI, bloqueo de KPI por calidad |
| AR10 · AR11 · AR14 · AR15 | `CLAUDE.md` al v17, ADR 0030, diccionario de Gold, técnicas con archivo y línea |
| AR20 · AR21 · AR23 | Anexo A de uso de IA, estado de los contratos, bitácora al cierre |
| — | **Lectura por posición** en el lector de contratos: lo que desbloqueó las tres hojas que empiezan en datos, y con ellas el `fact_unidad_mes` de Wilson |

**640 pruebas, 0 fallos.** `ci` en verde en `main`.

## Lo que me queda

| Commit | Espera |
|---|---|
| AR16 · AR17 · AR22 | La carga inicial a S3 |
| AR18 · AR19 | Que el escenario B sellado esté en `sim/_spec/` y corra su Lambda |
| AR24 | Los commits de Frank y mi AR17 |

## Por qué `main` sale en rojo

El check que falla es **`cd / Change set`**, y falla en su séptimo paso; los seis anteriores
pasan, pruebas y `cfn-lint` incluidos:

```
Run aws-actions/configure-aws-credentials@v4: failure
Credentials could not be loaded: Could not load credentials from any providers
```

Es el rol `costagas-github-deploy`: todavía no existe en la cuenta, así que no hay credenciales
que cargar. **No es de las pruebas y no lo causó ningún commit de código.** Lo resuelve Wilson con
el titular, desplegando el stack una primera vez o condicionando ese job.

## Frank: se puede entrenar hoy, sin esperar a nadie

El lago de AWS está vacío y el código desplegado es del 10/10: eso es cierto y lo resuelve
WR07-WR10. Pero **el pipeline completo corre en local con un comando**, y para eso existe la
muestra sintética:

```powershell
python -m src.pipeline --regenerar-muestra
```

Verificado hoy, de punta a punta: ingesta a Bronze, Silver con esquema declarado, conciliación en
Gold (47 107 movimientos, 10 152 filas), modelo base, modelo definitivo (LOF) y la validación
contra la verdad sintética. Con `--origen <carpeta>` corre sobre cualquier entrega de Excel.

Lo que **no** se puede hacer en local es publicar cifras del negocio: las de la muestra son
sintéticas y `CLAUDE.md` prohíbe presentarlas como resultados. Para eso hace falta la carga a S3.

**Los 35 Excel no van de mí a análisis y modelado.** La custodia es de Ingeniería de datos: van a
S3 con el perfil de Wilson, y de ahí se leen Silver y Gold. Es lo que dice `CLAUDE.md` sobre
`data/raw/` y lo que evita que acabemos con dos copias de la entrega circulando.

## Dos cosas que conviene no perder de vista

**Una prueba omitida se ve igual que una que pasa.** Las de Spark se omiten en Windows; por eso
`ci` las corre en Ubuntu y falla a propósito si alguna queda omitida.

**Implementado, probado, desplegado y corrido son cuatro cosas distintas.** Todo está
implementado y probado; **nada está corrido sobre los datos reales en AWS**. Las cifras de los
contratos salen de corridas locales y así están marcadas. Ninguna puede presentarse como
resultado de la empresa hasta la carga inicial.
