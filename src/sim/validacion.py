"""Validacion del detector con 100 semillas, escenarios A y B (commit AR06).

Mide lo que pide la Tabla 4.8h del informe v16, y lo mide de la unica forma en que el
numero significa algo: **el umbral se fija con el escenario A y la deteccion se mide con
el B sin volver a tocarlo**. Si el umbral se ajustara mirando los robos, la deteccion
que se reporte seria la de un detector que ya sabia la respuesta.

Una sola semilla no dice nada: cada una genera una flota y un ruido distintos, y con
doce unidades la diferencia entre semillas es grande. Por eso el experimento se repite
con 100 semillas, en lotes de 10, y cada lote deja su JSON en

    sim/resultados/lote=<n>.json

Los lotes son independientes a proposito: se pueden correr en tandas, en la Lambda
`costagas-validacion-detector` (W17) o en una laptop, y el cierre de la medicion
(AR19) junta los JSON que existan. Las semillas de cada lote se derivan del numero del
lote, asi que correr el mismo lote dos veces da el mismo resultado.

Lo que no se mide aqui se dice: la especificacion del escenario B no esta en el
repositorio (llega por `ESCENARIO_B_SPEC`, ver `src/sim/escenario_b.py`), asi que sin
ella este modulo no inventa un escenario sin robos: falla.

Uso:
    python -m src.sim.validacion --lote 1
    python -m src.sim.validacion --lotes 10 --destino sim/resultados
"""
from __future__ import annotations

import argparse
import datetime as dt
import statistics

import numpy as np
import pandas as pd

from src.common import config, lake_io, rutas
from src.models import detector
from src.sim import escenario_a, escenario_b

ENTIDAD = "placa_norm"
VALOR = "kg"
PERIODO = "periodo"
GRUPO = "rol"

TAMANO_LOTE = 10
SEMILLAS_TOTALES = 100

# Metas de la Tabla 4.8h. Cada una se compara contra lo medido y el JSON guarda las dos
# cifras, nunca solo el veredicto: un «cumple» sin el numero no se puede revisar.
METAS = {
    "falsas_alarmas_anio": config.FALSAS_ALARMAS_ANIO,      # <= 12, en cada granularidad
    "deteccion_faltantes_2pct": 0.80,                       # >= 80 %
    "semanas_hasta_alarma": 8,                              # <= 8 semanas (serie semanal)
    "error_semana_inicio": 2,                               # <= 2 semanas
    "error_relativo_kg": 0.20,                              # +- 20 %
    "error_relativo_soles": 0.20,                           # +- 20 %
}

# Un robo que afecta a toda la flota (entidad «*» en la especificacion) no lo puede ver
# este detector: compara cada unidad con sus pares, y si todas bajan a la vez el desvio
# relativo no se mueve. Esta en el escenario a proposito, para medir el limite del
# metodo; lo tiene que ver el balance de planta (KPI 1). No entra al denominador de la
# deteccion, y el JSON lo informa aparte para que nadie lo lea como un fallo oculto.
FALTANTE_MINIMO = 0.02


def semillas_del_lote(numero: int, tamano: int = TAMANO_LOTE,
                      base: int | None = None) -> list[int]:
    """Las semillas de un lote, derivadas de su numero para que sea reproducible."""
    if numero < 1:
        raise ValueError("el lote se numera desde 1")
    base = config.SEMILLA if base is None else base
    inicio = base + (numero - 1) * tamano
    return list(range(inicio, inicio + tamano))


def _indice_de_periodos(serie: pd.DataFrame) -> dict:
    return {p: i for i, p in enumerate(sorted(serie[PERIODO].unique()))}


