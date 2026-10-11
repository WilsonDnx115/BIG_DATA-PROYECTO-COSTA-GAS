"""WP 0.8: señal S2 con resolución y ventana del informe v6."""
import numpy as np
import pandas as pd
from src.signals.contratos import validar
from src.signals.common import _emitir, _ventana

def s2(compras):
    c = validar(compras, 'compras')
    c = c.loc[_ventana(c, 'S2')].copy()
    scop = c.codigo_scop.astype('string').fillna('').str.strip()
    repetido = scop.ne('') & scop.duplicated(keep=False)
    mask = scop.eq('') | repetido
    motivos = pd.Series(np.where(scop.eq(''), 'compra_sin_scop', 'scop_repetido'), index=c.index)
    return _emitir(c[mask], 'S2', motivos[mask])


