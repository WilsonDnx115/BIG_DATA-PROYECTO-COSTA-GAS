"""W21: conteo de GDELT con MapReduce, LDA sobre textos y contexto de mercado."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from src.common import rutas
from src.glue import externos_job as ext

PAISES = ("PE", "PE", "PE", "US")
FECHAS = ("20200115", "20200120", "20200210", "20200115")
CODIGOS = ("14", "14", "19", "14")
ARTICULOS = (3, 5, 2, 9)

ESQUEMA_MINIMO = ("sqldate string, event_root_code string, accion_geo_pais string, "
                  "n_articulos int, tono_promedio double")
EVENTOS = list(zip(FECHAS, CODIGOS, PAISES, ARTICULOS, (-1.0, -3.0, 1.0, 0.5), strict=True))

TEXTOS = [
    ("res-1", "resoluciones", "Resolucion que aprueba el margen comercial del gas "
                              "licuado de petroleo para el envasador regional"),
    ("vid-1", "youtube", "El precio del balon de gas subio en Trujillo segun los "
                         "vecinos del distrito"),
    ("vid-2", "youtube", "Operativo de fiscalizacion a locales de venta de balones "
                         "de gas sin autorizacion"),
]


@pytest.fixture()
def eventos(spark):
    return spark.createDataFrame(EVENTOS, ESQUEMA_MINIMO)


@pytest.fixture()
def textos(spark):
    return spark.createDataFrame(TEXTOS, "origen string, fuente string, texto string")


def test_el_esquema_de_gdelt_declara_los_61_campos():
    """Nunca inferSchema: el export de GDELT no trae encabezado."""
    assert len(ext.CAMPOS_GDELT) == 61
    esquema = ext.esquema_gdelt()
    assert esquema.startswith("global_event_id string")
    assert "n_articulos int" in esquema
    assert esquema.count(",") == 60


def test_ruta_fuente_rechaza_una_fuente_que_no_existe():
    with pytest.raises(ValueError, match="Fuente externa desconocida"):
        ext.ruta_fuente("tiktok")        # fuera del alcance corregido


def test_el_mapeo_deja_fuera_los_eventos_de_otro_pais(spark, eventos):
    pares = ext.mapear_eventos(spark, eventos)

    filas = pares.take(10)
    assert len(filas) == 3                       # la fila de US no entra
    assert {(f.anio, f.mes) for f in filas} == {(2020, 1), (2020, 2)}


def test_el_conteo_coincide_con_el_hecho_a_mano(spark, eventos):
    """Enero 2020: dos eventos 14 y 8 articulos. Febrero: uno 19 y 2 articulos."""
    conteo = {(f.anio, f.mes, f.codigo_evento): f
              for f in ext.contar_eventos(spark, eventos).take(10)}

    assert set(conteo) == {(2020, 1, "14"), (2020, 2, "19")}
    enero = conteo[(2020, 1, "14")]
    assert enero.n_eventos == 2
    assert enero.n_articulos == 8.0
    assert enero.tono_promedio == pytest.approx(-2.0)
    assert conteo[(2020, 2, "19")].n_eventos == 1


def test_los_eventos_se_escriben_particionados_por_anio_y_mes(spark, eventos, lago):
    ext.escribir_eventos(ext.contar_eventos(spark, eventos))

    raiz = Path(rutas.ruta(*ext.DESTINO_MR))
    assert sorted(p.name for p in raiz.glob("anio=*")) == ["anio=2020"]
    assert sorted(p.name for p in (raiz / "anio=2020").glob("mes=*")) == ["mes=1", "mes=2"]
    assert not list(raiz.glob("codigo_evento=*"))   # nunca por codigo de evento


def test_lda_devuelve_k_temas(textos):
    modelo, temas, documentos = ext.temas(textos, k=2)

    assert modelo is not None
    assert temas.count() == 2
    filas = temas.take(2)
    assert {f.tema for f in filas} == {0, 1}
    assert all(f.palabras for f in filas)
    assert "topicDistribution" in documentos.columns


def test_lda_quita_las_palabras_vacias_en_espanol(textos):
    """Ningun tema se describe con palabras de la lista vacia en espanol de MLlib.

    La lista se compara con la de Spark y no con una escrita a mano: la de Spark
    trae las formas acentuadas («segun» no esta, «segun» con tilde si), y una
    lista propia aqui probaria el texto de la prueba, no el pipeline.
    """
    from pyspark.ml.feature import StopWordsRemover

    vacias = set(StopWordsRemover.loadDefaultStopWords("spanish"))
    _, temas, _ = ext.temas(textos, k=2)

    palabras = {p for f in temas.take(2) for p in f.palabras}
    assert not palabras & vacias
    assert "gas" in palabras


def test_lda_no_corre_con_menos_textos_que_temas(textos):
    """Con 3 textos no se estiman 10 temas: antes que un modelo vacio, nada."""
    modelo, temas, documentos = ext.temas(textos, k=10)

    assert (modelo, temas, documentos) == (None, None, None)


def test_el_texto_de_las_resoluciones_sale_de_pdfplumber_en_el_executor(spark, lago):
    """El PDF se lee como binario; la extraccion se inyecta para no depender de pdfplumber."""
    carpeta = Path(rutas.ruta("landing", "externo", "resoluciones", "fecha_carga=2020-05-15"))
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "OS-123-2020.pdf").write_bytes(b"%PDF-1.7 fingido")

    df = ext.texto_de_resoluciones(spark, extractor=lambda b: "margen comercial del gas")

    fila = df.take(1)[0]
    assert fila.fuente == "resoluciones"
    assert fila.texto == "margen comercial del gas"
    assert fila.origen.endswith("OS-123-2020.pdf")


def test_el_texto_de_youtube_junta_titulo_y_descripcion(spark, lago):
    carpeta = Path(rutas.ruta("landing", "externo", "youtube", "fecha_carga=2020-05-15"))
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "precio_glp__2020-05-15.json").write_text(json.dumps({
        "consulta": "precio GLP", "consultado": "2020-05-15",
        "items": [{"title": "Sube el balon", "description": "en Trujillo",
                   "channelTitle": "Canal", "publishedAt": "2020-05-01T00:00:00Z",
                   "video_id": "abc123"}],
    }), encoding="utf-8")

    fila = ext.texto_de_youtube(spark).take(1)[0]

    assert fila.origen == "abc123"
    assert fila.texto == "Sube el balon. en Trujillo"


def test_el_precio_de_la_plaza_sale_de_facilito(spark, lago):
    carpeta = Path(rutas.ruta("landing", "externo", "facilito", "fecha_carga=2020-05-15"))
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "glp_envasado__2020-05-15.json").write_text(json.dumps({
        "producto": "GLP ENVASADO", "departamento": "LA LIBERTAD",
        "consultado": "2020-05-15",
        "registros": [{"establecimiento": "A", "distrito": "TRUJILLO",
                       "producto": "GLP ENVASADO", "precio": 38.0},
                      {"establecimiento": "B", "distrito": "TRUJILLO",
                       "producto": "GLP ENVASADO", "precio": 42.0}],
    }), encoding="utf-8")

    fila = ext.precios_mes(spark).take(1)[0]

    assert (fila.anio, fila.mes) == (2020, 5)
    assert fila.n_establecimientos == 2
    assert 38.0 <= fila.precio_mediano <= 42.0


def test_el_tipo_de_cambio_mensual_sale_del_bcrp(spark, lago):
    carpeta = Path(rutas.ruta("landing", "externo", "bcrp", "fecha_carga=2020-05-15"))
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "serie.json").write_text(json.dumps({"periods": [
        {"name": "14.May.20", "values": ["3.4000"]},
        {"name": "15.May.20", "values": ["3.4200"]},
    ]}), encoding="utf-8")

    fila = ext.tipo_cambio_mes(spark).take(1)[0]

    assert (fila.anio, fila.mes, fila.n_dias_tc) == (2020, 5, 2)
    assert fila.tipo_cambio_promedio == pytest.approx(3.41)


def test_mercado_mes_deja_nulo_lo_que_no_tiene_fuente(spark, eventos):
    """Un mes sin Facilito no es un mes con precio cero."""
    conteo = ext.contar_eventos(spark, eventos)

    filas = {(f.anio, f.mes): f for f in ext.mercado_mes(spark, conteo=conteo).take(10)}

    assert set(filas) == {(2020, 1), (2020, 2)}
    assert filas[(2020, 1)].n_eventos_gdelt == 2
    assert filas[(2020, 1)].precio_mediano_plaza is None
    assert filas[(2020, 1)].tipo_cambio_promedio is None
    assert filas[(2020, 1)].n_temas is None


def test_mercado_mes_sin_ninguna_fuente_no_devuelve_tabla(spark):
    assert ext.mercado_mes(spark) is None


def test_mercado_mes_junta_eventos_precios_y_tipo_de_cambio(spark, eventos):
    conteo = ext.contar_eventos(spark, eventos)
    precios = spark.createDataFrame(
        [(2020, 1, "GLP ENVASADO", 40.0, 2)],
        "anio int, mes int, producto string, precio_mediano double, n_establecimientos long")
    tc = spark.createDataFrame([(2020, 1, 3.41, 20)],
                               "anio int, mes int, tipo_cambio_promedio double, n_dias_tc int")

    fila = {(f.anio, f.mes): f for f in
            ext.mercado_mes(spark, conteo, precios, tc).take(10)}[(2020, 1)]

    assert fila.precio_mediano_plaza == 40.0
    assert fila.tipo_cambio_promedio == pytest.approx(3.41)
    assert fila.n_eventos_gdelt == 2


def test_mercado_mes_se_escribe_con_merge_idempotente(spark_iceberg, eventos):
    df = ext.mercado_mes(spark_iceberg, conteo=ext.contar_eventos(spark_iceberg, eventos))

    tabla = ext.escribir_mercado(spark_iceberg, df, catalogo="glue_catalog")
    antes = spark_iceberg.table(tabla).count()
    ext.escribir_mercado(spark_iceberg, df, catalogo="glue_catalog")

    assert spark_iceberg.table(tabla).count() == antes == 2


def test_leer_gdelt_lee_los_bloques_gzip_con_el_esquema_declarado(spark, lago):
    """El bloque que dejo W20: 61 campos separados por tabulador, sin encabezado."""
    carpeta = Path(rutas.ruta("landing", "externo", "gdelt",
                              "fecha_carga=2020-01-01", "anio=2020"))
    carpeta.mkdir(parents=True, exist_ok=True)
    fila = [""] * 61
    fila[1], fila[28], fila[33], fila[34], fila[53] = "20200115", "14", "3", "-1.5", "PE"
    (carpeta / "export-0001.csv.gz").write_bytes(
        gzip.compress(("\t".join(fila) + "\n").encode("utf-8")))

    leido = ext.leer_gdelt(spark).take(1)[0]

    assert leido.sqldate == "20200115"
    assert leido.event_root_code == "14"
    assert leido.accion_geo_pais == "PE"
    assert leido.n_articulos == 3


def test_ejecutar_sin_ninguna_fuente_no_escribe_nada(spark, lago):
    """Lago vacio: el job corre de principio a fin y declara lo que falto."""
    args = ext.argumentos(["--lake_uri", "file://lago-vacio", "--k", "2"])
    args.lake_uri = None                       # usa el lago temporal de la prueba

    resumen = ext.ejecutar(spark, args)

    assert resumen["escrito"] == []
    assert "gdelt" in resumen["sin_cobertura"]
    assert "texto" in resumen["sin_cobertura"]
