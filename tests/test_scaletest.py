"""W24: replicas 1x/10x/100x y recogida de las medidas reales de la Tabla 3.11."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.common import rutas
from src.scaletest import aws
from src.scaletest import replicar as rep

FILAS = [
    {"placa": "T1A-111", "anio": "2020", "mes": "5", "kg": "100", "documento": "F001-1"},
    {"placa": "R2B222", "anio": "2020", "mes": "5", "kg": "50", "documento": "F001-2"},
    {"placa": "T1A-111", "anio": "2020", "mes": "6", "kg": "70", "documento": "F002-1"},
]


@pytest.fixture()
def muestra(tmp_path):
    carpeta = tmp_path / "entrega" / "comercial"
    carpeta.mkdir(parents=True)
    pd.DataFrame(FILAS).to_csv(carpeta / "com_19.csv", index=False)
    return tmp_path / "entrega"


def test_la_muestra_que_falta_se_dice_con_el_comando_para_generarla(tmp_path):
    with pytest.raises(FileNotFoundError, match="src.common.muestra"):
        rep.archivos_muestra(tmp_path / "no-existe")


def test_las_replicas_van_a_sim_escala(lago, muestra):
    datos = rep.replicar(10, muestra)

    assert datos["ruta"].endswith("sim/escala/x10")
    assert Path(datos["ruta"], "com_19.csv").exists()
    assert datos["filas"] == 30
    assert datos["archivos"] == 1


@pytest.mark.parametrize("factor", [1, 10, 100])
def test_cada_factor_multiplica_las_filas(lago, muestra, factor):
    datos = rep.replicar(factor, muestra)

    assert datos["filas"] == len(FILAS) * factor


def test_cada_copia_desplaza_la_identidad_para_no_inventar_cruces(lago, muestra):
    rep.replicar(3, muestra)

    df = pd.read_csv(Path(rep.destino(3, "com_19.csv")), dtype="string")
    placas = set(df["placa"])
    assert "T1A-111" in placas                 # la copia 0 queda intacta
    assert {"T1A-111_r1", "T1A-111_r2"} <= placas
    assert len(set(df["documento"])) == len(FILAS) * 3    # ningun documento repetido


def test_la_primera_copia_es_identica_a_la_muestra(lago, muestra):
    rep.replicar(1, muestra)

    original = pd.read_csv(muestra / "comercial" / "com_19.csv", dtype="string")
    replica = pd.read_csv(Path(rep.destino(1, "com_19.csv")), dtype="string")
    pd.testing.assert_frame_equal(original, replica)


def test_la_medida_vertical_trae_duracion_y_memoria_pico(lago, muestra):
    rep.replicar(10, muestra)

    medida = rep.medir_pandas(10)

    assert medida["motor"] == "pandas (vertical)"
    assert medida["filas"] == 30
    assert medida["grupos"] == 2                # (2020,5) y (2020,6)
    assert medida["segundos"] >= 0
    assert medida["memoria_pico_mb"] > 0


def test_la_memoria_pico_crece_con_el_factor(lago, muestra):
    """Es justo lo que mide la Tabla 3.11: cuanto crece una sola maquina."""
    rep.replicar(1, muestra)
    rep.replicar(100, muestra)

    assert rep.medir_pandas(100)["filas"] > rep.medir_pandas(1)["filas"]


def test_un_motor_desconocido_se_rechaza(lago, muestra):
    with pytest.raises(ValueError, match="motor desconocido"):
        rep.ejecutar([1], ["dask"], origen=muestra)


def test_las_replicas_se_borran_al_terminar(lago, muestra):
    rep.main(["--factores", "1", "--motores", "pandas", "--muestra", str(muestra)])

    assert not Path(rutas.ruta("sim", "escala")).exists()


def test_con_conservar_las_replicas_quedan_para_medir_en_aws(lago, muestra):
    rep.main(["--factores", "1", "--motores", "pandas", "--conservar",
              "--muestra", str(muestra)])

    assert Path(rep.destino(1, "com_19.csv")).exists()


def test_la_tabla_en_markdown_lleva_las_columnas_de_la_3_11():
    md = rep.a_markdown([{"factor": 1, "motor": "pandas (vertical)", "mb_entrada": 0.11,
                          "segundos": 2.4, "memoria_pico_mb": 9.2}])

    assert md.splitlines()[0].startswith("| factor | motor | mb_entrada")
    assert "pandas (vertical)" in md


# --- medidas reales de AWS ----------------------------------------------------

REPORT = ("REPORT RequestId: abc Duration: 12345.67 ms Billed Duration: 12346 ms "
          "Memory Size: 10240 MB Max Memory Used: 10231 MB Init Duration: 420.00 ms")


class LogsFalso:
    def __init__(self, mensajes):
        self._mensajes = mensajes

    def filter_log_events(self, logGroupName, filterPattern, limit):  # noqa: N803, ARG002
        return {"events": [{"message": m} for m in self._mensajes]}


class GlueFalso:
    def __init__(self, corridas):
        self._corridas = corridas

    def get_job_runs(self, JobName, MaxResults):  # noqa: N803, ARG002
        return {"JobRuns": self._corridas}


def test_la_memoria_pico_sale_de_la_linea_report_de_cloudwatch():
    filas = aws.reportes_lambda("costagas-bronze-to-silver",
                                cliente=LogsFalso([REPORT]))

    assert filas[0]["memoria_usada_mb"] == 10231
    assert filas[0]["memoria_mb"] == 10240
    assert filas[0]["duracion_ms"] == pytest.approx(12345.67)
    assert filas[0]["agotado"] is False


def test_una_invocacion_agotada_queda_marcada():
    agotada = REPORT + "\nTask timed out after 900.02 seconds"

    assert aws.reportes_lambda("f", cliente=LogsFalso([agotada]))[0]["agotado"] is True


def test_las_corridas_de_glue_traen_trabajadores_y_clase():
    glue = GlueFalso([{"Id": "jr_1", "JobRunState": "SUCCEEDED", "ExecutionTime": 420,
                       "NumberOfWorkers": 5, "WorkerType": "G.1X",
                       "ExecutionClass": "FLEX"}])

    corridas = aws.corridas_glue("costagas-gold-conciliacion", cliente=glue)

    assert corridas[0]["trabajadores"] == 5
    assert corridas[0]["clase"] == "FLEX"
    assert corridas[0]["segundos"] == 420


def test_lo_que_no_se_corrio_queda_pendiente_y_no_en_cero():
    """Sin corrida no hay numero: la fila sale como pendiente con su motivo."""
    class Rota:
        def filter_log_events(self, **_):
            raise RuntimeError("ResourceNotFoundException")

    datos = aws.recoger(funcion="costagas-ingesta", logs=Rota())

    fila = datos["lambda"][0]
    assert fila["valor"] is None
    assert fila["estado"] == "pendiente"
    assert "ResourceNotFound" in fila["motivo"]


def test_recoger_sin_argumentos_no_inventa_nada():
    assert aws.recoger() == {"lambda": [], "glue": []}


def test_el_json_de_salida_es_serializable():
    datos = aws.recoger(funcion="f", logs=LogsFalso([REPORT]))

    assert json.loads(json.dumps(datos, default=str))["lambda"][0]["memoria_usada_mb"] == 10231
