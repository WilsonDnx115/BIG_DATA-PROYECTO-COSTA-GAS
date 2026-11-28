"""Tabla fact_serie: el detector de desvíos persistentes llevado a Gold (FR05; informe v16, Tabla 4.9).

Grano: entidad (unidad, vendedor o cliente) × semana o mes. Columnas que lee la vista
`v_semaforo_unidades`: entidad_tipo, entidad_id, granularidad, periodo, estado,
periodo_inicio, kg_acumulados y soles_acumulados; además valor_real, valor_esperado,
residuo, z, cusum y ewma para el expediente.

Cómo se reparte en Spark. Primero el valor esperado de cada entidad sale de una regresión
de MLlib sobre sus pares (`detector.esperado_mllib`, FR26). Después el CUSUM y el EWMA se
parten por **grupo de pares** con groupBy(...).applyInPandas(...): cada tarea recibe todas
las unidades de un rol (o todos los vendedores, o todos los clientes) y corre el detector
de `src/models/detector.py` en pandas. Los grupos son pocos y chicos (de 12 a 150 entidades),
así que caben en las tareas de un solo executor.

Fuentes:
  * unidades × mes: fact_unidad_mes (interfaz `unidad_mes` del WP 0.8); valor = kg del rol
    (kg vendidos en reparto y transportados en transporte);
  * unidades × semana: ventas_detalle de Silver (solo GLP), rol reparto;
  * vendedor y cliente × semana: solo para las unidades que ya están en ámbar o rojo
    (informe v16, 4.3), para no llenar la bandeja vigilando a todos.

El umbral y la σ de cada granularidad salen de `detector.calibrar_con_escenario_a()`
(ADR 0028); se pasan como `umbrales = {"semana": {...}, "mes": {...}}`.
"""
from __future__ import annotations

import pandas as pd

from src.common import config
from src.models import detector

COLUMNAS = ["entidad_tipo", "entidad_id", "grupo", "granularidad", "periodo", "anio", "mes",
            "valor_real", "valor_esperado", "residuo", "z", "cusum", "ewma", "estado",
            "periodo_inicio", "kg_acumulados", "soles_acumulados"]

ESQUEMA = ("entidad_tipo string, entidad_id string, grupo string, granularidad string, periodo date, "
           "anio int, mes int, valor_real double, valor_esperado double, residuo double, z double, "
           "cusum double, ewma double, estado string, periodo_inicio date, kg_acumulados double, "
           "soles_acumulados double")


# --- Núcleo en pandas (lo que corre dentro de cada tarea) ----------------------------
def serie_pandas(pdf: pd.DataFrame, umbral: dict, precio: float = config.PRECIO_REF_KG) -> pd.DataFrame:
    """Corre el detector sobre un grupo de pares ya armado.

    Entrada: entidad_tipo, entidad_id, grupo, granularidad, periodo (fecha) y valor; si trae
    `kg_error`, los pares redigitados se neutralizan. Salida: las COLUMNAS de fact_serie.
    """
    if pdf.empty:
        return pd.DataFrame(columns=COLUMNAS)
    d = detector.detectar(pdf, "entidad_id", "valor", "periodo", grupo="grupo",
                          k=umbral.get("k", config.DETECTOR_K), h=umbral["h"],
                          lam=umbral.get("lambda", config.DETECTOR_LAMBDA),
                          L=umbral.get("L", config.DETECTOR_L), sigma=umbral.get("sigma"),
                          precio=precio, periodos_base=umbral.get("periodos_base", config.DETECTOR_PERIODOS_BASE))
    periodo = pd.to_datetime(d["periodo"])
    salida = pd.DataFrame({
        "entidad_tipo": d["entidad_tipo"].astype(str), "entidad_id": d["entidad_id"].astype(str),
        "grupo": d["grupo"].astype(str), "granularidad": d["granularidad"].astype(str),
        "periodo": periodo.dt.date, "anio": periodo.dt.year.astype("int32"),
        "mes": periodo.dt.month.astype("int32"),
        "valor_real": pd.to_numeric(d["valor_corregido"], errors="coerce"),
        "valor_esperado": d["valor_esperado"], "residuo": d["residuo"], "z": d["z"],
        "cusum": d["cusum"], "ewma": d["ewma"], "estado": d["estado"].astype(str),
        "periodo_inicio": pd.to_datetime(d["periodo_inicio"]).dt.date,
        "kg_acumulados": d["kg_acumulados"].astype(float),
        "soles_acumulados": d["soles_acumulados"].astype(float),
    })
    return salida[COLUMNAS]


