"""W22: las cuatro funciones del portal, su CORS y la validacion del token.

El token se firma con una clave RSA generada en la prueba, asi que la
verificacion que corre es la de verdad (firma, emisor, audiencia y vigencia) y
no una simulada. Athena y S3 se sustituyen por clientes falsos.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path

import pytest

from src.common import rutas
from src.controles import jwt as cjwt
from src.portal import estado, firmar, kpis, revision

GRUPO = "us-east-2_prueba"
CLIENTE = "cliente-de-prueba"
ORIGEN = "https://d111111abcdef8.cloudfront.net"
USUARIO = "bruno.revisor"

@pytest.fixture(scope="module")
def clave_rsa():
    """Par RSA generado una vez: n, e y d, sin dependencias de criptografia."""
    import random

    def es_primo(n: int, intentos: int = 24) -> bool:
        if n < 2 or n % 2 == 0:
            return n == 2
        d, r = n - 1, 0
        while d % 2 == 0:
            d, r = d // 2, r + 1
        for _ in range(intentos):
            a = random.randrange(2, n - 1)       # noqa: S311
            x = pow(a, d, n)
            if x in (1, n - 1):
                continue
            for _ in range(r - 1):
                x = x * x % n
                if x == n - 1:
                    break
            else:
                return False
        return True

    def primo(bits: int) -> int:
        while True:
            c = random.getrandbits(bits) | (1 << (bits - 1)) | 1   # noqa: S311
            if es_primo(c):
                return c

    random.seed(20261126)
    e = 65537
    while True:
        p, q = primo(512), primo(512)
        if p != q and (p - 1) % e and (q - 1) % e:
            break
    n = p * q
    d = pow(e, -1, (p - 1) * (q - 1))
    return {"n": n, "e": e, "d": d}


def _b64(dato: bytes) -> str:
    return base64.urlsafe_b64encode(dato).rstrip(b"=").decode("ascii")


def _entero_b64(valor: int) -> str:
    return _b64(valor.to_bytes((valor.bit_length() + 7) // 8, "big"))


def firmar_token(clave_rsa, **cambios) -> str:
    """Token RS256 real: PKCS#1 v1.5 con el exponente privado."""
    encabezado = {"alg": "RS256", "kid": "kid-1", "typ": "JWT"}
    carga = {"iss": cjwt.emisor(GRUPO), "aud": CLIENTE, "token_use": "id",
             "exp": int(time.time()) + 3600, "cognito:username": USUARIO}
    carga.update(cambios.pop("carga", {}))
    encabezado.update(cambios.pop("encabezado", {}))
    firmado = f"{_b64(json.dumps(encabezado).encode())}.{_b64(json.dumps(carga).encode())}"

    tamano = (clave_rsa["n"].bit_length() + 7) // 8
    bloque = (b"\x00\x01"
              + b"\xff" * (tamano - len(cjwt.PREFIJO_SHA256) - 35)
              + b"\x00" + cjwt.PREFIJO_SHA256
              + hashlib.sha256(firmado.encode("ascii")).digest())
    firma = pow(int.from_bytes(bloque, "big"), clave_rsa["d"], clave_rsa["n"])
    return f"{firmado}.{_b64(firma.to_bytes(tamano, 'big'))}"


@pytest.fixture()
def cognito(clave_rsa, monkeypatch):
    """JWKS en cache con la clave publica de la prueba; no se sale a la red."""
    monkeypatch.setattr(cjwt, "GRUPO", GRUPO)
    monkeypatch.setattr(cjwt, "CLIENTE", CLIENTE)
    monkeypatch.setattr(cjwt, "_JWKS", {GRUPO: {"kid-1": {
        "kid": "kid-1", "kty": "RSA", "alg": "RS256",
        "n": _entero_b64(clave_rsa["n"]), "e": _entero_b64(clave_rsa["e"])}}})
    monkeypatch.setenv("PORTAL_ORIGEN", ORIGEN)
    monkeypatch.setattr("src.portal.ORIGEN", ORIGEN)
    return clave_rsa


def evento(token: str | None = None, cuerpo: dict | None = None, metodo: str = "POST") -> dict:
    return {"requestContext": {"http": {"method": metodo}},
            "headers": {"Authorization": f"Bearer {token}"} if token else {},
            "body": json.dumps(cuerpo) if cuerpo is not None else None}


