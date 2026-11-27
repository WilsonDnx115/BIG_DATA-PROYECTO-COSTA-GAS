"""Integridad referencial del modelo estrella de Gold (commit AR05).

Lo que comprueba: **ninguna fila de un hecho apunta a una clave que su dimension no
tiene**. Un hecho huerfano no rompe ninguna consulta: simplemente desaparece del
tablero cuando alguien hace el join, y nadie se entera de que faltan kilos.

Como se comprueba: con un `left_anti` de cada hecho contra cada dimension, que devuelve
exactamente las filas del hecho que **no** encuentran pareja. Debe dar 0. Cuando no da
0, la prueba imprime las filas con `take()`, porque «hay 3 huerfanos» no sirve para
arreglar nada y «el huerfano es la placa X9Z999» si.

Las dimensiones y los hechos son los de los DDL de `sql/athena/ddl/gold_*.sql` (W09) y
las llaves, las que declara `dimensiones.LLAVES`.

Nota sobre los nulos: una alerta de planta-mes no tiene unidad, y su `unidad_id` es nulo
a proposito. Un nulo **no es** una referencia rota, asi que se excluye del cruce; lo que
no puede haber es una placa que exista en el hecho y no en la dimension.
"""
from __future__ import annotations

import pytest

from src.glue import dimensiones as dim

# --- Datos: una flota minima y los hechos que la referencian -------------------
ESQUEMA_UNIDADES = ("placa_norm string, empresa string, clase string, uso string, "
                    "marca string, capacidad_glp_kg double, traslada_gas boolean")
ESQUEMA_VENTAS = ("placa_norm string, vendedor_hash string, articulo_codigo string, "
                  "articulo string, es_glp boolean")
ESQUEMA_COMPRAS = "placa_norm string, conductor_hash string"

UNIDADES = [
    ("T1A111", "COSTA GAS", "CISTERNA", "TRANSPORTE DE GLP", "VOLVO", 10000.0, True),
    ("R2B222", "COSTA GAS", "CAMION", "REPARTO", "HINO", 3000.0, False),
]
COMPRAS = [("T1A111", "hash-conductor-1")]
VENTAS = [("R2B222", "hash-vendedor-1", "BL10", "GLP ENVASE DE 10 KLG", True)]

ANIO, MES = 2020, 5

ESQUEMA_ALERTA = ("id_alerta string, senal string, unidad_id string, "
                  "anio int, mes int")
ALERTAS = [
    ("a1", "S9", "T1A111", ANIO, MES),
    ("a2", "S2", "R2B222", ANIO, MES),
    ("a3", "S11", None, ANIO, MES),          # planta-mes: sin unidad, y esta bien
]

ESQUEMA_UNIDAD_MES = "unidad_id string, rol string, anio int, mes int, kg_vendidos double"
UNIDAD_MES = [("T1A111", "transporte", ANIO, MES, 12000.0),
              ("R2B222", "reparto", ANIO, MES, 8000.0)]

ESQUEMA_SERIE = "entidad_id string, entidad_tipo string, granularidad string, periodo string"
SERIE = [("T1A111", "unidad", "mes", "2020-05"), ("R2B222", "unidad", "mes", "2020-05")]

ESQUEMA_FACTURA = "factura_id string, unidad_id string, anio int, mes int"
FACTURAS = [("PET-001-1", "T1A111", ANIO, MES), ("PET-001-2", None, ANIO, MES)]


@pytest.fixture(scope="module")
def dimensiones(spark) -> dict:
    unidades = spark.createDataFrame(UNIDADES, ESQUEMA_UNIDADES)
    compras = spark.createDataFrame(COMPRAS, ESQUEMA_COMPRAS)
    ventas = spark.createDataFrame(VENTAS, ESQUEMA_VENTAS)
    return {
        "dim_unidad": dim.dim_unidad(unidades, compras, ventas),
        "dim_tiempo": dim.dim_tiempo(spark),
        "dim_senal": dim.dim_senal(spark),
        "dim_producto": dim.dim_producto(ventas),
    }


@pytest.fixture(scope="module")
def hechos(spark) -> dict:
    return {
        "fact_alerta": spark.createDataFrame(ALERTAS, ESQUEMA_ALERTA),
        "fact_unidad_mes": spark.createDataFrame(UNIDAD_MES, ESQUEMA_UNIDAD_MES),
        "fact_serie": spark.createDataFrame(SERIE, ESQUEMA_SERIE),
        "modelo_factura": spark.createDataFrame(FACTURAS, ESQUEMA_FACTURA),
    }


def huerfanos(hecho, dimension, columnas: list[tuple[str, str]]):
    """Filas del hecho sin pareja en la dimension, cruzando por `columnas`.

    `columnas` son pares (columna del hecho, columna de la dimension). Las filas con
    algun nulo en la clave quedan fuera: un nulo es «no aplica», no una referencia rota.
    """
    izq = hecho
    for col, _ in columnas:
        izq = izq.filter(f"{col} is not null")
    der = dimension
    for col, col_dim in columnas:
        if col != col_dim:
            der = der.withColumnRenamed(col_dim, col)
    # Solo las columnas de la clave: evita que un nombre repetido entre hecho y
    # dimension haga ambigua la condicion del join.
    der = der.select(*[c for c, _ in columnas]).dropDuplicates()
    return izq.join(der, on=[c for c, _ in columnas], how="left_anti")


