"""Línea base del negocio (paso 1.4.1, Tabla 1.5) calculada sobre Silver.

Valores de referencia del informe (datos reales): 79 registros SCOP,
16 incidencias en campos clave, precio del balón de 10 kg S/ 17.45–24.15.
Con la muestra sintética los números difieren; el script documenta la diferencia.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.common import config, lake_io, rutas

REFERENCIA_INFORME = {"registros_scop": 79, "incidencias_campos_clave": 16,
                      "precio_b10_min": 17.45, "precio_b10_max": 24.15}


def calcular() -> dict:
    leer = lambda *p: lake_io.leer_parquet(rutas.ruta("silver", *p))  # noqa: E731
    compras = leer("compras", "aba_02_ordenes_scop")
    ventas = leer("ventas", "com_19_lineas")
    maestro = leer("maestro", "red_02_distribuidores")

    calidad_dir = Path(rutas.ruta("silver", "_calidad"))
    incidencias = {}
    if calidad_dir.exists():
        for f in sorted(calidad_dir.rglob("*.json")):
            rep = json.loads(f.read_text(encoding="utf-8"))
            for nombre, r in rep["reglas"].items():
                if isinstance(r, dict) and "fallan" in r:
                    incidencias[f"{rep['fuente']}.{nombre}"] = r["fallan"]

    b10 = ventas[ventas["id_producto"] == "B10"].groupby("canal")["precio"]
    precio = {c: {"min": round(float(s.min()), 2), "max": round(float(s.max()), 2),
                  "p50": round(float(s.median()), 2)} for c, s in b10}
    clases = maestro["clase_documento"].value_counts(normalize=True).round(4).to_dict()
    return {
        "registros_scop": int(compras["codigo_scop"].notna().sum()),
        "pct_compras_con_scop": round(float(compras["codigo_scop"].notna().mean()), 4),
        "incidencias_por_regla": incidencias,
        "pct_maestro_documento_invalido_o_vacio": round(clases.get("INVALIDO", 0) + clases.get("VACIO", 0), 4),
        "clases_documento_maestro": clases,
        "precio_b10_por_canal": precio,
        "referencia_informe": REFERENCIA_INFORME,
        "nota": "Con data/sample (sintética) los valores no reproducen el informe; con data/raw sí deben.",
        "lake_uri": config.LAKE_URI,
    }


if __name__ == "__main__":
    r = calcular()
    destino = config.RAIZ_REPO / "docs" / "evidencias" / "linea_base.json"
    destino.write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
