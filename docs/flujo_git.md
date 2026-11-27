# Flujo de Git del equipo

Proyecto Big Data - Costa Gas Trujillo. `main` está protegida: todo cambio entra por pull request
revisado por otro integrante. Los dueños de cada carpeta están en [`.github/CODEOWNERS`](../.github/CODEOWNERS).

## Ramas

Cada integrante trabaja en su propia rama `dev-<nombre>`:

| Integrante | Rama | Área (CODEOWNERS) |
|---|---|---|
| Wilson | `dev-wilson` | `infra/`, `src/ingest/`, `src/glue/gold_job.py`, Lambdas (`src/controles/*.py`, `src/portal/`), CD |
| Frank | `dev-frank` | `src/models/`, `src/signals/`, `sql/athena/vistas/` |
| Anghelo | `dev-anghelo` | `contracts/`, `src/quality/`, `src/sim/`, `docs/adr/`, CI |
| Bruno | `dev-bruno` | `dashboards/`, `portal/`, `docs/coordinacion/`, `sql/athena/vistas/v_revision_ciega.sql` |

Nadie trabaja directamente en `main`.

Primera vez:

```powershell
git switch main; git pull; git switch -c dev-<nombre>; git push -u origin dev-<nombre>
```

Antes de cada commit, traer lo último de `main`:

```powershell
git switch dev-<nombre>; git pull origin main
```

## Commits

- Un commit por ID del plan (por ejemplo, B01), solo con los archivos que ese commit lista.
- Mensaje: `tipo(alcance): WP x.y descripción` (por ejemplo, `feat(tablero): WP 1.7 página Resumen`).
  Tipos: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`.
- `git add` con rutas explícitas; nunca `git add .`. Nunca se versionan `data/raw/`, `.env`, claves ni la sal.
- Antes de subir código: `python -m pytest -q` en verde.

## Integración por fases

Las ramas se integran a `main` al cerrar cada bloque de su fase, con un pull request:

| Fase | Contenido | Wilson | Frank | Anghelo | Bruno |
|---|---|---|---|---|---|
| 1 · Base | Reglas, contratos y base del tablero | W01-W03 | F01-F04 | A01-A09 | B01-B02 |
| 2 · Gold y demostración | Job de Gold, vistas y tablero | W04-W11 | F05-F07 | A10-A13 | B03-B09 |
| 3 · Aprendizaje automático | Modelos y señales | W12-W15 | F08-F17 | A14-A19 | - |
| 4 · Controles y operación | Portal, controles y validación ciega | W16-W19 | F18 | - | B10-B17 |
| 5 · Externos, portal y CD | Fuentes externas y despliegue | W20-W23 | - | A20-A22 | B18-B21 |
| 6 · Resultados y cierre | Evidencias, sustentación y entrega | W24 | F19-F24 | A23-A24 | B22-B24 |

Una fase depende de lo que entregó la anterior: antes de abrir el PR, actualizar la rama con `main`
y resolver los conflictos en la rama propia, no en `main`.

## Revisión cruzada

- Cada PR usa la plantilla [`.github/pull_request_template.md`](../.github/pull_request_template.md):
  commits incluidos, pruebas, costo de AWS y la casilla «sin datos de data/raw ni datos personales».
- El autor **no aprueba su propio PR**. Lo revisa el integrante de apoyo; los PR de Bruno los revisa Anghelo.
  La coordinación (Bruno) revisa y aprueba los PR del resto del equipo.
- Si el PR toca una carpeta de otro dueño, CODEOWNERS pide también su revisión.
- Quien revisa comprueba que las pruebas pasan, que no hay datos personales ni secretos
  y que `PLAN.md` solo marca `[x]` lo verificado.
- Se fusiona con «Merge pull request», sin reescribir la historia.