def _sin_huerfanos(hecho, dimension, columnas, etiqueta: str):
    rotas = huerfanos(hecho, dimension, columnas)
    cuantas = rotas.count()
    assert cuantas == 0, f"{etiqueta}: {cuantas} fila(s) sin pareja -> {rotas.take(5)}"


# --- Cada hecho contra cada dimension que referencia ---------------------------
def test_fact_alerta_contra_dim_unidad(hechos, dimensiones):
    _sin_huerfanos(hechos["fact_alerta"], dimensiones["dim_unidad"],
                   [("unidad_id", "placa_norm")], "fact_alerta -> dim_unidad")


def test_fact_alerta_contra_dim_senal(hechos, dimensiones):
    _sin_huerfanos(hechos["fact_alerta"], dimensiones["dim_senal"],
                   [("senal", "id_senal")], "fact_alerta -> dim_senal")


def test_fact_alerta_contra_dim_tiempo(hechos, dimensiones):
    _sin_huerfanos(hechos["fact_alerta"], dimensiones["dim_tiempo"],
                   [("anio", "anio"), ("mes", "mes")], "fact_alerta -> dim_tiempo")


def test_fact_unidad_mes_contra_dim_unidad(hechos, dimensiones):
    _sin_huerfanos(hechos["fact_unidad_mes"], dimensiones["dim_unidad"],
                   [("unidad_id", "placa_norm")], "fact_unidad_mes -> dim_unidad")


def test_fact_unidad_mes_contra_dim_tiempo(hechos, dimensiones):
    _sin_huerfanos(hechos["fact_unidad_mes"], dimensiones["dim_tiempo"],
                   [("anio", "anio"), ("mes", "mes")], "fact_unidad_mes -> dim_tiempo")


def test_fact_serie_contra_dim_unidad(hechos, dimensiones):
    """`fact_serie` identifica la entidad con la placa, con otro nombre de columna."""
    solo_unidades = hechos["fact_serie"].filter("entidad_tipo = 'unidad'")
    _sin_huerfanos(solo_unidades, dimensiones["dim_unidad"],
                   [("entidad_id", "placa_norm")], "fact_serie -> dim_unidad")


def test_modelo_factura_contra_dim_unidad(hechos, dimensiones):
    _sin_huerfanos(hechos["modelo_factura"], dimensiones["dim_unidad"],
                   [("unidad_id", "placa_norm")], "modelo_factura -> dim_unidad")


def test_modelo_factura_contra_dim_tiempo(hechos, dimensiones):
    _sin_huerfanos(hechos["modelo_factura"], dimensiones["dim_tiempo"],
                   [("anio", "anio"), ("mes", "mes")], "modelo_factura -> dim_tiempo")


# --- Que la prueba sepa fallar --------------------------------------------------
def test_una_placa_que_no_esta_en_la_dimension_se_detecta(spark, dimensiones):
    """Sin esto, la prueba podria estar cruzando mal y pasar siempre."""
    con_huerfana = spark.createDataFrame(
        [*ALERTAS, ("a4", "S9", "X9Z999", ANIO, MES)], ESQUEMA_ALERTA)
    rotas = huerfanos(con_huerfana, dimensiones["dim_unidad"], [("unidad_id", "placa_norm")])
    assert rotas.count() == 1
    assert rotas.take(1)[0]["unidad_id"] == "X9Z999"


def test_un_mes_fuera_de_la_ventana_se_detecta(spark, dimensiones):
    fuera = spark.createDataFrame([("a5", "S9", "T1A111", 1999, 13)], ESQUEMA_ALERTA)
    rotas = huerfanos(fuera, dimensiones["dim_tiempo"],
                      [("anio", "anio"), ("mes", "mes")])
    assert rotas.count() == 1


def test_un_nulo_no_cuenta_como_referencia_rota(spark, dimensiones):
    """La alerta de planta-mes no tiene unidad: eso no es una referencia rota."""
    solo_nula = spark.createDataFrame([("a3", "S11", None, ANIO, MES)], ESQUEMA_ALERTA)
    assert huerfanos(solo_nula, dimensiones["dim_unidad"],
                     [("unidad_id", "placa_norm")]).count() == 0


# --- El mapa de llaves no se inventa --------------------------------------------
def test_las_llaves_son_las_que_declara_dimensiones():
    assert dim.LLAVES["dim_unidad"] == ["placa_norm"]
    assert dim.LLAVES["dim_senal"] == ["id_senal"]
    assert set(dim.LLAVES) == {"dim_tiempo", "dim_unidad", "dim_persona",
                               "dim_producto", "dim_contraparte", "dim_senal"}


def test_cada_dimension_cruzada_tiene_su_ddl_en_gold():
    from src.common import config                                  # noqa: PLC0415

    ddl = config.RAIZ_REPO / "sql" / "athena" / "ddl"
    for tabla in ("dim_unidad", "dim_tiempo", "dim_senal", "dim_producto",
                  "fact_alerta", "fact_balance_planta", "fact_serie", "modelo_factura"):
        assert (ddl / f"gold_{tabla}.sql").exists(), tabla
