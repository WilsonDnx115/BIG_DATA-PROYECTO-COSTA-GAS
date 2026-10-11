"""Línea base sobre Bronze, sin limpiar, deduplicar filas ni depender de Silver.

Uso: python -m src.quality.linea_base --tipo-datos sinteticos
Los faltantes se declaran como no disponibles, nunca como mediciones cero.
Solo se publican agregados: ningún documento, nombre o placa sale en el JSON.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.bronze_to_silver.handler import leer_crudo
from src.common import config, limpieza, schemas, rutas

REFERENCIA_PLAN = {
    "dias_produccion": 22, "dias_residuo_cero": 22, "registros_scop": 79,
    "incidencias_campos_clave": 16, "precio_b10_min": 17.45, "precio_b10_max": 24.15,
}
REFERENCIA_INFORME_V6 = {
    "documento": "Proyecto_BigData_CostaGas_Trujillo_final_v6.docx",
    "tabla": "1.5",
    "stock_octubre_2018": {"dias": 31, "dias_residuo_cero": 31, "cierres_medidos_fisicamente": 0},
    "ordenes_scop_enero_julio_2023": 29,
    "problemas_calidad_catalogados": 23,
    "precio_b10_2020": {"p05": 19.11, "p95": 29.91, "p50": 21.44},
    "documentos_grupo_longitud_invalida": 23,
    "documentos_grupo_vacios": 85,
    "nota_documentos": "Sección 3.3; el porcentaje requiere el denominador del maestro del grupo.",
}


def _leer_bronze(fecha_carga: str | None) -> tuple[dict, dict]:
    tablas, cobertura = {}, {}
    for codigo, fuente in schemas.FUENTES_LINEA_BASE.items():
        prefijo = rutas.ruta("bronze", "interno", "estructurado", fuente.proceso, codigo) + "/"
        if prefijo.startswith("s3://"):
            import awswrangler as wr  # noqa: PLC0415

            archivos = wr.s3.list_objects(prefijo)
        else:
            archivos = [f.as_posix() for f in Path(prefijo).rglob("*") if f.is_file()]
        # La última versión de cada archivo lógico evita sumar sus reentregas.
        versiones = {}
        for archivo in sorted(archivos):
            if Path(archivo).suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                continue
            rel = archivo[len(prefijo):]
            m = re.fullmatch(r"fecha_carga=(\d{4}-\d{2}-\d{2})/(.+)", rel)
            if not m or (fecha_carga and m[1] != fecha_carga):
                continue
            pd.Timestamp(m[1])  # una fecha imposible no define una entrega válida
            if m[2] not in versiones or m[1] > versiones[m[2]][0]:
                versiones[m[2]] = (m[1], archivo)
        partes = []
        for _, archivo in sorted(versiones.values()):
            crudo = leer_crudo(archivo)
            if not set(fuente.columnas).issubset(crudo.columns):
                raise ValueError(f"{codigo}: Bronze no cumple el contrato de línea base; revisar schemas.py")
            partes.append(crudo[list(fuente.columnas)].rename(
                columns={orig: dest for orig, (dest, _) in fuente.columnas.items()}))
        tablas[codigo] = pd.concat(partes, ignore_index=True) if partes else None
        cobertura[codigo] = {
            "archivos": len(partes), "filas_bronze": sum(len(p) for p in partes),
            "fechas_carga": sorted({v[0] for v in versiones.values()}),
            "estado": "disponible" if partes else "sin_archivos",
        }
    if not any(c["archivos"] for c in cobertura.values()):
        raise FileNotFoundError("No hay fuentes de línea base en Bronze para la entrega seleccionada.")
    return tablas, cobertura


def _numeros(serie: pd.Series) -> pd.Series:
    n = pd.to_numeric(serie, errors="coerce").fillna(
        pd.to_numeric(serie.map(limpieza.a_kg), errors="coerce")).astype(float)
    n = n.mask(serie.map(lambda v: isinstance(v, (bool, np.bool_))))
    return n.where(np.isfinite(n))


def _texto(serie: pd.Series) -> pd.Series:
    return serie.astype("string").fillna("").str.strip()


def _fechas(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["fecha"], format="mixed", dayfirst=True, errors="coerce")


def _en_alcance(df: pd.DataFrame) -> pd.Series:
    return _fechas(df).dt.year.between(config.ANIO_INI, config.ANIO_FIN)


def _documentos(df: pd.DataFrame | None) -> dict | None:
    if df is None:
        return None
    texto = _texto(df["documento_raw"]).str.replace(r"^(\d+)\.0+$", r"\1", regex=True)
    vacios = texto.eq("")
    longitud = ~texto.str.len().isin([8, 11]) & ~vacios
    formato = ~texto.str.fullmatch(r"\d{8}|\d{11}") & ~vacios & ~longitud
    dv = texto.str.fullmatch(r"\d{11}") & ~texto.map(limpieza.ruc_valido)
    total, informados, invalidos = len(df), int((~vacios).sum()), int(longitud.sum())
    return {
        "total": total, "informados": informados, "vacios": int(vacios.sum()),
        "longitud_invalida": invalidos, "formato_invalido_con_longitud_correcta": int(formato.sum()),
        "ruc_digito_verificador_invalido": int(dv.sum()),
        "pct_longitud_invalida": round(100 * invalidos / total, 4) if total else None,
        "pct_longitud_invalida_entre_informados": round(100 * invalidos / informados, 4) if informados else None,
        "criterio": "8 o 11 caracteres, sin rellenar ceros; vacíos y dígito verificador se cuentan aparte",
        "denominador_pct_longitud_invalida": "todas las filas del maestro en Bronze",
    }


def _incidencias(tablas: dict) -> dict:
    por_campo, filas_afectadas = {}, {}
    for codigo, df in tablas.items():
        if df is None:
            por_campo[codigo] = None
            filas_afectadas[codigo] = None
            continue
        controles = {}
        for col, tipo in schemas.FUENTES_LINEA_BASE[codigo].columnas.values():
            if tipo == "date":
                controles[col] = ~_en_alcance(df)
            elif tipo in {"double", "int"}:
                numero = _numeros(df[col])
                controles[col] = numero.isna()
                if col in {"kg", "precio", "tipo_cambio", "capacidad_kg"}:
                    controles[col] |= numero.le(0)
                if col == "linea":
                    controles[col] |= numero.lt(0) | numero.mod(1).ne(0)
                if col == "produccion":
                    controles[col] |= numero.lt(0)  # ajuste, no medición física
                if col in {"stock_inicial", "stock_final", "ventas", "bonificaciones"}:
                    controles[col] |= numero.lt(0)
            elif "placa" in col:
                controles[col] = df[col].map(lambda v: limpieza.normalizar_placa(v)[0]).isna()
            elif col == "documento_raw":
                t = _texto(df[col]).str.replace(r"^(\d+)\.0+$", r"\1", regex=True)
                controles[col] = ~t.str.fullmatch(r"\d{8}|\d{11}")
            else:
                controles[col] = _texto(df[col]).eq("")
        if codigo == "red_02":
            t = _texto(df["documento_raw"]).str.replace(r"^(\d+)\.0+$", r"\1", regex=True)
            controles["documento_raw"] |= t.str.fullmatch(r"\d{11}") & ~t.map(limpieza.ruc_valido)
        clave = list(schemas.FUENTES_LINEA_BASE[codigo].clave_unica)
        controles["clave_unica"] = df.duplicated(clave, keep="first")
        por_campo[codigo] = {campo: int(mask.sum()) for campo, mask in controles.items()}
        filas_afectadas[codigo] = int(pd.DataFrame(controles).any(axis=1).sum())
    return {
        "por_campo": por_campo,
        "total_ocurrencias": sum(sum(c.values()) for c in por_campo.values() if c is not None),
        "filas_afectadas_por_fuente": filas_afectadas,
        "definicion": "Una ocurrencia por fila y control de campo, más duplicados por clave; una fila puede fallar varios controles.",
        "limite": "No equivale al número de problemas catalogados en el informe ni a una validación externa de SCOP/SUNAT.",
    }


def _stock(df: pd.DataFrame | None) -> dict | None:
    if df is None:
        return None
    df = df.loc[_en_alcance(df)].copy()
    fechas = _fechas(df).dt.normalize()
    cols = ["stock_inicial", "produccion", "ventas", "bonificaciones", "stock_final"]
    n = df[cols].apply(_numeros)
    completos = n.notna().all(axis=1)
    duplicados = fechas.duplicated(keep=False)
    evaluables = completos & ~duplicados
    residuo = n.stock_inicial + n.produccion - n.ventas - n.bonificaciones - n.stock_final
    cero = pd.Series(np.isclose(residuo, 0, atol=config.TOL_RESIDUO_STOCK, rtol=0), index=df.index)
    mes_v6 = fechas.dt.year.eq(2018) & fechas.dt.month.eq(10)
    return {
        "dias_produccion": int(fechas.nunique()), "dias_evaluables": int(evaluables.sum()),
        "dias_residuo_cero": int((evaluables & cero).sum()),
        "dias_con_residuo": int((evaluables & ~cero).sum()),
        "filas_incompletas": int((~completos).sum()),
        "dias_con_registros_duplicados": int(fechas[duplicados].nunique()),
        "producciones_negativas": int(n.produccion.lt(0).sum()),
        "octubre_2018": {"dias": int(fechas[mes_v6].nunique()),
                         "dias_residuo_cero": int((mes_v6 & evaluables & cero).sum())},
        "ecuacion": "stock_inicial + produccion - ventas - bonificaciones - stock_final",
        "tolerancia_absoluta": config.TOL_RESIDUO_STOCK,
        "advertencia": "Residuo cero no demuestra una medición física independiente ni ausencia de pérdidas.",
    }


def _precios(df: pd.DataFrame | None, solo_2020: bool = False) -> dict | None:
    if df is None:
        return None
    mask = _en_alcance(df) & _texto(df["id_producto"]).eq("B10")
    if solo_2020:
        mask &= _fechas(df).dt.year.eq(2020)
    b10 = df.loc[mask].copy()
    b10["precio"] = _numeros(b10.precio)
    validos = b10.precio.notna() & b10.precio.gt(0)
    def resumen(s):
        return {"filas": len(s), "min": round(float(s.min()), 2), "max": round(float(s.max()), 2),
                "p05": round(float(s.quantile(.05)), 2), "p50": round(float(s.median()), 2),
                "p95": round(float(s.quantile(.95)), 2)}
    canales = _texto(b10.canal)
    por_canal = {c: resumen(g.precio) for c, g in b10.loc[validos & canales.ne("")].groupby(canales)}
    return {
        "por_canal": por_canal, "global": resumen(b10.loc[validos, "precio"]) if validos.any() else None,
        "filas_precio_invalido": int((~validos).sum()), "filas_sin_canal": int(canales.eq("").sum()),
        "unidad": "S/ por balón de 10 kg; Price del contrato com_19, sin convertir desde precio/kg",
        "periodo": "2020" if solo_2020 else f"{config.ANIO_INI}–{config.ANIO_FIN}",
    }


def _comparar(stock, scop, incidencias, precios, precios_2020) -> list[dict]:
    global_p = precios["global"] if precios else None
    global_v6 = precios_2020["global"] if precios_2020 else None
    valores = [
        ("PLAN.md", "dias_residuo_cero", stock["dias_residuo_cero"] if stock else None, 22),
        ("PLAN.md", "registros_scop", scop, 79),
        ("PLAN.md", "precio_b10_min", global_p["min"] if global_p else None, 17.45),
        ("PLAN.md", "precio_b10_max", global_p["max"] if global_p else None, 24.15),
        ("informe_v6", "dias_octubre_2018", stock["octubre_2018"]["dias"] if stock else None, 31),
        ("informe_v6", "dias_residuo_cero_octubre_2018", stock["octubre_2018"]["dias_residuo_cero"] if stock else None, 31),
    ]
    for k, ref in REFERENCIA_INFORME_V6["precio_b10_2020"].items():
        valores.append(("informe_v6", f"precio_b10_2020_{k}", global_v6[k] if global_v6 else None, ref))
    comparacion = [
        {"referencia": ref, "indicador": k, "calculado": valor, "esperado": esperado,
         "estado": "no_disponible" if valor is None else "coincide_numericamente" if np.isclose(valor, esperado) else "difiere",
         "diferencia": round(valor - esperado, 4) if valor is not None else None}
        for ref, k, valor, esperado in valores
    ]
    for ref, esperado in (("PLAN.md", 16), ("informe_v6", 23)):
        comparacion.append({"referencia": ref, "indicador": "incidencias_campos_clave",
                            "calculado": incidencias["total_ocurrencias"], "esperado": esperado,
                            "estado": "no_comparable", "motivo": "Ocurrencias fila/control frente a problemas catalogados; falta el catálogo original para igualar definiciones."})
    comparacion.append({"referencia": "informe_v6", "indicador": "ordenes_scop_enero_julio_2023",
                        "calculado": None, "esperado": 29, "estado": "no_comparable",
                        "motivo": "aba_02 es el contrato sintético v2; F05 y sus encabezados v3 no están declarados en este checkout."})
    return comparacion


def calcular(fecha_carga: str | None = None, tipo_datos: str = "no_declarado") -> dict:
    """Calcula agregados de las fuentes declaradas, con cobertura y referencias."""
    if tipo_datos not in {"sinteticos", "reales", "no_declarado"}:
        raise ValueError("tipo_datos debe ser sinteticos, reales o no_declarado")
    tablas, cobertura = _leer_bronze(fecha_carga)
    compras = tablas["aba_02"]
    compras = compras.loc[_en_alcance(compras)] if compras is not None else None
    scop = int(_texto(compras.codigo_scop).ne("").sum()) if compras is not None else None
    stock = _stock(tablas["pro_01"])
    documentos = _documentos(tablas["red_02"])
    incidencias = _incidencias(tablas)
    precios, precios_2020 = _precios(tablas["com_19"]), _precios(tablas["com_19"], solo_2020=True)
    return {
        "capa_origen": "bronze", "tipo_datos": tipo_datos, "lake_uri": config.LAKE_URI,
        "alcance": {"anio_ini": config.ANIO_INI, "anio_fin": config.ANIO_FIN,
                    "nota": "Se presupone entrega de Trujillo: los contratos actuales no tienen columna planta."},
        "seleccion_entregas": fecha_carga or "última versión por archivo lógico de cada fuente",
        "cobertura": cobertura,
        "stock": stock, "registros_scop": scop,
        "pct_compras_con_scop": round(100 * scop / len(compras), 4) if compras is not None and len(compras) else None,
        "documentos_maestro": documentos, "incidencias": incidencias,
        "precio_b10": precios, "precio_b10_2020": precios_2020,
        "referencia_plan": REFERENCIA_PLAN, "referencia_informe_v6": REFERENCIA_INFORME_V6,
        "comparacion": _comparar(stock, scop, incidencias, precios, precios_2020),
        "nota": "Las coincidencias numéricas no prueban reproducción del informe: verificar tipo de datos, período, fuente y definición. Las fuentes ausentes se declaran null.",
    }


def guardar(resultado: dict, destino: Path | None = None) -> Path:
    """Persiste solamente agregados en la evidencia local del repositorio."""
    destino = destino or config.RAIZ_REPO / "docs" / "evidencias" / "linea_base.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fecha-carga", help="Entrega YYYY-MM-DD; por defecto última versión por archivo")
    ap.add_argument("--tipo-datos", choices=["sinteticos", "reales", "no_declarado"], default="no_declarado")
    ap.add_argument("--salida", type=Path, help="Ruta del JSON; por defecto docs/evidencias/linea_base.json")
    args = ap.parse_args()
    resultado = calcular(args.fecha_carga, args.tipo_datos)
    print(f"Evidencia agregada guardada en {guardar(resultado, args.salida)}")
    