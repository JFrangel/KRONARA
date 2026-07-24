"""Lectura del HILO real de Reddit, sin credenciales, para reconstrucción de casos.

A diferencia de reddit_rss.py (que solo necesita el título abstracto), este módulo
existe para la identidad editorial "reconstruimos casos reales que aparecieron en
Reddit": trae el cuerpo completo del hilo y, sobre todo, sus **actualizaciones**
(los bloques "UPDATE"/"EDIT" del post y los comentarios de seguimiento del propio
autor, que es donde la historia real suele cerrarse).

Usa el endpoint público ``<permalink>.json`` — lectura conforme de contenido
público, sin login ni scraping autenticado (mismo espíritu que reddit_rss.py).
El ``transport`` es inyectable para tests herméticos (sin red).

Nota de privacidad/derechos: el autor original se conserva SOLO para poder
tacharlo en la anonimización posterior; el pipeline de reconstrucción cambia
nombres y detalles identificables antes de publicar.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from kronara.reddit_rss import DEFAULT_UA, _plain_text

# Marcadores de actualización al inicio de una línea (markdown y mayúsc./minúsc.):
# UPDATE, UPDATE 2, FINAL UPDATE, EDIT, EDIT 3, ETA. Captura la etiqueta y el
# resto de esa línea como encabezado del segmento.
_UPDATE_MARKER = re.compile(
    r"(?im)^[\s>#*_]*((?:final\s+)?update(?:\s*\d+)?|edit(?:\s*\d+)?|eta)\b[^\n]*"
)


@dataclass(frozen=True)
class ThreadUpdate:
    label: str  # p.ej. "UPDATE", "UPDATE 2", "FINAL UPDATE", "EDIT"
    text: str
    source: str  # "selftext" | "op_comment"


@dataclass(frozen=True)
class ThreadDetail:
    thread_id: str
    subreddit: str
    title: str
    body: str  # cuerpo original, con los bloques de actualización separados
    edited: bool
    updates: tuple[ThreadUpdate, ...] = ()
    op_followups: tuple[str, ...] = ()
    author: str = ""  # solo para anonimizar aguas abajo; no se publica

    @property
    def has_updates(self) -> bool:
        return bool(self.updates or self.op_followups)


def extract_updates(selftext: str) -> tuple[str, tuple[ThreadUpdate, ...]]:
    """Parte el selftext en (cuerpo_original, actualizaciones). Los "UPDATE:/EDIT:"
    del cuerpo son la continuación real del caso: se separan para que el
    reconstructor sepa qué pasó DESPUÉS y pueda cerrar la historia con hechos
    reales, no inventados."""
    text = selftext or ""
    matches = list(_UPDATE_MARKER.finditer(text))
    if not matches:
        return text.strip(), ()
    original = text[: matches[0].start()].strip()
    updates: list[ThreadUpdate] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.start() : end].strip()
        label = re.sub(r"[\s>#*_]+", " ", match.group(1)).strip().upper()
        updates.append(ThreadUpdate(label=label, text=segment, source="selftext"))
    return original, tuple(updates)


class RedditThreadReader:
    """Trae el detalle de un hilo por su permalink/id, sin login."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        max_retries: int = 3,
        backoff_base: float = 10.0,
        max_op_followups: int = 6,
        transport=None,
    ):
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_op_followups = max_op_followups
        self._transport = transport  # callable(url) -> (status, text)
        import time

        self._sleep = time.sleep

    def _get(self, url: str) -> tuple[int, str]:
        if self._transport is not None:
            return self._transport(url)
        response = httpx.get(
            url, headers={"User-Agent": self.user_agent}, timeout=20, follow_redirects=True
        )
        return response.status_code, response.text

    @staticmethod
    def _json_url(permalink_or_id: str) -> str:
        value = permalink_or_id.strip()
        if value.startswith("http"):
            base = value.split("?", 1)[0].rstrip("/")
            return f"{base}.json"
        # bare id -> comments endpoint (subreddit-agnostic redirect works)
        return f"https://www.reddit.com/comments/{value}.json"

    def fetch(self, permalink_or_id: str) -> ThreadDetail | None:
        url = self._json_url(permalink_or_id)
        for attempt in range(self.max_retries):
            status, text = self._get(url)
            if status == 200:
                return self._parse(text)
            if status == 429 and attempt < self.max_retries - 1:
                self._sleep(self.backoff_base * (attempt + 1))
                continue
            break
        return None

    def _parse(self, text: str) -> ThreadDetail | None:
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(payload, list) or not payload:
            return None
        try:
            post = payload[0]["data"]["children"][0]["data"]
        except (KeyError, IndexError, TypeError):
            return None
        author = str(post.get("author", "") or "")
        selftext = str(post.get("selftext", "") or "")
        body, updates = extract_updates(selftext)
        op_followups = self._op_followups(payload, author) if len(payload) > 1 else ()
        return ThreadDetail(
            thread_id=str(post.get("id", "") or ""),
            subreddit=str(post.get("subreddit", "") or ""),
            title=str(post.get("title", "") or ""),
            body=_plain_text(body, max_chars=12000),
            edited=bool(post.get("edited")),
            updates=tuple(
                ThreadUpdate(u.label, _plain_text(u.text, max_chars=6000), u.source) for u in updates
            ),
            op_followups=op_followups,
            author=author,
        )

    def _op_followups(self, payload: list, author: str) -> tuple[str, ...]:
        """Comentarios del PROPIO autor: en muchos casos la actualización real se
        publica ahí, no editando el post."""
        if not author or author == "[deleted]":
            return ()
        try:
            children = payload[1]["data"]["children"]
        except (KeyError, IndexError, TypeError):
            return ()
        out: list[str] = []
        for child in children:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            if str(data.get("author", "")) != author:
                continue
            comment = _plain_text(str(data.get("body", "") or ""), max_chars=4000)
            if len(comment) >= 120:  # skip one-liners; keep substantive follow-ups
                out.append(comment)
            if len(out) >= self.max_op_followups:
                break
        return tuple(out)
