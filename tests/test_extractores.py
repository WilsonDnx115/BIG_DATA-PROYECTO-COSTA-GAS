"""W20: cada extractor escribe en su prefijo de `landing/externo/`, sin salir a la red.

Las respuestas HTTP se simulan sustituyendo `extractores.pedir`, que es el unico
punto de red del paquete. Ninguna prueba abre un socket.
"""
from __future__ import annotations

import gzip
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from src.common import rutas
from src.extractores import ClaveAusente, RespuestaInvalida
from src.extractores import bcrp, facilito, gdelt, resoluciones, youtube

FECHA = date(2020, 5, 15)


def _sin_clave(nombre=None):
    raise ClaveAusente("sin clave en SSM")


@pytest.fixture()
def externo(lago, monkeypatch):
    """Lago local temporal; devuelve la carpeta `landing/externo/`."""
    monkeypatch.setattr("src.extractores.hoy", lambda: FECHA)
    for modulo in (bcrp, facilito, youtube, gdelt, resoluciones):
        monkeypatch.setattr(modulo, "hoy", lambda: FECHA, raising=False)
    return Path(rutas.ruta("landing", "externo"))


def _responder(monkeypatch, respuesta):
    """Sustituye la red: `respuesta` puede ser bytes o una funcion de la URL."""
    def falso(url, params=None, cabeceras=None):   # noqa: ARG001
        return respuesta(url, params) if callable(respuesta) else respuesta
    monkeypatch.setattr("src.extractores.pedir", falso)
    for modulo in (bcrp, facilito, youtube, gdelt):
        monkeypatch.setattr(modulo, "pedir", falso, raising=False)
    return falso


# --- BCRP --------------------------------------------------------------------

SERIE_BCRP = json.dumps({
    "periods": [{"name": "15.May.20", "values": ["3.4210"]},
                {"name": "16.May.20", "values": ["3.4195"]}],
}).encode("utf-8")


def test_bcrp_guarda_la_serie_en_su_prefijo(externo, monkeypatch):
    _responder(monkeypatch, SERIE_BCRP)

    ruta = Path(bcrp.extraer(date(2020, 5, 9), FECHA))

    assert ruta.parent == externo / "bcrp" / "fecha_carga=2020-05-15"
    assert ruta.name == "PD04640PD__2020-05-09__2020-05-15.json"
    assert json.loads(ruta.read_text(encoding="utf-8"))["periods"][0]["values"] == ["3.4210"]


def test_bcrp_pide_la_serie_del_tipo_de_cambio_venta(monkeypatch):
    vistas = []

    def falso(url, params=None, cabeceras=None):   # noqa: ARG001
        vistas.append(url)
        return SERIE_BCRP

    monkeypatch.setattr(bcrp, "pedir", falso)

    bcrp.descargar(date(2020, 1, 1), date(2020, 1, 8))

    assert vistas == [f"{bcrp.API}/PD04640PD/json/2020-01-01/2020-01-08"]


def test_bcrp_falla_si_la_serie_viene_sin_periodos(monkeypatch):
    _responder(monkeypatch, json.dumps({"periods": []}).encode("utf-8"))

    with pytest.raises(RespuestaInvalida, match="no trajo periodos"):
        bcrp.descargar(date(2020, 1, 1), date(2020, 1, 8))


# --- Facilito ----------------------------------------------------------------

PRECIOS = json.dumps({"data": [{"establecimiento": "GRIFO X", "distrito": "TRUJILLO",
                                "producto": "GLP ENVASADO", "precio": 38.5}]}).encode("utf-8")


def test_facilito_escribe_un_json_por_producto(externo, monkeypatch):
    _responder(monkeypatch, PRECIOS)

    escritas = [Path(p) for p in facilito.extraer()]

    assert len(escritas) == len(facilito.PRODUCTOS)
    assert {p.name for p in escritas} == {"glp_envasado__2020-05-15.json",
                                          "glp_granel__2020-05-15.json"}
    assert all(p.parent == externo / "facilito" / "fecha_carga=2020-05-15" for p in escritas)
    guardado = json.loads(escritas[0].read_text(encoding="utf-8"))
    assert guardado["departamento"] == "LA LIBERTAD"
    assert guardado["registros"][0]["precio"] == 38.5


def test_facilito_falla_si_no_hay_precios(monkeypatch):
    _responder(monkeypatch, json.dumps({"data": []}).encode("utf-8"))

    with pytest.raises(RespuestaInvalida, match="no devolvio precios"):
        facilito.descargar("GLP ENVASADO")


# --- YouTube -----------------------------------------------------------------

BUSQUEDA = json.dumps({"items": [
    {"id": {"videoId": "abc123"},
     "snippet": {"title": "Precio del balon", "description": "subio en Trujillo",
                 "channelTitle": "Canal", "publishedAt": "2020-05-01T00:00:00Z",
                 "thumbnails": {"default": {"url": "http://x"}}}},
]}).encode("utf-8")


def test_youtube_guarda_solo_el_texto_publico(externo, monkeypatch):
    _responder(monkeypatch, BUSQUEDA)

    ruta = Path(youtube.extraer(("precio GLP",), clave="clave-de-prueba")[0])

    assert ruta.parent == externo / "youtube" / "fecha_carga=2020-05-15"
    item = json.loads(ruta.read_text(encoding="utf-8"))["items"][0]
    assert set(item) == {*youtube.CAMPOS, "video_id"}
    assert "thumbnails" not in item


