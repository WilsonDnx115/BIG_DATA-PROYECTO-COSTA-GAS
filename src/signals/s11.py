"""WP 0.8: señal S11 con resolución y ventana del informe v6."""
import numpy as np
import pandas as pd
from src.common import config
from src.signals.contratos import validar
from src.signals.common import _emitir, _numero, _ventana

def s11(produccion):
    p = validar(produccion, 'produccion')
    p = p.loc[_ventana(p, 'S11')].copy()
    cols = ['stock_inicial', 'produccion', 'ventas', 'bonificaciones', 'stock_final']
    n = p[cols].apply(_numero)
    residuo = n.stock_inicial + n.produccion - n.ventas - n.bonificaciones - n.stock_final
    cero = pd.Series(np.isclose(residuo, 0, atol=config.TOL_RESIDUO_STOCK, rtol=0), index=p.index)
    mask = cero & n.notna().all(axis=1) & p.stock_final_es_calculado.eq(True).fillna(False)
    ajuste = n.produccion.lt(0) & (n.produccion + n.stock_inicial).abs().le(config.TOL_RESIDUO_STOCK)
    motivo = pd.Series(np.where(ajuste, 'cierre_calculado_con_ajuste', 'cierre_calculado_sin_medicion_independiente'), index=p.index)
    return _emitir(p[mask], 'S11', motivo[mask])


