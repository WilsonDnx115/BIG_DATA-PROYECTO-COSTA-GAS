"""Reglas de limpieza de la Tabla 3.5 (paso 3.3.1).

Principio: ninguna regla inventa datos. Lo que no se puede corregir pasa a nulo
y se cuenta en el reporte de calidad.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from functools import lru_cache

from src.common import config

_RE_FECHA = re.compile(r"\d{2}/\d{2}/\d{4}")
_RE_PLACA = re.compile(r"[A-Z0-9]{6}")
_PESOS_RUC = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

# Catálogo cerrado de estados (variantes → valor normalizado)
CATALOGO_ESTADOS = {
    "ATENDIDO": "ATENDIDO", "ATENDIDA": "ATENDIDO",
    "PENDIENTE": "PENDIENTE",
    "ANULADO": "ANULADO", "ANULADA": "ANULADO",
    "ACTIVO": "ACTIVO", "HABIDO": "HABIDO", "NO HABIDO": "NO HABIDO",
    "BAJA": "BAJA", "BAJA DE OFICIO": "BAJA",
}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar_placa(valor) -> tuple[str | None, str | None]:
    """Devuelve (placa, fecha) desde celdas como 't1a-123 15/07/2023'.

    Mayúsculas, sin espacios ni guiones; patrón de 6 caracteres alfanuméricos.
    """
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None, None
    s = str(valor).upper()
    fecha = _RE_FECHA.search(s)
    placa = re.sub(r"[^A-Z0-9]", "", _RE_FECHA.sub("", s))
    return (placa if _RE_PLACA.fullmatch(placa) else None,
            fecha.group(0) if fecha else None)


def solo_digitos(valor) -> str:
    if valor is None or (isinstance(valor, float) and valor != valor):
        return ""
    s = str(valor).strip()
    if re.fullmatch(r"\d+\.0+", s):          # número guardado como float en Excel
        s = s.split(".")[0]
    return re.sub(r"\D", "", s)


def ruc_valido(ruc) -> bool:
    """Dígito verificador del RUC (módulo 11, pesos 5432765432)."""
    r = solo_digitos(ruc)
    if len(r) != 11:
        return False
    suma = sum(int(a) * b for a, b in zip(r[:10], _PESOS_RUC))
    dv = 11 - suma % 11
    dv = {10: 0, 11: 1}.get(dv, dv)
    return dv == int(r[10])


def normalizar_dni(valor) -> str | None:
    """Rellena con ceros a 8 dígitos los DNI que perdieron ceros iniciales."""
    d = solo_digitos(valor)
    if not d or len(d) > 8:
        return None
    return d.zfill(8)


def clasificar_documento(valor) -> tuple[str | None, str]:
    """Devuelve (documento_normalizado, clase) con clase en RUC/DNI/INVALIDO/VACIO."""
    d = solo_digitos(valor)
    if not d:
        return None, "VACIO"
    if len(d) == 11:
        return (d, "RUC") if ruc_valido(d) else (d, "INVALIDO")
    if len(d) <= 8:
        return d.zfill(8), "DNI"
    return d, "INVALIDO"


@lru_cache(maxsize=1)
def obtener_sal() -> str:
    """Sal de seudonimización: variable de entorno en local, Parameter Store en AWS (3.8.4)."""
    sal = os.environ.get("SEUDONIMO_SAL")
    if sal:
        return sal
    try:
        import boto3  # noqa: PLC0415

        ssm = boto3.client("ssm", region_name=config.AWS_REGION)
        return ssm.get_parameter(Name=config.SSM_SAL, WithDecryption=True)["Parameter"]["Value"]
    except Exception as exc:  # pragma: no cover - depende de AWS
        raise RuntimeError(
            "No hay sal de seudonimización: defina SEUDONIMO_SAL en .env "
            f"o el parámetro {config.SSM_SAL} en SSM"
        ) from exc


def seudonimizar(valor, sal: str | None = None) -> str | None:
    """Hash SHA-256 con sal guardada fuera del lago (Ley 29733)."""
    if valor is None or (isinstance(valor, float) and valor != valor) or str(valor).strip() == "":
        return None
    sal = sal if sal is not None else obtener_sal()
    return hashlib.sha256((sal + str(valor).strip().upper()).encode("utf-8")).hexdigest()[:16]


def normalizar_estado(valor) -> str | None:
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    s = re.sub(r"\s+", " ", _sin_tildes(str(valor)).strip().upper())
    return CATALOGO_ESTADOS.get(s, "OTRO" if s else None)


def a_kg(valor) -> float | None:
    """Convierte capacidades y kilos a float.

    '5 000 kg' → 5000.0; '1,250.5' → 1250.5; TRUE/FALSE (fórmula rota) → None.
    """
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return None if valor != valor else float(valor)
    s = str(valor).strip().upper()
    if s in {"TRUE", "FALSE", "VERDADERO", "FALSO", ""}:
        return None
    s = re.sub(r"[A-Z\s]", "", s)            # quita 'KG' y espacios de miles
    if s.count(",") and s.count("."):
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) != 3:
        s = s.replace(",", ".")              # coma decimal
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def a_bool(valor) -> bool | None:
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    if isinstance(valor, bool):
        return valor
    s = _sin_tildes(str(valor)).strip().upper()
    if s in {"SI", "S", "TRUE", "1", "X", "VIGENTE"}:
        return True
    if s in {"NO", "N", "FALSE", "0", "VENCIDO"}:
        return False
    return None


def es_asiento_ajuste(produccion: float | None, saldo_anterior: float | None) -> bool:
    """Producción negativa que anula el saldo previo (p. ej. −9 095 el 23/10/2018)."""
    if produccion is None or saldo_anterior is None:
        return False
    return produccion < 0 and abs(produccion + saldo_anterior) < 1e-6


# --- Reglas del diccionario v3.0 (informe v6, Tabla 3.5) --------------------
_SUFIJOS_UNIDAD = re.compile(r"(CAMION|CISTERNA|TRACTO|GRANELERO|LABO|PICK ?UP|CAMIONETA)$")
_RE_FECHA_SUELTA = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
_RE_PLACA_V6 = re.compile(r"([A-Z0-9]{3})-?(\d{3})")
MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
         "SETIEMBRE": 9, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}


_ERRORES_EXCEL = frozenset({"#VALUE!", "#N/A", "#REF!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"})


def _vacio(valor) -> bool:
    """None, NaN, NaT o texto en blanco."""
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip() or valor.strip().upper() in _ERRORES_EXCEL
    try:
        return bool(valor != valor)
    except (TypeError, ValueError):
        return False


def parsear_placa(valor) -> tuple[str | None, str | None, str | None]:
    """Devuelve (placa_norm, fecha, centro_costo).

    'T2N - 841 CAMION' → ('T2N841', None, None) · 'B2E-983 (24/7/23)' → ('B2E983', '24/7/23', None)
    'PLANTA' → (None, None, 'PLANTA'): no es una placa, es un punto de venta o un área.
    """
    if _vacio(valor):
        return None, None, None
    s = str(valor).upper().strip()
    fecha = _RE_FECHA_SUELTA.search(s)
    limpio = _RE_FECHA_SUELTA.sub("", re.sub(r"\(.*?\)", "", s))
    compacto = _SUFIJOS_UNIDAD.sub("", re.sub(r"\s+", "", limpio))
    m = _RE_PLACA_V6.fullmatch(compacto)
    if m:
        return m.group(1) + m.group(2), fecha.group(0) if fecha else None, None
    return None, None, re.sub(r"\s+", " ", limpio).strip() or None


def mes_a_numero(valor) -> int | None:
    """'Setiembre', 'SET', 9 o '09' → 9."""
    if _vacio(valor):
        return None
    if isinstance(valor, (int, float)) and 1 <= int(valor) <= 12:
        return int(valor)
    s = _sin_tildes(str(valor)).strip().upper()
    if s.isdigit() and 1 <= int(s) <= 12:
        return int(s)
    for nombre, n in MESES.items():
        if s == nombre or (len(s) >= 3 and nombre.startswith(s)):
            return n
    return None


def a_fecha(valor):
    """Fecha desde datetime, texto dd/mm/aaaa o número de serie de Excel. Lo no convertible → None."""
    import datetime as _dt  # noqa: PLC0415

    if _vacio(valor):
        return None
    if isinstance(valor, _dt.datetime):
        return valor.date()
    if isinstance(valor, _dt.date):
        return valor
    if isinstance(valor, (int, float)):
        if 20000 < valor < 80000:                       # serie de Excel (1954–2119)
            return (_dt.datetime(1899, 12, 30) + _dt.timedelta(days=float(valor))).date()
        return None
    s = str(valor).strip()
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(s, formato).date()
        except ValueError:
            continue
    return None


def corregir_fecha_por_mes(fecha, anio: int | None, mes: int | None):
    """Devuelve (fecha, estado) con estado en ok / invertida / discrepa / sin_fecha.

    Si la fecha no cae en el mes de su hoja pero sí al intercambiar día y mes, se
    invierte (75 de 1 066 facturas de compra en el diccionario v3.0).
    """
    import datetime as _dt  # noqa: PLC0415

    if fecha is None:
        return None, "sin_fecha"
    if mes is None or (fecha.month == mes and (anio is None or fecha.year == anio)):
        return fecha, "ok"
    if fecha.day <= 12 and fecha.day == mes and (anio is None or fecha.year == anio):
        return _dt.date(fecha.year, fecha.day, fecha.month), "invertida"
    return fecha, "discrepa"


def tc_valido(tc) -> bool:
    """Tipo de cambio dentro del rango válido; 1 o valores millonarios son relleno."""
    return tc is not None and tc == tc and config.TC_MIN <= tc <= config.TC_MAX


_RE_PRESENTACION = re.compile(r"(?<!\d)(5|10|15|45)\s*(?:KGS?|KLGS?|KILOS?)\b|\bBL?(05|10|15|45)\b")


def presentacion_kg(descripcion) -> float | None:
    """Kilos por balón desde 'GLP ENVASE DE 10 KLG', 'GLP 10 KG' o 'BL10'. Granel y otros → None."""
    if _vacio(descripcion):
        return None
    m = _RE_PRESENTACION.search(_sin_tildes(str(descripcion)).upper())
    return float(m.group(1) or m.group(2)) if m else None


def a_kilos(unidad, cantidad, descripcion=None) -> float | None:
    """Convierte una cantidad vendida a kg: unidades × presentación, galones × 2.04, litros × 0.54."""
    if cantidad is None or cantidad != cantidad:
        return None
    u = _sin_tildes(str(unidad or "")).strip().upper()
    if u.startswith(("KILO", "KG", "KLG")):
        return float(cantidad)
    if u.startswith("GAL"):
        return float(cantidad) * config.KG_POR_GALON
    if u.startswith(("LITRO", "LT")):
        return float(cantidad) * config.KG_POR_LITRO
    if u.startswith(("UNID", "UND", "BAL")):
        pres = presentacion_kg(descripcion)
        return float(cantidad) * pres if pres else None
    return None


def es_fila_total(*valores) -> bool:
    """Filas de total o subtotal metidas dentro del detalle ('TOTAL GENERAL', 'Total')."""
    return any(not _vacio(v) and _sin_tildes(str(v)).strip().upper().startswith(("TOTAL", "SUBTOTAL", "SUMA "))
               for v in valores)


def es_glp(descripcion) -> bool:
    """El artículo es GLP (envasado o granel). La planta también vende abarrotes, que no entran al balance."""
    return not _vacio(descripcion) and bool(re.search(r"\bGLP\b", _sin_tildes(str(descripcion)).upper()))