def test_youtube_falla_con_mensaje_claro_si_no_hay_clave(externo, monkeypatch):
    """Sin clave en SSM no se guarda un archivo vacio: se para la corrida."""
    _responder(monkeypatch, BUSQUEDA)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(youtube, "clave_youtube", _sin_clave)

    with pytest.raises(ClaveAusente, match="sin clave"):
        youtube.extraer(("precio GLP",))

    assert not (externo / "youtube").exists()


def test_youtube_consulta_las_cinco_busquedas_del_plan(externo, monkeypatch):
    """ADR 0015 y paso 3.2.7: cinco busquedas, sin canal mientras no haya id."""
    _responder(monkeypatch, BUSQUEDA)

    escritas = youtube.extraer(clave="clave-de-prueba", canal="")

    assert len(youtube.CONSULTAS) == 5
    assert len(escritas) == 5
    assert not [r for r in escritas if "canal__" in r]


def test_youtube_agrega_el_canal_de_osinergmin_cuando_hay_id(externo, monkeypatch):
    vistos = []

    def falso(url, params=None, cabeceras=None):   # noqa: ARG001
        vistos.append(params)
        return BUSQUEDA

    monkeypatch.setattr("src.extractores.pedir", falso)
    monkeypatch.setattr(youtube, "pedir", falso)

    escritas = youtube.extraer(("precio GLP",), clave="k", canal="UC-osinergmin")

    assert len(escritas) == 2
    assert escritas[1].endswith("canal__glp__2020-05-15.json")
    assert vistos[0].get("channelId") is None      # la busqueda normal no filtra canal
    assert vistos[1]["channelId"] == "UC-osinergmin"


def test_youtube_no_pone_la_clave_en_la_ruta(externo, monkeypatch):
    _responder(monkeypatch, BUSQUEDA)

    ruta = youtube.extraer(("precio GLP",), clave="clave-secreta")[0]

    assert "clave-secreta" not in ruta


# --- GDELT -------------------------------------------------------------------

LISTA = ("1234 abcd http://data.gdeltproject.org/gdeltv2/20200515000000.export.CSV.zip\n"
         "1234 abcd http://data.gdeltproject.org/gdeltv2/20200515001500.export.CSV.zip\n"
         "1234 abcd http://data.gdeltproject.org/gdeltv2/20190101000000.export.CSV.zip\n"
         "1234 abcd http://data.gdeltproject.org/gdeltv2/20200515000000.mentions.CSV.zip\n")


def _zip_con(texto: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("20200515000000.export.CSV", texto)
    return buf.getvalue()


def test_gdelt_toma_solo_los_export_del_anio_pedido():
    urls = gdelt.urls_del_anio(2020, LISTA)

    assert len(urls) == 2
    assert all("export" in u and "/2020" in u for u in urls)


def test_gdelt_junta_los_zip_en_bloques_gzip(externo, monkeypatch):
    fila = b"evento;trujillo;glp\n"
    _responder(monkeypatch, lambda url, params: LISTA.encode() if "masterfile" in url
               else _zip_con(fila))

    # Bloque diminuto: los dos archivos del anio caen en dos bloques y se prueba el corte.
    escritas = gdelt.cargar_anio(2020, bytes_por_bloque=len(fila))

    assert len(escritas) == 2
    primero = Path(escritas[0])
    assert primero.parent == externo / "gdelt" / "fecha_carga=2020-01-01" / "anio=2020"
    assert primero.name == "export-0001.csv.gz"
    assert gzip.decompress(primero.read_bytes()) == fila


def test_gdelt_no_deja_el_zip_en_el_lago(externo, monkeypatch):
    _responder(monkeypatch, lambda url, params: LISTA.encode() if "masterfile" in url
               else _zip_con(b"x;y;z\n"))

    gdelt.cargar_anio(2020)

    assert not list(externo.rglob("*.zip"))
    assert list(externo.rglob("*.csv.gz"))


def test_gdelt_rechaza_un_zip_con_varios_archivos():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.csv", b"a")
        z.writestr("b.csv", b"b")

    with pytest.raises(RespuestaInvalida, match="un CSV por zip"):
        gdelt.descomprimir(buf.getvalue())


# --- Resoluciones ------------------------------------------------------------

def test_resoluciones_guarda_el_pdf_con_su_nombre_de_origen(externo):
    url = "https://www.osinergmin.gob.pe/res/OS-123-2020-OS-CD.pdf"

    ruta = Path(resoluciones.extraer([url], descargador=lambda u: b"%PDF-1.7 contenido")[0])

    assert ruta.parent == externo / "resoluciones" / "fecha_carga=2020-05-15"
    assert ruta.name == "OS-123-2020-OS-CD.pdf"
    assert ruta.read_bytes().startswith(b"%PDF-")


def test_resoluciones_rechaza_lo_que_no_sea_pdf(externo):
    with pytest.raises(RespuestaInvalida, match="no devolvio un PDF"):
        resoluciones.extraer(["https://x/a.pdf"], descargador=lambda u: b"<html>error</html>")

    assert not (externo / "resoluciones").exists()


def test_resoluciones_sin_lista_no_escribe_nada(externo):
    with pytest.raises(RespuestaInvalida, match="sin URL de resoluciones"):
        resoluciones.extraer([])

    assert not (externo / "resoluciones").exists()
