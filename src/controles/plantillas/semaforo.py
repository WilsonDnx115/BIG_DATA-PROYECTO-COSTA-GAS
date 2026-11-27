"""Texto del correo del semáforo diario de unidades (B17; informe, Tabla 4.8i).

Lo llama la función del semáforo diario (W17, 6:30) con las filas de
`costagas_gold.v_semaforo_unidades` y publica el resultado en SNS. Esta función no
consulta ni envía nada: solo arma texto plano.

Cada fila es un diccionario (o cualquier objeto con `.get`) con:

| Campo              | Significado                                              |
|--------------------|----------------------------------------------------------|
| `placa_norm`       | placa normalizada de la unidad (o `placa`)               |
| `color`            | `rojo`, `ambar` (o `ámbar`) o `verde`                    |
| `inicio_desvio`    | periodo de inicio del desvío, por ejemplo `2026-09`      |
| `kg_acumulados`    | kg acumulados desde el inicio del desvío                 |
| `soles_acumulados` | S/ acumulados desde el inicio del desvío                 |

Sin datos personales: el texto solo usa esos campos (lista cerrada), así que cualquier
otra columna que traiga la fila (nombres, DNI, RUC, hashes) nunca llega al correo.
Como máximo se listan `MAX_UNIDADES` (50) unidades, primero las rojas; el resto se
cuenta y se remite al tablero. Un valor ausente se escribe «sin dato», nunca 0.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta, timezone

MAX_UNIDADES = 50
ZONA_LIMA = timezone(timedelta(hours=-5), "America/Lima")   # Perú no usa horario de verano
SIN_DATO = "sin dato"
COLORES = {"rojo": "rojo", "ambar": "ambar", "ámbar": "ambar", "verde": "verde"}
CAMPO_PLACA = ("placa_norm", "placa")


def _texto(valor) -> str | None:
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _numero(valor) -> float | None:
    """Convierte a número; lo no convertible queda como None (no como cero)."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return None if n != n else n            # NaN → None


def _miles(n: float, decimales: int) -> str:
    return f"{n:,.{decimales}f}".replace(",", " ")


def formatear_kg(valor) -> str:
    n = _numero(valor)
    return SIN_DATO if n is None else f"{_miles(n, 0)} kg"


def formatear_soles(valor) -> str:
    n = _numero(valor)
    return SIN_DATO if n is None else f"S/ {_miles(n, 2)}"


def normalizar(fila: Mapping) -> dict | None:
    """Toma solo los campos permitidos. Devuelve None si la fila no tiene color válido."""
    color = COLORES.get((_texto(fila.get("color")) or "").lower())
    if color is None:
        return None
    placa = next((_texto(fila.get(c)) for c in CAMPO_PLACA if _texto(fila.get(c))), None)
    return {
        "placa": placa or SIN_DATO,
        "color": color,
        "inicio_desvio": _texto(fila.get("inicio_desvio")) or SIN_DATO,
        "kg": _numero(fila.get("kg_acumulados")),
        "soles": _numero(fila.get("soles_acumulados")),
    }


def _orden(u: dict):
    # Más kg primero; sin dato al final; desempate estable por placa.
    return (u["kg"] is None, -(u["kg"] or 0.0), u["placa"])


def _linea(u: dict) -> str:
    return (f"- {u['placa']} · desvío desde {u['inicio_desvio']} · "
            f"{formatear_kg(u['kg'])} · {formatear_soles(u['soles'])}")


def formatear_resumen(filas: Iterable[Mapping] | None, fecha: date | datetime | None = None,
                      enlace_tablero: str | None = None, max_unidades: int = MAX_UNIDADES) -> str:
    """Texto plano del correo del semáforo diario.

    `fecha` por defecto es hoy en Lima. `enlace_tablero` es la URL de la página Semáforo de
    Grafana; la pasa quien llama (no se escribe fija en el código).
    """
    if fecha is None:
        fecha = datetime.now(ZONA_LIMA).date()
    elif isinstance(fecha, datetime):
        fecha = fecha.date()
    tope = max(int(max_unidades), 0)

    unidades = [u for u in (normalizar(f) for f in (filas or [])) if u is not None]
    rojas = sorted((u for u in unidades if u["color"] == "rojo"), key=_orden)
    ambar = sorted((u for u in unidades if u["color"] == "ambar"), key=_orden)
    verdes = sum(1 for u in unidades if u["color"] == "verde")

    cupo_rojo = rojas[:tope]
    cupo_ambar = ambar[:max(tope - len(cupo_rojo), 0)]
    omitidas = (len(rojas) - len(cupo_rojo)) + (len(ambar) - len(cupo_ambar))

    lineas = [f"Semáforo diario de unidades · {fecha.isoformat()}", ""]

    if rojas:
        lineas.append(f"Unidades en rojo ({len(rojas)}):")
        lineas.extend(_linea(u) for u in cupo_rojo)
    else:
        lineas.append("Sin unidades en rojo hoy.")
    lineas.append("")

    if ambar:
        lineas.append(f"Unidades en ámbar ({len(ambar)}):")
        lineas.extend(_linea(u) for u in cupo_ambar)
        if not cupo_ambar:
            lineas.append("- (no caben en este correo; ver el tablero)")
    else:
        lineas.append("Sin unidades en ámbar hoy.")
    lineas.append("")

    lineas.append(f"Unidades en verde: {verdes}.")
    if omitidas:
        lineas.append(f"Se muestran {len(cupo_rojo) + len(cupo_ambar)} unidades; "
                      f"{omitidas} más en el tablero.")
    lineas.append("")
    lineas.append(f"Tablero: {enlace_tablero.strip() if enlace_tablero and enlace_tablero.strip() else 'enlace no configurado'}")
    lineas.append("Una unidad en rojo es una alerta para revisar con su expediente, no una pérdida confirmada.")
    return "\n".join(lineas) + "\n"
