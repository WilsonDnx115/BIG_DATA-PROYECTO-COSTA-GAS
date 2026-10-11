"""WP 0.8: señal S9 con resolución y ventana del informe v6."""
import numpy as np
import pandas as pd
from src.models import base_mad
from src.signals.contratos import validar
from src.signals.common import _emitir, _ventana

def s9(unidad_mes):
    um = validar(unidad_mes, 'unidad_mes')
    p = base_mad.puntuar(um.loc[_ventana(um, 'S9')])
    sin_volumen = p.gasto_combustible.gt(0) & p.kg_base_rol.eq(0)
    raro = p.alerta_base
    motivo = pd.Series(np.where(sin_volumen, 'combustible_sin_volumen_del_rol', 'combustible_por_tonelada_atipico'), index=p.index)
    puntaje = p.puntaje.where(raro, 1.0)
    tipo = pd.Series(np.where(raro, 'regla_y_modelo', 'regla'), index=p.index)
    return _emitir(p[sin_volumen | raro], 'S9', motivo[sin_volumen | raro], puntaje[sin_volumen | raro], tipo[sin_volumen | raro])


