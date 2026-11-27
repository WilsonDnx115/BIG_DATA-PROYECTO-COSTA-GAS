"""Escenario B: el escenario A con robos inyectados a ciegas (commit A17).

El escenario A fija el umbral del detector con un presupuesto de falsas alarmas. El B
mide si ese umbral encuentra robos de verdad. Para que la medida valga algo, **quien
disenio el detector no puede saber donde estan los robos**: si los conoce, termina
ajustando el detector a esos casos y la precision que reporte sera de mentira.

Por eso la especificacion con los robos reales **nunca entra al repositorio**. Aqui
solo vive el codigo que la aplica. El archivo real:

* lo escribe Calidad y documentacion,
* se entrega sellado a Ingenieria de datos, que lo sube a `sim/_spec/` (W19),
* y su huella SHA-256 queda publicada en `docs/modelos/formato_spec_b.md`, para poder
  demostrar despues que la medicion se hizo contra ese archivo y no contra otro.

La ruta llega por la variable `ESCENARIO_B_SPEC` o, en AWS, por `sim/_spec/`.

Uso:
    from src.sim.escenario_a import generar
    from src.sim.escenario_b import inyectar
    b = inyectar(generar(42), ruta_spec=None)   # toma ESCENARIO_B_SPEC
    b["semanal"], b["verdad"]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

VARIABLE_RUTA = "ESCENARIO_B_SPEC"
PREFIJO_S3 = "sim/_spec/"
ENTIDAD_TODAS = "*"
# La validacion corre 100 semillas y cada una genera una flota distinta, asi que la
# especificacion no puede nombrar placas: usa selectores por rol y posicion
# («reparto#0» es la primera unidad de reparto de esa semilla). Una placa literal
# tambien se acepta, pero solo sirve para una semilla concreta.
RE_SELECTOR = re.compile(r"^(reparto|transporte)#([0-9]+)$")

# Tipos de robo que entiende la especificacion. El ultimo es deliberadamente de una
# forma que el detector no tuvo en cuenta al disenarse: ver formato_spec_b.md.
TIPOS = ("escalon", "sangrado", "rampa", "pulsos", "canal", "a_la_sombra")


class EspecificacionInvalida(ValueError):
    """La especificacion no se puede aplicar; no se inventa un escenario a medias."""


def ruta_por_defecto() -> str:
    ruta = os.environ.get(VARIABLE_RUTA)
    if not ruta:
        raise EspecificacionInvalida(
            f"no hay especificacion del escenario B: defina {VARIABLE_RUTA} o apunte a "
            f"{PREFIJO_S3} en S3. El archivo real no esta en el repositorio.")
    return ruta


def huella(ruta: str | Path) -> str:
    """SHA-256 del archivo, para sellar contra que especificacion se midio."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def cargar_spec(ruta: str | Path | None = None) -> dict:
    """Lee y valida la especificacion. No se aplica nada si algo no cuadra."""
    ruta = Path(ruta or ruta_por_defecto())
    if not ruta.exists():
        raise EspecificacionInvalida(f"no existe la especificacion: {ruta}")
    spec = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}

    robos = spec.get("robos")
    if not robos:
        raise EspecificacionInvalida(f"{ruta.name}: no declara ningun robo")
    vistos = set()
    for r in robos:
        for campo in ("id", "tipo", "entidad", "desde", "magnitud"):
            if campo not in r:
                raise EspecificacionInvalida(f"{ruta.name}: a un robo le falta «{campo}»")
        if r["tipo"] not in TIPOS:
            raise EspecificacionInvalida(f"{ruta.name}: tipo desconocido «{r['tipo']}», use {TIPOS}")
        if not 0 < float(r["magnitud"]) < 1:
            raise EspecificacionInvalida(f"{ruta.name}: la magnitud de {r['id']} debe estar entre 0 y 1")
        if r["id"] in vistos:
            raise EspecificacionInvalida(f"{ruta.name}: el id {r['id']} esta repetido")
        vistos.add(r["id"])
    spec["huella_sha256"] = huella(ruta)
    spec["archivo"] = ruta.name
    return spec


def resolver_entidad(entidad: str, unidades: pd.DataFrame) -> str:
    """«reparto#0» → la placa de la primera unidad de reparto de esta semilla."""
    m = RE_SELECTOR.match(str(entidad))
    if not m:
        return str(entidad)
    rol, posicion = m.group(1), int(m.group(2))
    del_rol = unidades[unidades["rol"] == rol]["placa_norm"].tolist()
    if posicion >= len(del_rol):
        raise EspecificacionInvalida(
            f"«{entidad}»: solo hay {len(del_rol)} unidades de {rol} en esta semilla")
    return del_rol[posicion]


def _a_fecha(valor) -> dt.date:
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    return dt.date.fromisoformat(str(valor))


