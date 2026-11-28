"""Las páginas del tablero cumplen las reglas del propio repositorio.

No se conecta a Grafana ni a Athena: lee los JSON de `dashboards/grafana/` y los amarra a lo
que ya existe aquí, para que un cambio en un lado se note en el otro.

* las columnas que la página pide a cada vista existen en `sql/athena/vistas/<vista>.sql`;
* toda consulta a un hecho filtra por `anio` (regla de costo del README del tablero);
* una sola consulta por página y refresco (ADR 0016): los demás paneles la reutilizan;
* las variables son las de `_variables.json`, sin copias divergentes;
* ninguna página pide una columna de persona natural.
"""
import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
DIR = RAIZ / "dashboards" / "grafana"
DIR_VISTAS = RAIZ / "sql" / "athena" / "vistas"

PAGINAS = ("01_resumen", "02_balance_unidades", "03_bandeja", "05_semaforo")

# Columnas que nunca pueden salir en un tablero (CLAUDE.md, «Datos y privacidad»).
PROHIBIDAS = ("razon_social", "nombre_hash", "documento_hash", "ruc", "dni", "conductor",
              "direccion")


def pagina(nombre: str) -> dict:
    return json.loads((DIR / f"{nombre}.json").read_text(encoding="utf-8"))


def paneles(doc: dict) -> list[dict]:
    salida = []
    for p in doc["panels"]:
        salida.append(p)
        salida.extend(p.get("panels", []))
    return salida


def consultas(doc: dict) -> list[str]:
    return [t["rawSQL"] for p in paneles(doc) for t in p.get("targets", []) if "rawSQL" in t]


def sin_comentarios(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def columnas_de_la_vista(vista: str) -> set[str]:
    """Todo identificador que aparece en el SQL de la vista: alias, columnas y tablas.

    Es deliberadamente amplio. Sirve para cazar el error que de verdad ocurre —pedirle a una
    vista una columna que no existe o que se renombró— sin reimplementar un analizador de SQL.
    """
    cuerpo = sin_comentarios((DIR_VISTAS / f"{vista}.sql").read_text(encoding="utf-8"))
    return {c.lower() for c in re.findall(r"\b\w+\b", cuerpo)}


@pytest.mark.parametrize("nombre", PAGINAS)
def test_el_json_es_valido_y_tiene_uid_propio(nombre):
    doc = pagina(nombre)
    assert doc["uid"].startswith("costagas-")
    assert doc["title"].startswith("Costa Gas")
    assert doc["refresh"] == "5m", "el refresco de 5 min es la regla de costo del ADR 0016"


def test_los_uid_no_se_repiten():
    uids = [pagina(n)["uid"] for n in PAGINAS]
    assert len(set(uids)) == len(uids)


@pytest.mark.parametrize("nombre", PAGINAS)
def test_una_sola_consulta_por_pagina(nombre):
    """ADR 0016: una consulta por refresco; los demás paneles comparten su resultado."""
    doc = pagina(nombre)
    assert len(consultas(doc)) == 1

    reusan = [t for p in paneles(doc) for t in p.get("targets", []) if "panelId" in t]
    for t in reusan:
        assert t["datasource"]["uid"] == "-- Dashboard --"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_las_variables_comunes_no_divergen(nombre):
    """Cada página trae las cinco variables comunes tal cual; puede añadir las suyas después."""
    comunes = json.loads((DIR / "_variables.json").read_text(encoding="utf-8"))["templating"]["list"]
    propias = pagina(nombre)["templating"]["list"]

    assert propias[:len(comunes)] == comunes
    extra = {v["name"] for v in propias[len(comunes):]}
    assert not extra & {v["name"] for v in comunes}, "una variable común redefinida en la página"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_toda_consulta_a_un_hecho_filtra_por_anio(nombre):
    """Regla de costo: los hechos están particionados por anio/mes y Athena debe podarlos."""
    for sql in consultas(pagina(nombre)):
        cuerpo = sin_comentarios(sql)
        for bloque in re.findall(r"FROM costagas_gold\.(v_\w+|fact_\w+)(.*?)(?=FROM costagas_gold\.|$)",
                                 cuerpo, re.S):
            vista, resto = bloque
            if vista in ("v_semaforo_unidades",):
                continue          # no tiene anio: ya trae el periodo más reciente de cada unidad
            assert "anio" in resto, f"{vista} sin filtro de anio en {nombre}"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_las_columnas_existen_en_la_vista(nombre):
    """Lo que la página agrega de cada vista tiene que existir en esa vista."""
    for sql in consultas(pagina(nombre)):
        cuerpo = sin_comentarios(sql)
        # En SQL la lista de columnas va ANTES de su FROM: se empareja cada SELECT con su tabla.
        for seleccion, vista in re.findall(r"SELECT(.*?)FROM costagas_gold\.(\w+)", cuerpo, re.S):
            if not (DIR_VISTAS / f"{vista}.sql").exists():
                continue                      # dim_tiempo y los hechos tienen su DDL, no una vista
            disponibles = columnas_de_la_vista(vista)
            pedidas = {c.lower() for c in re.findall(r"\b(?:SUM|MAX|MIN)\((\w+)\)", seleccion)}
            faltan = {c for c in pedidas if c not in disponibles}
            assert not faltan, f"{nombre} pide a {vista} columnas que no expone: {sorted(faltan)}"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_ninguna_pagina_pide_datos_de_persona(nombre):
    """Se mira el SQL sin comentarios: un comentario puede nombrar lo que no se publica."""
    for sql in consultas(pagina(nombre)):
        palabras = {c.lower() for c in re.findall(r"\b\w+\b", sin_comentarios(sql))}
        pedidas = palabras & set(PROHIBIDAS)
        assert not pedidas, f"{nombre} consulta columnas de persona: {sorted(pedidas)}"


def test_el_readme_lista_cada_pagina():
    readme = (DIR / "README.md").read_text(encoding="utf-8")
    for nombre in PAGINAS:
        assert f"{nombre}.json" in readme
