"""YouTube Data API v3, semanal (W20, fuente externa opcional del alcance v6).

Titulos, descripciones y comentarios de videos sobre GLP en la region, que
alimentan el analisis de texto del job de externos (W21: LDA sobre texto
consolidado). TikTok y Facebook quedan fuera del alcance corregido; YouTube es
opcional, asi que esta funcion no bloquea ningun paquete posterior.

La clave se lee de SSM (`/costagas/youtube/api_key`) en cada invocacion y nunca
se escribe en el log ni se versiona. Sin clave, el extractor falla con un
mensaje claro en lugar de guardar un archivo vacio.

De la respuesta se guarda solo el texto publico del video (titulo, descripcion,
canal y fecha). No se guardan identificadores de autores de comentarios: las
fuentes externas operan a nivel de marca y mercado, nunca de personas.
"""
from __future__ import annotations

import json
import os

from src.extractores import ClaveAusente, RespuestaInvalida, clave_youtube, escribir, hoy, pedir

API = "https://www.googleapis.com/youtube/v3/search"
FUENTE = "youtube"
# Las cinco busquedas del paso 3.2.7 del PLAN, orientadas a la pregunta 7 del
# informe: si el cliente percibe balones con menos peso de nuestras marcas.
CONSULTAS_POR_DEFECTO = (
    "balon de gas Trujillo",
    "precio GLP La Libertad",
    "balon de gas peso incompleto",
    "NOR GAS balon",
    "COSTA GAS PLUS balon",
)
CONSULTAS = tuple(filter(None, os.environ.get("YOUTUBE_CONSULTAS", "").split("|")))     or CONSULTAS_POR_DEFECTO
# Canal de Osinergmin (NE-02): su id va en YOUTUBE_CANAL. Sin id no se consulta,
# y queda dicho en el log; no se adivina un canal.
CANAL = os.environ.get("YOUTUBE_CANAL", "")
MAXIMO = int(os.environ.get("YOUTUBE_MAX_RESULTADOS", "50"))
CAMPOS = ("title", "description", "channelTitle", "publishedAt")


def buscar(consulta: str, clave: str, maximo: int = MAXIMO,
           canal: str | None = None) -> list[dict]:
    """Una pagina de resultados, reducida a los campos de texto publico."""
    params = {"part": "snippet", "q": consulta, "type": "video",
              "maxResults": maximo, "regionCode": "PE",
              "relevanceLanguage": "es", "key": clave}
    if canal:
        params["channelId"] = canal
    crudo = pedir(API, params=params)
    datos = json.loads(crudo)
    if "items" not in datos:
        raise RespuestaInvalida(f"la API no devolvio items para «{consulta}»: {datos.get('error')}")
    salida = []
    for item in datos["items"]:
        s = item.get("snippet", {})
        fila = {c: s.get(c) for c in CAMPOS}
        fila["video_id"] = item.get("id", {}).get("videoId")
        salida.append(fila)
    return salida


def _nombre(consulta: str, fecha, canal: str | None = None) -> str:
    base = consulta.lower().replace(" ", "_")
    prefijo = "canal__" if canal else ""
    return f"{prefijo}{base}__{fecha.isoformat()}.json"


def extraer(consultas=None, clave: str | None = None,
            canal: str | None = None) -> list[str]:
    """Un JSON por consulta, mas el canal de Osinergmin si su id esta definido.

    Levanta `ClaveAusente` si SSM no tiene la clave: sin clave no se guarda un
    archivo vacio.
    """
    api_key = clave or clave_youtube()
    if not api_key:
        raise ClaveAusente("la clave de YouTube llego vacia")
    busquedas = tuple(consultas) if consultas is not None else CONSULTAS
    canal_id = CANAL if canal is None else canal
    fecha = hoy()
    escritas = []
    for consulta in busquedas:
        items = buscar(consulta, api_key)
        cuerpo = json.dumps({"consulta": consulta, "consultado": fecha.isoformat(),
                             "items": items}, ensure_ascii=False).encode("utf-8")
        escritas.append(escribir(cuerpo, FUENTE, _nombre(consulta, fecha), fecha))
    if canal_id:
        items = buscar("GLP", api_key, canal=canal_id)
        cuerpo = json.dumps({"consulta": "canal", "canal": canal_id,
                             "consultado": fecha.isoformat(), "items": items},
                            ensure_ascii=False).encode("utf-8")
        escritas.append(escribir(cuerpo, FUENTE, _nombre("glp", fecha, canal_id), fecha))
    else:
        print("[youtube] sin YOUTUBE_CANAL: no se consulta el canal de Osinergmin (NE-02)")
    return escritas


def lambda_handler(event: dict | None = None, context=None) -> dict:  # noqa: ARG001
    """Programa `costagas-youtube-semanal`."""
    evento = event or {}
    return {"fuente": FUENTE,
            "rutas": extraer(evento.get("consultas"), canal=evento.get("canal"))}
