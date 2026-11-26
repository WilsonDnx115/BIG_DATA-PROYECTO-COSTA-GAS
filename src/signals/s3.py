"""WP 0.8: señal S3 con resolución y ventana del informe v6."""
import numpy as np
import pandas as pd
from src.common import config
from src.signals.contratos import validar
from src.signals.common import _emitir, _numero, _ventana

def s3(compras):
    c = validar(compras, 'compras')
    c = c.loc[_ventana(c, 'S3')].copy()
    precio = _numero(c.precio_usd_kg).where(lambda s: s > 0)
    grupos = [c.proveedor_id, c.fecha.dt.year, c.fecha.dt.month]
    mediana = precio.groupby(grupos).transform('median')
    pactado = _numero(c.precio_pactado_usd_kg) if 'precio_pactado_usd_kg' in c else pd.Series(np.nan, index=c.index)
    base = pactado.where(pactado.gt(0), mediana).where(lambda s: s > 0)
    desvio = (precio - base).abs() / base
    mask = desvio.gt(config.TOL_PRECIO_COMPRA)
    motivo = pd.Series(np.where(pactado.gt(0), 'precio_fuera_de_lo_pactado', 'precio_fuera_de_mediana_proveedor_mes'), index=c.index)
    return _emitir(c[mask], 'S3', motivo[mask], desvio[mask])


def s3_control(sobrecobros):
    requeridas = {'factura_id', 'fecha', 'monto_facturado_soles', 'monto_pactado_soles'}
    if not requeridas <= set(sobrecobros):
        raise ValueError('control_sobrecobros: contrato F08 incompleto')
    c = sobrecobros.copy().reset_index(drop=True)
    c['fecha'] = pd.to_datetime(c.fecha, errors='coerce').dt.normalize()
    if c.fecha.isna().any() or c.factura_id.isna().any() or c.factura_id.duplicated().any():
        raise ValueError('control_sobrecobros: fecha o factura inválida/duplicada')
    facturado, pactado = _numero(c.monto_facturado_soles), _numero(c.monto_pactado_soles)
    diferencia = facturado - pactado
    mask = _ventana(c, 'S3') & facturado.ge(0) & pactado.gt(0) & diferencia.gt(0)
    return _emitir(c[mask], 'S3', 'sobrecobro_control_F08', diferencia[mask] / pactado[mask], valor=diferencia[mask])


