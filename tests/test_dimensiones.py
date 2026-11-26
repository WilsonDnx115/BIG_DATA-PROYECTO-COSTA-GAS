"""W08: las seis dimensiones del modelo estrella, sin datos personales."""
from __future__ import annotations

import pytest

from src.common import config
from src.glue import dimensiones as dim
from src.glue import senales_spark

PROHIBIDAS = ("nombre", "documento", "dni", "ruc", "razon", "apellido", "conductor", "vendedor")

ESQUEMA_UNIDADES = ("placa_norm string, empresa string, clase string, uso string, "
                    "marca string, capacidad_glp_kg double, traslada_gas boolean")
ESQUEMA_COMPRAS = "placa_norm string, conductor_hash string"
ESQUEMA_VENTAS = ("placa_norm string, vendedor_hash string, articulo_codigo string, "
                  "articulo string, es_glp boolean")
ESQUEMA_MAESTRO = ("documento_hash string, clase_documento string, ruc string, "
                   "ruc_valido boolean, capacidad_kg double, canal string")

UNIDADES = [
    ("T1A111", "COSTA GAS", "CISTERNA", "TRANSPORTE DE GLP", "VOLVO", 10000.0, True),
    ("R2B222", "COSTA GAS", "CAMION", "REPARTO", "HINO", 3000.0, False),
]
COMPRAS = [("T1A111", "hash-conductor-1"), ("T1A111", None)]
VENTAS = [
    ("R2B222", "hash-vendedor-1", "BL10", "GLP ENVASE DE 10 KLG", True),
    ("R2B222", "hash-vendedor-1", "GRA", "GLP A GRANEL", True),
    ("X9Z999", "hash-vendedor-2", "ARZ", "ARROZ 5 KG", False),
]
MAESTRO = [("hash-doc-1", "RUC", "20123456789", True, 5000.0, "MAYORISTA")]


def test_cada_dimension_declara_su_llave():
    assert set(dim.LLAVES) == {"dim_tiempo", "dim_unidad", "dim_persona",
                               "dim_producto", "dim_contraparte", "dim_senal"}
    assert dim.LLAVES["dim_persona"] == ["persona_hash", "tipo"]


def test_dim_senal_cubre_el_catalogo_de_frank():
    assert len(senales_spark.CATALOGO) == 12
    assert set(senales_spark.CATALOGO) >= {"S1", "S12"}


@pytest.fixture()
def fuentes(spark):
    return {
        "unidades": spark.createDataFrame(UNIDADES, ESQUEMA_UNIDADES),
        "compras": spark.createDataFrame(COMPRAS, ESQUEMA_COMPRAS),
        "ventas": spark.createDataFrame(VENTAS, ESQUEMA_VENTAS),
        "maestro": spark.createDataFrame(MAESTRO, ESQUEMA_MAESTRO),
    }


def test_dim_persona_no_tiene_nombre_ni_documento(spark, fuentes):
    d = dim.dim_persona(fuentes["compras"], fuentes["ventas"])

    assert d.columns == ["persona_hash", "tipo"]
    assert not [c for c in d.columns for p in PROHIBIDAS if p in c.lower()]
    tipos = {(f.persona_hash, f.tipo) for f in d.take(10)}
    assert tipos == {("hash-conductor-1", "conductor"), ("hash-vendedor-1", "vendedor"),
                     ("hash-vendedor-2", "vendedor")}


def test_ninguna_dimension_publica_datos_personales(spark, fuentes):
    for tabla, d in dim.construir(spark, fuentes).items():
        malas = [c for c in d.columns for p in PROHIBIDAS if p in c.lower()]
        assert not malas, f"{tabla} expone {malas}"


def test_dim_contraparte_guarda_el_ruc_valido_no_el_ruc(spark, fuentes):
    d = dim.dim_contraparte(fuentes["maestro"])

    assert "ruc" not in d.columns
    assert "ruc_valido" in d.columns
    assert d.take(1)[0]["tipo"] == "RUC"


def test_dim_tiempo_es_generada_y_marca_2020(spark):
    d = dim.dim_tiempo(spark)

    anios = config.ANIO_FIN - config.ANIO_INI + 1
    assert d.count() == anios * 12
    primera = d.take(1)[0]
    assert primera["id_tiempo"] == config.ANIO_INI * 100 + 1
    assert primera["trimestre"] == 1
    pandemia = d.filter("pandemia_2020").take(13)
    assert len(pandemia) == 12
    assert {f.anio for f in pandemia} == {config.ANIO_PILOTO}


def test_dim_unidad_marca_la_placa_que_no_esta_en_el_maestro(spark, fuentes):
    d = {f.placa_norm: f for f in dim.dim_unidad(fuentes["unidades"], fuentes["compras"],
                                                 fuentes["ventas"]).take(10)}

    assert d["T1A111"].rol == "transporte"
    assert d["T1A111"].habilitada_glp is True
    assert d["T1A111"].capacidad_kg == 10000.0
    assert d["R2B222"].rol == "reparto"
    assert d["T1A111"].presente_en_maestro is True
    assert d["X9Z999"].presente_en_maestro is False      # vista en ventas, no en el maestro


def test_dim_producto_separa_envasado_de_granel(spark, fuentes):
    d = {f.articulo_codigo: f for f in dim.dim_producto(fuentes["ventas"]).take(10)}

    assert set(d) == {"BL10", "GRA"}                     # el arroz no entra
    assert (d["BL10"].producto, d["BL10"].presentacion_kg) == ("GLP-E", 10.0)
    assert (d["GRA"].producto, d["GRA"].presentacion_kg) == ("GLP-G", None)
    assert d["BL10"].marca is None                       # sin fuente: nula, no inventada


def test_dim_senal_trae_las_doce_senales(spark):
    d = dim.dim_senal(spark)

    assert d.count() == 12
    assert d.columns == ["id_senal", "descripcion", "grado_evidencia"]
    primera = d.take(1)[0]
    assert primera["id_senal"] == "S1"
    assert primera["grado_evidencia"] == "indicio"


def test_construir_y_escribir_deja_las_seis_en_iceberg(spark_iceberg, fuentes_iceberg):
    escritas = dim.construir_y_escribir(spark_iceberg, fuentes_iceberg, base="pruebas")

    assert len(escritas) == 6
    # Idempotencia: una segunda corrida no duplica filas.
    antes = spark_iceberg.table("glue_catalog.pruebas.dim_senal").count()
    dim.construir_y_escribir(spark_iceberg, fuentes_iceberg, base="pruebas")
    assert spark_iceberg.table("glue_catalog.pruebas.dim_senal").count() == antes


@pytest.fixture()
def fuentes_iceberg(spark_iceberg):
    return {
        "unidades": spark_iceberg.createDataFrame(UNIDADES, ESQUEMA_UNIDADES),
        "compras": spark_iceberg.createDataFrame(COMPRAS, ESQUEMA_COMPRAS),
        "ventas": spark_iceberg.createDataFrame(VENTAS, ESQUEMA_VENTAS),
        "maestro": spark_iceberg.createDataFrame(MAESTRO, ESQUEMA_MAESTRO),
    }
