"""Vistas de Athena para KPI, cubo y semáforo (F06).

Las vistas se despliegan con `python -m sql.athena.crear_tablas --solo vistas` (Wilson).
Esta prueba revisa su forma sin conectarse a AWS y las amarra a lo que ya existe en el
repositorio, para que un cambio de nombre en cualquier lado se note aquí:

* `sql/athena/tablero/resumen.sql` (Bruno): qué columnas lee de cada v_kpi_N;
* `src/portal/revision.py` (Wilson): qué columnas inserta en revision_alerta;
* `fact_alerta_base` (schemas.py) y la interfaz `unidad_mes` del WP 0.8 (contratos.py).

COLUMNAS_GOLD es lo que las vistas leen de Gold: los DDL de W09 y las tablas de W06,
W07, W12, F07 y F15 deben tener esas columnas con esos nombres.
"""
import re
from pathlib import Path

import pytest

from src.common import schemas
from src.signals.contratos import ENTRADAS

RAIZ = Path(__file__).resolve().parents[1]
DIR = RAIZ / "sql" / "athena" / "vistas"

VISTAS = ("v_alerta", "v_kpi_1", "v_kpi_2", "v_kpi_3", "v_kpi_4", "v_kpi_5", "v_cubo_unidad",
          "v_semaforo_unidades")


def _columnas_revision() -> list[str]:
    """Columnas del INSERT de src/portal/revision.py, la única función que escribe revision_alerta."""
    fuente = (RAIZ / "src" / "portal" / "revision.py").read_text(encoding="utf-8")
    (lista,) = re.findall(r'"\(([a-z_, ]+)\) "', fuente)
    return [c.strip() for c in lista.split(",")]


COLUMNAS_GOLD = {
    "fact_balance_planta": ["producto", "anio", "mes", "kg_comprados", "kg_vendidos", "delta_stock_kg",
                            "merma_tecnica_kg", "merma_es_supuesto", "kg_no_explicados", "valor_soles",
                            "mes_completo"],
    "fact_unidad_mes": ENTRADAS["unidad_mes"][1] + ["kg_base_rol", "soles_comb_por_t", "z", "puntaje",
                                                     "alerta_base", "estado_puntaje", "senales", "n_senales"],
    "fact_alerta": schemas.CONTRATOS["fact_alerta_base"].columnas() + ["probabilidad"],
    "revision_alerta": _columnas_revision(),
    "modelo_factura": ["anio", "mes", "clase_s12"],
    "fact_serie": ["entidad_tipo", "entidad_id", "granularidad", "periodo", "estado", "periodo_inicio",
                   "kg_acumulados", "soles_acumulados"],
}
TABLAS_PERMITIDAS = set(COLUMNAS_GOLD) | set(VISTAS)


def _sql(nombre: str) -> str:
    return (DIR / f"{nombre}.sql").read_text(encoding="utf-8")


