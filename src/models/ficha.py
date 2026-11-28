"""Ficha de cada version del modelo S12, generada desde el registro (commit AR07).

El registro de W13 deja en `gold/_modelos/s12/vigente.json` la ficha de la corrida
que esta puntuando hoy: su ruta, su version, su umbral y sus metricas. Este modulo
convierte ese JSON en el documento que se revisa y se adjunta al informe, con el
formato de `docs/modelos/plantilla_ficha.md`.

Se genera, no se escribe a mano, por una razon concreta: una ficha copiada a mano
envejece en silencio: queda describiendo un umbral que el modelo ya no usa. Aqui el
umbral que se publica es el que esta en el registro o no se publica nada.

Que hace cuando falta un dato: lo dice. Si `vigente.json` no trae los sesgos o el
PSI, la ficha sale con «no cubierto» y el motivo, nunca en blanco ni con un
«por confirmar» (regla 2 del equipo). Un campo vacio en una ficha de modelo se lee
como que el modelo no tiene sesgos, que es muy distinto de que nadie los midio.

Uso:
    python -m src.models.ficha                      # la del vigente, a stdout
    python -m src.models.ficha --destino docs/modelos/ficha_s12.md
"""
from __future__ import annotations

import argparse

from src.models import registro

# Las metricas que la ficha busca por nombre, en el orden en que se publican.
# `pr_auc` es la de la Tabla 4.8b; `precision` y `recall` gobiernan la promocion
# del retador en `registro.promover_si_mejora`.
METRICAS = ("precision", "recall", "pr_auc", "f1")

# Sesgos del paso 5.3 del PLAN: por tipo de unidad, producto y canal.
SESGOS = (("por_rol", "tipo de unidad (rol)"), ("por_producto", "producto"),
          ("por_canal", "canal"))

FALTA = "no cubierto"
_MOTIVO = "lo escribe el entrenamiento en vigente.json (W13)"


def _no_cubierto(clave: str, motivo: str = _MOTIVO) -> str:
    return f"{FALTA}: sin `{clave}` en el registro; {motivo}"


def _intervalo(ic, metrica: str):
    """`[bajo, alto]` del bootstrap, o None si esa metrica no lo trae."""
    if not isinstance(ic, dict):
        return None
    valor = ic.get(metrica)
    if not isinstance(valor, (list, tuple)) or len(valor) != 2:
        return None
    return [float(valor[0]), float(valor[1])]


def construir(ficha_vigente: dict | None = None, base: str | None = None,
              modelo_nombre: str = registro.MODELO) -> dict:
    """La ficha completa del modelo vigente, lista para `a_markdown()`.

    Sin modelo promovido devuelve `{"estado": "sin_vigente"}`: todavia no hay nada
    que describir, y eso tambien es un resultado.
    """
    vig = ficha_vigente if ficha_vigente is not None else registro.vigente(base, modelo_nombre)
    if not vig:
        return {"estado": "sin_vigente",
                "motivo": _no_cubierto("vigente.json", "ningun modelo promovido todavia")}

    metricas = vig.get("metricas") or {}
    ic = metricas.get("ic") or metricas.get("intervalos")

    medidas = {}
    for nombre in METRICAS:
        valor = metricas.get(nombre)
        medidas[nombre] = {"valor": None if valor is None else float(valor),
                           "ic95": _intervalo(ic, nombre),
                           "remuestreos": metricas.get("remuestreos")}

    datos = metricas.get("datos") or {}
    variables = metricas.get("variables")
    psi = metricas.get("psi")
    sesgos = metricas.get("sesgos") or {}

    return {
        "estado": "ok",
        "version": vig.get("version") or _no_cubierto("version"),
        "corrida": vig.get("corrida") or _no_cubierto("corrida"),
        "ruta": vig.get("ruta") or _no_cubierto("ruta"),
        "umbral": vig.get("umbral", metricas.get("umbral")),
        "datos": datos or _no_cubierto("metricas.datos"),
        "variables": list(variables) if variables else _no_cubierto("metricas.variables"),
        "metricas": medidas,
        "psi": psi if psi else _no_cubierto("metricas.psi",
                                           "se mide con src.models.deriva al puntuar"),
        "sesgos": {clave: sesgos.get(clave) or _no_cubierto(f"metricas.sesgos.{clave}",
                                                            "paso 5.3 del PLAN")
                   for clave, _ in SESGOS},
    }


