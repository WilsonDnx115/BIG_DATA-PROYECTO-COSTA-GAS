"""Detector de desvíos persistentes: CUSUM y EWMA frente a los pares (informe v16, 4.3 y Figura 4.5).

Un faltante de 2 % en un periodo se confunde con el ruido; lo que lo delata es que se
repite hacia el mismo lado. Por eso se acumula:

1. **Valor esperado con una regresión sobre los pares** (informe v16/v17, 4.3, primera
   etapa). Cada entidad (unidad, vendedor, cliente o proveedor) se compara con el resto de
   su grupo en el mismo periodo, no con su propio pasado: una caída que afecta a todos
   (estacionalidad, cuarentena) no es un desvío. Variables: lo que vendieron sus pares en
   el periodo (promedio del grupo sin la propia entidad) escalado por la participación
   histórica de la entidad (mediana de sus cocientes ANTERIORES, con al menos
   DETECTOR_PERIODOS_BASE periodos), la semana del año (seno y coseno), la marca de pandemia
   (PANDEMIA_INICIO a PANDEMIA_FIN) y, si se entregan, los eventos de mercado y el precio de
   lista del periodo. Es una regresión lineal por mínimos cuadrados: en el job de Glue con
   `LinearRegression` de MLlib (`esperado_mllib`) y en la Lambda de validación, que no tiene
   Spark, con numpy (`esperado_regresion`); las dos dan el mismo resultado.
2. **Desvío estandarizado.** z = (real − esperado) ÷ esperado ÷ σ, con σ = 1.4826 × MAD de
   los desvíos relativos del grupo (escala robusta).
3. **CUSUM de un solo lado (faltante)** con k y h, y **EWMA** con λ y L (Montgomery;
   valores en config.py y ADR 0028). El CUSUM confirma (rojo); el EWMA avisa antes (ámbar).
4. **Punto de cambio:** el periodo siguiente al último en que el CUSUM estaba en 0.

Los errores de digitación corregidos se neutralizan antes con
`src/quality/redigitados.compensar` sobre el desvío con signo (`kg_error`), como pide su
autora: un par +X/−X no es un desvío; un error suelto sí se deja, porque puede ser lo que
hay que detectar.

Funciones puras en pandas; el job de Gold las aplica por entidad con applyInPandas
(`src/glue/fact_serie.py`). Una entidad o un grupo sin variación (MAD 0) queda
«no_evaluable»: no se inventa una escala.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config
from src.quality.redigitados import compensar

ESTADOS = ("verde", "ambar", "rojo", "no_evaluable")


# --- 1. Valor esperado ---------------------------------------------------------
def neutralizar_redigitados(df: pd.DataFrame, entidad: str, valor: str, periodo: str,
                            error: str = "kg_error") -> pd.DataFrame:
    """Quita del valor el efecto de los errores de digitación que alguien corrigió.

    Si la tabla trae la columna `error` (desvío de digitación con signo), los pares
    +X/−X que `compensar` empareja se restan del valor; los errores sueltos se quedan.
    Sin esa columna, el valor pasa tal cual (`<valor>_corregido` = `<valor>`).
    """
    salida = df.copy()
    corregido = f"{valor}_corregido"
    if error not in salida.columns:
        salida[corregido] = pd.to_numeric(salida[valor], errors="coerce")
        salida["redigitado"] = False
        return salida
    salida = compensar(salida, entidad=entidad, valor=error, periodo=periodo)
    quitar = salida[error].fillna(0) - salida[f"{error}_compensado"].fillna(0)
    salida[corregido] = pd.to_numeric(salida[valor], errors="coerce") - quitar
    return salida


CONTEXTO_OPCIONAL = ("eventos_mercado", "precio_lista")
VARIABLES_BASE = ["base_pares", "semana_sin", "semana_cos", "pandemia"]


def _fecha_del_periodo(periodo: pd.Series) -> pd.Series:
    """Fecha de cada periodo: fechas, «AAAA-MM-DD» o «AAAA-MM». Si no es una fecha (un número
    de periodo), queda nula y la semana y la pandemia no entran a la regresión."""
    texto = periodo.astype(str).str.slice(0, 10)
    dia = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
    mes = pd.to_datetime(texto.str.slice(0, 7), format="%Y-%m", errors="coerce")
    return dia.fillna(mes)


def variables_del_esperado(df: pd.DataFrame, entidad: str, valor: str, periodo: str, grupo: str,
                           periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> pd.DataFrame:
    """Variables de la regresión del valor esperado (las mismas que `esperado_mllib`).

    pares: promedio del grupo en el periodo sin la propia entidad; participacion: mediana de
    los cocientes valor ÷ pares de los periodos ANTERIORES (nula sin `periodos_base` de ellos);
    base_pares = participacion × pares; semana_sin y semana_cos; pandemia (0 o 1).
    """
    d = df.copy()
    d["_v"] = pd.to_numeric(d[valor], errors="coerce").astype(float)
    g = d.groupby([grupo, periodo])["_v"]
    n, suma = g.transform("count"), g.transform("sum")
    propio = d["_v"].notna().astype(int)
    d["pares"] = ((suma - d["_v"].fillna(0)) / (n - propio)).where(n - propio > 0)
    d["_cociente"] = d["_v"] / d["pares"].where(d["pares"] > 0)
    d = d.sort_values([entidad, periodo], kind="stable")
    d["participacion"] = d.groupby(entidad)["_cociente"].transform(
        lambda s: s.shift(1).expanding(min_periods=periodos_base).median())
    d["base_pares"] = d["participacion"] * d["pares"]
    fecha = _fecha_del_periodo(d[periodo])
    semana = fecha.dt.isocalendar().week.astype(float)
    d["semana_sin"] = np.sin(2 * np.pi * semana / 52)
    d["semana_cos"] = np.cos(2 * np.pi * semana / 52)
    d["pandemia"] = ((fecha >= pd.Timestamp(config.PANDEMIA_INICIO))
                     & (fecha <= pd.Timestamp(config.PANDEMIA_FIN))).astype(float).where(fecha.notna())
    return d.drop(columns=["_cociente"]).sort_index()


def _columnas_regresion(d: pd.DataFrame) -> list[str]:
    """Variables con datos. Si el periodo no es una fecha, la semana y la pandemia no se pueden
    calcular y no entran (quedan solo los pares y el contexto que se haya entregado)."""
    candidatas = VARIABLES_BASE + [c for c in CONTEXTO_OPCIONAL if c in d.columns]
    return [c for c in candidatas if d[c].notna().any()]


def esperado_regresion(df: pd.DataFrame, entidad: str, valor: str, periodo: str, grupo: str,
                       hasta=None, periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> pd.DataFrame:
    """Valor esperado por mínimos cuadrados con numpy (la Lambda de validación no tiene Spark).

    Se ajusta con intercepto sobre las filas con base_pares y, si se da `hasta`, solo con
    los periodos hasta esa fecha; se predice en todas las filas con base_pares.
    """
    d = variables_del_esperado(df, entidad, valor, periodo, grupo, periodos_base)
    cols = _columnas_regresion(d)
    usable = d[cols].notna().all(axis=1) & d["_v"].notna()
    entrena = usable
    if hasta is not None:
        entrena = usable & (_fecha_del_periodo(d[periodo]) <= pd.Timestamp(hasta))
    d["valor_esperado"] = np.nan
    if int(entrena.sum()) > len(cols) + 1:
        X = np.column_stack([np.ones(int(entrena.sum())), d.loc[entrena, cols].to_numpy(float)])
        coef, *_ = np.linalg.lstsq(X, d.loc[entrena, "_v"].to_numpy(float), rcond=None)
        Xp = np.column_stack([np.ones(int(usable.sum())), d.loc[usable, cols].to_numpy(float)])
        d.loc[usable, "valor_esperado"] = Xp @ coef
    return d.drop(columns=["_v"])


def esperado_mllib(df, entidad: str = "entidad_id", valor: str = "valor", periodo: str = "periodo",
                   grupo: str = "grupo", hasta=None, periodos_base: int = config.DETECTOR_PERIODOS_BASE):
    """Valor esperado con `LinearRegression` de MLlib en el job de Glue (informe, 4.3).

    Mismas variables y mismo ajuste que `esperado_regresion`: mínimos cuadrados con
    intercepto, sin regularización y con el solver «normal», calculados en Spark con
    ventanas. Devuelve el DataFrame con `valor_esperado` (nulo donde no hay base_pares).
    """
    from pyspark.ml.feature import VectorAssembler  # noqa: PLC0415
    from pyspark.ml.regression import LinearRegression  # noqa: PLC0415
    from pyspark.sql import Window  # noqa: PLC0415
    from pyspark.sql import functions as F  # noqa: PLC0415

    wg = Window.partitionBy(grupo, periodo)
    we = Window.partitionBy(entidad).orderBy(periodo).rowsBetween(Window.unboundedPreceding, -1)
    fecha = F.to_date(F.substring(F.col(periodo).cast("string"), 1, 10))
    semana = F.weekofyear(fecha).cast("double")
    propio = F.col("_v").isNotNull().cast("int")
    d = (df.withColumn("_v", F.col(valor).cast("double"))
         .withColumn("_n", F.count("_v").over(wg)).withColumn("_s", F.sum("_v").over(wg))
         .withColumn("pares", F.when(F.col("_n") - propio > 0,
                                     (F.col("_s") - F.coalesce(F.col("_v"), F.lit(0.0))) / (F.col("_n") - propio)))
         .withColumn("_cociente", F.when(F.col("pares") > 0, F.col("_v") / F.col("pares")))
         .withColumn("_previos", F.count("_cociente").over(we))
         .withColumn("participacion", F.when(F.col("_previos") >= periodos_base,
                                             F.expr("percentile(_cociente, 0.5)").over(we)))
         .withColumn("base_pares", F.col("participacion") * F.col("pares"))
         .withColumn("semana_sin", F.sin(F.lit(2 * np.pi) * semana / 52))
         .withColumn("semana_cos", F.cos(F.lit(2 * np.pi) * semana / 52))
         .withColumn("pandemia", ((fecha >= F.lit(config.PANDEMIA_INICIO).cast("date"))
                                  & (fecha <= F.lit(config.PANDEMIA_FIN).cast("date"))).cast("double")))
    cols = VARIABLES_BASE + [c for c in CONTEXTO_OPCIONAL if c in df.columns]
    usable = F.col("base_pares").isNotNull() & F.col("_v").isNotNull()
    if hasta is not None:
        usable_ent = usable & (fecha <= F.lit(str(hasta)).cast("date"))
    else:
        usable_ent = usable
    ensamblador = VectorAssembler(inputCols=cols, outputCol="_x", handleInvalid="keep")
    modelo = LinearRegression(featuresCol="_x", labelCol="_v", predictionCol="_pred", regParam=0.0,
                              solver="normal", standardization=False).fit(
        ensamblador.transform(d.filter(usable_ent)))
    pred = modelo.transform(ensamblador.transform(d))
    return (pred.withColumn("valor_esperado", F.when(F.col("base_pares").isNotNull(), F.col("_pred")))
            .drop("_v", "_n", "_s", "_cociente", "_previos", "_x", "_pred"))


def escala_robusta(desvios: pd.Series) -> float | None:
    """σ robusta = 1.4826 × MAD. None si no hay datos o el MAD es 0 (no evaluable)."""
    x = pd.to_numeric(desvios, errors="coerce").dropna()
    if x.empty:
        return None
    mad = float((x - x.median()).abs().median())
    return 1.4826 * mad if mad > 0 else None


# --- 2. CUSUM, EWMA y punto de cambio -------------------------------------------
def cusum(x, k: float = config.DETECTOR_K) -> np.ndarray:
    """CUSUM tabular de un solo lado: S_t = max(0, S_{t−1} + x_t − k). Un nulo no suma."""
    s, salida = 0.0, []
    for v in np.asarray(x, dtype=float):
        if np.isfinite(v):
            s = max(0.0, s + v - k)
        salida.append(s)
    return np.array(salida)


def ewma(x, lam: float = config.DETECTOR_LAMBDA) -> np.ndarray:
    """E_t = λ x_t + (1 − λ) E_{t−1}, con E_0 = 0 (la media en control del desvío estandarizado)."""
    e, salida = 0.0, []
    for v in np.asarray(x, dtype=float):
        if np.isfinite(v):
            e = lam * v + (1 - lam) * e
        salida.append(e)
    return np.array(salida)


def limite_ewma(lam: float = config.DETECTOR_LAMBDA, L: float = config.DETECTOR_L) -> float:
    """Límite asintótico del EWMA para desvíos con σ = 1: L × √(λ ÷ (2 − λ))."""
    return L * float(np.sqrt(lam / (2 - lam)))


def punto_cambio(s, h: float = config.DETECTOR_H) -> int | None:
    """Posición donde empezó el desvío: la siguiente al último 0 del CUSUM antes de cruzar h."""
    s = np.asarray(s, dtype=float)
    cruces = np.flatnonzero(s > h)
    if not cruces.size:
        return None
    primero = int(cruces[0])
    ceros = np.flatnonzero(s[: primero + 1] == 0)
    return int(ceros[-1]) + 1 if ceros.size else 0


# --- 3. Detector completo por entidad ---------------------------------------------
def desvios(df: pd.DataFrame, entidad: str, valor: str, periodo: str, grupo: str = "rol",
            sigma: dict | None = None,
            periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> pd.DataFrame:
    """Desvío estandarizado de cada entidad y periodo: `valor_esperado`, `residuo` y `z`.

    Es el paso común del detector y de su calibración, así los dos usan exactamente el
    mismo z. `sigma` fija la escala por grupo (la de la calibración); si falta un grupo,
    se estima con los datos recibidos. La escala usada queda en la columna `_sigma`.
    """
    d = neutralizar_redigitados(df, entidad, valor, periodo)
    corregido = f"{valor}_corregido"
    if "valor_esperado" not in d.columns:            # en Glue llega ya calculado por esperado_mllib
        d = esperado_regresion(d, entidad, corregido, periodo, grupo, periodos_base=periodos_base)
    esperado = d["valor_esperado"]
    d["desvio_rel"] = (d[corregido] - esperado) / esperado.where(esperado > 0)
    escalas = dict(sigma or {})
    for g, desv in d.groupby(grupo)["desvio_rel"]:
        escalas.setdefault(g, escala_robusta(desv))
    d["_sigma"] = pd.to_numeric(d[grupo].map(escalas), errors="coerce").astype(float)
    d["residuo"] = d[f"{valor}_corregido"] - d["valor_esperado"]
    d["z"] = (d["desvio_rel"] / d["_sigma"]).astype(float)
    return d


def detectar(df: pd.DataFrame, entidad: str, valor: str, periodo: str, grupo: str = "rol",
             k: float = config.DETECTOR_K, h: float = config.DETECTOR_H,
             lam: float = config.DETECTOR_LAMBDA, L: float = config.DETECTOR_L,
             sigma: dict | None = None, precio: float = config.PRECIO_REF_KG,
             periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> pd.DataFrame:
    """Serie del detector por entidad y periodo.

    Columnas que agrega: `valor_esperado`, `residuo` (real − esperado, en kg), `z`,
    `cusum`, `ewma`, `estado` (verde, ambar, rojo o no_evaluable), `periodo_inicio`,
    `kg_acumulados` y `soles_acumulados` (faltante neto desde el inicio estimado).
    `sigma` permite usar la escala fijada en la calibración (por grupo); si no se da,
    se estima con los datos recibidos.
    """
    d = desvios(df, entidad, valor, periodo, grupo, sigma, periodos_base)
    limite = limite_ewma(lam, L)

    partes, inicios = [], {}
    for ent, g in d.sort_values([entidad, periodo], kind="stable").groupby(entidad, sort=False):
        g = g.copy()
        faltante = -g["z"].to_numpy(dtype=float)          # un faltante es un desvío negativo
        s, e = cusum(faltante, k), ewma(faltante, lam)
        g["cusum"], g["ewma"] = s, e
        evaluable = g["_sigma"].notna().to_numpy() & np.isfinite(g["z"].to_numpy(dtype=float))
        estado = np.where(s > h, "rojo", np.where(e > limite, "ambar", "verde"))
        g["estado"] = np.where(evaluable, estado, "no_evaluable")
        inicio = punto_cambio(s, h)
        g["kg_acumulados"] = 0.0
        if inicio is not None:
            inicios[ent] = g[periodo].iloc[inicio]
            desde = np.arange(len(g)) >= inicio
            faltante_kg = (-g["residuo"]).where(desde, 0.0).fillna(0.0)
            g["kg_acumulados"] = faltante_kg.cumsum().where(desde, 0.0)
        g["soles_acumulados"] = g["kg_acumulados"] * precio
        partes.append(g)
    salida = pd.concat(partes).sort_index() if partes else d
    # El inicio se asigna al final: así ninguna parte llega a concat con la columna vacía.
    salida["periodo_inicio"] = salida[entidad].map(inicios)
    return salida.drop(columns=["_sigma"])


def alarmas(serie: pd.DataFrame, entidad: str, periodo: str) -> pd.DataFrame:
    """Primer periodo en rojo de cada entidad, con su inicio estimado. Lo usa calibrar_h."""
    rojas = serie[serie["estado"] == "rojo"].sort_values([entidad, periodo])
    return rojas.groupby(entidad, as_index=False).first()[[entidad, periodo, "periodo_inicio"]]


# --- 4. Calibración del umbral con el escenario A ------------------------------------
PERIODOS_POR_ANIO = {"semana": 52, "mes": 12}


def contar_alarmas(x, k: float, h: float) -> int:
    """Episodios de alarma de una serie: cada vez que el CUSUM cruza h cuenta uno y se reinicia.

    Reiniciar tras la señal es la práctica habitual de un CUSUM (se revisa la unidad y se
    vuelve a empezar); así una sola desviación larga no cuenta como muchas alarmas.
    """
    s, n = 0.0, 0
    for v in np.asarray(x, dtype=float):
        if not np.isfinite(v):
            continue
        s = max(0.0, s + v - k)
        if s > h:
            n += 1
            s = 0.0
    return n


def calibrar_h(serie_a: pd.DataFrame, entidad: str, valor: str, periodo: str, granularidad: str,
               grupo: str = "rol", presupuesto: int = config.FALSAS_ALARMAS_ANIO,
               k: float = config.DETECTOR_K, rejilla=None,
               periodos_base: int = config.DETECTOR_PERIODOS_BASE) -> dict:
    """El menor h que deja como máximo `presupuesto` falsas alarmas al año en TODO el sistema.

    `serie_a` es una serie sin robos (escenario A): toda alarma en ella es falsa. El
    presupuesto es del sistema y no por entidad (informe v16, 4.3; Tabla 4.8h: 12 al año
    en cada granularidad), para que vigilar muchas entidades no llene la bandeja.
    Devuelve un dict listo para `gold/_modelos/detector/umbral.json`, con la escala σ por
    grupo que se fijó aquí y que el detector debe reutilizar al puntuar.
    """
    if granularidad not in PERIODOS_POR_ANIO:
        raise ValueError(f"granularidad debe ser una de {sorted(PERIODOS_POR_ANIO)}")
    d = desvios(serie_a, entidad, valor, periodo, grupo, periodos_base=periodos_base)
    sigma = {str(g): (None if pd.isna(v) else float(v))
             for g, v in d.groupby(grupo)["_sigma"].first().items()}
    series = [-g.sort_values(periodo)["z"].to_numpy(dtype=float) for _, g in d.groupby(entidad)]
    anios = d[periodo].nunique() / PERIODOS_POR_ANIO[granularidad]
    rejilla = np.round(np.arange(0.5, 50.0001, 0.1), 4) if rejilla is None else np.asarray(rejilla)
    for h in rejilla:
        alarmas_total = sum(contar_alarmas(x, k, float(h)) for x in series)
        tasa = alarmas_total / anios
        if tasa <= presupuesto:
            return {"granularidad": granularidad, "h": float(h), "k": float(k),
                    "lambda": float(config.DETECTOR_LAMBDA), "L": float(config.DETECTOR_L),
                    "sigma": sigma, "periodos_base": int(periodos_base),
                    "presupuesto_falsas_alarmas_anio": int(presupuesto),
                    "falsas_alarmas_total": int(alarmas_total),
                    "falsas_alarmas_anio": round(float(tasa), 4),
                    "anios": round(float(anios), 4), "entidades": len(series)}
    raise ValueError(f"ningún h de la rejilla deja ≤ {presupuesto} falsas alarmas al año")


def calibrar_con_escenario_a(semilla: int = config.SEMILLA) -> dict:
    """Calibra h dos veces con el escenario A de Anghelo (`src/sim/escenario_a`): semanas y meses.

    Solo usa el escenario A (sin robos). El escenario B nunca se lee aquí: con él se mide
    la detección, sin volver a tocar el umbral (Tabla 4.8h).
    """
    from src.sim import escenario_a  # noqa: PLC0415

    datos = escenario_a.generar(semilla)
    return {
        "semana": calibrar_h(datos["semanal"], "placa_norm", "kg", "periodo", "semana"),
        "mes": calibrar_h(datos["mensual"], "placa_norm", "kg", "periodo", "mes"),
        "semilla": int(semilla),
    }
