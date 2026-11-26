"""W01: el orden de ejecucion de los DDL y las vistas de Athena (3.5)."""
from __future__ import annotations

import pytest

from sql.athena import crear_tablas


@pytest.fixture()
def arbol(tmp_path):
    """Un archivo de cada grupo, dos del mismo grupo y un DDL antiguo."""
    (tmp_path / "ddl").mkdir()
    (tmp_path / "vistas").mkdir()
    nombres = [
        "ddl/silver_ventas_detalle.sql",
        "ddl/silver_compras_glp.sql",
        "ddl/gold_fact_balance_planta.sql",
        "vistas/v_kpi_1.sql",
        "ddl/01_silver_movimientos.sql",   # antiguo: no corresponde al informe
        "ddl/02_gold_fact_conciliacion_unidad.sql",  # antiguo
    ]
    for n in nombres:
        (tmp_path / n).write_text("-- sql de prueba\nSELECT 1;\n", encoding="utf-8")
    return tmp_path


def test_orden_silver_gold_vistas(arbol):
    assert [f.name for f in crear_tablas.archivos_a_ejecutar(arbol)] == [
        "silver_compras_glp.sql",
        "silver_ventas_detalle.sql",
        "gold_fact_balance_planta.sql",
        "v_kpi_1.sql",
    ]


def test_excluye_los_ddl_antiguos(arbol):
    nombres = [f.name for f in crear_tablas.archivos_a_ejecutar(arbol)]
    assert not [n for n in nombres if n[0].isdigit()]


def test_solo_un_grupo(arbol):
    assert [f.name for f in crear_tablas.archivos_a_ejecutar(arbol, "gold")] == [
        "gold_fact_balance_planta.sql"
    ]
    assert [f.name for f in crear_tablas.archivos_a_ejecutar(arbol, "vistas")] == ["v_kpi_1.sql"]


def test_grupo_desconocido(arbol):
    with pytest.raises(ValueError):
        crear_tablas.archivos_a_ejecutar(arbol, "kpis")


def test_sin_carpeta_de_vistas(tmp_path):
    """Mientras F06 no entregue las vistas, la carpeta no existe y no debe fallar."""
    (tmp_path / "ddl").mkdir()
    (tmp_path / "ddl" / "silver_scop.sql").write_text("SELECT 1;\n", encoding="utf-8")
    assert [f.name for f in crear_tablas.archivos_a_ejecutar(tmp_path)] == ["silver_scop.sql"]


def test_repositorio_sin_ddl_antiguos():
    """En el repositorio real solo quedan los DDL con la convencion vigente."""
    for f in (crear_tablas.DIR / "ddl").glob("*.sql"):
        assert f.name.startswith(("silver_", "gold_")), f.name
    assert not (crear_tablas.DIR / "kpis").exists()