def cuerpo_de(respuesta: dict) -> dict:
    return json.loads(respuesta["body"])


# --- Token -------------------------------------------------------------------

def test_un_token_bien_firmado_pasa(cognito):
    claims = cjwt.verificar(firmar_token(cognito), grupo=GRUPO, cliente=CLIENTE)

    assert cjwt.usuario(claims) == USUARIO


def test_un_token_vencido_da_401(cognito):
    vencido = firmar_token(cognito, carga={"exp": int(time.time()) - 3600})

    r = firmar.lambda_handler(evento(vencido, {"nombre": "VENTAS 2020.xlsx"}))

    assert r["statusCode"] == 401
    assert "vencido" in cuerpo_de(r)["error"]


def test_un_token_de_otro_cliente_da_401(cognito):
    ajeno = firmar_token(cognito, carga={"aud": "otro-cliente"})

    r = firmar.lambda_handler(evento(ajeno, {"nombre": "VENTAS 2020.xlsx"}))

    assert r["statusCode"] == 401
    assert "otro cliente" in cuerpo_de(r)["error"]


def test_un_token_de_otro_emisor_da_401(cognito):
    ajeno = firmar_token(cognito, carga={"iss": "https://cognito-idp.us-east-1.amazonaws.com/x"})

    assert firmar.lambda_handler(evento(ajeno, {"nombre": "a.xlsx"}))["statusCode"] == 401


def test_una_firma_alterada_da_401(cognito):
    token = firmar_token(cognito)
    partido = token.rsplit(".", 1)[0] + "." + ("A" * len(token.rsplit(".", 1)[1]))

    r = firmar.lambda_handler(evento(partido, {"nombre": "a.xlsx"}))

    assert r["statusCode"] == 401
    assert "firma" in cuerpo_de(r)["error"]


def test_sin_cabecera_authorization_da_401(cognito):
    assert firmar.lambda_handler(evento(None, {"nombre": "a.xlsx"}))["statusCode"] == 401


def test_el_algoritmo_none_no_se_acepta(cognito):
    """Un token sin firma («alg»: none) es el ataque clasico contra JWT."""
    encabezado = _b64(json.dumps({"alg": "none", "kid": "kid-1"}).encode())
    carga = _b64(json.dumps({"iss": cjwt.emisor(GRUPO), "aud": CLIENTE,
                             "token_use": "id", "exp": int(time.time()) + 60}).encode())

    with pytest.raises(cjwt.TokenInvalido, match="algoritmo"):
        cjwt.verificar(f"{encabezado}.{carga}.", grupo=GRUPO, cliente=CLIENTE)


# --- CORS --------------------------------------------------------------------

def test_el_cors_se_limita_al_dominio_de_cloudfront(cognito):
    r = firmar.lambda_handler(evento(metodo="OPTIONS"))

    assert r["statusCode"] == 204
    assert r["headers"]["Access-Control-Allow-Origin"] == ORIGEN
    assert r["headers"]["Access-Control-Allow-Origin"] != "*"


def test_sin_dominio_configurado_no_se_declara_cors():
    assert "Access-Control-Allow-Origin" not in __import__(
        "src.portal", fromlist=["cors"]).cors("")


# --- firmar ------------------------------------------------------------------

class S3Falso:
    def __init__(self):
        self.pedidos = []

    def generate_presigned_url(self, metodo, Params, ExpiresIn):  # noqa: N803
        self.pedidos.append((metodo, Params, ExpiresIn))
        return f"https://s3.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"


def test_la_url_prefirmada_dura_cinco_minutos_y_apunta_a_landing_interno():
    s3 = S3Falso()

    datos = firmar.firmar("VENTAS 2020.xlsx", bucket="lago", cliente=s3)

    assert datos["vigencia_s"] == 300
    assert datos["clave"] == "landing/interno/VENTAS 2020.xlsx"
    metodo, params, vigencia = s3.pedidos[0]
    assert metodo == "put_object"
    assert params["ServerSideEncryption"] == "AES256"
    assert vigencia == 300


