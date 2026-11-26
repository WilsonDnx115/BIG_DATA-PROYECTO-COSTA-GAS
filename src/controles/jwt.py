"""Validacion del token de Cognito (parte de W16 que W22 necesita).

Las funciones del portal y el control previo al pago tienen URL de funcion con
`AuthType: NONE`, asi que **toda** la autorizacion ocurre aqui: sin un token
valido de Cognito la peticion no pasa de esta linea. Se comprueban, en orden:

1. la firma RS256 contra la clave publica del grupo de usuarios (JWKS, en cache
   de proceso para no pedirla en cada invocacion);
2. el emisor (`iss`), que debe ser el grupo de usuarios del proyecto;
3. la audiencia (`aud` en el token de identidad, `client_id` en el de acceso);
4. la vigencia (`exp`, con un margen de reloj de 60 s) y `token_use`.

La verificacion RSA se hace con `pow()` y `hashlib`, sin dependencias nuevas:
`s^e mod n` devuelve el bloque PKCS#1 v1.5, que se compara con el DigestInfo de
SHA-256 del encabezado y la carga. Asi la Lambda no necesita una capa con
`cryptography`, que en Glue y Lambda hay que empaquetar a mano. Si mas adelante
se agrega esa capa, `verificar()` se puede cambiar por PyJWT sin tocar a quien
la llama.

El revisor nunca llega en el cuerpo de la peticion: se toma de los claims del
token (`cognito:username`), que es lo que hace que la revision documental sea
atribuible a una persona sin que el formulario pueda mentir.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from urllib.request import urlopen

REGION = os.environ.get("AWS_REGION", "us-east-2")
GRUPO = os.environ.get("COGNITO_USER_POOL_ID", "")
CLIENTE = os.environ.get("COGNITO_CLIENT_ID", "")
MARGEN_RELOJ_S = 60
USOS = ("id", "access")
# DigestInfo de SHA-256 en PKCS#1 v1.5 (RFC 8017, 9.2): identifica el algoritmo.
PREFIJO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")

_JWKS: dict[str, dict] = {}


class TokenInvalido(Exception):
    """El token no pasa alguna comprobacion: la respuesta es 401."""


def url_jwks(grupo: str | None = None, region: str | None = None) -> str:
    g = grupo or GRUPO
    if not g:
        raise TokenInvalido("falta COGNITO_USER_POOL_ID en la funcion")
    return (f"https://cognito-idp.{region or REGION}.amazonaws.com/{g}"
            "/.well-known/jwks.json")


def emisor(grupo: str | None = None, region: str | None = None) -> str:
    return f"https://cognito-idp.{region or REGION}.amazonaws.com/{grupo or GRUPO}"


def jwks(grupo: str | None = None, region: str | None = None, recargar: bool = False) -> dict:
    """Claves publicas del grupo, en cache por `kid` mientras viva el proceso."""
    clave_cache = grupo or GRUPO
    if recargar or clave_cache not in _JWKS:
        with urlopen(url_jwks(grupo, region), timeout=5) as r:  # noqa: S310
            datos = json.loads(r.read())
        _JWKS[clave_cache] = {k["kid"]: k for k in datos.get("keys", [])}
    return _JWKS[clave_cache]


def _b64(dato: str | bytes) -> bytes:
    crudo = dato.encode("ascii") if isinstance(dato, str) else dato
    return base64.urlsafe_b64decode(crudo + b"=" * (-len(crudo) % 4))


def _entero(valor: str) -> int:
    return int.from_bytes(_b64(valor), "big")


def partes(token: str) -> tuple[dict, dict, bytes, bytes]:
    """Encabezado, carga, firma y el texto firmado, sin validar nada todavia."""
    try:
        encabezado, carga, firma = token.split(".")
    except ValueError as e:
        raise TokenInvalido("el token no tiene tres partes") from e
    try:
        return (json.loads(_b64(encabezado)), json.loads(_b64(carga)),
                _b64(firma), f"{encabezado}.{carga}".encode("ascii"))
    except Exception as e:                      # noqa: BLE001
        raise TokenInvalido("el token no se puede decodificar") from e


def firma_valida(firmado: bytes, firma: bytes, clave: dict) -> bool:
    """RS256 con PKCS#1 v1.5: `s^e mod n` tiene que dar 00 01 FF.. 00 DigestInfo."""
    n, e = _entero(clave["n"]), _entero(clave["e"])
    tamano = (n.bit_length() + 7) // 8
    if len(firma) != tamano:
        return False
    bloque = pow(int.from_bytes(firma, "big"), e, n).to_bytes(tamano, "big")
    esperado = (b"\x00\x01" + b"\xff" * (tamano - len(PREFIJO_SHA256) - 35)
                + b"\x00" + PREFIJO_SHA256 + hashlib.sha256(firmado).digest())
    return bloque == esperado


def verificar(token: str, grupo: str | None = None, cliente: str | None = None,
              region: str | None = None, ahora: float | None = None) -> dict:
    """Devuelve los claims si el token es valido; si no, levanta `TokenInvalido`."""
    encabezado, carga, firma, firmado = partes(token)
    if encabezado.get("alg") != "RS256":
        raise TokenInvalido(f"algoritmo no admitido: {encabezado.get('alg')}")

    claves = jwks(grupo, region)
    clave = claves.get(encabezado.get("kid"))
    if clave is None:                            # rotacion de claves: se recarga una vez
        clave = jwks(grupo, region, recargar=True).get(encabezado.get("kid"))
    if clave is None:
        raise TokenInvalido("el kid del token no esta en el JWKS del grupo")
    if not firma_valida(firmado, firma, clave):
        raise TokenInvalido("la firma del token no corresponde")

    if carga.get("iss") != emisor(grupo, region):
        raise TokenInvalido("emisor distinto del grupo de usuarios del proyecto")
    uso = carga.get("token_use")
    if uso not in USOS:
        raise TokenInvalido(f"token_use no admitido: {uso}")
    audiencia = carga.get("aud") if uso == "id" else carga.get("client_id")
    esperada = cliente or CLIENTE
    if esperada and audiencia != esperada:
        raise TokenInvalido("el token es de otro cliente de Cognito")
    expira = carga.get("exp")
    if not isinstance(expira, (int, float)):
        raise TokenInvalido("el token no declara su vencimiento")
    if expira + MARGEN_RELOJ_S < (ahora if ahora is not None else time.time()):
        raise TokenInvalido("el token esta vencido")
    return carga


def usuario(claims: dict) -> str:
    """Quien firma la accion: el nombre del token, nunca uno del cuerpo."""
    nombre = claims.get("cognito:username") or claims.get("username") or claims.get("sub")
    if not nombre:
        raise TokenInvalido("el token no identifica al usuario")
    return str(nombre)
