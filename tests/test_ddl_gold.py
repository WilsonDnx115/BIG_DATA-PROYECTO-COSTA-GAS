"""W09: los DDL de Gold en Iceberg.

Estas pruebas no hablan con Athena. Lo que comprueban es que el DDL versionado
diga lo mismo que el codigo que escribe la tabla: si alguien agrega una columna
en `balance.py` y no la agrega aqui, el `MERGE INTO` de Iceberg falla en la
corrida, no en la revision. Por eso el contraste es contra las constantes del
productor y contra las vistas de F06 que leen de estas tablas, no contra una
lista escrita a mano.

Faltan dos tablas de la lista del paquete y es a proposito:

* `fact_unidad_mes` es el W07 y espera `contracts/gastos.yaml` (A06). De sus
  columnas solo se conocen las seis que consume `v_semaforo_unidades`.
* `fact_operacion` es el W18 y todavia no tiene columnas en ninguna parte.

No se declaran tablas cuyo esquema no este definido: un DDL inventado es peor
que un DDL ausente, porque parece acordado.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from sql.athena import crear_tablas
from src.glue import balance, dimensiones

DIR_DDL = Path(crear_tablas.DIR) / "ddl"
ARCHIVOS = sorted(DIR_DDL.glob("gold_*.sql"))

# Columnas que nunca pueden aparecer en claro en Gold (CLAUDE.md, privacidad).
PROHIBIDAS = ("nombre", "documento", "dni", "ruc", "razon", "apellido", "conductor", "vendedor")
SEGURAS = ("_hash", "_valido")

_RE_COLUMNA = re.compile(r"^\s{2}([a-z_0-9]+)\s+([a-z<>,\s]+?)(?:\s+COMMENT|,|\)|$)")
_RE_PARTICION = re.compile(r"^PARTITIONED BY \((.+)\)\s*$", re.MULTILINE)


def _texto(archivo: Path) -> str:
    return archivo.read_text(encoding="utf-8")


def columnas_tipadas(archivo: Path) -> list[tuple[str, str]]:
    """(nombre, tipo) de cada columna del DDL, en orden."""
    return [(m.group(1), m.group(2).strip()) for linea in _texto(archivo).splitlines()
            if (m := _RE_COLUMNA.match(linea))]


def columnas(archivo: Path) -> list[str]:
    """Nombres de columna del DDL, en orden."""
    return [n for n, _ in columnas_tipadas(archivo)]


def particiones(archivo: Path) -> list[str]:
    m = _RE_PARTICION.search(_texto(archivo))
    return [c.strip() for c in m.group(1).split(",")] if m else []


def ddl(tabla: str) -> Path:
    return DIR_DDL / f"gold_{tabla}.sql"


def test_hay_un_ddl_por_tabla_declarada():
    # 15 desde que W07 agrego gold_fact_unidad_mes.sql (PR #32).
    assert len(ARCHIVOS) == 15, [a.name for a in ARCHIVOS]


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda a: a.stem)
def test_cada_ddl_es_iceberg_con_retencion_de_instantaneas(archivo):
    """Sin `vacuum_max_snapshot_age_seconds` las instantaneas crecen sin limite."""
    sql = _texto(archivo)

    assert "'table_type'='ICEBERG'" in sql
    assert "'vacuum_max_snapshot_age_seconds'='604800'" in sql      # 7 dias
    assert "CREATE TABLE IF NOT EXISTS" in sql


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda a: a.stem)
def test_nunca_se_particiona_por_placa_ruc_ni_documento(archivo):
    """La regla del proyecto: solo `anio` y `mes` particionan un hecho."""
    assert set(particiones(archivo)) <= {"anio", "mes"}


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda a: a.stem)
def test_ninguna_columna_publica_un_identificador_en_claro(archivo):
    """Solo las de texto pueden llevar el valor.

    `documento_presente` es una tasa de completitud de `calidad_silver`: un
    double no guarda un DNI. Lo que no puede existir es una columna `string`
    con el nombre, el documento o la razon social.
    """
    filtradas = [n for n, tipo in columnas_tipadas(archivo)
                 if tipo == "string" and not n.endswith(SEGURAS)
                 and any(p in n for p in PROHIBIDAS)]

    assert filtradas == []


@pytest.mark.parametrize("archivo", ARCHIVOS, ids=lambda a: a.stem)
def test_el_nombre_del_archivo_y_la_tabla_y_la_ubicacion_coinciden(archivo):
    tabla = archivo.stem.removeprefix("gold_")
    sql = _texto(archivo)

    assert f"costagas_gold.{tabla} (" in sql
    assert f"LOCATION '${{LAKE}}/gold/{tabla}/'" in sql


def test_crear_tablas_los_ejecuta_despues_de_silver():
    """El orden importa: Gold se crea despues de Silver y antes de las vistas."""
    todos = [f.name for f in crear_tablas.archivos_a_ejecutar()]
    solo_gold = [f.name for f in crear_tablas.archivos_a_ejecutar(solo="gold")]

    assert solo_gold == [a.name for a in ARCHIVOS]
    primer_gold = min(todos.index(n) for n in solo_gold)
    assert all(todos.index(n) < primer_gold for n in todos if n.startswith("silver_"))


# --- el DDL dice lo mismo que el codigo que escribe la tabla ------------------

def test_el_balance_declara_exactamente_lo_que_escribe_W06():
    assert columnas(ddl("fact_balance_planta")) == list(balance.COLUMNAS)


def test_la_dimension_de_senales_declara_el_esquema_de_W08():
    esperadas = [c.split()[0] for c in dimensiones.ESQUEMA_SENAL.split(", ")]

    assert columnas(ddl("dim_senal")) == esperadas


@pytest.mark.parametrize("tabla,llave", sorted(dimensiones.LLAVES.items()))
def test_cada_dimension_declara_su_llave(tabla, llave):
    assert set(llave) <= set(columnas(ddl(tabla)))


def test_las_seis_dimensiones_tienen_su_ddl():
    assert {f"dim_{n}" for n in ("tiempo", "unidad", "persona", "producto",
                                 "contraparte", "senal")} == set(dimensiones.LLAVES)
    for tabla in dimensiones.LLAVES:
        assert ddl(tabla).exists()


def test_una_dimension_no_se_particiona():
    for tabla in dimensiones.LLAVES:
        assert particiones(ddl(tabla)) == []


def test_los_hechos_por_mes_se_particionan_por_anio_y_mes():
    for tabla in ("fact_balance_planta", "fact_alerta", "mercado_mes", "modelo_factura", "fact_serie",
                  "fact_operacion"):
        assert particiones(ddl(tabla)) == ["anio", "mes"]


# --- el DDL cubre lo que leen las vistas de F06 y lo que escribe el portal ----

VISTAS = Path(crear_tablas.DIR) / "vistas"


def _columnas_leidas(vista: str, alias: str) -> set[str]:
    """Columnas que la vista pide con `alias.columna`."""
    sql = (VISTAS / f"{vista}.sql").read_text(encoding="utf-8")
    return set(re.findall(rf"\b{alias}\.([a-z_0-9]+)", sql))


def test_fact_alerta_tiene_lo_que_pide_la_vista_de_la_bandeja():
    """`v_alerta` de F06 lee `a.<columna>` de fact_alerta, `probabilidad` incluida."""
    pedidas = _columnas_leidas("v_alerta", "a")

    assert pedidas, "la vista v_alerta no se pudo leer"
    assert pedidas <= set(columnas(ddl("fact_alerta")))


def test_revision_alerta_tiene_lo_que_inserta_el_portal():
    from src.portal import revision

    sql = revision.sentencia({"id_alerta": "a", "estado": "confirmada", "causa": "digitacion",
                              "nivel_evidencia": 3, "nota": None, "revisor_hash": "h",
                              "revisado_en": "2026-01-01T00:00:00Z"})
    insertadas = re.search(r"\(([^)]+)\) VALUES", sql).group(1)
    insertadas = {c.strip() for c in insertadas.split(",")}

    assert insertadas <= set(columnas(ddl("revision_alerta")))


def test_el_kpi_1_encuentra_sus_columnas_en_el_balance():
    sql = (VISTAS / "v_kpi_1.sql").read_text(encoding="utf-8")
    declaradas = set(columnas(ddl("fact_balance_planta")))

    for columna in ("kg_comprados", "kg_vendidos", "delta_stock_kg", "merma_tecnica_kg",
                    "merma_es_supuesto", "mes_completo"):
        assert columna in sql and columna in declaradas


def test_modelo_factura_fact_serie_y_operacion_declaran_lo_que_escriben():
    """FR05, FR07 y FR14: el DDL es el esquema de lo que escribe cada productor, en su orden."""
    from src.glue import fact_serie, modelo_factura, operacion

    for tabla, productor in (("modelo_factura", modelo_factura.COLUMNAS), ("fact_serie", fact_serie.COLUMNAS),
                             ("fact_operacion", operacion.COLUMNAS)):
        assert sorted(columnas(ddl(tabla))) == sorted(productor), tabla
