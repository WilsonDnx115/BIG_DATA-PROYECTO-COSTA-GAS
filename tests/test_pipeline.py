"""Integración Bronze → Silver → Gold sobre una muestra pequeña."""
import pandas as pd
import pytest

from src.bronze_to_silver import handler
from src.common import lake_io, muestra, rutas, schemas
from src.common.reproceso import regenerar
from src.ingest import internos
from src.signals import senales
from src.silver_to_gold import conciliacion


@pytest.fixture()
def lago_cargado(lago):
    origen = lago / "entrega"
    verdad = muestra.generar(n_unidades=8, semilla=7, destino=origen)
    archivos = internos.ingerir(origen, fecha_carga="2026-10-07")
    for a in archivos:
        handler.procesar_archivo(a)
    handler.construir_movimientos()
    return verdad, archivos


def test_bronze_inmutable_y_manifiesto(lago_cargado):
    _, archivos = lago_cargado
    assert all("fecha_carga=2026-10-07" in a for a in archivos)
    man = pd.read_json(rutas.ruta("_manifests", "fecha_carga=2026-10-07", "manifest.json"))
    assert set(man["ruta_bronze"]) == set(archivos)
    assert man["sha256"].str.len().eq(64).all()


def test_silver_cumple_contratos(lago_cargado):
    for tabla, contrato in [(("movimientos",), "movimientos"),
                            (("flota", "dis_01_vehiculos"), "flota"),
                            (("maestro", "red_02_distribuidores"), "maestro")]:
        df = lake_io.leer_parquet(rutas.ruta("silver", *tabla))
        assert schemas.validar(df, contrato) == [], contrato


def test_silver_sin_datos_personales(lago_cargado):
    flota = lake_io.leer_parquet(rutas.ruta("silver", "flota", "dis_01_vehiculos"))
    assert "conductor" not in flota.columns
    assert not flota["conductor_hash"].str.contains("CONDUCTOR").any()


def test_rechazos_y_duplicados(lago_cargado):
    compras = lake_io.leer_parquet(handler.destino_silver("aba_02"))
    ventas = lake_io.leer_parquet(handler.destino_silver("com_19"))
    assert compras["anio"].between(2016, 2024).all()
    assert not ventas.duplicated(["documento", "linea"]).any()


def test_conciliacion_conserva_kg(lago_cargado):
    movs = lake_io.leer_parquet(rutas.ruta("silver", "movimientos"))
    conc = conciliacion.conciliar_pandas()
    assert conc["kg_comprados"].sum() == pytest.approx(movs["kg_comprados"].sum())
    assert conc["kg_vendidos"].sum() == pytest.approx(movs["kg_vendidos"].sum())
    assert not conc.duplicated(["placa_norm", "fecha", "id_producto"]).any()
    assert schemas.validar(conc, "fact_conciliacion_unidad") == []


def test_partition_pruning(lago_cargado):
    conc = conciliacion.conciliar_pandas(anios=[2020])
    assert set(conc["anio"]) == {2020}


def test_senales_recuperan_inyectadas(lago_cargado):
    verdad, _ = lago_cargado
    alertas = senales.calcular_todas()
    assert schemas.validar(alertas, "fact_alerta") == []
    s1 = set(alertas.loc[alertas["senal"] == "S1", "placa_norm"])
    assert s1 and s1 <= set(verdad["unidades_anomalas"])
    s7 = set(alertas.loc[alertas["senal"] == "S7", "placa_norm"])
    assert s7 == set(verdad["no_habilitadas"])


def test_reproceso_regenera_particion_identica(lago_cargado):
    r = regenerar("aba_02", 2020, 7)
    assert r["tras_borrar"]["filas"] == 0
    assert r["identica"]


def test_esquema_declarado_rechaza_archivo(lago, tmp_path):
    malo = tmp_path / "malo.csv"
    pd.DataFrame({"SCOP": ["1"], "FECHA": ["2020-01-01"]}).to_csv(malo, index=False)
    with pytest.raises(ValueError, match="esquema declarado"):
        handler.procesar_archivo(str(malo), "aba_02")


def test_ingerir_rechaza_origen_inexistente(tmp_path):
    origen = tmp_path / "no_existe"
    with pytest.raises(FileNotFoundError, match="No existe la carpeta origen"):
        internos.ingerir(origen)
