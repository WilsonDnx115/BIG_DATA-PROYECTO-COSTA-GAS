"""Fuentes declaradas por posicion, para hojas que empiezan en datos (commit AR25).

Tres de las hojas de la entrega no tienen fila de encabezado: empiezan en datos
(`GASTOS FLOTA`, `CO01/Sheet1` y `PRIMAX`). El lector de contratos empareja por nombre
de encabezado normalizado, asi que esas hojas no se podian declarar.

Apuntar `fila_encabezado` a la primera fila de datos no es una alternativa: los nombres
de columna saldrian de una fila que trae una placa y un proveedor con su RUC, y ademas
esa fila se perderia como dato.

Lo que agrega este modo: `primera_fila` y `posiciones` (letra de columna -> nombre
estandar). Es aditivo; las fuentes con nombre no cambian en nada.
"""
from __future__ import annotations

import textwrap

import pandas as pd
import pytest

from src.silver import contratos

# Un contrato minimo, con una fuente por posicion, para escribir en un archivo temporal.
CONTRATO = """
tabla: gastos_prueba
dominio: gastos
descripcion: Contrato de prueba con una fuente por posicion
grano: linea
llave: [origen, fila]

fuentes:
  - id: por_posicion
    familia: F99
    archivo: '^LIBRO\\.xls$'
    hojas: '^HOJA$'
    primera_fila: 3
    exigir: [monto_soles]
    posiciones:
      A: mes_texto
      C: placa_norm
      G: monto_soles

columnas:
  - {nombre: origen, tipo: string, rol: linaje, regla: "id de la fuente"}
  - {nombre: hoja, tipo: string, rol: linaje, regla: "hoja de origen"}
  - {nombre: fila, tipo: int, rol: linaje, regla: "fila de origen"}
  - {nombre: mes_texto, tipo: string, rol: dimension, regla: "mes como texto"}
  - {nombre: placa_norm, tipo: string, rol: llave, regla: "placa normalizada"}
  - {nombre: monto_soles, tipo: double, rol: medida, regla: "monto en soles"}
  - {nombre: llave_repetida, tipo: bool, rol: calidad, regla: "llave repetida"}
"""


def _contrato(tmp_path, texto: str = CONTRATO):
    ruta = tmp_path / "gastos_prueba.yaml"
    ruta.write_text(textwrap.dedent(texto), encoding="utf-8")
    return contratos._leer(ruta)                                   # noqa: SLF001


# --- El contrato se declara ----------------------------------------------------
def test_una_fuente_por_posicion_se_carga(tmp_path):
    fuente = _contrato(tmp_path).fuentes[0]
    assert fuente.primera_fila == 3
    assert fuente.columnas == {}                                   # no hay encabezado que emparejar


def test_las_letras_se_traducen_a_indices_de_columna(tmp_path):
    """A es la primera columna, es decir el indice 0; G es la septima, el indice 6."""
    fuente = _contrato(tmp_path).fuentes[0]
    assert fuente.posiciones == {"mes_texto": 0, "placa_norm": 2, "monto_soles": 6}


def test_una_fuente_con_nombres_no_cambia(tmp_path):
    """Lo que ya funcionaba sigue igual: sin `posiciones` y con su fila de encabezado."""
    con_nombres = CONTRATO.replace("""    primera_fila: 3
    exigir: [monto_soles]
    posiciones:
      A: mes_texto
      C: placa_norm
      G: monto_soles""", """    fila_encabezado: 1
    exigir: [monto_soles]
    columnas:
      MES: mes_texto
      PLACA: placa_norm
      MONTO: monto_soles""")
    fuente = _contrato(tmp_path, con_nombres).fuentes[0]
    assert fuente.fila_encabezado == 1 and fuente.posiciones == {}
    assert fuente.columnas == {"MES": "mes_texto", "PLACA": "placa_norm", "MONTO": "monto_soles"}


# --- Lo que el contrato no puede declarar --------------------------------------
def test_una_fuente_no_puede_declarar_las_dos_formas(tmp_path):
    """Con nombres y por posicion a la vez no se sabe cual manda."""
    mezcla = CONTRATO.replace("""    posiciones:
      A: mes_texto""", """    fila_encabezado: 1
    columnas:
      MES: mes_texto
    posiciones:
      A: mes_texto""")
    with pytest.raises(ValueError, match="por nombre o por posicion"):
        _contrato(tmp_path, mezcla)


def test_una_fuente_tiene_que_declarar_alguna_de_las_dos(tmp_path):
    sin_nada = CONTRATO.replace("""    primera_fila: 3
    exigir: [monto_soles]
    posiciones:
      A: mes_texto
      C: placa_norm
      G: monto_soles""", "    exigir: [monto_soles]")
    with pytest.raises(ValueError, match="por nombre o por posicion"):
        _contrato(tmp_path, sin_nada)


def test_una_letra_de_columna_invalida_se_rechaza(tmp_path):
    malo = CONTRATO.replace("      A: mes_texto", "      3: mes_texto")
    with pytest.raises(ValueError, match="letra de columna"):
        _contrato(tmp_path, malo)