def _numero(valor) -> str:
    if valor is None:
        return FALTA
    return f"{valor:.4f}" if isinstance(valor, float) else str(valor)


def _fila_metrica(nombre: str, medida: dict) -> str:
    ic = medida["ic95"]
    texto_ic = f"{ic[0]:.4f} a {ic[1]:.4f}" if ic else f"{FALTA}: sin bootstrap de `{nombre}`"
    return f"| {nombre} | {_numero(medida['valor'])} | {texto_ic} |"


def _bloque(titulo: str, contenido, nivel: str = "##") -> str:
    """Una seccion de la ficha. Si el dato falta, se imprime el motivo, no un hueco."""
    if isinstance(contenido, str):
        return f"{nivel} {titulo}\n\n{contenido}\n"
    if isinstance(contenido, dict):
        cuerpo = "\n".join(f"- **{k}:** {v}" for k, v in contenido.items())
    elif isinstance(contenido, (list, tuple)):
        cuerpo = "\n".join(f"- `{v}`" for v in contenido)
    else:
        cuerpo = str(contenido)
    return f"## {titulo}\n\n{cuerpo}\n"


def a_markdown(ficha: dict) -> str:
    """La ficha en el formato de `docs/modelos/plantilla_ficha.md`."""
    if ficha.get("estado") != "ok":
        return ("# Ficha del modelo S12\n\n"
                f"**Sin modelo vigente.** {ficha.get('motivo', _no_cubierto('vigente.json'))}\n")

    partes = [f"# Ficha del modelo {ficha['version']}", "",
              f"- **Corrida:** {ficha['corrida']}",
              f"- **Artefacto:** `{ficha['ruta']}`",
              f"- **Umbral de decision:** {_numero(ficha['umbral'])}",
              "",
              "Generada con `python -m src.models.ficha` desde "
              "`gold/_modelos/s12/vigente.json` (registro de W13).", ""]

    partes.append(_bloque("Datos de entrenamiento", ficha["datos"]))
    partes.append(_bloque("Variables", ficha["variables"]))

    partes.append("## Metricas\n")
    partes.append("Intervalo del 95 % por bootstrap "
                  f"({_numero(ficha['metricas']['precision']['remuestreos'])} remuestreos, "
                  "`BOOTSTRAP_REMUESTREOS`).\n")
    partes.append("| Metrica | Valor | IC 95 % |")
    partes.append("|---|---|---|")
    partes += [_fila_metrica(n, ficha["metricas"][n]) for n in METRICAS]
    partes.append("")

    partes.append(_bloque("Deriva (PSI)", ficha["psi"]))

    partes.append("## Sesgos (paso 5.3 del PLAN)\n")
    for clave, etiqueta in SESGOS:
        partes.append(_bloque(f"Por {etiqueta}", ficha["sesgos"][clave], nivel="###"))

    return "\n".join(partes).rstrip() + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ficha del modelo vigente, desde el registro")
    ap.add_argument("--destino", help="archivo .md donde escribirla; sin esto va a stdout")
    ap.add_argument("--base", help="prefijo del registro; por defecto gold/_modelos/<modelo>")
    ap.add_argument("--modelo", default=registro.MODELO)
    a = ap.parse_args(argv)

    ficha = construir(base=a.base, modelo_nombre=a.modelo)
    texto = a_markdown(ficha)
    if a.destino:
        from pathlib import Path  # noqa: PLC0415

        Path(a.destino).parent.mkdir(parents=True, exist_ok=True)
        Path(a.destino).write_text(texto, encoding="utf-8")
        print(f"ficha escrita en {a.destino}")
    else:
        print(texto)
    # Sin modelo vigente no es un error del programa: es el estado del registro.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
