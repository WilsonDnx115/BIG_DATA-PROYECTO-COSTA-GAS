"""Plantilla del correo del semáforo diario (B17). Datos de prueba sintéticos."""
from datetime import date, datetime

from src.controles.plantillas import semaforo
from src.controles.plantillas.semaforo import formatear_resumen

FECHA = date(2026, 11, 26)
ENLACE = "https://ejemplo.grafana.net/d/costagas-semaforo"


def fila(placa, color, kg=100.0, soles=50.0, inicio="2026-09", **extra):
    return {"placa_norm": placa, "color": color, "inicio_desvio": inicio,
            "kg_acumulados": kg, "soles_acumulados": soles, **extra}


def test_sin_unidades_en_rojo():
    texto = formatear_resumen([fila("AAA111", "verde"), fila("BBB222", "ambar")], FECHA, ENLACE)
    assert "Sin unidades en rojo hoy." in texto
    assert "Unidades en rojo" not in texto
    assert "Unidades en ámbar (1):" in texto


def test_lista_vacia_o_nula():
    for filas in ([], None):
        texto = formatear_resumen(filas, FECHA, ENLACE)
        assert "Sin unidades en rojo hoy." in texto
        assert "Sin unidades en ámbar hoy." in texto
        assert "Unidades en verde: 0." in texto


def test_encabezado_fecha_y_enlace():
    texto = formatear_resumen([], FECHA, ENLACE)
    assert texto.startswith("Semáforo diario de unidades · 2026-11-26\n")
    assert f"Tablero: {ENLACE}" in texto


def test_fecha_datetime_y_por_defecto():
    assert "· 2026-11-26" in formatear_resumen([], datetime(2026, 11, 26, 6, 30), ENLACE)
    assert formatear_resumen([], None, ENLACE).startswith("Semáforo diario de unidades · ")


def test_enlace_ausente():
    assert "Tablero: enlace no configurado" in formatear_resumen([], FECHA, None)
    assert "Tablero: enlace no configurado" in formatear_resumen([], FECHA, "  ")


def test_linea_de_unidad_roja():
    texto = formatear_resumen([fila("ABC123", "rojo", kg=12345.4, soles=6789.5, inicio="2026-08")],
                              FECHA, ENLACE)
    assert "Unidades en rojo (1):" in texto
    assert "- ABC123 · desvío desde 2026-08 · 12 345 kg · S/ 6 789.50" in texto


def test_rojas_ordenadas_por_kg_y_sin_dato_al_final():
    filas = [fila("CCC333", "rojo", kg=None), fila("AAA111", "rojo", kg=10),
             fila("BBB222", "rojo", kg=500)]
    texto = formatear_resumen(filas, FECHA, ENLACE)
    assert texto.index("BBB222") < texto.index("AAA111") < texto.index("CCC333")


def test_valor_ausente_no_se_muestra_como_cero():
    texto = formatear_resumen([fila("AAA111", "rojo", kg=None, soles="no numero", inicio=None)],
                              FECHA, ENLACE)
    assert "- AAA111 · desvío desde sin dato · sin dato · sin dato" in texto
    assert " 0 kg" not in texto and "S/ 0.00" not in texto


def test_ambar_con_tilde_y_mayusculas():
    texto = formatear_resumen([fila("AAA111", "Ámbar"), fila("BBB222", "ROJO")], FECHA, ENLACE)
    assert "Unidades en ámbar (1):" in texto
    assert "Unidades en rojo (1):" in texto


def test_colores_desconocidos_se_ignoran():
    texto = formatear_resumen([fila("AAA111", "azul"), fila("BBB222", None)], FECHA, ENLACE)
    assert "AAA111" not in texto and "BBB222" not in texto


def test_verdes_se_cuentan_sin_listarse():
    texto = formatear_resumen([fila("VVV111", "verde"), fila("VVV222", "verde")], FECHA, ENLACE)
    assert "Unidades en verde: 2." in texto
    assert "VVV111" not in texto


def test_maximo_50_unidades_primero_las_rojas():
    rojas = [fila(f"R{i:05d}", "rojo", kg=1000 - i) for i in range(45)]
    ambar = [fila(f"A{i:05d}", "ambar", kg=500 - i) for i in range(20)]
    texto = formatear_resumen(rojas + ambar, FECHA, ENLACE)
    listadas = [ln for ln in texto.splitlines() if ln.startswith("- ") and "desvío" in ln]
    assert len(listadas) == semaforo.MAX_UNIDADES == 50
    assert sum(ln.startswith("- R") for ln in listadas) == 45
    assert sum(ln.startswith("- A") for ln in listadas) == 5
    assert "Unidades en rojo (45):" in texto and "Unidades en ámbar (20):" in texto
    assert "15 más en el tablero" in texto


def test_rojas_que_llenan_el_cupo():
    rojas = [fila(f"R{i:05d}", "rojo", kg=1000 - i) for i in range(60)]
    texto = formatear_resumen(rojas + [fila("A00001", "ambar")], FECHA, ENLACE)
    assert "R00049" in texto and "R00050" not in texto
    assert "(no caben en este correo; ver el tablero)" in texto
    assert "11 más en el tablero" in texto


def test_sin_datos_personales_aunque_vengan_en_la_fila():
    personal = fila("ABC123", "rojo", conductor="JUAN PEREZ", dni="12345678",
                    ruc="10123456789", conductor_hash="f" * 64)
    texto = formatear_resumen([personal], FECHA, ENLACE)
    for dato in ("JUAN", "PEREZ", "12345678", "10123456789", "f" * 64):
        assert dato not in texto


def test_campo_placa_alternativo():
    texto = formatear_resumen([{"placa": "XYZ789", "color": "rojo"}], FECHA, ENLACE)
    assert "- XYZ789 · desvío desde sin dato · sin dato · sin dato" in texto


def test_texto_plano_sin_html():
    texto = formatear_resumen([fila("<b>X</b>", "rojo")], FECHA, ENLACE)
    assert texto.endswith("\n")
    assert "<html" not in texto.lower()
