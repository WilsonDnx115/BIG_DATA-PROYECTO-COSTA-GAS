"""Orquestador local de extremo a extremo (equivale a la cadena de AWS).

  muestra → Bronze (+manifiesto) → Lambda Bronze→Silver → movimientos
          → Glue conciliación (Gold) → señales (fact_alerta) → features
          → modelo base MAD → modelo definitivo → evidencias

Uso:
  python -m src.pipeline                       # todo con la muestra sintética y motor pandas
  python -m src.pipeline --motor spark         # Gold con PySpark local
  python -m src.pipeline --origen data/raw     # datos reales (requiere SEUDONIMO_SAL)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.common import config

EVID = config.RAIZ_REPO / "docs" / "evidencias"


def _guardar(nombre: str, obj) -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / nombre).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def correr(origen: Path | None, motor: str, regenerar_muestra: bool) -> dict:
    from src.bronze_to_silver import handler
    from src.common import muestra
    from src.ingest import internos
    from src.models import base_mad, definitivo
    from src.quality import linea_base, volumen
    from src.signals import senales
    from src.silver_to_gold import conciliacion, features

    os.environ.setdefault("SEUDONIMO_SAL", "sal-local-solo-para-muestra")
    resumen: dict = {"lake_uri": config.LAKE_URI, "motor": motor}

    if origen is None:
        origen = muestra.DESTINO
        if regenerar_muestra or not origen.exists():
            resumen["muestra"] = muestra.generar()

    print("1) Ingesta a Bronze (ELT, inmutable, manifiesto)")
    archivos = internos.ingerir(origen)
    resumen["bronze_archivos"] = len(archivos)

    print("2) Bronze → Silver (pandas, esquema declarado, calidad)")
    calidad = {}
    for a in archivos:
        r = handler.procesar_archivo(a)
        calidad[r["fuente"]] = {k: r.get(k) for k in ("filas_entrada", "filas_salida", "rechazadas")}
    resumen["silver"] = calidad
    resumen["movimientos"] = len(handler.construir_movimientos())

    print(f"3) Silver → Gold: conciliación ({motor})")
    resumen["gold_conciliacion"] = conciliacion.ejecutar(motor)

    print("4) Señales determinísticas → gold/fact_alerta")
    alertas = senales.calcular_todas()
    senales.guardar(alertas)
    resumen["senales"] = senales.resumen(alertas).to_dict(orient="records")

    print("5) Features unidad-mes y modelo base (MAD)")
    um = features.unidad_mes()
    features.guardar(um)
    y = base_mad.etiqueta_debil(um, alertas)
    base = base_mad.puntuar(um)
    resumen["modelo_base"] = base_mad.metricas(base, y)
    _guardar("linea_base_tecnica.json", resumen["modelo_base"])
    base_mad.top_k(base).to_csv(EVID / "top20_base.csv", index=False)

    print("6) Modelo definitivo (Isolation Forest vs LOF, partición temporal)")
    feats = [f for f in features.FEATURES if f != "flag_placa_divergente"]  # evita fuga con la etiqueta débil
    res = definitivo.ajustar(um, y, feats)
    res["tabla"].to_csv(EVID / "rejilla_modelos.csv", index=False)
    resumen["modelo_definitivo"] = res["mejor"]
    _guardar("modelo_definitivo.json", res["mejor"])

    verdad_f = origen / "_verdad_sintetica.json"
    if verdad_f.exists():          # solo con la muestra: ¿los modelos recuperan las unidades inyectadas?
        anom = set(json.loads(verdad_f.read_text(encoding="utf-8"))["unidades_anomalas"])
        yv = um["placa_norm"].isin(anom).astype(int)
        p = res["puntuado"]
        resumen["validacion_sintetica"] = {
            "precision@20_base_vs_verdad": base_mad.precision_at_k(base["puntaje"], yv),
            "precision@20_definitivo_vs_verdad": base_mad.precision_at_k(p["puntaje_modelo"], yv.loc[p.index]),
        }

    print("7) Evidencias: línea base y volumen")
    _guardar("linea_base.json", linea_base.calcular())
    (EVID / "volumen.md").write_text("# Volumen por capa (1.7.1)\n\n" + volumen.a_markdown(volumen.medir()) + "\n",
                                     encoding="utf-8")
    _guardar("resumen_pipeline.json", resumen)
    return resumen


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--origen", type=Path, default=None)
    ap.add_argument("--motor", choices=["pandas", "spark"], default="pandas")
    ap.add_argument("--regenerar-muestra", action="store_true")
    a = ap.parse_args()
    r = correr(a.origen, a.motor, a.regenerar_muestra)
    print(json.dumps({k: r[k] for k in ("bronze_archivos", "silver", "movimientos", "gold_conciliacion",
                                        "modelo_base", "modelo_definitivo") if k in r} | {"validacion_sintetica": r.get("validacion_sintetica")}, indent=2, default=str))