@pytest.mark.parametrize("nombre", [
    "../../gold/fact_alerta.xlsx",          # salirse del prefijo
    "landing/externo/otro.xlsx",            # otra capa
    "ventas.csv",                           # extension fuera de _archivos.yaml
    "ventas.xlsx.exe",
    "",
])
def test_firmar_rechaza_nombres_que_salen_del_prefijo_o_de_las_extensiones(nombre):
    with pytest.raises(ValueError):
        firmar.clave(nombre)


def test_las_extensiones_salen_del_contrato_de_archivos():
    assert firmar.extensiones() == (".xlsx", ".xls")


# --- estado ------------------------------------------------------------------

def test_el_estado_cuenta_los_manifiestos_por_fecha(lago):
    raiz = Path(rutas.ruta("_manifests"))
    for fecha, archivos in (("2026-11-20", 2), ("2026-11-21", 1)):
        carpeta = raiz / f"fecha_carga={fecha}"
        carpeta.mkdir(parents=True, exist_ok=True)
        for i in range(archivos):
            (carpeta / f"codigo_{i}__abc{i}.json").write_text("{}", encoding="utf-8")

    assert estado.cargas_por_fecha() == {"2026-11-20": 2, "2026-11-21": 1}


def test_el_estado_devuelve_el_control_de_calidad_de_silver(lago):
    carpeta = Path(rutas.ruta("silver", "_control"))
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "compras_glp.json").write_text(
        json.dumps({"placa_valida": 0.996, "filas": 1066}), encoding="utf-8")

    calidad = estado.calidad_por_tabla()

    assert calidad["compras_glp"]["placa_valida"] == 0.996


def test_el_estado_sobre_un_lago_vacio_no_falla(lago):
    assert estado.cargas_por_fecha() == {}
    assert estado.calidad_por_tabla() == {}


# --- kpis --------------------------------------------------------------------

class AthenaFalso:
    def __init__(self, estado_final="SUCCEEDED", motivo=None, filas=None):
        self.consultas = []
        self._estado = estado_final
        self._motivo = motivo
        self._filas = filas or [["anio", "mes", "pct"], ["2020", "5", "1.95"]]

    def start_query_execution(self, QueryString, WorkGroup, QueryExecutionContext):  # noqa: N803
        self.consultas.append(QueryString)
        return {"QueryExecutionId": "q-1"}

    def get_query_execution(self, QueryExecutionId):  # noqa: N803, ARG002
        return {"QueryExecution": {"Status": {"State": self._estado,
                                              "StateChangeReason": self._motivo}}}

    def get_query_results(self, QueryExecutionId, MaxResults):  # noqa: N803, ARG002
        return {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": v} for v in f]}
                                       for f in self._filas]}}


def test_los_kpis_se_leen_de_su_vista():
    athena = AthenaFalso()

    salida = kpis.leer("kpi_1", cliente=athena)

    assert salida["estado"] == "ok"
    assert salida["filas"] == [{"anio": "2020", "mes": "5", "pct": "1.95"}]
    assert athena.consultas == ["SELECT * FROM costagas_gold.v_kpi_1 LIMIT 500"]


def test_el_portal_no_puede_mandar_sql():
    """El cliente manda el nombre del indicador, nunca la consulta."""
    with pytest.raises(kpis.VistaDesconocida):
        kpis.consulta("fact_alerta; DROP TABLE costagas_gold.fact_alerta")
    with pytest.raises(kpis.VistaDesconocida):
        kpis.consulta("v_kpi_1")        # ni el nombre de la vista: el del indicador


def test_el_limite_de_filas_tiene_tope():
    assert kpis.consulta("kpi_4", limite=10_000).endswith("LIMIT 500")


def test_una_vista_que_todavia_no_existe_se_declara_sin_vista():
    """Hasta que F06 despliegue las vistas, el KPI no se devuelve en cero."""
    athena = AthenaFalso("FAILED", motivo="line 1:15: Table does not exist")

    salida = kpis.leer("kpi_5", cliente=athena)

    assert salida["estado"] == "sin_vista"
    assert salida["filas"] == []


# --- revision ----------------------------------------------------------------

REVISION = {"id_alerta": "AL-2023-0001", "estado": "confirmada",
            "causa": "pago_tardio", "nivel_evidencia": 2}


@pytest.fixture(autouse=True)
def sal(monkeypatch):
    monkeypatch.setenv("SEUDONIMO_SAL", "sal-de-prueba")


