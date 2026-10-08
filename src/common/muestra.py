"""Generador de la muestra sintética y anonimizada (paso 3.8.5).

Produce archivos con el MISMO formato que las fuentes internas (encabezados del
diccionario v2.0) para que el pipeline completo pueda correr sin datos reales.
Inyecta a propósito los problemas de la Tabla 3.5 (placas en cuatro formas,
placa+fecha en una celda, RUC con ceros perdidos, «5 000 kg», TRUE en kg,
duplicados, fechas fuera de rango) y anomalías conocidas (S1, S4, S7, S8, S10)
para poder medir si las señales y modelos las recuperan.

Uso:  python -m src.common.muestra --unidades 25 --semilla 42
Nada de aquí representa a personas o unidades reales.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.common import config

DESTINO = config.RAIZ_REPO / "data" / "sample" / "entrega"
PRODUCTOS = {"B05": 5, "B10": 10, "B15": 15, "B45": 45, "GRANEL": 1}
PESO_PRODUCTO = [0.08, 0.62, 0.12, 0.10, 0.08]          # B10 concentra (data skew, S3)
CANALES = {"MAYORISTA": 1.75, "MINORISTA": 2.20, "DIRECTO": 2.40}  # S/ por kg (≈ 17.5–24 el B10)


def _placa(rng) -> str:
    letras = "ABCDFHMTUVWX"
    return f"{rng.choice(list(letras))}{rng.integers(1, 9)}{rng.choice(list(letras))}{rng.integers(100, 999)}"


def _ensuciar_placa(placa: str, rng) -> str:
    """Cuatro formas de escribir la misma placa (Tabla 3.5)."""
    forma = rng.integers(0, 4)
    return [placa, f"{placa[:3]}-{placa[3:]}", f"{placa[:3].lower()} {placa[3:]}", f" {placa} "][forma]


def _ruc(rng, prefijo="20") -> str:
    base = prefijo + "".join(str(d) for d in rng.integers(0, 10, 8))
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    dv = 11 - sum(int(a) * b for a, b in zip(base, pesos)) % 11
    return base + str({10: 0, 11: 1}.get(dv, dv))


def generar(n_unidades: int = 25, semilla: int = config.SEMILLA, destino: Path = DESTINO) -> dict:
    rng = np.random.default_rng(semilla)
    destino = Path(destino)

    # --- Flota (DIS-01) -------------------------------------------------------
    placas = sorted({_placa(rng) for _ in range(n_unidades * 2)})[:n_unidades]
    anomalas = set(rng.choice(placas, size=max(2, n_unidades // 8), replace=False))
    no_habilitadas = set(rng.choice([p for p in placas if p not in anomalas], size=2, replace=False))
    flota = pd.DataFrame({
        "PLACA": [_ensuciar_placa(p, rng) for p in placas],
        "Capacidad Total de GLP Autorizado (KG)": rng.choice([3000, 4500, 6000, 8000], len(placas)),
        "TRASLADO DE GAS (SI/NO)": ["NO" if p in no_habilitadas else rng.choice(["SI", "Si", "si"]) for p in placas],
        "TIPO UNIDAD": rng.choice(["CAMION", "FURGON"], len(placas)),
        "CONDUCTOR": [f"CONDUCTOR SINTETICO {i:03d}" for i in range(len(placas))],
    })
    cap = dict(zip(placas, flota["Capacidad Total de GLP Autorizado (KG)"]))

    # --- Maestro de distribuidores (RED-02) ----------------------------------
    n_cli = n_unidades * 5
    docs = []
    for _ in range(n_cli):
        r = rng.random()
        if r < 0.55:
            docs.append(_ruc(rng, rng.choice(["10", "20"])))
        elif r < 0.75:
            docs.append(str(rng.integers(1_000_000, 9_999_999)))         # DNI sin cero inicial (7 dígitos)
        elif r < 0.85:
            docs.append(_ruc(rng)[:-1] + str((int(_ruc(rng)[-1]) + 1) % 10))  # RUC con dígito errado
        else:
            docs.append("")
    maestro = pd.DataFrame({
        "CardCode": [f"C{i:05d}" for i in range(n_cli)],
        "RUC/DNI": docs,
        "CAP. ALMAC. TOTAL (KG)": [f"{c:,} kg".replace(",", " ") for c in rng.choice([5000, 10000, 20000, 40000], n_cli)],
        "ESTADO": rng.choice(["Activo", "ACTIVO", "activo", "Baja"], n_cli, p=[0.4, 0.4, 0.15, 0.05]),
        "CANAL": rng.choice(list(CANALES), n_cli, p=[0.3, 0.5, 0.2]),
    })
    canal_cli = dict(zip(maestro["CardCode"], maestro["CANAL"]))

    # --- Tipo de cambio diario (PU-02, formato BCRPData) ---------------------
    dias = pd.date_range(f"{config.ANIO_INI}-01-01", f"{config.ANIO_FIN}-12-31", freq="B")
    tc = 3.30 + np.cumsum(rng.normal(0, 0.004, len(dias))).clip(-0.3, 0.6)
    tc_dia = dict(zip(dias.date, tc.round(3)))
    bcrp = {"config": {"series": [{"name": "Tipo de cambio - compra (S/ por US$)"}]},
            "periods": [{"name": d.strftime("%d.%b.%y"), "values": [f"{v:.3f}"]} for d, v in tc_dia.items()]}

    # --- Compras (ABA-02) y ventas (COM-19) ---------------------------------
    compras, ventas = [], []
    n_doc, n_scop = 100000, 500000
    for anio in range(config.ANIO_INI, config.ANIO_FIN + 1):
        pandemia = 0.75 if anio == 2020 else 1.0
        for mes in range(1, 13):
            for p in placas:
                for _ in range(rng.poisson(4 * pandemia)):
                    dia = date(anio, mes, int(rng.integers(1, 29)))
                    prod = rng.choice(list(PRODUCTOS), p=PESO_PRODUCTO)
                    kg = float(round(cap[p] * rng.uniform(0.55, 0.95), 1))
                    if rng.random() < 0.01:
                        kg = float(round(cap[p] * rng.uniform(1.10, 1.35), 1))  # S4
                    n_doc += 1
                    n_scop += 1
                    scop = f"{n_scop}" if rng.random() > 0.03 else ""              # compra sin SCOP
                    fact = p
                    if p in anomalas and rng.random() < 0.20:
                        fact = rng.choice([x for x in placas if x != p])          # S1
                    fact_txt = _ensuciar_placa(fact, rng)
                    if rng.random() < 0.15:
                        fact_txt = f"{fact_txt} {dia:%d/%m/%Y}"                   # placa + fecha
                    tc_reg = tc_dia.get(dia, 3.5) * (1 + (rng.normal(0, 0.03) if rng.random() < 0.02 else 0))
                    kg_txt: object = kg if rng.random() > 0.004 else "TRUE"      # fórmula rota
                    compras.append({
                        "SCOP": scop, "FECHA": dia.isoformat(), "PLACA CARGADA": _ensuciar_placa(p, rng),
                        "PLACA FACTURADA": fact_txt, "PRODUCTO": prod, "KG": kg_txt,
                        "T.C.": round(tc_reg, 3), "N DOC": f"F{n_doc}",
                        "ESTADO": rng.choice(["Atendido", "ATENDIDO", "atendido"]),
                    })
                    # Ventas: el faltante se concentra en unidades anómalas (H1) + merma técnica (H5)
                    merma = rng.uniform(0.0, config.MERMA_TECNICA * 2)
                    if p in anomalas and rng.random() < 0.35:
                        merma += rng.uniform(0.04, 0.10)
                    restante = kg * (1 - merma)
                    n_lin = int(rng.integers(2, 6))
                    partes = rng.dirichlet(np.ones(n_lin)) * restante
                    for linea, kv in enumerate(partes):
                        cli = f"C{int(rng.integers(0, n_cli)):05d}"
                        canal = canal_cli[cli]
                        precio_kg = CANALES[canal] * (1 + 0.02 * (anio - 2016)) * rng.normal(1, 0.03)
                        if rng.random() < 0.01:
                            precio_kg *= rng.uniform(0.6, 0.8)                     # S10
                        scop_v = scop if rng.random() > 0.01 else f"{rng.integers(900000, 999999)}"  # S8
                        ventas.append({
                            "DocNum": f"V{n_doc}", "LineNum": linea, "DocDate": dia.isoformat(),
                            "CardCode": cli, "U_CTG_SCOPNUM": scop_v, "U_PLACA": _ensuciar_placa(p, rng),
                            "ItemCode": prod, "Kg": round(float(kv), 1),
                            "Price": round(precio_kg * PRODUCTOS[prod], 2) if prod != "GRANEL" else round(precio_kg, 2),
                            "Canal": canal,
                        })
    compras = pd.DataFrame(compras)
    ventas = pd.DataFrame(ventas)
    # Duplicados y fechas fuera de alcance (Tabla 3.5 / 3.7)
    ventas = pd.concat([ventas, ventas.sample(frac=0.005, random_state=semilla)], ignore_index=True)
    malas = compras.sample(n=5, random_state=semilla).index
    compras.loc[malas, "FECHA"] = (date(config.ANIO_INI, 1, 1) - timedelta(days=30)).isoformat()

    # --- Escritura con estructura <proceso>/<codigo>/<archivo original> -----
    salidas = {
        "abastecimiento/aba_02/ABA-02 Ordenes SCOP.csv": compras,
        "comercial/com_19/COM-19 Lineas de venta.csv": ventas,
        "distribucion/dis_01/DIS-01 Vehiculos.csv": flota,
        "redes/red_02/RED-02 Distribuidores.csv": maestro,
    }
    for rel, df in salidas.items():
        f = destino / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(f, index=False, encoding="utf-8")
    f = destino / "externo" / "bcrp_tc" / "PD04640PD.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(bcrp), encoding="utf-8")

    verdad = {"unidades_anomalas": sorted(anomalas), "no_habilitadas": sorted(no_habilitadas),
              "compras": len(compras), "ventas": len(ventas), "semilla": semilla}
    (destino / "_verdad_sintetica.json").write_text(json.dumps(verdad, indent=2), encoding="utf-8")
    return verdad


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unidades", type=int, default=25)
    ap.add_argument("--semilla", type=int, default=config.SEMILLA)
    a = ap.parse_args()
    print(json.dumps(generar(a.unidades, a.semilla), indent=2))
