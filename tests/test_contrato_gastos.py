"""Contrato de la tabla Silver gastos (commit AR01).

El gasto de flota es lo que alimenta `gasto_combustible` de `fact_unidad_mes`, y con el
el KPI 4 y la senal S9. De las tres hojas de gasto de la entrega solo `OTROS GASTOS`
tiene encabezado; las otras dos empiezan en datos y esperan lectura por posicion.

Lo que estas pruebas cuidan, en orden de importancia:

1. Que **ninguna columna del contrato ni de su DDL nombre a una persona**.
2. Que el contrato **no afirme que tiene una placa** cuando no la tiene: la columna
   `PLACA` de `OTROS GASTOS` no trae placas (medido en
   `docs/evidencias/gastos_posiciones.md`), asi que va a `unidad_codigo`, no a
   `placa_norm`.
3. Que lo no cubierto este declarado con su motivo y con la evidencia que lo sostiene.

Lo que **no** se prueba aqui, y por que: que la hoja pase por el pipeline. `procesar`
despacha por tabla a `transformar.TRANSFORMACIONES`, y `gastos` todavia no esta ahi
porque `src/silver/` es de ingenieria de datos. Hay una prueba que deja ese estado
escrito en vez de suponerlo.
"""
from pathlib import Path

from src.silver import contratos

EVIDENCIA = Path(__file__).resolve().parents[1] / "docs" / "evidencias" / "gastos_posiciones.md"


# --- El contrato ---------------------------------------------------------------
def test_el_contrato_declara_la_tabla_y_su_grano():
    c = contratos.cargar()["gastos"]
    assert c.dominio == "gastos" and c.grano == "linea de gasto"
    assert c.llave == ("origen", "fila")
    assert "LOCATION '${LAKE}/silver/gastos/gastos/'" in c.ddl()


def test_declara_lo_que_fact_unidad_mes_necesita():
    """El W07 agrega por placa, anio y mes el monto de los gastos de combustible."""
    nombres = contratos.cargar()["gastos"].nombres()
    for columna in ("placa_norm", "anio", "mes", "monto_soles", "es_combustible"):
        assert columna in nombres, columna


def test_ninguna_columna_nombra_a_una_persona():
    c = contratos.cargar()["gastos"]
    for col in c.columnas:
        assert col.personal is False, f"{col.nombre} quedaria como dato personal"
    # El proveedor es una razon social, no una persona natural; el RUC no se declara.
    assert "ruc" not in c.nombres() and "documento" not in c.nombres()


# --- El hallazgo que cambia el mapeo previsto ----------------------------------
def test_la_columna_placa_de_otros_gastos_no_se_mapea_a_placa_norm():
    """Medido: 0 % de sus valores tiene forma de placa y ninguno coincide con la flota."""
    fuente = next(f for f in contratos.cargar()["gastos"].fuentes
                  if f.id == "otros_gastos_2020")
    destinos = dict(fuente.columnas)
    assert "placa_norm" not in destinos.values()
    assert any(d == "unidad_codigo" for d in destinos.values())


def test_la_evidencia_de_las_posiciones_existe_y_el_contrato_la_cita():
    """Sin ese documento, «no cubierta» seria una afirmacion sin respaldo."""
    assert EVIDENCIA.exists()
    texto = EVIDENCIA.read_text(encoding="utf-8")
    for pieza in ("GASTOS FLOTA", "CO01", "| **E** |", "15.6 %", "combustible"):
        assert pieza in texto, pieza
    crudo = (contratos.DIR_CONTRATOS / "gastos.yaml").read_text(encoding="utf-8")
    assert "gastos_posiciones.md" in crudo


def test_lo_no_cubierto_esta_declarado_con_su_motivo():
    crudo = (contratos.DIR_CONTRATOS / "gastos.yaml").read_text(encoding="utf-8")
    for pieza in ("GASTOS FLOTA", "CO01", "no cubierta", "GASTOS FLOTA 2020"):
        assert pieza in crudo, pieza


# --- Lo que todavia no puede correr, y por que ---------------------------------
def test_la_tabla_tiene_su_transformacion():
    """`procesar` despacha por tabla a `transformar.TRANSFORMACIONES`."""
    from src.silver.transformar import TRANSFORMACIONES      # noqa: PLC0415

    assert "gastos" in TRANSFORMACIONES


def test_las_tres_hojas_de_gasto_estan_declaradas():
    """La que tiene encabezado, por nombre; las dos que empiezan en datos, por posicion."""
    c = contratos.cargar()["gastos"]
    por_id = {f.id: f for f in c.fuentes}
    assert set(por_id) == {"otros_gastos_2020", "gastos_flota_2020", "gastos_proyecto_2019"}

    assert por_id["otros_gastos_2020"].fila_encabezado == 1
    assert not por_id["otros_gastos_2020"].por_posicion

    flota = por_id["gastos_flota_2020"]
    assert flota.por_posicion and flota.primera_fila == 3
    # La C es la placa y la E la categoria: de ahi sale es_combustible (evidencia, seccion 1).
    assert flota.posiciones["placa_norm"] == 2
    assert flota.posiciones["categoria"] == 4

    co01 = por_id["gastos_proyecto_2019"]
    assert co01.por_posicion and "placa_norm" not in co01.posiciones   # no tiene placa


def test_el_ddl_versionado_es_el_del_contrato():
    c = contratos.cargar()["gastos"]
    versionado = (contratos.config.RAIZ_REPO / "sql" / "athena" / "ddl" /
                  "silver_gastos.sql").read_text(encoding="utf-8")
    assert versionado == c.ddl()


def test_ninguna_columna_del_ddl_nombra_a_una_persona():
    """Lo que pide el AR01: del contrato al DDL, ninguna COLUMNA nombra a una persona.

    Se miran los nombres de columna, no los comentarios: el comentario del proveedor
    explica justamente que el RUC no se publica aunque venga pegado al nombre, y esa
    frase no es una fuga.
    """
    import re                                                # noqa: PLC0415

    ddl = contratos.cargar()["gastos"].ddl()
    columnas = re.findall(r"^  (\w+) ", ddl, re.M)
    assert columnas, "el DDL no declaro ninguna columna"
    for col in columnas:
        for prohibida in ("nombre", "dni", "apellido", "conductor", "vendedor", "ruc"):
            assert prohibida not in col.lower(), f"{col} nombra a una persona"