def test_la_revision_se_inserta_con_el_revisor_del_token():
    fila = revision.validar(REVISION, USUARIO)

    assert fila["revisor_hash"] != USUARIO
    assert len(fila["revisor_hash"]) == 32
    assert USUARIO not in revision.sentencia(fila)


def test_el_revisor_del_cuerpo_se_ignora():
    """Aunque el formulario mande otro revisor, manda el del token."""
    fila = revision.validar({**REVISION, "revisor": "otra.persona"}, USUARIO)

    assert fila["revisor_hash"] == revision.revisor_hash(USUARIO)


def test_la_sentencia_es_solo_un_insert():
    sql = revision.sentencia(revision.validar(REVISION, USUARIO))

    assert sql.startswith("INSERT INTO costagas_gold.revision_alerta")
    for prohibido in ("UPDATE", "DELETE", "MERGE", "DROP", "ALTER"):
        assert prohibido not in sql.upper()


def test_el_modulo_no_sabe_escribir_otra_cosa_que_un_insert():
    """Ni en el codigo fuente hay un UPDATE, un DELETE o un MERGE."""
    fuente = Path("src/portal/revision.py").read_text(encoding="utf-8").upper()

    for prohibido in ("UPDATE ", "DELETE ", "MERGE "):
        assert prohibido not in fuente.replace("NO CONSTRUYE `UPDATE`", "")


@pytest.mark.parametrize("causa", ["robo", "otra", "", None, "DIGITACION"])
def test_una_causa_fuera_de_las_seis_se_rechaza(causa):
    with pytest.raises(revision.CausaNoValida):
        revision.validar({**REVISION, "causa": causa}, USUARIO)


def test_las_seis_causas_del_informe_se_aceptan():
    assert len(revision.CAUSAS) == 6
    for causa in revision.CAUSAS:
        nivel = 3 if causa == "sustraccion_confirmada" else 1
        fila = revision.validar({**REVISION, "causa": causa, "nivel_evidencia": nivel},
                                USUARIO)
        assert fila["causa"] == causa


@pytest.mark.parametrize("nivel", [0, 4, "alto", None])
def test_un_nivel_de_evidencia_fuera_de_1_a_3_se_rechaza(nivel):
    with pytest.raises(revision.EvidenciaNoValida):
        revision.validar({**REVISION, "nivel_evidencia": nivel}, USUARIO)


def test_la_sustraccion_solo_existe_en_el_nivel_3():
    with pytest.raises(revision.EvidenciaNoValida, match="nivel 3"):
        revision.validar({**REVISION, "causa": "sustraccion_confirmada",
                          "nivel_evidencia": 2}, USUARIO)


@pytest.mark.parametrize("id_alerta", ["AL'; DROP TABLE x --", "al/otra", "a" * 65, ""])
def test_un_id_de_alerta_con_comillas_o_rutas_se_rechaza(id_alerta):
    with pytest.raises(ValueError):
        revision.validar({**REVISION, "id_alerta": id_alerta}, USUARIO)


def test_la_nota_no_admite_comillas_ni_comentarios_sql():
    with pytest.raises(ValueError):
        revision.validar({**REVISION, "nota": "pago' OR 1=1 --"}, USUARIO)


def test_la_fila_no_lleva_el_puntaje_del_modelo():
    """La revision es ciega: la probabilidad no viaja ni se guarda."""
    fila = revision.validar({**REVISION, "probabilidad": 0.97}, USUARIO)

    assert "probabilidad" not in fila
    assert "0.97" not in revision.sentencia(fila)


def test_la_revision_completa_responde_200(cognito, monkeypatch):
    athena = AthenaFalso()
    monkeypatch.setattr(revision, "insertar", lambda fila, cliente=None: "q-9")

    r = revision.lambda_handler(evento(firmar_token(cognito), REVISION))

    assert r["statusCode"] == 200
    cuerpo = cuerpo_de(r)
    assert cuerpo["registrado"] is True
    assert cuerpo["causa"] == "pago_tardio"
    assert "revisor_hash" not in cuerpo and USUARIO not in r["body"]
    assert athena.consultas == []


def test_una_causa_invalida_por_la_funcion_da_400(cognito):
    r = revision.lambda_handler(evento(firmar_token(cognito), {**REVISION, "causa": "robo"}))

    assert r["statusCode"] == 400
    assert "causa no valida" in cuerpo_de(r)["error"]