def _primera_alarma(serie_detectada: pd.DataFrame, entidad: str, desde_periodo: str):
    """Primera alarma roja de una entidad **desde** el periodo indicado.

    El «desde» no es un detalle: en el escenario A esa misma unidad puede tener alguna
    alarma falsa antes del robo. Contarla como la deteccion del robo daria un retardo
    negativo y una deteccion que en realidad nadie hizo.
    """
    de_la_entidad = serie_detectada[serie_detectada[ENTIDAD] == entidad].sort_values(
        PERIODO, kind="stable").reset_index(drop=True)
    candidatas = de_la_entidad[(de_la_entidad["estado"] == "rojo")
                               & (de_la_entidad[PERIODO] >= desde_periodo)]
    if candidatas.empty:
        return None
    idx = int(candidatas.index[0])
    primera = de_la_entidad.loc[idx]

    # El inicio se estima para ESTA alarma: la semana siguiente al ultimo cero del CUSUM
    # antes de cruzar. La columna `periodo_inicio` del detector se refiere al primer
    # cruce de toda la serie de la entidad, que es lo que necesita la bandeja de
    # revision, pero aqui se mide el error contra la semana en que empezo este robo.
    ceros = [i for i in range(idx + 1) if float(de_la_entidad.loc[i, "cusum"]) == 0.0]
    inicio = (ceros[-1] + 1) if ceros else 0
    inicio = min(inicio, idx)

    # Los kg se acumulan en esa misma ventana, por coherencia con el inicio de arriba:
    # la columna `kg_acumulados` del detector cuenta desde su propio inicio, que puede
    # ser mucho anterior, y entonces el faltante estimado incluiria semanas sin robo.
    faltante = -pd.to_numeric(de_la_entidad.loc[inicio:idx, "residuo"], errors="coerce")
    kg = float(faltante.fillna(0.0).sum())
    return {"periodo": primera[PERIODO],
            "periodo_inicio": de_la_entidad.loc[inicio, PERIODO],
            "kg_acumulados": kg,
            "soles_acumulados": round(kg * config.PRECIO_REF_KG, 2)}


def _error_relativo(estimado: float, real: float) -> float | None:
    """|estimado − real| ÷ real. None si el real es 0: no hay porcentaje que calcular."""
    if real == 0:
        return None
    return abs(estimado - real) / abs(real)


def medir_escenario_a(datos_a: dict, umbral_semana: dict, umbral_mes: dict) -> dict:
    """Falsas alarmas al año y cuantos eventos legitimos llegan a alerta.

    Toda alarma del escenario A es falsa por construccion: no hay robos. El numero sale
    de la propia calibracion, que es la que lo acota; aqui se agrega lo que el umbral
    hace con los 15 eventos legitimos y con los errores de digitacion, que es la otra
    mitad de la meta («cerca de 0 %»).
    """
    serie = detector.detectar(datos_a["semanal"], ENTIDAD, VALOR, PERIODO, GRUPO,
                              h=umbral_semana["h"], sigma=umbral_semana["sigma"])
    alertadas = serie["estado"].isin(("rojo", "ambar"))
    con_evento = serie["evento"].ne("")
    con_error = serie["error_digitacion"].fillna(False).astype(bool) \
        if "error_digitacion" in serie.columns else pd.Series(False, index=serie.index)

    def _pct(mascara) -> float | None:
        total = int(mascara.sum())
        return None if total == 0 else round(float((alertadas & mascara).sum()) / total, 4)

    return {
        "h": {"semana": umbral_semana["h"], "mes": umbral_mes["h"]},
        "falsas_alarmas_anio": {"semana": umbral_semana["falsas_alarmas_anio"],
                                "mes": umbral_mes["falsas_alarmas_anio"]},
        "falsas_alarmas_total": {"semana": umbral_semana["falsas_alarmas_total"],
                                 "mes": umbral_mes["falsas_alarmas_total"]},
        "eventos_legitimos": int(con_evento.sum()),
        "eventos_legitimos_en_alerta_pct": _pct(con_evento),
        "errores_digitacion": int(con_error.sum()),
        "errores_digitacion_en_alerta_pct": _pct(con_error),
        "periodos_no_evaluables": int((serie["estado"] == "no_evaluable").sum()),
        "cumple_falsas_alarmas": bool(
            umbral_semana["falsas_alarmas_anio"] <= METAS["falsas_alarmas_anio"]
            and umbral_mes["falsas_alarmas_anio"] <= METAS["falsas_alarmas_anio"]),
    }


