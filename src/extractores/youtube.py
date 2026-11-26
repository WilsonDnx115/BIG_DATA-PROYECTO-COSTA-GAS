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
CONSULTAS = tuple(os.environ.get(
    "YOUTUBE_CONSULTAS", "balon de gas Trujillo|precio GLP La Libertad").split("|"))
MAXIMO = int(os.environ.get("YOUTUBE_MAX_RESULTADOS", "50"))
CAMPOS = ("title", "description", "channelTitle", "publishedAt")


def buscar(consulta: str, clave: str, maximo: int = MAXIMO) -> list[dict]:
    """Una pagina de resultados, reducida a los campos de texto publico."""
    crudo = pedir(API, params={"part": "snippet", "q": consulta, "type": "video",
                               "maxResults": maximo, "regionCode": "PE",
                               "relevanceLanguage": "es", "key": clave})
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


def extraer(consultas=CONSULTAS, clave: str | None = None) -> list[str]:
    """Un JSON por consulta. Levanta `ClaveAusente` si SSM no tiene la clave."""
    api_key = clave or clave_youtube()
    if not api_key:
        raise ClaveAusente("la clave de YouTube llego vacia")
    fecha = hoy()
    escritas = []
    for consulta in consultas:
        items = buscar(consulta, api_key)
        nombre = f"{consulta.lower().replace(' ', '_')}__{fecha.isoformat()}.json"
        cuerpo = json.dumps({"consulta": consulta, "consultado": fecha.isoformat(),
                             "items": items}, ensure_ascii=False).encode("utf-8")
        escritas.append(escribir(cuerpo, FUENTE, nombre, fecha))
    return escritas


def lambda_handler(event: dict | None = None, context=None) -> dict:  # noqa: ARG001
    """Programa `costagas-youtube-semanal`."""
    evento = event or {}
    consultas = tuple(evento.get("consultas") or CONSULTAS)
    return {"fuente": FUENTE, "rutas": extraer(consultas)}
