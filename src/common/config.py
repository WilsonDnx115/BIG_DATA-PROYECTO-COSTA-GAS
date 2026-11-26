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
AWS_REGION = _env("AWS_REGION", "us-east-2")   # asignada por el plan gratuito (ADR 0011)
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
TC_MIN = _env_float("TC_MIN", 3.2)                 # rango válido del tipo de cambio (Tabla 3.7 del v6)
TC_MAX = _env_float("TC_MAX", 4.2)
MAX_FILAS_VACIAS = _env_int("MAX_FILAS_VACIAS", 3000)   # corte de hojas infladas por fórmulas (hallazgo C6)
KG_POR_GALON = _env_float("KG_POR_GALON", 2.04)    # sensibilidad 2.04–2.10 (hallazgo B4)
KG_POR_LITRO = _env_float("KG_POR_LITRO", 0.54)

# --- Señales y modelos (4.2, 4.3) -------------------------------------------
UMBRAL_Z_MAD = _env_float("UMBRAL_Z_MAD", 3.5)
TOP_K = _env_int("TOP_K", 20)
TOL_PRECIO_S10 = _env_float("TOL_PRECIO_S10", 0.10)   # 10 % bajo la mediana del canal
MERMA_TECNICA = _env_float("MERMA_TECNICA", 0.005)     # merma que se simula al generar la muestra sintética
UMBRAL_KPI_DIF = _env_float("UMBRAL_KPI_DIF", 0.02)    # umbral de referencia del KPI 1 (2 %)
SEMILLA = _env_int("SEMILLA", 42)
PRECIO_REF_KG = _env_float("PRECIO_REF_KG", 2.10)      # S/ por kg; se reemplaza por referencia pública

# --- KPI 1 · balance de planta (H5) ------------------------------------------
# La empresa no ha fijado su merma técnica. Para que el KPI 1 se calcule y quede
# evidencia, el equipo asume 0.5 % de lo comprado como SUPUESTO DE TRABAJO, no como
# dato de la empresa. El tablero muestra el KPI con y sin la merma, y la etiqueta
# «supuesto» mientras MERMA_TECNICA_ES_SUPUESTO sea verdadero. Si la empresa entrega
# su tolerancia, se cambian el valor, la fuente y la marca en .env, sin tocar código.
MERMA_TECNICA_PCT = _env_float("MERMA_TECNICA_PCT", 0.005)
MERMA_TECNICA_FUENTE = _env("MERMA_TECNICA_FUENTE", "Supuesto de trabajo del equipo: 0.5 % de lo comprado")
MERMA_TECNICA_ES_SUPUESTO = _env("MERMA_TECNICA_ES_SUPUESTO", "si").strip().lower() in ("si", "sí", "true", "1")

# --- Modelo S12 y su operación (4.3) -----------------------------------------
MADUREZ_DIAS = _env_int("MADUREZ_DIAS", 30)                  # la etiqueta madura 30 días después del vencimiento
VENTANA_MEDIANA_DIAS = _env_int("VENTANA_MEDIANA_DIAS", 90)  # mediana móvil de USD/kg a la fecha de la factura
INICIO_EVAL_ADELANTE = _env("INICIO_EVAL_ADELANTE", "2022-08")  # evaluación hacia adelante, mes a mes
META_PRECISION = _env_float("META_PRECISION", 0.70)          # precisión de la clase positiva
META_AUC = _env_float("META_AUC", 0.70)
RECALL_MIN_RETADOR = _env_float("RECALL_MIN_RETADOR", 0.50)  # el retador no reemplaza al vigente por debajo
REVISIONES_REENTRENO = _env_int("REVISIONES_REENTRENO", 20)  # revisiones nuevas que adelantan el reentrenamiento
RF_ARBOLES = _env_int("RF_ARBOLES", 100)
RF_PROFUNDIDAD = _env_int("RF_PROFUNDIDAD", 6)
BOOTSTRAP_REMUESTREOS = _env_int("BOOTSTRAP_REMUESTREOS", 1000)
PSI_UMBRAL = _env_float("PSI_UMBRAL", 0.2)                   # un PSI mayor adelanta el reentrenamiento
PSI_MIN_OBS = _env_int("PSI_MIN_OBS", 100)                   # con menos facturas el PSI salta por ruido
PSI_BINS = _env_int("PSI_BINS", 10)                          # deciles fijados en el entrenamiento

# --- Detector de desvíos persistentes (4.3, Tabla 4.8h) ----------------------
FALSAS_ALARMAS_ANIO = _env_int("FALSAS_ALARMAS_ANIO", 12)    # en todo el sistema y en cada granularidad
SEMILLAS_DETECTOR = _env_int("SEMILLAS_DETECTOR", 100)
LOTE_SEMILLAS = _env_int("LOTE_SEMILLAS", 10)

# --- Controles preventivos (Tabla 4.8i) --------------------------------------
TOL_PRECIO_PAGO = _env_float("TOL_PRECIO_PAGO", 0.05)        # USD/kg sobre la mediana móvil del proveedor


@dataclass(frozen=True)
class Alcance:
    planta: str = PLANTA
    anio_ini: int = ANIO_INI
    anio_fin: int = ANIO_FIN
    anio_piloto: int = ANIO_PILOTO
    anios: tuple = field(default_factory=lambda: tuple(range(ANIO_INI, ANIO_FIN + 1)))


ALCANCE = Alcance()