def medir_escenario_b(datos_b: dict, umbral_semana: dict) -> dict:
    """Deteccion de cada robo con el umbral ya fijado por el escenario A.

    `sigma` y `h` son los de la calibracion: no se recalculan con el escenario B. Esa es
    toda la validez de esta medicion.
    """
    serie = detector.detectar(datos_b["semanal"], ENTIDAD, VALOR, PERIODO, GRUPO,
                              h=umbral_semana["h"], sigma=umbral_semana["sigma"])
    indice = _indice_de_periodos(serie)
    verdad = datos_b["verdad"]

    robos = []
    for robo_id, filas in verdad.groupby("robo_id", sort=True):
        afectadas = sorted(set(filas[ENTIDAD]))
        toda_la_flota = str(filas["entidad_spec"].iloc[0]) == escenario_b.ENTIDAD_TODAS
        robado_kg = float(filas["robado_kg"].sum())
        primera_fecha = min(filas["fecha"])
        primer_periodo = primera_fecha.isoformat() if hasattr(primera_fecha, "isoformat") \
            else str(primera_fecha)

        # Magnitud del faltante: lo robado sobre lo que la unidad habria vendido sin robo.
        kg_tras_robo = float(serie[serie[ENTIDAD].isin(afectadas)
                                   & (serie[PERIODO] >= primer_periodo)][VALOR].sum())
        magnitud = robado_kg / (kg_tras_robo + robado_kg) if (kg_tras_robo + robado_kg) else None

        detalle = []
        for entidad in afectadas:
            alarma = _primera_alarma(serie, entidad, primer_periodo)
            de_esta = filas[filas[ENTIDAD] == entidad]
            kg_de_esta = float(de_esta["robado_kg"].sum())

            # Los kg se comparan en el mismo corte: lo que el detector acumulo hasta su
            # alarma, contra lo que el robo se habia llevado hasta esa misma semana.
            # Compararlo contra el robo completo mediria el retardo, no la estimacion.
            kg_estimados = None if alarma is None else alarma["kg_acumulados"]
            if alarma is None:
                kg_hasta_alarma = None
            else:
                hasta = alarma["periodo"]
                kg_hasta_alarma = float(de_esta[[
                    (f.isoformat() if hasattr(f, "isoformat") else str(f)) <= hasta
                    for f in de_esta["fecha"]]]["robado_kg"].sum())

            soles_estimados = None if alarma is None else alarma["soles_acumulados"]
            soles_inyectados = (None if kg_hasta_alarma is None
                                else round(kg_hasta_alarma * config.PRECIO_REF_KG, 2))
            detalle.append({
                "entidad_detectada": alarma is not None,
                "periodo_alarma": None if alarma is None else alarma["periodo"],
                "semanas_hasta_alarma": (None if alarma is None
                                         else indice[alarma["periodo"]] - indice[primer_periodo]),
                "error_semana_inicio": (None if alarma is None or not alarma["periodo_inicio"]
                                        else abs(indice[alarma["periodo_inicio"]]
                                                 - indice[primer_periodo])),
                "kg_estimados": kg_estimados,
                "kg_inyectados_hasta_la_alarma": kg_hasta_alarma,
                "kg_inyectados_total": kg_de_esta,
                "error_relativo_kg": (None if kg_estimados is None
                                      else _error_relativo(kg_estimados, kg_hasta_alarma)),
                "soles_estimados": soles_estimados,
                "soles_inyectados_hasta_la_alarma": soles_inyectados,
                "error_relativo_soles": (None if soles_estimados is None or soles_inyectados is None
                                         else _error_relativo(soles_estimados, soles_inyectados)),
            })

        detectado = any(d["entidad_detectada"] for d in detalle)
        esperas = [d["semanas_hasta_alarma"] for d in detalle
                   if d["semanas_hasta_alarma"] is not None]
        errores_inicio = [d["error_semana_inicio"] for d in detalle
                          if d["error_semana_inicio"] is not None]
        robos.append({
            "robo_id": str(robo_id),
            "tipo": str(filas["tipo"].iloc[0]),
            "entidades": len(afectadas),
            "robado_kg": round(robado_kg, 2),
            "magnitud_faltante": None if magnitud is None else round(magnitud, 4),
            "faltante_de_2pct_o_mas": bool(magnitud is not None and magnitud >= FALTANTE_MINIMO),
            # Un robo que baja a toda la flota a la vez no lo ve un detector que compara
            # unidades entre si: es el limite del metodo, declarado en el escenario.
            "no_detectable_comparando_unidades": toda_la_flota,
            "detectado": detectado,
            "semanas_hasta_alarma": None if not esperas else int(min(esperas)),
            "error_semana_inicio": None if not errores_inicio else int(min(errores_inicio)),
            "por_entidad": detalle,
        })

    comparables = [r for r in robos
                   if r["faltante_de_2pct_o_mas"] and not r["no_detectable_comparando_unidades"]]
    detectados = [r for r in comparables if r["detectado"]]
    esperas = [r["semanas_hasta_alarma"] for r in detectados if r["semanas_hasta_alarma"] is not None]
    errores_inicio = [r["error_semana_inicio"] for r in detectados
                      if r["error_semana_inicio"] is not None]
    errores_kg = [d["error_relativo_kg"] for r in detectados for d in r["por_entidad"]
                  if d["error_relativo_kg"] is not None]
    errores_soles = [d["error_relativo_soles"] for r in detectados for d in r["por_entidad"]
                     if d["error_relativo_soles"] is not None]

    return {
        "robos": robos,
        "robos_inyectados": len(robos),
        "robos_comparables": len(comparables),
        "robos_detectados": len(detectados),
        "deteccion_faltantes_2pct": (None if not comparables
                                     else round(len(detectados) / len(comparables), 4)),
        "robos_no_detectables_por_diseno": [r["robo_id"] for r in robos
                                            if r["no_detectable_comparando_unidades"]],
        "semanas_hasta_alarma_mediana": None if not esperas else float(statistics.median(esperas)),
        "semanas_hasta_alarma_max": None if not esperas else int(max(esperas)),
        "error_semana_inicio_mediana": (None if not errores_inicio
                                        else float(statistics.median(errores_inicio))),
        "error_relativo_kg_mediana": (None if not errores_kg
                                      else round(float(statistics.median(errores_kg)), 4)),
        "error_relativo_soles_mediana": (None if not errores_soles
                                         else round(float(statistics.median(errores_soles)), 4)),
        "precio_ref_kg": config.PRECIO_REF_KG,
    }


