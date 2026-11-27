# Formato de la especificación del escenario B

El escenario B es el escenario A con robos inyectados. Sirve para medir si el umbral que
se calibró sin robos encuentra los robos de verdad.

**El archivo con los robos reales no está en este repositorio, y no debe estarlo.** Si
quien diseñó el detector puede leerlo, terminará ajustando el detector a esos casos y la
precisión que reporte no medirá nada. Aquí solo viven el formato y la huella.

## Cómo circula el archivo

1. Calidad y documentación escribe la especificación fuera del repositorio.
2. La entrega **sellada** a Ingeniería de datos, que la sube a `sim/_spec/` (W19).
3. La huella SHA-256 se publica aquí, para poder demostrar después que la medición de la
   Tabla 4.8h se hizo contra ese archivo y no contra otro.
4. Análisis y modelado no lo ve hasta que la medición esté cerrada.

El código lo lee de la ruta que indique la variable `ESCENARIO_B_SPEC` o, en AWS, de
`sim/_spec/`. Sin esa variable, `src/sim/escenario_b.py` falla con un mensaje claro en
vez de seguir sin robos.

## Archivo sellado vigente

| Campo | Valor |
|---|---|
| Fecha del sellado | 2026-11-27 |
| Robos | 6 |
| SHA-256 | `7293b4fa2be33eaa21de002d12f375575ee07d4898b83505300eaa02768895c7` |

Para comprobar que un archivo es el sellado:

```powershell
python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('escenario_b_spec.yaml').read_bytes()).hexdigest())"
```

`inyectar()` devuelve esa misma huella en `spec.huella_sha256`, así que cada resultado de
la validación queda atado a la especificación con la que se midió.

## Estructura

```yaml
version: 1
descripcion: texto libre
robos:
  - id: R1                 # único dentro del archivo
    tipo: sangrado         # uno de los seis de abajo
    entidad: reparto#2     # rol y posición, placa literal, o "*" para toda la flota
    desde: 2020-09-07      # primer periodo en que actúa (AAAA-MM-DD)
    hasta: 2022-04-25      # opcional; sin él, hasta el final de la serie
    magnitud: 0.03         # fracción de los kg que se lleva; 0 < m < 1
    nota: por qué está este caso
```

**Las entidades van por rol y posición, no por placa.** La validación corre 100 semillas
y cada una genera una flota distinta, así que `reparto#2` es «la tercera unidad de
reparto de esta semilla». Una placa literal también se acepta, pero solo sirve para una
semilla concreta y no debería usarse en el archivo real.

Si falta un campo, el tipo no existe, la magnitud se sale de rango, hay un `id` repetido
o la entidad no existe en esa semilla, la carga falla. No se aplica una especificación a
medias: un escenario B incompleto daría una detección mejor de la real sin avisar.

## Los seis tipos

| Tipo | Qué hace | Campos propios | Para qué está |
|---|---|---|---|
| `sangrado` | Una fracción fija de cada despacho, sin pausa | — | Poco por semana, mucho al año. Es el caso que justifica el proyecto |
| `escalon` | Caída brusca y sostenida entre dos fechas | — | Cuántas semanas tarda en verse, y si deja de marcarse al parar |
| `rampa` | Crece desde cero hasta la magnitud | `semanas_rampa` | El desvío mínimo que el detector distingue |
| `pulsos` | Solo cada N periodos | `cada_n_periodos` | Separa el grano semanal del mensual: el promedio mensual casi no se mueve |
| `canal` | Afecta a toda la flota a la vez (`entidad: "*"`) | — | Un detector que compara cada unidad con el resto **no puede verlo por diseño**. Tiene que salir en el balance de planta (KPI 1) |
| `a_la_sombra` | Solo en periodos que ya tienen un evento legítimo | — | El tipo que el detector no tuvo en cuenta al diseñarse |

### Por qué `a_la_sombra`

El escenario A trae 15 eventos legítimos documentados (paradas, campañas, altas de
clientes) y el detector se calibra para tolerarlos. `a_la_sombra` roba **solo en esas
semanas**: el salto queda explicado por el evento y nadie lo revisa dos veces. Es un caso
que el diseño del detector no contempla, y por eso tiene que estar en la medición: una
validación que solo usa las formas que el detector ya conoce no mide su alcance, mide su
memoria.

### Por qué `canal` cuenta como límite y no como fallo

`canal` mueve a todas las unidades a la vez. El detector compara cada unidad con el resto
de la flota en el mismo mes, así que por construcción no lo ve. Está en la
especificación para que ese límite quede **medido y escrito**, no para castigar al
detector: su lugar es el balance de planta, que necesita las ventas SAP y el stock
físico (Tablas 1.8 y 6.2 del informe).

## Qué devuelve la inyección

`inyectar(escenario_a, ruta_spec)` entrega los mismos granos que el escenario A, con los
kg ya descontados, más:

- `robado_kg` y `robo_id` en la serie, y
- `verdad`: una fila por entidad y periodo robado, con el tipo y los kg.

`verdad` es la respuesta del examen. Se usa para medir la detección y **no se publica
junto con la serie**.
