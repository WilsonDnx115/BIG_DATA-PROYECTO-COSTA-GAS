## Resumen

<!-- Qué cambia y por qué, en dos o tres líneas. -->

**Paquete / tarea:** WP x.y
**Rama:** `dev-<nombre>` → `main`

## Commits incluidos

<!-- IDs del plan de commits (W__, F__, A__, B__), uno por línea. -->

- [ ] ...

## Pruebas ejecutadas

<!-- Comando y resultado. Para código: python -m pytest -q -->

```text
python -m pytest -q
...
```

- [ ] Las funciones nuevas tienen pruebas en `tests/`.
- [ ] Las consultas de Athena filtran por `anio` y `mes` (menos de 1 GB escaneado).
- [ ] Si cambia un contrato, se regeneró el DDL en este mismo PR.

## Costo de AWS

<!-- Recursos creados o consultas ejecutadas, con el costo estimado y el real. -->

| Servicio | Acción | Costo estimado (US$) | Costo real (US$) |
|---|---|---|---|
| Ninguno | — | 0.00 | 0.00 |

## Datos y seguridad

- [ ] Sin datos de `data/raw/` ni datos personales (nombres, DNI o RUC de personas naturales).
- [ ] Sin secretos: ni `.env`, ni claves, ni la sal de seudonimización.
- [ ] Solo identificadores seudonimizados en tablero, portal, evidencias y logs.

## Revisión

- [ ] Revisado por un integrante distinto del autor (revisión cruzada, `docs/flujo_git.md`).
- [ ] `PLAN.md` actualizado: `[x]` solo en lo verificado.