def medir_semilla(semilla: int, ruta_spec=None) -> dict:
    """Una semilla completa: calibra con A, mide con B y no vuelve a tocar el umbral."""
    datos_a = escenario_a.generar(semilla)
    umbral_semana = detector.calibrar_h(datos_a["semanal"], ENTIDAD, VALOR, PERIODO, "semana")
    umbral_mes = detector.calibrar_h(datos_a["mensual"], ENTIDAD, VALOR, PERIODO, "mes")

    datos_b = escenario_b.inyectar(datos_a, ruta_spec)
    return {
        "semilla": int(semilla),
        "escenario_a": medir_escenario_a(datos_a, umbral_semana, umbral_mes),
        "escenario_b": medir_escenario_b(datos_b, umbral_semana),
        "spec": datos_b["spec"],          # huella SHA-256 del archivo con el que se midio
    }


def _mediana(valores) -> float | None:
    limpios = [v for v in valores if v is not None]
    return None if not limpios else round(float(statistics.median(limpios)), 4)


def resumir(medidas: list[dict]) -> dict:
    """Resumen del lote con las cifras de la Tabla 4.8h y si cada meta se cumple.

    El resumen guarda la cifra y la meta juntas. Un «cumple: true» suelto no se puede
    revisar, y esta medicion existe justamente para poder revisarla.
    """
    fa_semana = [m["escenario_a"]["falsas_alarmas_anio"]["semana"] for m in medidas]
    fa_mes = [m["escenario_a"]["falsas_alarmas_anio"]["mes"] for m in medidas]
    deteccion = [m["escenario_b"]["deteccion_faltantes_2pct"] for m in medidas]
    esperas = [m["escenario_b"]["semanas_hasta_alarma_mediana"] for m in medidas]
    inicio = [m["escenario_b"]["error_semana_inicio_mediana"] for m in medidas]
    err_kg = [m["escenario_b"]["error_relativo_kg_mediana"] for m in medidas]
    err_soles = [m["escenario_b"]["error_relativo_soles_mediana"] for m in medidas]

    med_deteccion, med_esperas = _mediana(deteccion), _mediana(esperas)
    med_inicio, med_kg, med_soles = _mediana(inicio), _mediana(err_kg), _mediana(err_soles)

    def _cumple(valor, meta, mayor_es_mejor=False) -> bool | None:
        if valor is None:
            return None                      # no medido: no es ni cumple ni incumple
        return valor >= meta if mayor_es_mejor else valor <= meta

    return {
        "semillas": len(medidas),
        "falsas_alarmas_anio_max": {"semana": max(fa_semana), "mes": max(fa_mes)},
        "falsas_alarmas_anio_mediana": {"semana": _mediana(fa_semana), "mes": _mediana(fa_mes)},
        "h_mediana": {"semana": _mediana([m["escenario_a"]["h"]["semana"] for m in medidas]),
                      "mes": _mediana([m["escenario_a"]["h"]["mes"] for m in medidas])},
        "eventos_legitimos_en_alerta_pct_mediana":
            _mediana([m["escenario_a"]["eventos_legitimos_en_alerta_pct"] for m in medidas]),
        "errores_digitacion_en_alerta_pct_mediana":
            _mediana([m["escenario_a"]["errores_digitacion_en_alerta_pct"] for m in medidas]),
        "deteccion_faltantes_2pct_mediana": med_deteccion,
        "semanas_hasta_alarma_mediana": med_esperas,
        "error_semana_inicio_mediana": med_inicio,
        "error_relativo_kg_mediana": med_kg,
        "error_relativo_soles_mediana": med_soles,
        "metas": dict(METAS),
        "cumple": {
            "falsas_alarmas_anio": bool(max(fa_semana) <= METAS["falsas_alarmas_anio"]
                                        and max(fa_mes) <= METAS["falsas_alarmas_anio"]),
            "deteccion_faltantes_2pct": _cumple(med_deteccion,
                                                METAS["deteccion_faltantes_2pct"], True),
            "semanas_hasta_alarma": _cumple(med_esperas, METAS["semanas_hasta_alarma"]),
            "error_semana_inicio": _cumple(med_inicio, METAS["error_semana_inicio"]),
            "error_relativo_kg": _cumple(med_kg, METAS["error_relativo_kg"]),
            "error_relativo_soles": _cumple(med_soles, METAS["error_relativo_soles"]),
        },
    }


