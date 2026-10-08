"""Reglas de calidad como código (pasos 3.4.1 y 3.4.2, Tablas 3.7 y 3.8).

Cada regla devuelve una Serie booleana «cumple» y declara su acción ante el
fallo: rechazar (el registro no pasa a Silver), marcar (pasa con bandera) o
clasificar. `Reporte` acumula aceptados / marcados / rechazados por regla y la
completitud de campos críticos: es la evidencia de la V de veracidad (S1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from src.common import config

RECHAZAR, MARCAR, CLASIFICAR = "rechazar", "marcar", "clasificar"


@dataclass
class Regla:
    nombre: str
    campo: str
    criterio: str
    accion: str
    meta: float | None = None


REGLAS = {
    "placa_valida": Regla("placa_valida", "placa", "6 alfanuméricos tras normalizar", MARCAR, config.META_PLACA_VALIDA),
    "ruc_valido": Regla("ruc_valido", "ruc/dni", "11 dígitos y dígito verificador", CLASIFICAR, 1.0),
    "ruc_existente": Regla("ruc_existente", "ruc/dni", "presente en padrón SUNAT", CLASIFICAR, 1.0),
    "kg_en_rango": Regla("kg_en_rango", "kg", "> 0 y ≤ capacidad de la unidad", MARCAR, config.META_KG_EN_RANGO),
    "fecha_coherente": Regla("fecha_coherente", "fecha", f"dentro de {config.ANIO_INI}–{config.ANIO_FIN}", RECHAZAR, 1.0),
    "tc_coherente": Regla("tc_coherente", "tipo_cambio", f"desvío ≤ {config.TOL_TIPO_CAMBIO:.0%} vs BCRP", MARCAR),
    "precio_en_rango": Regla("precio_en_rango", "precio", "entre P1 y P99 de su canal y mes", MARCAR),
    "unicidad": Regla("unicidad", "documento+linea", "sin duplicados", RECHAZAR, 1.0),
}


# --- Funciones de regla -------------------------------------------------------
def placa_valida(placa: pd.Series) -> pd.Series:
    return placa.notna()


def kg_en_rango(kg: pd.Series, capacidad: pd.Series | None = None) -> pd.Series:
    ok = kg.notna() & (kg > 0)
    if capacidad is not None:
        ok &= capacidad.isna() | (kg <= capacidad)
    return ok


def fecha_coherente(fecha: pd.Series) -> pd.Series:
    f = pd.to_datetime(fecha, errors="coerce")
    return f.dt.year.between(config.ANIO_INI, config.ANIO_FIN).fillna(False).astype(bool)


def tc_coherente(tc: pd.Series, tc_oficial: pd.Series) -> pd.Series:
    desvio = (tc - tc_oficial).abs() / tc_oficial
    return desvio.isna() | (desvio <= config.TOL_TIPO_CAMBIO)


def precio_en_rango(df: pd.DataFrame, col_precio="precio", grupo=("canal", "id_producto", "anio", "mes")) -> pd.Series:
    g = df.groupby(list(grupo))[col_precio]
    p_inf = g.transform(lambda s: s.quantile(config.PRECIO_PCT_INF))
    p_sup = g.transform(lambda s: s.quantile(config.PRECIO_PCT_SUP))
    return df[col_precio].isna() | df[col_precio].between(p_inf, p_sup)


def unicidad(df: pd.DataFrame, clave: tuple[str, ...]) -> pd.Series:
    return ~df.duplicated(subset=list(clave), keep="first")


# --- Reporte -------------------------------------------------------------------
@dataclass
class Reporte:
    fuente: str
    filas_entrada: int = 0
    reglas: dict = field(default_factory=dict)
    completitud: dict = field(default_factory=dict)
    filas_salida: int = 0
    rechazadas: int = 0

    def registrar(self, nombre: str, cumple: pd.Series) -> pd.Series:
        r = REGLAS[nombre]
        n, ok = int(len(cumple)), int(cumple.sum())
        tasa = ok / n if n else 1.0
        self.reglas[nombre] = {
            "campo": r.campo, "criterio": r.criterio, "accion": r.accion,
            "cumplen": ok, "fallan": n - ok, "tasa": round(tasa, 4),
            "meta": r.meta, "cumple_meta": None if r.meta is None else tasa >= r.meta,
        }
        return cumple

    def medir_completitud(self, df: pd.DataFrame, campos: list[str]) -> None:
        for c in campos:
            if c in df.columns:
                self.completitud[c] = round(float(df[c].notna().mean()) if len(df) else 0.0, 4)

    def a_dict(self) -> dict:
        return {"fuente": self.fuente,
                "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "filas_entrada": self.filas_entrada, "filas_salida": self.filas_salida,
                "rechazadas": self.rechazadas, "reglas": self.reglas,
                "completitud": self.completitud}
