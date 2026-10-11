"""WP 0.8: señal S6 con resolución y ventana del informe v6."""
from src.common import config
from src.signals.contratos import validar
from src.signals.common import _emitir, _numero, _ventana

def s6(compras, tc):
    c, oficial = validar(compras, 'compras'), validar(tc, 'tc')
    c = c.loc[_ventana(c, 'S6')]
    c = c.merge(oficial[['fecha', 'tc_oficial']], on='fecha', how='left', validate='many_to_one')
    base, registrado = _numero(c.tc_oficial), _numero(c.tipo_cambio)
    desvio = (registrado - base).abs() / base.where(base.gt(0))
    mask = desvio.gt(config.TOL_TIPO_CAMBIO) & registrado.gt(0)
    return _emitir(c[mask], 'S6', 'tipo_cambio_difiere_del_oficial', desvio[mask])
