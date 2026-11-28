"""La página del portal está cableada con lo que las funciones de verdad responden.

No abre un navegador: lee `portal/` y lo amarra a `src/portal/`, que es donde están las
funciones. Lo que se comprueba es lo que se puede romper sin darse cuenta:

* `index.html` carga `panel.js` después de `app.js`, que es quien define `Portal.llamar`;
* `panel.js` solo llama a funciones que existen en `src/portal/`;
* no hay URL, bucket ni clave escritos a mano: todo sale de `config.js`;
* el portal no pinta un cero cuando no hay dato;
* la subida manda el cifrado con el que se firma la URL, o S3 la rechaza.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PORTAL = RAIZ / "portal"
FUNCIONES = RAIZ / "src" / "portal"

PANEL = (PORTAL / "panel.js").read_text(encoding="utf-8")
INDICE = (PORTAL / "index.html").read_text(encoding="utf-8")


def test_index_carga_panel_despues_de_app():
    assert "panel.js" in INDICE
    assert INDICE.index("app.js") < INDICE.index("panel.js"), \
        "panel.js usa Portal.llamar, que define app.js"


def test_solo_llama_a_funciones_que_existen():
    llamadas = set(re.findall(r'pedir\("(\w+)"', PANEL))
    disponibles = {p.stem for p in FUNCIONES.glob("*.py")} - {"__init__"}

    assert llamadas, "panel.js no llama a ninguna función"
    assert llamadas <= disponibles, f"funciones que no existen: {sorted(llamadas - disponibles)}"


def test_no_hay_direcciones_ni_claves_escritas_a_mano():
    for prohibido in ("amazonaws.com", "costagas-trujillo-lake", "AKIA", "s3://", "http://"):
        assert prohibido not in PANEL, f"panel.js trae {prohibido} escrito a mano"


def test_la_subida_manda_el_cifrado_con_el_que_se_firma():
    """firmar.py firma con ServerSideEncryption=AES256: el PUT debe repetirlo o S3 da 403."""
    firmar = (FUNCIONES / "firmar.py").read_text(encoding="utf-8")
    assert '"ServerSideEncryption": "AES256"' in firmar
    assert "x-amz-server-side-encryption" in PANEL
    assert 'CIFRADO = "AES256"' in PANEL


def test_la_subida_va_del_navegador_a_s3():
    """El archivo no pasa por una función: una entrega de 100 MB no cabe en una Lambda."""
    assert 'peticion.open("PUT"' in PANEL


@pytest.mark.parametrize("indicador", [f"kpi_{n}" for n in range(1, 6)])
def test_estan_los_cinco_kpi(indicador):
    assert indicador in PANEL


def test_un_indicador_sin_dato_no_se_pinta_como_cero():
    """CLAUDE.md: no presentar ceros como mediciones cuando falte la fuente."""
    resumen = PANEL[PANEL.index("function resumirKpi"):]
    resumen = resumen[:resumen.index("function refrescarKpis")]

    assert resumen.count('"sin dato"') >= 3
    assert "sin_vista" in resumen, "una vista no desplegada tiene que decirse"
    assert not re.search(r"valor:\s*0\b", resumen)


def test_el_estado_no_inventa_las_capas_que_la_funcion_no_informa():
    """estado.py solo lee manifiestos y silver/_control: landing y Gold no se pintan en verde."""
    estado = (FUNCIONES / "estado.py").read_text(encoding="utf-8")
    assert "PREFIJO_MANIFIESTOS" in estado and "PREFIJO_CONTROL" in estado

    for capa in ("landing", "gold"):
        bloque = PANEL[PANEL.index(f'filaCapa("{capa}"'):]
        bloque = bloque[:bloque.index(");")]
        assert "no lo informa" in bloque or "no lo consulta" in bloque
        assert '"sin dato"' in bloque


def test_el_refresco_se_detiene_con_la_pestana_oculta():
    """Cada llamada a `kpis` es una consulta de Athena: una pestaña olvidada no debe gastar."""
    assert "visibilitychange" in PANEL
    assert "visibilityState" in PANEL
    assert "REFRESCO_MS = 10000" in PANEL, "index.html anuncia que el estado se actualiza cada 10 s"
