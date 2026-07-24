"""Distribución pódcast: feed RSS de los episodios (Spotify for Podcasters, etc.).

Sirve para TODOS los programas (los de Reddit y reflexión/bíblico): cada episodio
ya tiene su audio dentro del MP4; aquí se extrae a mp3 y se arma un feed RSS 2.0
con etiquetas iTunes (temporada/episodio) que Spotify for Podcasters puede ingerir.

``build_rss`` es puro (testeable). ``extract_audio`` usa ffmpeg. Nota: para que
Spotify lo lea, el feed debe servirse en una URL pública (self-host); en local
funciona para previsualizar/generar.
"""

from __future__ import annotations

import html
import subprocess
from email.utils import formatdate
from pathlib import Path
from typing import Any


def _esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def build_rss(
    *,
    title: str,
    description: str,
    self_url: str = "",
    language: str = "es",
    author: str = "Kronara",
    image_url: str = "",
    episodes: "list[dict[str, Any]]",
) -> str:
    """Feed RSS 2.0 + iTunes. Cada episodio: {title, description, audio_url,
    audio_bytes, duration_seconds, pub_ts, guid, season?, episode_number?}."""
    items: list[str] = []
    for episode in episodes:
        parts = [
            "    <item>",
            f"      <title>{_esc(episode.get('title'))}</title>",
            f"      <description>{_esc(episode.get('description'))}</description>",
            f'      <enclosure url="{_esc(episode.get("audio_url"))}" type="audio/mpeg" length="{int(episode.get("audio_bytes") or 0)}"/>',
            f'      <guid isPermaLink="false">{_esc(episode.get("guid") or episode.get("audio_url"))}</guid>',
            f"      <pubDate>{formatdate(float(episode.get('pub_ts') or 0))}</pubDate>",
            f"      <itunes:duration>{_duration(episode.get('duration_seconds') or 0)}</itunes:duration>",
        ]
        if episode.get("season"):
            parts.append(f"      <itunes:season>{int(episode['season'])}</itunes:season>")
        if episode.get("episode_number"):
            parts.append(f"      <itunes:episode>{int(episode['episode_number'])}</itunes:episode>")
        parts.append("    </item>")
        items.append("\n".join(parts))
    image = f'\n    <itunes:image href="{_esc(image_url)}"/>' if image_url else ""
    items_xml = ("\n".join(items) + "\n") if items else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        "  <channel>\n"
        f"    <title>{_esc(title)}</title>\n"
        f"    <description>{_esc(description)}</description>\n"
        f"    <link>{_esc(self_url)}</link>\n"
        f"    <language>{_esc(language)}</language>\n"
        f"    <itunes:author>{_esc(author)}</itunes:author>{image}\n"
        f"{items_xml}"
        "  </channel>\n"
        "</rss>\n"
    )


def extract_audio(video_path: "str | Path", dest_mp3: "str | Path", *, ffmpeg: str = "ffmpeg", timeout: int = 300) -> str:
    """Extrae el audio del MP4 del episodio a mp3 (para el enclosure del pódcast)."""
    Path(dest_mp3).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-i", str(video_path), "-vn", "-c:a", "libmp3lame", "-q:a", "4", str(dest_mp3)],
        check=True,
        capture_output=True,
        timeout=timeout,
    )
    return str(dest_mp3)