def unidades_mes_pandas(unidad_mes: pd.DataFrame) -> pd.DataFrame:
    """fact_unidad_mes → entrada del detector: una fila por unidad y mes con el kg de su rol."""
    u = unidad_mes.copy()
    valor = u["kg_vendidos"].where(u["rol"] == "reparto", u["kg_transportados"])
    return pd.DataFrame({
        "entidad_tipo": "unidad", "entidad_id": u["unidad_id"].astype(str), "grupo": u["rol"].astype(str),
        "granularidad": "mes",
        "periodo": pd.to_datetime(dict(year=u["anio"], month=u["mes"], day=1)),
        "valor": pd.to_numeric(valor, errors="coerce"),
    })


def _semanas(df: pd.DataFrame, entidad: str, entidad_tipo: str, grupo: str) -> pd.DataFrame:
    """Suma kg de GLP por entidad y semana (lunes de la semana ISO)."""
    v = df[df["es_glp"].fillna(False).astype(bool)].copy()
    v["periodo"] = pd.to_datetime(v["fecha"]).dt.to_period("W-SUN").dt.start_time
    s = v.groupby([entidad, "periodo"], as_index=False)["kg"].sum()
    return pd.DataFrame({"entidad_tipo": entidad_tipo, "entidad_id": s[entidad].astype(str),
                         "grupo": grupo, "granularidad": "semana", "periodo": s["periodo"],
                         "valor": s["kg"].astype(float)})


def unidades_semana_pandas(ventas_detalle: pd.DataFrame) -> pd.DataFrame:
    """ventas_detalle de Silver → kg de GLP vendidos por unidad de reparto y semana."""
    v = ventas_detalle.dropna(subset=["placa_norm"])
    return _semanas(v, "placa_norm", "unidad", "reparto")


def bajar_a_vendedor_y_cliente(ventas_detalle: pd.DataFrame, serie_unidades: pd.DataFrame) -> pd.DataFrame:
    """Vendedores y clientes de las unidades que ya están en ámbar o rojo (informe v16, 4.3).

    Solo se vigila a quienes vendieron desde esas unidades; cada uno se compara con los
    demás de su tipo (grupo «vendedor» o «cliente»), con identificadores seudonimizados.
    """
    marcadas = set(serie_unidades.loc[serie_unidades["estado"].isin(["ambar", "rojo"]), "entidad_id"])
    v = ventas_detalle[ventas_detalle["placa_norm"].isin(marcadas)]
    if v.empty:
        return pd.DataFrame(columns=["entidad_tipo", "entidad_id", "grupo", "granularidad", "periodo", "valor"])
    partes = [_semanas(v.dropna(subset=["vendedor_hash"]), "vendedor_hash", "vendedor", "vendedor"),
              _semanas(v.dropna(subset=["cliente_id"]), "cliente_id", "cliente", "cliente")]
    return pd.concat(partes, ignore_index=True)


# --- Spark: un grupo de pares por tarea ------------------------------------------------
def construir(spark_df, umbral: dict, hasta=None):
    """Aplica el detector en Spark (FR26): valor esperado con MLlib y CUSUM por grupo de pares.

    1. `detector.esperado_mllib` estima el valor esperado con `LinearRegression` de MLlib
       sobre todo el DataFrame (ajustado hasta `hasta`, si se da).
    2. groupBy(...).applyInPandas(...) corre el CUSUM y el EWMA, un grupo de pares por tarea;
       el detector usa el `valor_esperado` que ya trae cada fila.
    `spark_df` tiene las columnas de entrada del detector (las que devuelven
    unidades_mes_pandas, unidades_semana_pandas o bajar_a_vendedor_y_cliente) de una sola
    granularidad; `umbral` es el de esa granularidad.
    """
    con_esperado = detector.esperado_mllib(spark_df, hasta=hasta)
    return con_esperado.groupBy("entidad_tipo", "grupo").applyInPandas(
        lambda pdf: serie_pandas(pdf, umbral), schema=ESQUEMA)
