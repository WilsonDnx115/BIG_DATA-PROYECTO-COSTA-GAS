"""Escenario A: operación sin robos, calibrada con los agregados de 2020 (commit A16).

La serie es el banco de pruebas del detector: si sobre esta serie, donde no hay ningun
robo, el detector levanta mas alarmas de las que el equipo puede atender, el umbral
esta mal puesto. Por eso el escenario A tiene que parecerse a la operacion real en lo
que importa, y por eso se calibra con **agregados publicados**, nunca con registros:

* 5.0 millones de kg de envasado vendidos en 2020 (informe v16, Tabla 1.5).
* 9 unidades de reparto con venta y combustible en 2020.
* Correlacion de Spearman 0.66 entre kg vendidos y gasto de combustible por unidad-mes.
* Merma tecnica de 0.5 %, declarada como supuesto del equipo (`MERMA_TECNICA_ES_SUPUESTO`).

Lo que la serie incluye a proposito, porque el detector tiene que convivir con ello sin
confundirlo con un robo:

* **Estacionalidad**: en la costa norte el consumo de GLP sube en invierno (jun-ago).
* **Pandemia**: caida fuerte desde la cuarentena del 16/03/2020 y recuperacion gradual.
* **15 eventos legitimos**: paradas de planta, campanias y altas de clientes, cada uno
  con su motivo escrito. Son saltos reales que no son robos.
* **Errores de digitacion**: unos corregidos (par +X / -X, que `src/quality/redigitados.py`
  compensa) y otros sin corregir, que se quedan en la serie como ruido real.

Los identificadores son ficticios y usan un alfabeto de placas **disjunto** del de
`src/common/muestra.py`, para que no se pueda confundir una serie simulada con la
muestra. No hay ningun dato de persona.

Uso:
    from src.sim.escenario_a import generar
    datos = generar(semilla=42)
    datos["semanal"], datos["mensual"]
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from src.common import config

# --- Calibracion (informe v16, Tabla 1.5) -------------------------------------
KG_ENVASADO_2020 = 5_000_000.0        # kg vendidos de envasado en 2020
UNIDADES_REPARTO = 9                  # con venta y combustible en 2020
UNIDADES_TRANSPORTE = 3
SPEARMAN_OBJETIVO = 0.66              # kg vendidos frente a gasto de combustible
PRECIO_MEDIANO_BALON = 21.44          # S/ por balon de 10 kg
SOLES_POR_T_BASE = 54.7               # gasto de combustible por tonelada movida
# Dispersion del gasto de combustible. No es un parametro libre: es el valor que
# reproduce la Spearman de 0.66 medida en 2020. Con menos ruido la relacion sale
# casi perfecta y el detector pareceria mejor de lo que es.
RUIDO_COMBUSTIBLE = 0.8

INICIO = dt.date(2020, 1, 6)          # primer lunes de 2020
FIN = dt.date(2022, 12, 26)
CUARENTENA = dt.date(2020, 3, 16)     # inicio de la cuarentena en Peru

# Alfabeto disjunto del de src/common/muestra.py ("ABCDFHMTUVWX"): ninguna placa
# simulada puede coincidir con una de la muestra.
LETRAS_SIM = "GJKLNPQRSZ"

N_EVENTOS_LEGITIMOS = 15
N_REDIGITADOS_CORREGIDOS = 8
N_REDIGITADOS_SIN_CORREGIR = 4

MOTIVOS_EVENTO = (
    "parada de planta por mantenimiento",
    "campania comercial de fin de mes",
    "alta de un distribuidor grande",
    "baja temporal de un distribuidor",
    "desvio de flota a otra planta",
    "feriado largo",
)


def _placas(rng, cuantas: int) -> list[str]:
    """Placas con el formato real (letra, digito, letra, 3 digitos) y alfabeto propio."""
    vistas: list[str] = []
    while len(vistas) < cuantas:
        p = (f"{rng.choice(list(LETRAS_SIM))}{rng.integers(1, 10)}"
             f"{rng.choice(list(LETRAS_SIM))}{rng.integers(100, 1000)}")
        if p not in vistas:
            vistas.append(p)
    return vistas


def unidades(semilla: int | None = None) -> pd.DataFrame:
    """Las unidades de la simulacion, con su rol y su tamanio relativo."""
    rng = np.random.default_rng(config.SEMILLA if semilla is None else semilla)
    placas = _placas(rng, UNIDADES_REPARTO + UNIDADES_TRANSPORTE)
    roles = ["reparto"] * UNIDADES_REPARTO + ["transporte"] * UNIDADES_TRANSPORTE
    # Tamanios heterogeneos: en una flota real unas unidades mueven el doble que otras.
    peso = rng.uniform(0.6, 1.5, len(placas))
    return pd.DataFrame({"placa_norm": placas, "rol": roles,
                         "peso": np.round(peso / peso[:UNIDADES_REPARTO].sum(), 6)})


def _semanas() -> list[dt.date]:
    dias, actual = [], INICIO
    while actual <= FIN:
        dias.append(actual)
        actual += dt.timedelta(days=7)
    return dias


def _estacionalidad(fechas: np.ndarray) -> np.ndarray:
    """Pico en invierno (jun-ago), valle en verano. +-12 % sobre la media."""
    dia_del_anio = np.array([f.timetuple().tm_yday for f in fechas])
    return 1 + 0.12 * np.cos(2 * np.pi * (dia_del_anio - 196) / 365.25)


# Caida y recuperacion de la cuarentena. La forma es un supuesto declarado del equipo,
# no una medicion: el diccionario v3.0 no publica el perfil mensual de 2020. Se declara
# aqui para que cualquiera pueda cambiarlo y volver a calibrar.
CAIDA_PANDEMIA = 0.45
RECUPERACION_SEMANAS = 13.0


def _pandemia(fechas: np.ndarray) -> np.ndarray:
    """Caida en la cuarentena del 16/03/2020, recuperada de forma exponencial."""
    factor = np.ones(len(fechas))
    for i, f in enumerate(fechas):
        semanas = (f - CUARENTENA).days / 7
        if semanas >= 0:
            factor[i] = 1 - CAIDA_PANDEMIA * float(np.exp(-semanas / RECUPERACION_SEMANAS))
    return factor


def _eventos(rng, fechas: list[dt.date], placas: list[str]) -> pd.DataFrame:
    """15 saltos legitimos, con su motivo. No son robos y el detector debe tolerarlos.

    Los primeros se reparten uno por unidad y el resto cae al azar: en tres anios toda
    unidad tiene alguna variacion explicada, y asi ningun escenario queda sin eventos
    en una unidad concreta solo por suerte de la semilla.
    """
    elegidas = rng.choice(len(fechas), size=N_EVENTOS_LEGITIMOS, replace=False)
    asignadas = (placas + [placas[int(i)] for i in
                           rng.integers(0, len(placas), max(N_EVENTOS_LEGITIMOS - len(placas), 0))]
                 )[:N_EVENTOS_LEGITIMOS]
    filas = []
    for k, idx in enumerate(sorted(elegidas.tolist())):
        sube = bool(rng.integers(0, 2))
        filas.append({
            "evento_id": f"EV{k + 1:02d}",
            "fecha": fechas[idx],
            "placa_norm": asignadas[k],
            "factor": float(rng.uniform(1.25, 1.60) if sube else rng.uniform(0.45, 0.75)),
            "motivo": MOTIVOS_EVENTO[k % len(MOTIVOS_EVENTO)],
        })
    return pd.DataFrame(filas)


def _digitacion(rng, df: pd.DataFrame) -> pd.DataFrame:
    """Errores de digitacion: unos corregidos al periodo siguiente y otros no.

    Los corregidos son el par +X / -X que compensa `src/quality/redigitados.py`.
    Los que nadie corrigio se quedan: son ruido real y el detector tiene que aguantarlo.
    """
    df = df.copy()
    df["error_digitacion"] = ""
    # `kg_error` guarda el desvio que mete la digitacion, con signo. El par corregido
    # es +X y -X, que es exactamente lo que `src/quality/redigitados.py` compensa: sobre
    # los kg absolutos no se podria, porque cada semana parte de una base distinta.
    df["kg_error"] = 0.0
    candidatos = rng.choice(len(df) - 1, size=N_REDIGITADOS_CORREGIDOS + N_REDIGITADOS_SIN_CORREGIR,
                            replace=False)
    corregidos = sorted(candidatos[:N_REDIGITADOS_CORREGIDOS].tolist())
    sueltos = sorted(candidatos[N_REDIGITADOS_CORREGIDOS:].tolist())

    for i in corregidos:
        # el mismo dedo que tecleo de mas lo corrige en el periodo siguiente de esa unidad
        placa = df.at[df.index[i], "placa_norm"]
        siguientes = df.index[(df["placa_norm"] == placa) & (df.index > df.index[i])]
        if len(siguientes) == 0:
            continue
        j = siguientes[0]
        exceso = float(rng.uniform(300, 900))
        df.at[df.index[i], "kg"] += exceso
        df.at[j, "kg"] -= exceso
        df.at[df.index[i], "kg_error"] = exceso
        df.at[j, "kg_error"] = -exceso
        df.at[df.index[i], "error_digitacion"] = "corregido"
        df.at[j, "error_digitacion"] = "correccion"

    for i in sueltos:
        if df.at[df.index[i], "error_digitacion"]:
            continue
        suelto = float(rng.uniform(200, 700))
        df.at[df.index[i], "kg"] += suelto
        df.at[df.index[i], "kg_error"] = suelto
        df.at[df.index[i], "error_digitacion"] = "sin_corregir"
    return df


def generar(semilla: int | None = None) -> dict[str, pd.DataFrame]:
    """Serie 2020-2022 sin robos, con grano semanal y mensual.

    La misma semilla produce exactamente el mismo resultado: la calibracion del umbral
    tiene que ser reproducible para poder defenderla.
    """
    semilla = config.SEMILLA if semilla is None else semilla
    rng = np.random.default_rng(semilla)

    flota = unidades(semilla)
    reparto = flota[flota["rol"] == "reparto"]
    fechas = _semanas()
    estacional = _estacionalidad(np.array(fechas))
    pandemia = _pandemia(np.array(fechas))

    # El reparto mueve los 5.0 M kg de envasado de 2020. Los 5.0 M son la cifra ya
    # medida, con la pandemia dentro, asi que la base se divide entre el efecto medio
    # de 2020: si no, el ano simulado saldria un 12 % por debajo del real.
    en_2020 = np.array([f.year == 2020 for f in fechas])
    semanas_2020 = int(en_2020.sum())
    efecto_2020 = float((estacional * pandemia)[en_2020].mean())
    kg_semana_flota = KG_ENVASADO_2020 / (semanas_2020 * efecto_2020)

    filas = []
    for _, u in flota.iterrows():
        es_reparto = u["rol"] == "reparto"
        peso = u["peso"] if es_reparto else u["peso"] * 0.7
        base = kg_semana_flota * peso
        ruido = rng.normal(1.0, 0.09, len(fechas))
        kg = base * estacional * pandemia * ruido
        for f, k in zip(fechas, kg):
            filas.append({"placa_norm": u["placa_norm"], "rol": u["rol"], "fecha": f,
                          "kg": float(max(k, 0.0))})
    df = pd.DataFrame(filas)

    eventos = _eventos(rng, fechas, flota["placa_norm"].tolist())
    for _, e in eventos.iterrows():
        toca = (df["placa_norm"] == e["placa_norm"]) & (df["fecha"] == e["fecha"])
        df.loc[toca, "kg"] *= e["factor"]
    df["evento"] = ""
    for _, e in eventos.iterrows():
        df.loc[(df["placa_norm"] == e["placa_norm"]) & (df["fecha"] == e["fecha"]), "evento"] = e["evento_id"]

    df = _digitacion(rng, df)

    # Merma tecnica: lo despachado es mayor que lo vendido. Es un supuesto declarado.
    df["merma_kg"] = df["kg"] * config.MERMA_TECNICA_PCT
    df["kg_despachado"] = df["kg"] + df["merma_kg"]

    # Combustible correlacionado con los kg: el ruido se calibra para quedar cerca de
    # la Spearman 0.66 que se midio en 2020, no en una correlacion perfecta.
    ideal = SOLES_POR_T_BASE * df["kg"] / 1000.0
    df["combustible"] = np.maximum(ideal * rng.normal(1.0, RUIDO_COMBUSTIBLE, len(df)), 0.0).round(2)

    df["anio"] = [f.year for f in df["fecha"]]
    df["mes"] = [f.month for f in df["fecha"]]
    df["semana"] = [f.isocalendar()[1] for f in df["fecha"]]
    df["periodo"] = [f.isoformat() for f in df["fecha"]]
    semanal = df[["placa_norm", "rol", "fecha", "periodo", "anio", "mes", "semana",
                  "kg", "merma_kg", "kg_despachado", "combustible", "evento",
                  "error_digitacion", "kg_error"]].reset_index(drop=True)

    mensual = (semanal.groupby(["placa_norm", "rol", "anio", "mes"], as_index=False)
               .agg(kg=("kg", "sum"), merma_kg=("merma_kg", "sum"),
                    kg_despachado=("kg_despachado", "sum"),
                    combustible=("combustible", "sum"),
                    semanas=("kg", "size")))
    mensual["periodo"] = [f"{a}-{m:02d}" for a, m in zip(mensual["anio"], mensual["mes"])]

    return {"semanal": semanal, "mensual": mensual, "eventos": eventos, "unidades": flota,
            "semilla": semilla}


def escribir(datos: dict, destino: str) -> list[str]:
    """Guarda la simulacion en `destino`, que nunca puede estar en Silver ni en Gold.

    La regla no es una recomendacion: una serie simulada mezclada con Silver o Gold
    contaminaria las cifras del informe sin que se note.
    """
    from pathlib import Path  # noqa: PLC0415

    normalizado = destino.replace("\\", "/").rstrip("/")
    for capa in ("/silver", "/gold", "silver/", "gold/"):
        if capa in f"{normalizado}/":
            raise ValueError(f"la simulacion no se escribe en Silver ni en Gold: {destino}")

    raiz = Path(normalizado.removeprefix("file:///").removeprefix("file://"))
    raiz.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nombre in ("semanal", "mensual", "eventos", "unidades"):
        ruta = raiz / f"{nombre}.parquet"
        datos[nombre].to_parquet(ruta, index=False)
        escritos.append(str(ruta))
    return escritos
