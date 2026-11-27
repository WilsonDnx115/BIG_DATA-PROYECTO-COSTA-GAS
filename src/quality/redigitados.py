"""Compensación de pares redigitados (commit A14).

Un error de digitación corregido deja dos movimientos en la serie: uno de +X en un
periodo y otro de −X poco después, cuando alguien lo corrige. Para el negocio los dos
juntos valen cero, pero para un detector de desvíos son dos saltos enormes: el primero
dispara la alarma y el segundo la vuelve a disparar al revés.

Este módulo encuentra esos pares y los neutraliza, **sin tocar los errores que nadie
corrigió**: un +500 suelto puede ser justamente lo que hay que detectar, así que se deja
intacto y marcado como no compensado.

No se borra ninguna fila. Se añaden dos columnas:

* `redigitado`: si la fila es parte de un par corregido.
* `<valor>_compensado`: el valor que debe mirar el detector, 0 en las filas del par.

Lo usa el detector de Frank (F13).

Uso:
    from src.quality.redigitados import compensar
    df = compensar(movimientos, entidad="placa_norm", valor="kg")
"""
from __future__ import annotations

import pandas as pd

# Dos digitaciones de la misma cifra pueden diferir por el redondeo del sistema.
TOLERANCIA_KG = 1.0


def compensar(df: pd.DataFrame, entidad: str, valor: str, ventana: int = 2,
              periodo: str = "periodo", tolerancia: float = TOLERANCIA_KG) -> pd.DataFrame:
    """Marca y neutraliza los pares +X / −X de una misma entidad en periodos cercanos.

    `ventana` es cuántos periodos después se acepta la corrección: con 2, la corrección
    puede estar en el periodo siguiente o en el subsiguiente. `periodo` tiene que ser
    ordenable (un entero, una fecha o un «AAAA-MM»); solo se usa su orden, no su
    distancia, así que sirve igual para series semanales y mensuales.

    Cuando varios errores compiten por una misma correccion, se la queda el mas antiguo:
    la regla es determinista y no depende del orden de las filas de entrada. Una
    correccion nunca cancela dos errores.

    Devuelve una copia con `redigitado` y `<valor>_compensado`. El orden de las filas
    de la entrada se conserva.
    """
    for columna in (entidad, valor, periodo):
        if columna not in df.columns:
            raise KeyError(f"falta la columna «{columna}» en el DataFrame")

    salida = df.copy()
    salida["redigitado"] = False
    compensado = f"{valor}_compensado"
    salida[compensado] = pd.to_numeric(salida[valor], errors="coerce")

    for _, grupo in salida.groupby(entidad, sort=False, dropna=False):
        orden = grupo.sort_values(periodo, kind="stable")
        indices = list(orden.index)
        valores = orden[valor].tolist()
        emparejado: set[int] = set()

        for i, origen in enumerate(indices):
            if origen in emparejado:
                continue
            v = valores[i]
            if pd.isna(v) or v == 0:
                continue
            # La corrección está en alguno de los `ventana` periodos siguientes.
            for j in range(i + 1, min(i + 1 + ventana, len(indices))):
                destino = indices[j]
                if destino in emparejado:
                    continue
                w = valores[j]
                if pd.isna(w) or (v > 0) == (w > 0):        # tiene que ser del signo contrario
                    continue
                if abs(v + w) <= tolerancia:
                    emparejado.update({origen, destino})
                    salida.loc[[origen, destino], "redigitado"] = True
                    salida.loc[[origen, destino], compensado] = 0.0
                    break

    return salida


def resumen(df: pd.DataFrame, valor: str) -> dict:
    """Cuántos pares se compensaron y cuántos kilos se neutralizaron."""
    marcadas = int(df["redigitado"].sum())
    neutralizados = float(df.loc[df["redigitado"], valor].abs().sum())
    return {"filas_redigitadas": marcadas, "pares": marcadas // 2,
            "valor_neutralizado": neutralizados,
            "filas_sin_compensar": int((~df["redigitado"]).sum())}
