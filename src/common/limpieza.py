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