# --- La hoja se lee por posicion -----------------------------------------------
CONTRATO_XLSX = CONTRATO.replace(r"'^LIBRO\.xls$'", r"'^LIBRO\.xlsx$'")

# Muestra sintetica: ni una celda viene de los archivos de la empresa.
FILAS = [
    ["ENERO", "ignorada", "T1A111", None, None, None, 125.50],
    ["FEBRERO", "ignorada", "R2B222", None, None, None, 80.0],
]


def _libro(tmp_path, filas=FILAS, titulo=True):
    from openpyxl import Workbook                                  # noqa: PLC0415

    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("HOJA")
    if titulo:
        ws.append(["Reporte de prueba"])                           # fila 1: titulo
        ws.append([])                                              # fila 2: vacia
    for f in filas:
        ws.append(f)                                               # los datos empiezan en la 3
    ruta = tmp_path / "LIBRO.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_la_hoja_sin_encabezado_se_lee_desde_su_primera_fila(tmp_path):
    from src.silver import lector                                  # noqa: PLC0415

    fuente = _contrato(tmp_path, CONTRATO_XLSX).fuentes[0]
    lectura = lector.leer_hoja(_libro(tmp_path), "HOJA", fuente)

    assert list(lectura.datos.columns) == ["mes_texto", "placa_norm", "monto_soles", "fila"]
    assert lectura.efectivas == 2


def test_la_primera_fila_de_datos_no_se_pierde_como_encabezado(tmp_path):
    """Es lo que pasaria apuntando `fila_encabezado` a la primera fila de datos."""
    from src.silver import lector                                  # noqa: PLC0415

    fuente = _contrato(tmp_path, CONTRATO_XLSX).fuentes[0]
    datos = lector.leer_hoja(_libro(tmp_path), "HOJA", fuente).datos

    assert len(datos) == 2
    assert datos["mes_texto"].tolist() == ["ENERO", "FEBRERO"]
    assert datos["fila"].tolist() == [3, 4]                        # la numeracion es la de Excel


def test_cada_posicion_trae_la_columna_que_le_toca(tmp_path):
    from src.silver import lector                                  # noqa: PLC0415

    fuente = _contrato(tmp_path, CONTRATO_XLSX).fuentes[0]
    datos = lector.leer_hoja(_libro(tmp_path), "HOJA", fuente).datos

    assert datos["placa_norm"].tolist() == ["T1A111", "R2B222"]    # la C, no la B
    assert datos["monto_soles"].tolist() == [125.50, 80.0]         # la G


def test_una_fila_mas_corta_que_la_posicion_pedida_no_rompe(tmp_path):
    """Excel no rellena las celdas finales vacias: la fila llega mas corta."""
    from src.silver import lector                                  # noqa: PLC0415

    fuente = _contrato(tmp_path, CONTRATO_XLSX).fuentes[0]
    corta = [["MARZO", "ignorada", "T1A111"]]                      # sin llegar a la G
    datos = lector.leer_hoja(_libro(tmp_path, FILAS + corta), "HOJA", fuente).datos

    assert len(datos) == 3
    # pandas representa el hueco como NaN en una columna de numeros; lo que importa es
    # que la fila entra y que la celda que no existe no trae un valor inventado.
    assert pd.isna(datos["monto_soles"].tolist()[2])


def test_la_hoja_que_no_llega_a_la_primera_fila_se_rechaza(tmp_path):
    from src.silver import lector                                  # noqa: PLC0415

    fuente = _contrato(tmp_path, CONTRATO_XLSX).fuentes[0]
    with pytest.raises(lector.HojaRechazada, match="primera fila"):
        lector.leer_hoja(_libro(tmp_path, [], titulo=True), "HOJA", fuente)


# --- La validacion de contratos reconoce las dos formas ------------------------
def test_validar_no_se_queja_de_una_fuente_por_posicion():
    """`validar()` exige que cada fuente declare columnas; una por posicion tambien."""
    fallos = [f for f in contratos.validar() if "no declara ninguna columna" in f]
    assert fallos == []


# --- El filtrado previo a la transformacion ------------------------------------
def test_filtrar_no_rompe_con_una_fuente_por_posicion(tmp_path):
    """`_filtrar` busca encabezados repetidos en medio de los datos comparando cada
    celda con el titulo de su columna. En una fuente por posicion no hay titulos, y
    antes eso reventaba con KeyError sobre la columna exigida."""
    from src.silver import procesar                               # noqa: PLC0415

    fuente = _contrato(tmp_path, CONTRATO_XLSX).fuentes[0]
    crudo = pd.DataFrame([{"mes_texto": "ENERO", "placa_norm": "T1A111", "monto_soles": 10.0},
                          {"mes_texto": "FEBRERO", "placa_norm": "R2B222", "monto_soles": None}])

    filtrado, descartes = procesar._filtrar(crudo, fuente)        # noqa: SLF001

    assert len(filtrado) == 1                                     # la fila sin monto se descarta
    assert descartes["sin_campos_exigidos"] == 1
    assert descartes["encabezados_repetidos"] == 0                # no hay titulos que repetir
