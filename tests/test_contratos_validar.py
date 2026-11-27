"""Validación de los contratos antes de desplegar (parte del commit A11).

`python -m src.silver.contratos --validar` es lo que corre la integración continua en
cada pull request: un contrato sin llave, con un tipo que Athena no entiende o cuyo DDL
versionado quedó viejo rompe el despliegue de Silver, y conviene verlo en el pull
request y no en la corrida.
"""
import subprocess
import sys
import textwrap

import pytest
import yaml

from src.common import config
from src.silver import contratos

BASE = {
    "tabla": "prueba", "dominio": "compras", "descripcion": "contrato de prueba",
    "grano": "fila", "llave": ["documento"],
    "fuentes": [{"id": "f1", "familia": "F00", "archivo": r"^X\.xlsx$", "hojas": "^H$",
                 "fila_encabezado": 1, "exigir": [], "columnas": {"DOC": "documento"}}],
    "columnas": [{"nombre": "documento", "tipo": "string", "rol": "llave"}],
}


@pytest.fixture()
def contratos_en(tmp_path, monkeypatch):
    """Apunta el cargador a una carpeta de contratos de prueba."""
    def poner(*docs):
        carpeta = tmp_path / "contracts"
        carpeta.mkdir(exist_ok=True)
        for i, d in enumerate(docs):
            (carpeta / f"c{i}.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        monkeypatch.setattr(contratos, "DIR_CONTRATOS", carpeta)
        contratos.cargar.cache_clear()
        return carpeta
    yield poner
    contratos.cargar.cache_clear()


# --- El repositorio tal como está ------------------------------------------------
def test_los_contratos_del_repositorio_estan_bien():
    assert contratos.validar() == []


def test_hay_contratos_que_validar():
    assert len(contratos.cargar()) >= 5


# --- Lo que tiene que detectar ----------------------------------------------------
def test_detecta_un_ddl_que_quedo_viejo(contratos_en, tmp_path, monkeypatch):
    contratos_en(BASE)
    (tmp_path / "ddl").mkdir()
    monkeypatch.setattr(config, "RAIZ_REPO", tmp_path)
    assert any("falta silver_prueba.sql" in p for p in contratos.validar())

    destino = tmp_path / "sql" / "athena" / "ddl"
    destino.mkdir(parents=True)
    (destino / "silver_prueba.sql").write_text("-- desactualizado\n", encoding="utf-8")
    contratos.cargar.cache_clear()
    assert any("no coincide con el contrato" in p for p in contratos.validar())


def test_detecta_un_tipo_que_athena_no_entiende(contratos_en):
    malo = {**BASE, "columnas": [{"nombre": "documento", "tipo": "uuid", "rol": "llave"}]}
    contratos_en(malo)
    assert any("no se pueden cargar" in p or "no admitido" in p for p in contratos.validar())


def test_detecta_una_llave_que_no_esta_en_las_columnas(contratos_en):
    malo = {**BASE, "llave": ["no_existe"]}
    contratos_en(malo)
    assert any("llave" in p for p in contratos.validar())


def test_detecta_dos_archivos_que_declaran_la_misma_tabla(contratos_en, tmp_path, monkeypatch):
    """cargar() indexa por tabla, asi que sin esta comprobacion uno se perderia en silencio."""
    monkeypatch.setattr(config, "RAIZ_REPO", tmp_path)
    contratos_en(BASE, {**BASE, "descripcion": "otra"})
    assert any("ya declarada en" in p for p in contratos.validar())
    assert len(contratos.cargar()) == 1          # efectivamente solo sobrevive uno


def test_detecta_una_fuente_sin_columnas(contratos_en, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAIZ_REPO", tmp_path)
    fuente = {**BASE["fuentes"][0], "columnas": {}}
    contratos_en({**BASE, "fuentes": [fuente]})
    assert any("no declara ninguna columna" in p or "no se pueden cargar" in p
               for p in contratos.validar())


def test_una_carpeta_sin_contratos_se_informa(contratos_en):
    contratos_en()
    assert contratos.validar() == ["no hay ningun contrato en contracts/"]


# --- La línea de comandos ----------------------------------------------------------
def test_la_orden_sale_con_cero_cuando_todo_esta_bien():
    r = subprocess.run([sys.executable, "-m", "src.silver.contratos", "--validar"],
                       cwd=config.RAIZ_REPO, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "0 problemas" in r.stdout


def test_la_orden_sale_con_uno_cuando_algo_falla(tmp_path):
    """Si no saliera con 1, la integración continua pasaría en verde con el DDL viejo."""
    guion = textwrap.dedent("""
        import sys, yaml, pathlib
        from src.common import config
        from src.silver import contratos
        carpeta = pathlib.Path(sys.argv[1]) / "contracts"; carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "malo.yaml").write_text(yaml.safe_dump({
            "tabla": "malo", "dominio": "compras", "llave": ["doc"],
            "fuentes": [{"id": "f", "archivo": "^X$", "hojas": "^H$", "fila_encabezado": 1,
                         "columnas": {"DOC": "doc"}}],
            "columnas": [{"nombre": "doc", "tipo": "string"}]}), encoding="utf-8")
        contratos.DIR_CONTRATOS = carpeta
        config.RAIZ_REPO = pathlib.Path(sys.argv[1])
        contratos.cargar.cache_clear()
        sys.exit(1 if contratos.validar() else 0)
    """)
    archivo = tmp_path / "comprobar.py"
    archivo.write_text(guion, encoding="utf-8")
    r = subprocess.run([sys.executable, str(archivo), str(tmp_path)],
                       cwd=config.RAIZ_REPO, capture_output=True, text=True)
    assert r.returncode == 1          # falta su DDL
