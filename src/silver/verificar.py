"""Verificación local de las tablas Silver contra los conteos del diccionario (WP 0.2).

Procesa una carpeta con los archivos reales de la empresa y muestra SOLO números:
filas por tabla, filas esperadas y métricas de calidad. No imprime ningún valor
de los datos, así que la salida se puede pegar en un pull request o en el informe.

Uso:
  python -m src.silver.verificar --origen "C:/ruta/a/los/archivos"
  python -m src.silver.verificar --origen "C:/ruta" --guardar    # deja docs/evidencias/silver_<fecha>.json
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from src.common import config
from src.silver import contratos, procesar

EXTENSIONES = {".xlsx", ".xls"}


def verificar(origen: Path) -> dict:
    if not Path(origen).is_dir():
        raise SystemExit(f"No existe la carpeta '{origen}'. Revise la ruta de --origen.")
    archivos = sorted(p for p in Path(origen).rglob("*") if p.suffix.lower() in EXTENSIONES and not p.name.startswith("~$"))
    controles, sin_contrato = [], []
    for a in archivos:
        t0 = time.perf_counter()
        for r in procesar.procesar_archivo(str(a)):
            if r.get("estado") == "sin_contrato":
                sin_contrato.append(a.name)
            else:
                controles.append({**r, "segundos": round(time.perf_counter() - t0, 2)})

    tablas = {}
    for nombre, c in contratos.cargar().items():
        df = procesar.leer_tabla(nombre)
        propios = [x for x in controles if x.get("tabla") == nombre]
        tablas[nombre] = {
            "filas": len(df),
            "filas_esperadas": c.filas_esperadas,
            "placas_distintas": int(df["placa_norm"].nunique()) if "placa_norm" in df.columns else None,
            "fuentes": [{k: x.get(k) for k in ("fuente", "estado", "filas_leidas", "filas_efectivas", "filas_salida",
                                               "filas_con_llave_repetida", "descartes", "calidad", "celdas_con_dato", "segundos")} for x in propios],
            "hojas_rechazadas": [h["motivo"] for x in propios for h in x.get("hojas", []) if h["estado"] == "rechazada"],
            "hojas_cortadas": [f"{x['fuente']} · {h['hoja']}: leídas {h['filas_leidas']}, con dato {h['filas_efectivas']}"
                               for x in propios for h in x.get("hojas", []) if h.get("cortada_por_filas_vacias")],
            "pendiente": list(c.pendiente),
        }
    return {"fecha": date.today().isoformat(), "archivos_en_origen": len(archivos),
            "archivos_sin_contrato": len(sin_contrato), "tablas": tablas}


def imprimir(res: dict) -> None:
    print(f"Archivos en la carpeta: {res['archivos_en_origen']} · sin contrato todavía: {res['archivos_sin_contrato']}\n")
    print(f"{'Tabla':<20}{'Filas':>9}{'Esperadas':>11}  Fuentes")
    for nombre, t in res["tablas"].items():
        fuentes = ", ".join(f"{f['fuente']}={f['filas_salida']}" for f in t["fuentes"]) or "sin archivo de origen"
        print(f"{nombre:<20}{t['filas']:>9}{str(t['filas_esperadas'] or '-'):>11}  {fuentes}")
    print()
    for nombre, t in res["tablas"].items():
        for f in t["fuentes"]:
            print(f"[{nombre} · {f['fuente']}] leídas {f.get('filas_leidas')} · efectivas {f.get('filas_efectivas')} · "
                  f"salida {f.get('filas_salida')} · con llave repetida {f.get('filas_con_llave_repetida')} · {f.get('segundos')} s")
            print(f"    descartes: {f.get('descartes')}")
            print(f"    calidad:   {f.get('calidad')}")
            print(f"    celdas con dato: {f.get('celdas_con_dato')}")
        for motivo in t["hojas_rechazadas"]:
            print(f"    HOJA RECHAZADA: {motivo}")
        for aviso in t["hojas_cortadas"]:
            print(f"    hoja cortada por filas vacías: {aviso}")
        if t["placas_distintas"] is not None:
            print(f"    placas distintas en {nombre}: {t['placas_distintas']}")


# Columnas de catálogo (productos, unidades de medida, estados). No identifican a personas.
CATALOGOS = {"ventas_detalle": ["unidad_medida", "articulo", "kg_origen"],
             "ventas_unidad_mes": ["unidad_medida", "tipo", "unidad_negocio", "articulo"],
             "compras_glp": ["tipo", "estado", "estado_fecha", "centro_costo"],
             "scop": ["producto", "estado"],
             "unidades": ["clase", "uso", "estado_soat"]}


def imprimir_catalogos(maximo: int = 40) -> None:
    """Valores distintos de las columnas de catálogo, con su frecuencia. Sirve para ajustar la limpieza."""
    for tabla, columnas in CATALOGOS.items():
        df = procesar.leer_tabla(tabla)
        for col in columnas:
            conteo = df[col].value_counts(dropna=False).head(maximo)
            print(f"\n[{tabla}.{col}] {df[col].nunique()} valores distintos")
            for valor, n in conteo.items():
                print(f"    {n:>6}  {valor}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--origen", type=Path, required=True, help="carpeta con los Excel de la empresa")
    ap.add_argument("--guardar", action="store_true", help="guarda el resultado en docs/evidencias/")
    ap.add_argument("--catalogos", action="store_true",
                    help="lista los valores de las columnas de catálogo (productos, unidades, estados)")
    a = ap.parse_args()
    config.LAKE_URI = "file://data/lake_verificacion"     # siempre local: nunca escribe en S3
    resultado = verificar(a.origen)
    imprimir(resultado)
    if a.catalogos:
        imprimir_catalogos()
    if a.guardar:
        destino = config.RAIZ_REPO / "docs" / "evidencias" / f"silver_{resultado['fecha']}.json"
        destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nGuardado en {destino.relative_to(config.RAIZ_REPO)}")
