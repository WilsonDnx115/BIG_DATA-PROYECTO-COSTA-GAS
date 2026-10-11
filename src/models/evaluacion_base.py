"""WP 0.8: expedientes, muestra ciega y métricas con evidencia independiente."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.common import config, lake_io, rutas
from src.models import base_mad
from src.signals import senales
from src.signals.contratos import leer_entradas, validar, ENTRADAS


def priorizar(alertas: pd.DataFrame, k: int = config.TOP_K) -> pd.DataFrame:
    """Orden operativo: evidencia, percentil dentro de señal, fecha e ID estable."""
    if k <= 0 or alertas.id_alerta.duplicated().any():
        raise ValueError('k debe ser positivo y las alertas deben tener IDs únicos')
    df = alertas.copy()
    df['_evidencia'] = df.grado_evidencia.map({'alto': 2, 'medio': 1, 'nulo': 0})
    if df._evidencia.isna().any():
        raise ValueError('Grado de evidencia inválido')
    p = pd.to_numeric(df.puntaje, errors='coerce')
    if (~np.isfinite(p)).any():
        raise ValueError('Puntajes no finitos no pueden priorizarse')
    df['_percentil_senal'] = p.groupby(df.senal).rank(method='average', pct=True)
    df = df.sort_values(['_evidencia', '_percentil_senal', 'fecha', 'id_alerta'],
                        ascending=[False, False, False, True], kind='stable')
    return df.head(k).drop(columns=['_evidencia', '_percentil_senal']).reset_index(drop=True)


def muestra_ciega(alertas: pd.DataFrame, top: pd.DataFrame,
                  n_azar: int = config.MUESTRA_REVISION_ALEATORIA) -> tuple[pd.DataFrame, list[str]]:
    """Quita puntaje, grado y selección; mezcla top y control aleatorio reproducible."""
    restantes = alertas[~alertas.id_alerta.isin(top.id_alerta)]
    if n_azar < 0:
        raise ValueError('El tamaño aleatorio no puede ser negativo')
    azar = restantes.sample(n=min(n_azar, len(restantes)), random_state=config.SEMILLA)
    muestra = (pd.concat([top, azar], ignore_index=True) if len(azar) else top.copy()).sample(
        frac=1, random_state=config.SEMILLA)
    campos = ['id_alerta', 'senal', 'resolucion', 'fecha', 'unidad_id', 'rol', 'factura_id',
              'codigo_scop', 'kg', 'motivo', 'fuentes']
    ciega = muestra[campos].copy().reset_index(drop=True)
    for c in ('confirmada', 'revisor_id', 'evidencia_ref'):
        ciega[c] = None
    return ciega, azar.id_alerta.tolist()


def _revisiones(revisiones: pd.DataFrame | None, autor_modelo: str, ids: set) -> pd.DataFrame:
    campos = ['id_alerta', 'confirmada', 'revisor_id', 'evidencia_ref']
    if revisiones is None:
        return pd.DataFrame(columns=campos)
    if not set(campos) <= set(revisiones):
        raise ValueError('Revisión documental incompleta')
    r = revisiones[campos].copy()
    if r.id_alerta.isna().any() or r.id_alerta.duplicated().any() or not set(r.id_alerta) <= ids:
        raise ValueError('Revisiones con IDs ausentes, repetidos o desconocidos')
    completadas = r.confirmada.notna()
    if not r.loc[completadas, 'confirmada'].isin([True, False, 1, 0]).all():
        raise ValueError('confirmada debe ser booleana, 0/1 o nula')
    terminadas = r.loc[completadas]
    if len(terminadas) and (not autor_modelo.strip() or terminadas.revisor_id.fillna('').str.strip().eq('').any()
                           or terminadas.revisor_id.str.strip().str.casefold().eq(autor_modelo.strip().casefold()).any()
                           or terminadas.evidencia_ref.fillna('').str.strip().eq('').any()):
        raise ValueError('Toda decisión requiere revisor distinto del autor y referencia de evidencia')
    return r.set_index('id_alerta', drop=False)


def metricas(alertas: pd.DataFrame, top: pd.DataFrame, ids_azar: list[str], periodos: pd.DataFrame,
             revisiones: pd.DataFrame | None = None, autor_modelo: str = '',
             casos: pd.DataFrame | None = None, diferencias: pd.DataFrame | None = None,
             k: int = config.TOP_K) -> dict:
    """Sin revisión/diferencias/casos, la métrica correspondiente es null, no cero."""
    if k <= 0 or alertas.id_alerta.duplicated().any() or top.id_alerta.duplicated().any():
        raise ValueError('k positivo e IDs únicos son obligatorios')
    ids = set(alertas.id_alerta)
    if not set(top.id_alerta) <= ids or not set(ids_azar) <= ids or set(ids_azar) & set(top.id_alerta):
        raise ValueError('Top/control contienen IDs desconocidos o superpuestos')
    r = _revisiones(revisiones, autor_modelo, ids)
    decisiones = r['confirmada'] if len(r) else pd.Series(dtype=object)
    etiquetas_top = decisiones.reindex(top.id_alerta)
    etiquetas_azar = decisiones.reindex(ids_azar)
    precision = float(etiquetas_top.astype(float).mean()) if len(top) == k and etiquetas_top.notna().all() else None
    tasa_base = float(etiquetas_azar.astype(float).mean()) if len(ids_azar) == config.MUESTRA_REVISION_ALEATORIA and etiquetas_azar.notna().all() else None
    if not {'anio', 'mes'} <= set(periodos):
        raise ValueError('Faltan los períodos observados')
    if not periodos.mes.between(1, 12).all():
        raise ValueError('Mes inválido en períodos')
    meses = pd.MultiIndex.from_frame(periodos[['anio', 'mes']].drop_duplicates())
    conteos = alertas.groupby(['anio', 'mes']).id_alerta.nunique()
    if not set(conteos.index) <= set(meses):
        raise ValueError('Hay alertas de meses no observados')
    conteos = conteos.reindex(meses, fill_value=0)
    recuperacion = None
    n_casos = None
    if casos is not None:
        necesarias = {'caso_id', 'id_alerta', 'confirmado_documentalmente', 'revisor_id', 'evidencia_ref'}
        if not necesarias <= set(casos) or casos.caso_id.isna().any() or casos.caso_id.duplicated().any():
            raise ValueError('Catálogo de casos conocidos inválido')
        if not casos.confirmado_documentalmente.isin([True]).all():
            raise ValueError('Los casos conocidos deben estar confirmados documentalmente')
        if len(casos) and (not autor_modelo.strip() or casos.revisor_id.fillna('').str.strip().eq('').any()
                          or casos.revisor_id.str.strip().str.casefold().eq(autor_modelo.strip().casefold()).any()
                          or casos.evidencia_ref.fillna('').str.strip().eq('').any()):
            raise ValueError('Casos conocidos requieren revisión independiente y evidencia')
        n_casos = len(casos)
        recuperacion = float(casos.id_alerta.isin(ids).mean()) if n_casos else None
    cobertura = None
    total_kg = None
    if diferencias is not None:
        if not {'caso_id', 'id_alerta', 'kg_diferencia', 'evidencia_ref'} <= set(diferencias):
            raise ValueError('Falta trazabilidad de las diferencias atribuibles')
        kg = pd.to_numeric(diferencias.kg_diferencia, errors='coerce')
        if diferencias.caso_id.isna().any() or diferencias.caso_id.duplicated().any() or (~np.isfinite(kg)).any() or diferencias.evidencia_ref.fillna('').str.strip().eq('').any():
            raise ValueError('Diferencias sin clave única, kg finitos o evidencia')
        kg = kg.clip(lower=0)
        total_kg = float(kg.sum())
        cobertura = float(kg[diferencias.id_alerta.isin(ids)].sum() / total_kg) if total_kg else None
    evaluadas = decisiones.dropna()
    return {
        'precision@20_documental' if k == 20 else f'precision@{k}_documental': precision,
        'tasa_base_control_aleatorio': tasa_base,
        'recuperacion_casos_conocidos': recuperacion, 'casos_conocidos': n_casos,
        'pct_kg_cubiertos': cobertura, 'kg_diferencia_total_atribuible': total_kg,
        'alertas_total': len(alertas), 'top_disponibles': len(top),
        'top_revisadas': int(etiquetas_top.notna().sum()), 'control_disponible': len(ids_azar),
        'control_revisadas': int(etiquetas_azar.notna().sum()),
        'revisadas_total': len(evaluadas), 'confirmadas_total': int(evaluadas.astype(float).sum()),
        'alertas_por_mes': {f'{a}-{m:02d}': int(n) for (a, m), n in conteos.items()},
        'alertas_por_mes_media': float(conteos.mean()) if len(conteos) else None,
        'alertas_por_mes_max': int(conteos.max()) if len(conteos) else None,
        'nota': 'Métricas documentales requieren revisión independiente; no se usan etiquetas débiles S1/S8. Cobertura de kg requiere casos atribuibles, no volumen de operación.',
    }


def ejecutar(tablas: dict, tipo_datos: str, destino: Path, revisiones=None, autor_modelo='',
             casos=None, diferencias=None) -> dict:
    """Calcula y exporta; tablas de prueba solo fuera del repo o en .build/."""
    if tipo_datos not in {'reales', 'muestra_enmascarada', 'prueba'}:
        raise ValueError('Declare tipo_datos: reales, muestra_enmascarada o prueba')
    destino = Path(destino)
    if tipo_datos == 'prueba' and destino.resolve().is_relative_to(config.RAIZ_REPO.resolve()) and not destino.resolve().is_relative_to((config.RAIZ_REPO / '.build').resolve()):
        raise ValueError('Los resultados de prueba no se guardan como evidencias versionadas; use .build/')
    if not set(ENTRADAS) <= tablas.keys():
        raise ValueError('Faltan tablas de entrada WP 0.8')
    tablas = {t: validar(tablas[t], t) for t in ENTRADAS} | (
        {'sobrecobros': tablas['sobrecobros']} if 'sobrecobros' in tablas else {})
    alertas = senales.calcular(tablas)
    p = base_mad.puntuar(tablas['unidad_mes'].loc[tablas['unidad_mes'].anio.eq(config.ANIO_PILOTO)])
    top = priorizar(alertas)
    ciega, azar = muestra_ciega(alertas, top)
    observadas = [('compras', 'S2'), ('produccion', 'S11')]
    periodos = pd.concat([tablas['unidad_mes'].loc[tablas['unidad_mes'].anio.eq(2020), ['anio', 'mes']],
                          *[pd.DataFrame({'anio': tablas[t].loc[senales._ventana(tablas[t], s), 'fecha'].dt.year,
                                         'mes': tablas[t].loc[senales._ventana(tablas[t], s), 'fecha'].dt.month})
                            for t, s in observadas]], ignore_index=True).drop_duplicates()
    m = metricas(alertas, top, azar, periodos, revisiones, autor_modelo, casos, diferencias)
    resultado = {
        'paquete': 'WP 0.8', 'tipo_datos': tipo_datos,
        'estado': 'calculado_pendiente_validacion' if any(m[x] is None for x in (f'precision@{config.TOP_K}_documental', 'tasa_base_control_aleatorio', 'recuperacion_casos_conocidos', 'pct_kg_cubiertos')) else 'medido_con_evidencia_documental',
        'entradas': {t: len(df) for t, df in tablas.items()}, 'metricas': m,
        'modelo': {'unidad_mes': len(p), 'evaluable': int(p.z.notna().sum()),
                   'no_evaluable': int(p.z.isna().sum()), 'alertas_mad': int(p.alerta_base.sum()),
                   'variable': 'log(S/ combustible por tonelada del rol)', 'umbral_abs_z': config.UMBRAL_Z_MAD},
        'senales': senales.resumen(alertas).set_index('senal').alertas.to_dict(),
        'evaluabilidad': senales.evaluabilidad(tablas),
        'S8': 'no_resoluble', 'S12': 'WP 0.11 pendiente',
        'control_F08': 'disponible' if 'sobrecobros' in tablas else 'no_disponible',
        'metas_referencia_no_resultados': {'precision_documental': config.META_PRECISION_DOCUMENTAL,
                                          'recuperacion_casos': config.META_RECUPERACION_CASOS,
                                          'pct_kg_cubiertos': config.META_KG_CUBIERTOS,
                                          'alertas_por_mes': config.META_ALERTAS_MES},
        'priorizacion': 'Grado de evidencia, percentil de puntaje dentro de señal, fecha descendente e ID; criterio operativo, no probabilidad de robo ni puntaje calibrado entre señales.',
        'nota_tipo_datos': 'Declaración del operador; la interfaz no certifica por sí sola procedencia ni anonimización.',
    }
    # Todos los cálculos/validaciones se completan antes de reemplazar evidencias.
    texto = json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False)
    destino.mkdir(parents=True, exist_ok=True)
    top.to_csv(destino / 'top20_base.csv', index=False)
    ciega.to_csv(destino / 'expedientes_revision.csv', index=False)
    (destino / 'linea_base_tecnica.json').write_text(texto + '\n', encoding='utf-8')
    p.to_parquet(destino / 'puntajes_unidad_mes.parquet', index=False)
    return resultado


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tipo-datos', required=True, choices=['reales', 'muestra_enmascarada', 'prueba'])
    ap.add_argument('--salida', type=Path)
    ap.add_argument('--revisiones', type=Path)
    ap.add_argument('--casos', type=Path)
    ap.add_argument('--diferencias', type=Path)
    ap.add_argument('--autor-modelo', default='')
    a = ap.parse_args()
    salida = a.salida or config.RAIZ_REPO / ('.build/wp-0.8' if a.tipo_datos == 'prueba' else 'docs/evidencias')
    try:
        tablas = leer_entradas()
        control = lake_io.leer_parquet(rutas.ruta('silver', 'control_sobrecobros'))
        if not control.empty:
            tablas['sobrecobros'] = control
        leer = lambda p: pd.read_csv(p) if p else None
        resultado = ejecutar(tablas, a.tipo_datos, salida, leer(a.revisiones), a.autor_modelo,
                              leer(a.casos), leer(a.diferencias))
    except (FileNotFoundError, ValueError) as exc:
        ap.exit(2, f'WP 0.8 pendiente: {exc}\n')
    print(f'WP 0.8: {resultado["estado"]}; expedientes y métricas en {salida}')