def _sin_comentarios(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def _interfaz_del_tablero() -> dict[str, set[str]]:
    """Columnas que resumen.sql lee de cada v_kpi_N: las de SUM/MAX y los filtros."""
    sql = _sin_comentarios((RAIZ / "sql" / "athena" / "tablero" / "resumen.sql").read_text(encoding="utf-8"))
    interfaz = {}
    for seleccion, vista, resto in re.findall(r"SELECT(.*?)FROM costagas_gold\.(v_kpi_\d)(.*?)GROUP BY", sql, re.S):
        cols = set(re.findall(r"(?:SUM|MAX)\((\w+)\)", seleccion)) | {"anio", "mes"}
        cols |= set(re.findall(r"\b(producto|rol) IN", resto))
        interfaz[vista] = cols
    return interfaz


def test_estan_todas_las_vistas():
    assert sorted(p.stem for p in DIR.glob("*.sql")) == sorted(VISTAS)


@pytest.mark.parametrize("nombre", VISTAS)
def test_crea_la_vista_con_su_nombre(nombre):
    cuerpo = _sin_comentarios(_sql(nombre)).strip()
    assert cuerpo.startswith(f"CREATE OR REPLACE VIEW costagas_gold.{nombre} AS")
    assert not cuerpo.endswith(";")          # Athena ejecuta una sentencia por llamada


@pytest.mark.parametrize("nombre", VISTAS)
def test_solo_lee_tablas_de_gold_declaradas(nombre):
    cuerpo = _sin_comentarios(_sql(nombre))
    leidas = set(re.findall(r"costagas_gold\.(\w+)", cuerpo)) - {nombre}
    assert leidas and leidas <= TABLAS_PERMITIDAS, leidas - TABLAS_PERMITIDAS
    assert "costagas_silver" not in cuerpo   # el tablero solo ve Gold (svc-dashboard)


@pytest.mark.parametrize("nombre", VISTAS)
def test_sin_rutas_ni_umbrales_fijos(nombre):
    cuerpo = _sin_comentarios(_sql(nombre))
    assert "s3://" not in cuerpo and "${" not in cuerpo
    # Los umbrales viven en config.py: ninguna vista fija el 2 % del KPI 1, el 0.5 % de merma ni el z de 3.5.
    for umbral in ("0.02", "0.005", "3.5", "0.05"):
        assert umbral not in cuerpo, umbral


@pytest.mark.parametrize("nombre", VISTAS)
def test_usa_solo_columnas_del_contrato(nombre):
    """Cada columna calificada (alias.columna) existe en la tabla de Gold de ese alias."""
    cuerpo = _sin_comentarios(_sql(nombre))
    alias = {a: t for t, a in re.findall(r"costagas_gold\.(\w+)\s+(?:AS\s+)?([a-z])\b", cuerpo)}
    for a, columna in re.findall(r"\b([a-z])\.(\w+)", cuerpo):
        tabla = alias.get(a)
        if tabla in COLUMNAS_GOLD:
            assert columna in COLUMNAS_GOLD[tabla], f"{nombre}: {tabla}.{columna}"


@pytest.mark.parametrize("vista", ["v_kpi_1", "v_kpi_2", "v_kpi_3", "v_kpi_4", "v_kpi_5"])
def test_entrega_lo_que_lee_el_tablero_de_bruno(vista):
    interfaz = _interfaz_del_tablero()
    assert vista in interfaz, "resumen.sql ya no lee esta vista"
    cuerpo = _sin_comentarios(_sql(vista))
    faltan = {c for c in interfaz[vista] if not re.search(rf"\b{c}\b", cuerpo)}
    assert not faltan, f"{vista} no entrega {faltan}"


def test_el_portal_tiene_todas_las_vistas_de_su_lista():
    """src/portal/kpis.py solo consulta vistas de su lista cerrada; todas deben existir aquí."""
    fuente = (RAIZ / "src" / "portal" / "kpis.py").read_text(encoding="utf-8")
    pedidas = set(re.findall(r'"(v_\w+)"', fuente)) | {f"v_kpi_{n}" for n in range(1, 6)}
    assert pedidas <= set(VISTAS), pedidas - set(VISTAS)


def test_kpi1_expone_bruto_neto_y_supuestos():
    cuerpo = _sin_comentarios(_sql("v_kpi_1"))
    for columna in ("kpi1_bruto", "kpi1_neto", "stock_es_supuesto", "merma_es_supuesto", "merma_tecnica_pct"):
        assert columna in cuerpo


def test_alerta_toma_la_ultima_revision():
    cuerpo = _sin_comentarios(_sql("v_alerta"))
    assert "ORDER BY revisado_en DESC" in cuerpo and "orden = 1" in cuerpo and "'pendiente'" in cuerpo


def test_kpi5_sin_pendientes_ni_indicios():
    cuerpo = _sin_comentarios(_sql("v_kpi_5"))
    assert "IN ('confirmada', 'descartada')" in cuerpo
    assert "grado_evidencia <> 'indicio'" in cuerpo


def test_semaforo_sigue_la_tabla_4_8i():
    cuerpo = _sin_comentarios(_sql("v_semaforo_unidades"))
    for color in ("'rojo'", "'ambar'", "'verde'"):
        assert color in cuerpo
    assert "contains(u.senales, 'S9')" in cuerpo
