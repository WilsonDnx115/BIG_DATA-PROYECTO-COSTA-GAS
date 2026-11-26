"""WP 0.8: señal S7 con resolución y ventana del informe v6."""
from src.signals.contratos import validar
from src.signals.common import _emitir, _numero, _ventana

def s7(unidad_mes, unidades):
    um, u = validar(unidad_mes, 'unidad_mes'), validar(unidades, 'unidades')
    um = um.loc[_ventana(um, 'S7')].merge(u[['unidad_id', 'habilitada']], on='unidad_id', how='left', validate='many_to_one')
    actividad = um[['gasto_total', 'gasto_combustible', 'kg_vendidos', 'kg_transportados']].apply(_numero).gt(0).any(axis=1)
    mask = um.habilitada.eq(False).fillna(False) & actividad
    um['kg_base_rol'] = um.kg_vendidos.where(um.rol.eq('reparto'), um.kg_transportados)
    return _emitir(um[mask], 'S7', 'actividad_en_unidad_no_habilitada')