def _factor(robo: dict, fechas: pd.Series, con_evento: pd.Series) -> np.ndarray:
    """Fraccion de kg que se lleva el robo en cada periodo. 0 donde no actua."""
    desde = _a_fecha(robo["desde"])
    hasta = _a_fecha(robo["hasta"]) if robo.get("hasta") else None
    magnitud = float(robo["magnitud"])
    dentro = fechas.map(lambda f: f >= desde and (hasta is None or f <= hasta)).to_numpy()
    factor = np.zeros(len(fechas))
    tipo = robo["tipo"]

    if tipo in ("escalon", "canal"):
        factor[dentro] = magnitud
    elif tipo == "sangrado":
        # Constante y pequenio: el mas dificil de ver de golpe y el mas caro al anio.
        factor[dentro] = magnitud
    elif tipo == "rampa":
        # Crece desde cero hasta la magnitud a lo largo de `semanas_rampa`.
        semanas = float(robo.get("semanas_rampa", 26))
        avance = fechas.map(lambda f: max((f - desde).days / 7.0, 0.0) / semanas).to_numpy()
        factor[dentro] = magnitud * np.clip(avance[dentro], 0.0, 1.0)
    elif tipo == "pulsos":
        cada = int(robo.get("cada_n_periodos", 4))
        indice = np.arange(len(fechas))
        factor[dentro & (indice % cada == 0)] = magnitud
    elif tipo == "a_la_sombra":
        # Solo roba en periodos que ya tienen un evento legitimo documentado: el salto
        # queda explicado por el evento y el detector no lo separa del ruido normal.
        factor[dentro & con_evento.to_numpy()] = magnitud
    return factor


def inyectar(escenario_a: dict, ruta_spec: str | Path | None = None) -> dict:
    """Aplica los robos de la especificacion sobre una serie del escenario A.

    Devuelve los mismos granos que el escenario A mas `verdad`, que dice por entidad y
    periodo cuantos kg se llevo cada robo. `verdad` es la respuesta del examen: se usa
    para medir la deteccion y **no se publica junto con la serie**.
    """
    spec = cargar_spec(ruta_spec)
    semanal = escenario_a["semanal"].copy()
    semanal["robado_kg"] = 0.0
    semanal["robo_id"] = ""

    placas = set(semanal["placa_norm"])
    verdad = []
    for robo in spec["robos"]:
        entidad = robo["entidad"]
        if entidad != ENTIDAD_TODAS:
            entidad = resolver_entidad(entidad, escenario_a["unidades"])
        if entidad != ENTIDAD_TODAS and entidad not in placas:
            raise EspecificacionInvalida(
                f"{robo['id']}: la entidad «{entidad}» no esta en el escenario A")
        alcance = (semanal["placa_norm"] == entidad) if entidad != ENTIDAD_TODAS \
            else pd.Series(True, index=semanal.index)
        sub = semanal[alcance]
        factor = _factor(robo, sub["fecha"], sub["evento"].ne(""))
        robado = sub["kg"].to_numpy() * factor

        semanal.loc[alcance, "kg"] = sub["kg"].to_numpy() - robado
        semanal.loc[alcance, "robado_kg"] = sub["robado_kg"].to_numpy() + robado
        # Dos robos pueden caer en la misma semana (por ejemplo uno por unidad y otro
        # de canal). Los ids se acumulan separados por «+»; si se pisaran, la serie
        # diria que solo actuo el ultimo.
        marcadas = sub.index[robado > 0]
        previos = semanal.loc[marcadas, "robo_id"]
        semanal.loc[marcadas, "robo_id"] = [
            f"{p}+{robo['id']}" if p else robo["id"] for p in previos]

        for idx in marcadas:
            verdad.append({"robo_id": robo["id"], "tipo": robo["tipo"],
                           "entidad_spec": robo["entidad"],
                           "placa_norm": semanal.at[idx, "placa_norm"],
                           "fecha": semanal.at[idx, "fecha"],
                           "robado_kg": float(robado[sub.index.get_loc(idx)])})

    semanal["kg_despachado"] = semanal["kg"] + semanal["merma_kg"]
    mensual = (semanal.groupby(["placa_norm", "rol", "anio", "mes"], as_index=False)
               .agg(kg=("kg", "sum"), merma_kg=("merma_kg", "sum"),
                    kg_despachado=("kg_despachado", "sum"),
                    combustible=("combustible", "sum"),
                    robado_kg=("robado_kg", "sum"), semanas=("kg", "size")))
    mensual["periodo"] = [f"{a}-{m:02d}" for a, m in zip(mensual["anio"], mensual["mes"])]

    return {"semanal": semanal, "mensual": mensual,
            "eventos": escenario_a["eventos"], "unidades": escenario_a["unidades"],
            "verdad": pd.DataFrame(verdad), "semilla": escenario_a.get("semilla"),
            "spec": {"archivo": spec["archivo"], "huella_sha256": spec["huella_sha256"],
                     "robos": len(spec["robos"])}}
