# 0025 · El token de Cognito se verifica con `pow()` y `hashlib`, sin capa de criptografía

- **Fecha:** 2026-11-27
- **Estado:** aceptada
- **Responsable:** Wilson Mirano Ríos (Ingeniería de datos)

## Contexto
Las cuatro funciones del portal (W22) y el control previo al pago (W16) se exponen con **URL de
función** y `AuthType: NONE`, porque el navegador las llama directo con el token que le dio
Cognito y una URL de función no sabe validar un token de un grupo de usuarios. Es decir: **toda
la autorización ocurre en el código**. Si la validación del token es débil, cualquiera en
internet puede pedir una URL prefirmada de carga o insertar una revisión documental.

Validar un token RS256 exige verificar su firma contra la clave pública del grupo (JWKS). La
forma habitual es `PyJWT` con `cryptography`, pero `cryptography` trae binarios compilados: en
Lambda hay que empaquetarla en una capa construida para `manylinux`, y este proyecto ya depende
de una capa gestionada (AWS SDK for pandas) y tiene prohibido crear recursos fuera de
`stack.yaml`. Sumar una capa propia significa construirla, versionarla, subirla y mantenerla
para cuatro funciones de 256 MB que hacen una llamada HTTP y una consulta.

## Alternativas evaluadas
1. **Capa propia con `PyJWT[crypto]`.** Descartada por ahora: es la opción ortodoxa, pero añade
   un artefacto binario que hay que construir y mantener fuera de la plantilla, y el beneficio
   sobre la alternativa elegida es nulo para RS256.
2. **Confiar en que el token viene de Cognito y leer los claims sin verificar la firma.**
   Descartada, y vale decir por qué: un token JWT es texto que cualquiera puede escribir. Sin
   verificar la firma, `cognito:username` es un campo que el atacante elige, y la revisión
   documental dejaría de ser atribuible. Sería peor que no tener autenticación, porque parecería
   tenerla.
3. **Verificar RSA PKCS#1 v1.5 con la biblioteca estándar.** Elegida.

## Criterio
- **La verificación es completa, no parcial.** `s^e mod n` es una exponenciación modular que
  `pow()` hace en C, y el bloque que devuelve se compara **entero** con el esperado:
  `00 01 FF… 00` + el DigestInfo de SHA-256 + el hash del encabezado y la carga (RFC 8017, 9.2).
  No se recorta el relleno ni se busca el hash dentro del bloque, que es el error clásico de las
  implementaciones caseras (firma de Bleichenbacher).
- **Solo verificación, nunca firma.** El código no genera firmas ni maneja claves privadas: ahí
  es donde los ataques de canal lateral importan, y ahí no estamos.
- **Sin dependencias nuevas** en una función alcanzable desde internet: menos superficie que
  mantener al día.
- **Reversible en una función.** Si más adelante se agrega la capa, se cambia el cuerpo de
  `verificar()` por `jwt.decode(...)` y nadie que la llame se entera.

## Consecuencia
- [`src/controles/jwt.py`](../../src/controles/jwt.py) valida, en este orden: `alg` igual a
  RS256 (un token con `alg: none` se rechaza antes de mirar nada más), firma contra el `kid` del
  JWKS —con una recarga si el `kid` no está, para tolerar la rotación de claves—, emisor,
  `token_use`, audiencia (`aud` en el token de identidad, `client_id` en el de acceso) y
  vigencia con 60 segundos de margen de reloj.
- El JWKS se guarda en caché de proceso: no se pide en cada invocación.
- El revisor y quien pide una carga salen de los claims (`cognito:username`), **nunca del cuerpo
  de la petición**.
- [`tests/test_portal.py`](../../tests/test_portal.py) firma los tokens con un par RSA generado
  en la propia prueba, así que lo que se ejercita es la verificación real: cubre token válido,
  vencido, de otro cliente, de otro emisor, con la firma alterada y con `alg: none`.
- **Pendiente:** si el proyecto llega a necesitar `cryptography` por otro motivo, conviene
  cambiar `verificar()` por PyJWT y dejar este ADR como reemplazado.
