"""Hipótesis del proyecto como código (paso 1.3.1, Tabla 1.4).

Señales, EDA y modelos referencian la hipótesis por su código (H1…H5), de modo
que cada resultado diga qué hipótesis apoya o descarta.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hipotesis:
    codigo: str
    nombre: str
    evidencia: str
    fuentes: tuple[str, ...]
    senales: tuple[str, ...]
    variables: tuple[str, ...]


HIPOTESIS: dict[str, Hipotesis] = {
    "H1": Hipotesis("H1", "Sustracción en ruta o cambio de unidad",
                    "Placa cargada distinta de la facturada; diferencia persistente concentrada en pocas unidades",
                    ("aba_02", "com_19", "pu_03", "ne_07"), ("S1", "S4", "S5", "S7", "S8"),
                    ("kg_diferencia", "flag_placa_divergente", "ratio_carga_capacidad")),
    "H2": Hipotesis("H2", "Error de registro",
                    "Diferencias que desaparecen al normalizar placas, RUC y unidades",
                    ("diccionario_v2", "pu_01"), ("S1",),
                    ("placa_valida", "ruc_valido")),
    "H3": Hipotesis("H3", "Descalibración de balanzas",
                    "Diferencia sistemática y pequeña en todas las unidades de una balanza o período",
                    ("prod", "calibracion"), (),
                    ("pct_diferencia",)),
    "H4": Hipotesis("H4", "Efecto de mercado",
                    "Caída de volumen o margen que también se observa en el sector, en especial en 2020",
                    ("pu_02", "en_01", "ne_08", "ne_09"), ("S10",),
                    ("desvio_tc", "es_pandemia_2020", "evento_mercado", "precio_vs_mediana_canal")),
    "H5": Hipotesis("H5", "Merma técnica",
                    "Diferencia estable dentro del rango técnico admitido",
                    ("empresa", "normativa"), (),
                    ("pct_diferencia",)),
}

# Hipótesis principal de cada señal (la primera que la declara: S1 apoya H1 y, si desaparece al normalizar, H2)
SENAL_A_HIPOTESIS: dict[str, str] = {}
for _h in HIPOTESIS.values():
    for _s in _h.senales:
        SENAL_A_HIPOTESIS.setdefault(_s, _h.codigo)