def ruta_lote(numero: int, destino: str | None = None) -> str:
    base = destino or rutas.ruta("sim", "resultados")
    return f"{base.rstrip('/')}/lote={numero}.json"


def ejecutar_lote(numero: int, semillas=None, ruta_spec=None, destino: str | None = None,
                  tamano: int = TAMANO_LOTE) -> dict:
    """Mide un lote de semillas y deja su JSON en `sim/resultados/lote=<n>.json`."""
    semillas = list(semillas) if semillas is not None else semillas_del_lote(numero, tamano)
    medidas = [medir_semilla(s, ruta_spec) for s in semillas]
    resultado = {
        "lote": int(numero),
        "semillas": [int(s) for s in semillas],
        "generado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fuente_metas": "informe v16, Tabla 4.8h",
        "umbral_fijado_con": "escenario A (sin robos); el escenario B no recalibra nada",
        "resumen": resumir(medidas),
        "por_semilla": medidas,
    }
    ruta = ruta_lote(numero, destino)
    lake_io.escribir_json(resultado, ruta)
    resultado["ruta"] = ruta
    return resultado


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validacion del detector con escenarios A y B")
    ap.add_argument("--lote", type=int, help="numero de lote a correr")
    ap.add_argument("--lotes", type=int, help="corre los lotes 1..N (100 semillas con N=10)")
    ap.add_argument("--tamano", type=int, default=TAMANO_LOTE, help="semillas por lote")
    ap.add_argument("--spec", help="ruta de la especificacion del escenario B")
    ap.add_argument("--destino", help="prefijo donde escribir; por defecto sim/resultados")
    a = ap.parse_args(argv)

    if not a.lote and not a.lotes:
        ap.error("indique --lote N o --lotes N")

    numeros = [a.lote] if a.lote else list(range(1, a.lotes + 1))
    for numero in numeros:
        r = ejecutar_lote(numero, ruta_spec=a.spec, destino=a.destino, tamano=a.tamano)
        resumen = r["resumen"]
        print(f"lote {numero}: {resumen['semillas']} semillas -> {r['ruta']}")
        print(f"  falsas alarmas/anio (max): semana "
              f"{resumen['falsas_alarmas_anio_max']['semana']}, "
              f"mes {resumen['falsas_alarmas_anio_max']['mes']} "
              f"(meta <= {METAS['falsas_alarmas_anio']})")
        print(f"  deteccion de faltantes >= 2 %: "
              f"{resumen['deteccion_faltantes_2pct_mediana']} "
              f"(meta >= {METAS['deteccion_faltantes_2pct']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
