"""Escenas animadas por image-to-video generativo (opcional, opt-in).

Investigación (jul-2026): Cloudflare Workers AI NO ofrece i2v (su changelog no
lista ningún modelo de video); el i2v real y barato es fal.ai `fal-ai/wan-i2v`
(Wan 2.x): anima una imagen de referencia + prompt de movimiento, 9:16, cola
async (~1 min/clip), ~$0.20 (480p) / $0.40 (720p) por clip.

Por eso i2v NO corre automático en cada escena (sería lento y costoso): es una
acción OPT-IN y deliberada -- animar una escena concreta bajo demanda (encaja con
la edición por prompt). Gated por FAL_KEY; sin key el provider no existe y el
pipeline sigue con Pexels loops (gratis) o Ken Burns.

transport y download inyectables -> tests herméticos sin red ni gasto.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Callable

_QUEUE_BASE = "https://queue.fal.run/fal-ai/wan-i2v"
_TRUTHY = {"1", "true", "yes", "on"}


def _image_data_uri(image_path: str) -> str:
    raw = Path(image_path).read_bytes()
    suffix = Path(image_path).suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode('ascii')}"


class FalWanI2VProvider:
    """image-to-video vía fal.ai Wan. animate() es best-effort: cualquier fallo o
    timeout devuelve None y el caller degrada a la imagen fija."""

    def __init__(
        self,
        *,
        api_key: str,
        resolution: str = "480p",
        aspect_ratio: str = "9:16",
        poll_interval: float = 3.0,
        max_polls: int = 40,
        transport: Callable[..., tuple[int, dict[str, Any]]] | None = None,
        download: Callable[[str, str], None] | None = None,
    ):
        if not api_key:
            raise ValueError("FalWanI2VProvider requires an api_key")
        self.api_key = api_key
        self.resolution = resolution
        self.aspect_ratio = aspect_ratio
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self._transport = transport
        self._download = download
        self._sleep = time.sleep

    @classmethod
    def from_env(cls, env: dict[str, str], **kwargs: Any) -> "FalWanI2VProvider | None":
        """Provider solo si i2v está habilitado Y hay FAL_KEY. Si no, None (modo
        original: Pexels loops / Ken Burns)."""
        enabled = str(env.get("KRONARA_I2V_ENABLED", "")).lower().strip() in _TRUTHY
        api_key = env.get("KRONARA_FAL_KEY") or env.get("FAL_KEY") or ""
        if not enabled or not api_key:
            return None
        resolution = env.get("KRONARA_I2V_RESOLUTION", "480p")
        return cls(api_key=api_key, resolution=resolution, **kwargs)

    def _http(self, method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        if self._transport is not None:
            return self._transport(method, url, payload)
        import httpx

        response = httpx.request(
            method,
            url,
            headers={"Authorization": f"Key {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        try:
            body = response.json()
        except Exception:
            body = {}
        return response.status_code, body

    def _download_file(self, url: str, dest: str) -> None:
        if self._download is not None:
            self._download(url, dest)
            return
        import httpx

        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as response:
            response.raise_for_status()
            with open(dest, "wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    def animate(self, *, image_path: str, prompt: str, dest: str) -> str | None:
        """Anima image_path según prompt y guarda el clip en dest. None si algo
        falla o se agota el tiempo (el caller usa la imagen fija)."""
        try:
            status, submit = self._http(
                "POST",
                _QUEUE_BASE,
                {
                    "prompt": prompt,
                    "image_url": _image_data_uri(image_path),
                    "resolution": self.resolution,
                    "aspect_ratio": self.aspect_ratio,
                },
            )
            if status >= 400:
                return None
            request_id = str(submit.get("request_id") or "")
            if not request_id:
                return None
            for _ in range(self.max_polls):
                s_status, s_body = self._http("GET", f"{_QUEUE_BASE}/requests/{request_id}/status")
                state = str(s_body.get("status") or "").upper()
                if state == "COMPLETED":
                    break
                if s_status >= 400 or state in ("FAILED", "ERROR", "CANCELLED"):
                    return None
                self._sleep(self.poll_interval)
            else:
                return None  # timed out still queued/in-progress
            _r_status, result = self._http("GET", f"{_QUEUE_BASE}/requests/{request_id}")
            video_url = ((result.get("video") or {}).get("url")) if isinstance(result.get("video"), dict) else None
            if not video_url:
                return None
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            self._download_file(str(video_url), dest)
            return dest if Path(dest).exists() else None
        except Exception:
            return None
