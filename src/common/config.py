"""Parámetros del proyecto (pasos 1.6.1 y 2.3.1).

Todo valor configurable se lee de variables de entorno (o de `.env`) con un
valor por defecto. Ningún módulo debe escribir rutas ni umbrales fijos: los
importa de aquí. Cambiar LAKE_URI de `file://data/lake` a `s3://...` es lo único
necesario para pasar de local a la nube (prueba de sustitución, S2).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]


def _cargar_env(ruta: Path = RAIZ_REPO / ".env") -> None:
    """Carga `.env` sin dependencias externas. No pisa variables ya definidas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env()


def _env(nombre: str, defecto: str) -> str:
    return os.environ.get(nombre, defecto)


def _env_int(nombre: str, defecto: int) -> int:
    return int(_env(nombre, str(defecto)))


def _env_float(nombre: str, defecto: float) -> float:
    return float(_env(nombre, str(defecto)))


# --- Alcance (1.6) -----------------------------------------------------------
PLANTA = _env("PLANTA", "TRUJILLO")
ANIO_INI = _env_int("ANIO_INI", 2016)
ANIO_FIN = _env_int("ANIO_FIN", 2024)
ANIO_PILOTO = _env_int("ANIO_PILOTO", 2020)

# --- Infraestructura (2.x, D) ------------------------------------------------
AWS_REGION = _env("AWS_REGION", "us-east-1")
SUFIJO = _env("PROYECTO_SUFIJO", "dev")
BUCKET = _env("LAKE_BUCKET", f"costagas-trujillo-lake-{SUFIJO}")
LAKE_URI = _env("LAKE_URI", "file://data/lake")
ATHENA_WORKGROUP = _env("ATHENA_WORKGROUP", "costagas-wg")
SSM_SAL = _env("SSM_PARAM_SAL", "/costagas/seudonimo/sal")

# --- Procesamiento (S2, S3, S4, S5) -----------------------------------------
TAMANO_OBJETIVO_MB = _env_int("TAMANO_OBJETIVO_MB", 128)   # bloque HDFS de referencia
PARTICIONES = ("anio", "mes")                              # nunca alta cardinalidad
COLUMNAS_ALTA_CARDINALIDAD = ("placa_norm", "ruc", "documento", "card_code", "codigo_scop")
SPARK_SHUFFLE_PARTITIONS = _env_int("SPARK_SHUFFLE_PARTITIONS", 8)
SALTING_BUCKETS = _env_int("SALTING_BUCKETS", 0)           # 0 = solo AQE

# --- Calidad (Tabla 3.7) ----------------------------------------------------
META_PLACA_VALIDA = _env_float("META_PLACA_VALIDA", 0.98)
META_KG_EN_RANGO = _env_float("META_KG_EN_RANGO", 0.99)
META_SCOP_COMPRAS = _env_float("META_SCOP_COMPRAS", 0.95)
TOL_TIPO_CAMBIO = _env_float("TOL_TIPO_CAMBIO", 0.01)
PRECIO_PCT_INF = _env_float("PRECIO_PCT_INF", 0.01)
PRECIO_PCT_SUP = _env_float("PRECIO_PCT_SUP", 0.99)

# --- Señales y modelos (4.2, 4.3) -------------------------------------------
UMBRAL_Z_MAD = _env_float("UMBRAL_Z_MAD", 3.5)
TOP_K = _env_int("TOP_K", 20)
TOL_PRECIO_S10 = _env_float("TOL_PRECIO_S10", 0.10)   # 10 % bajo la mediana del canal
MERMA_TECNICA = _env_float("MERMA_TECNICA", 0.005)     # a confirmar con la empresa (H5)
UMBRAL_KPI_DIF = _env_float("UMBRAL_KPI_DIF", 0.02)
SEMILLA = _env_int("SEMILLA", 42)
PRECIO_REF_KG = _env_float("PRECIO_REF_KG", 2.10)      # S/ por kg; se reemplaza por referencia pública


@dataclass(frozen=True)
class Alcance:
    planta: str = PLANTA
    anio_ini: int = ANIO_INI
    anio_fin: int = ANIO_FIN
    anio_piloto: int = ANIO_PILOTO
    anios: tuple = field(default_factory=lambda: tuple(range(ANIO_INI, ANIO_FIN + 1)))


ALCANCE = Alcance()
