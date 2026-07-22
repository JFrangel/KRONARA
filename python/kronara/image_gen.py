"""Local Stable Diffusion image generation — unlimited, free, no API keys.

Runs entirely on the local GPU via ``diffusers`` (no ComfyUI/local HTTP
server — this matches the exact lazy-load-in-process pattern
``SentenceTransformerEmbeddingProvider`` already uses for local embedding
models, including dependency-injectable loading for testability without a
GPU). One SDXL base checkpoint stays resident; quality tiers are toggled by
swapping a small LoRA on top of it rather than loading a second checkpoint:

- ``fast`` tier (60-70% of shots — connective/context scenes): SDXL-Lightning
  8-step LoRA, low guidance, ~2-5s/image on an 8GB card.
- ``premium`` tier (hook, revelation, climax, final shot): the Lightning LoRA
  unloaded, DPM++ Karras scheduler, 32-36 steps, ~12-20s/image.

``PlaceholderImageProvider`` (Pillow-drawn flat/gradient PNGs) implements the
same ``ImageGenerationProvider`` protocol so the rest of the pipeline
(composition, mixing, QC) is fully testable with zero GPU.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

# Native SDXL training buckets close to each target aspect — generating here
# (not at the final output resolution) measurably helps SDXL coherence; Ken
# Burns' extra panning headroom comes from the ffmpeg upscale stage instead.
SDXL_BUCKET_9x16 = (768, 1344)
SDXL_BUCKET_16x9 = (1344, 768)

FAST_STEPS = 8
FAST_GUIDANCE = 1.5
PREMIUM_STEPS = 34
PREMIUM_GUIDANCE = 6.5

LIGHTNING_LORA_REPO = "ByteDance/SDXL-Lightning"
LIGHTNING_LORA_WEIGHT = "sdxl_lightning_8step_lora.safetensors"
IP_ADAPTER_REPO = "h94/IP-Adapter"
IP_ADAPTER_SUBFOLDER = "sdxl_models"
IP_ADAPTER_WEIGHT = "ip-adapter-plus_sdxl_vit-h.safetensors"


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    negative_prompt: str = ""
    width: int = SDXL_BUCKET_9x16[0]
    height: int = SDXL_BUCKET_9x16[1]
    seed: int = 0
    quality_tier: str = "fast"  # "fast" | "premium"
    reference_image_path: str | None = None  # IP-Adapter conditioning (character sheet)
    reference_strength: float = 0.6

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        if self.quality_tier not in {"fast", "premium"}:
            raise ValueError(f"unknown quality_tier: {self.quality_tier}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width/height must be positive")

    def cache_key(self) -> str:
        payload = (
            f"{self.prompt}|{self.negative_prompt}|{self.width}x{self.height}|"
            f"{self.seed}|{self.quality_tier}|{self.reference_image_path}|{self.reference_strength}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ImageGenerationResult:
    image_path: str
    seed: int
    width: int
    height: int
    quality_tier: str
    generation_ms: int
    degraded: bool = False  # True on OOM-offload retry or black/NaN-frame fallback


class ImageGenerationProvider(Protocol):
    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...


def find_sd_model_dir() -> str | None:
    """KRONARA_SD_MODEL_DIR env var, else the default local cache location.
    Never downloads implicitly — matches the embeddings registry's
    local_files_only discipline."""
    override = os.environ.get("KRONARA_SD_MODEL_DIR")
    if override and Path(override).exists():
        return override
    default = Path(".kronara") / "models" / "sdxl-base-1.0"
    return str(default) if default.exists() else None


def find_lightning_lora_dir() -> str:
    """Use the local D: model cache when the fast-tier LoRA is installed."""
    override = os.environ.get("KRONARA_SD_LORA_DIR")
    if override and (Path(override) / LIGHTNING_LORA_WEIGHT).exists():
        return override
    default = Path(".kronara") / "models" / "sdxl-lightning"
    if (default / LIGHTNING_LORA_WEIGHT).exists():
        return str(default)
    return LIGHTNING_LORA_REPO


class PlaceholderImageProvider:
    """No-GPU stand-in: a deterministic illustrated storyboard frame.

    This is intentionally not presented as AI output. It keeps the visual
    pipeline reviewable when SDXL is unavailable, while avoiding the old flat
    colour frame with the raw prompt printed across the image.
    """

    def __init__(self, *, output_dir: str):
        self.output_dir = output_dir

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        import time

        import random

        from PIL import Image, ImageDraw, ImageFilter

        started = time.monotonic()
        os.makedirs(self.output_dir, exist_ok=True)
        # Deterministic palette derived from the seed so repeated seeds are
        # visually distinguishable while keeping a dark editorial language.
        rng_seed = request.seed or 1
        rng = random.Random(rng_seed)
        r = 7 + (rng_seed * 13) % 18
        g = 12 + (rng_seed * 17) % 22
        b = 30 + (rng_seed * 29) % 34
        width, height = request.width, request.height
        image = Image.new("RGB", (width, height))
        pixels = image.load()
        for y in range(height):
            progress = y / max(height - 1, 1)
            shade = 0.82 + progress * 0.18
            for x in range(width):
                horizontal = 0.88 + 0.12 * (x / max(width - 1, 1))
                pixels[x, y] = (
                    min(255, int(r * shade * horizontal)),
                    min(255, int(g * shade * horizontal)),
                    min(255, int(b * shade * horizontal)),
                )

        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse(
            (width * 0.5, height * 0.06, width * 0.99, height * 0.4),
            fill=(148, 95, 255, 80),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(max(12, width // 16)))
        image = Image.alpha_composite(image.convert("RGBA"), glow)

        draw = ImageDraw.Draw(image)
        # Depth cues: stars, distant cloud bands and a layered skyline.
        for _ in range(58):
            star_x = rng.randint(int(width * 0.06), int(width * 0.94))
            star_y = rng.randint(int(height * 0.06), int(height * 0.48))
            radius = rng.choice((1, 1, 2, 3))
            alpha = rng.randint(90, 210)
            draw.ellipse((star_x - radius, star_y - radius, star_x + radius, star_y + radius), fill=(210, 220, 255, alpha))

        horizon = int(height * 0.66)
        draw.ellipse(
            (width * 0.64, height * 0.14, width * 0.88, height * 0.38),
            fill=(245, 232, 211, 236),
            outline=(255, 247, 231, 245),
            width=max(1, width // 220),
        )
        moon_craters = ((0.71, 0.21, 0.035), (0.81, 0.29, 0.02), (0.76, 0.33, 0.026))
        for crater_x, crater_y, crater_size in moon_craters:
            cx, cy = int(width * crater_x), int(height * crater_y)
            radius = int(width * crater_size)
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(214, 198, 184, 120))

        for index in range(9):
            left = int(index * width / 9 + rng.randint(-width // 30, width // 30))
            building_width = rng.randint(max(35, width // 14), max(60, width // 7))
            building_height = rng.randint(int(height * 0.09), int(height * 0.2))
            top = horizon - building_height
            draw.rectangle((left, top, left + building_width, horizon), fill=(12, 14, 28, 220))
            for window in range(max(1, building_width // 35)):
                wx = left + 12 + window * 28
                wy = top + 24
                draw.rectangle((wx, wy, wx + 8, wy + 14), fill=(191, 119, 70, 130))

        draw.polygon(
            [(0, horizon), (width * 0.22, height * 0.48), (width * 0.42, horizon),
             (width * 0.64, height * 0.5), (width, horizon), (width, height), (0, height)],
            fill=(8, 10, 20, 220),
        )
        building_left = width * 0.28
        building_right = width * 0.7
        building_top = height * 0.41
        draw.rectangle((building_left, building_top, building_right, horizon), fill=(10, 12, 24, 245))
        draw.polygon(
            [(building_left - width * 0.05, building_top),
             (width * 0.49, height * 0.31),
             (building_right + width * 0.05, building_top)],
            fill=(7, 9, 18, 250),
        )
        draw.polygon(
            [(building_left + width * 0.06, building_top), (width * 0.49, height * 0.35),
             (building_right - width * 0.05, building_top)],
            outline=(64, 44, 93, 220), width=max(2, width // 160),
        )
        draw.rectangle((building_right - width * 0.08, height * 0.48, building_right + width * 0.02, horizon), fill=(7, 9, 18, 245))
        draw.rectangle((width * 0.43, height * 0.54, width * 0.55, horizon), fill=(5, 7, 16, 250))
        draw.polygon([(width * 0.4, height * 0.54), (width * 0.49, height * 0.47), (width * 0.58, height * 0.54)], fill=(7, 9, 18, 250))
        for row in range(2):
            for column in range(3):
                x = int(building_left + width * 0.08 + column * width * 0.11)
                y = int(building_top + height * 0.08 + row * height * 0.11)
                draw.rounded_rectangle(
                    (x, y, x + max(8, width // 18), y + max(12, height // 34)),
                    radius=max(1, width // 80),
                    fill=(255, 184, 94, 205),
                )
        draw.rectangle((width * 0.46, height * 0.62, width * 0.52, horizon), fill=(67, 42, 68, 255))
        draw.ellipse((width * 0.49, height * 0.72, width * 0.5, height * 0.73), fill=(244, 177, 87, 220))

        # Match a few visual nouns from the prompt without pretending this is
        # diffusion: an audio/phone motif makes a generated cover relevant.
        prompt = request.prompt.casefold()
        if any(token in prompt for token in ("audio", "llamada", "teléfono", "phone")):
            phone_left, phone_top = int(width * 0.12), int(height * 0.62)
            phone_right, phone_bottom = int(width * 0.32), int(height * 0.88)
            draw.rounded_rectangle((phone_left, phone_top, phone_right, phone_bottom), radius=width // 28, fill=(12, 15, 30, 250), outline=(151, 102, 227, 220), width=max(2, width // 120))
            draw.rounded_rectangle((phone_left + width * 0.025, phone_top + height * 0.035, phone_right - width * 0.025, phone_bottom - height * 0.05), radius=width // 45, fill=(24, 30, 58, 255))
            for bar in range(7):
                bar_x = phone_left + width * (0.055 + bar * 0.024)
                bar_height = height * (0.025 + (bar % 3) * 0.018)
                draw.rounded_rectangle((bar_x, height * 0.75 - bar_height, bar_x + width * 0.012, height * 0.75 + bar_height), radius=3, fill=(184, 108, 255, 230))

        # Soft foreground mist prevents the geometry from reading as a flat
        # icon and helps separate the subject from the background.
        mist = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        mist_draw = ImageDraw.Draw(mist)
        mist_draw.ellipse((width * -0.2, height * 0.57, width * 0.75, height * 0.83), fill=(170, 183, 230, 32))
        mist_draw.ellipse((width * 0.35, height * 0.62, width * 1.2, height * 0.9), fill=(200, 153, 230, 24))
        image = Image.alpha_composite(image, mist.filter(ImageFilter.GaussianBlur(max(10, width // 22))))
        draw = ImageDraw.Draw(image)
        draw.line((width * 0.08, horizon, width * 0.92, horizon), fill=(242, 164, 110, 130), width=max(1, width // 180))
        draw.rounded_rectangle(
            (width * 0.06, height * 0.06, width * 0.94, height * 0.94),
            radius=max(4, width // 30),
            outline=(255, 255, 255, 70),
            width=max(1, width // 250),
        )
        draw.text((width * 0.08, height * 0.91), "KRONARA · VISTA LOCAL", fill=(225, 214, 232, 180))
        path = os.path.join(self.output_dir, f"{request.cache_key()[:16]}.png")
        image.convert("RGB").save(path)
        return ImageGenerationResult(
            image_path=path,
            seed=request.seed,
            width=request.width,
            height=request.height,
            quality_tier=request.quality_tier,
            generation_ms=int((time.monotonic() - started) * 1000),
        )


class DiffusersImageProvider:
    """Local SDXL generation via diffusers. Lazy-loaded; ``warmup()``/
    ``release()`` bound the VRAM lifetime to one episode's image batch (the
    model must coexist with other local GPU work, e.g. faster-whisper, and
    should never hold the GPU longer than a batch needs)."""

    def __init__(
        self,
        *,
        model_dir: str | None = None,
        lightning_lora_repo: str | None = None,
        lightning_lora_weight: str = LIGHTNING_LORA_WEIGHT,
        ip_adapter_repo: str | None = IP_ADAPTER_REPO,
        output_dir: str,
        pipeline_loader: Callable[[str], Any] | None = None,
        device: str | None = None,
    ):
        self.model_dir = model_dir or find_sd_model_dir()
        self.lightning_lora_repo = lightning_lora_repo or find_lightning_lora_dir()
        self.lightning_lora_weight = lightning_lora_weight
        self.ip_adapter_repo = ip_adapter_repo
        self.output_dir = output_dir
        self._pipeline_loader = pipeline_loader or self._default_loader
        # None -> auto-detect at generate() time (deferred torch import), so
        # constructing a provider never requires torch/CUDA to be importable
        # and a machine without a GPU degrades to CPU instead of hard-erroring
        # on generator construction.
        self._device_override = device
        self._pipe: Any | None = None
        self._lora_loaded = False
        self._ip_adapter_loaded = False

    @property
    def device(self) -> str:
        if self._device_override is not None:
            return self._device_override
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def warmup(self) -> None:
        self._load()

    def release(self) -> None:
        if self._pipe is not None:
            try:
                import gc

                import torch

                del self._pipe
                self._pipe = None
                gc.collect()
                torch.cuda.empty_cache()
            except ImportError:
                self._pipe = None
        self._lora_loaded = False
        self._ip_adapter_loaded = False

    def __enter__(self) -> "DiffusersImageProvider":
        self.warmup()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        import time

        import numpy as np
        import torch

        started = time.monotonic()
        pipe = self._load()
        self._set_tier(pipe, request.quality_tier)

        if request.reference_image_path and self.ip_adapter_repo:
            self._ensure_ip_adapter(pipe)
            pipe.set_ip_adapter_scale(request.reference_strength)

        steps = FAST_STEPS if request.quality_tier == "fast" else PREMIUM_STEPS
        guidance = FAST_GUIDANCE if request.quality_tier == "fast" else PREMIUM_GUIDANCE
        generator = torch.Generator(device=self.device).manual_seed(request.seed)

        kwargs: dict[str, Any] = dict(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt or None,
            width=request.width,
            height=request.height,
            num_inference_steps=steps,
            guidance_scale=guidance,
            generator=generator,
        )
        if request.reference_image_path and self.ip_adapter_repo:
            from PIL import Image as PILImage

            kwargs["ip_adapter_image"] = PILImage.open(request.reference_image_path).convert("RGB")

        degraded = False
        try:
            output = pipe(**kwargs)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            pipe.enable_model_cpu_offload()
            output = pipe(**kwargs)
            degraded = True

        image = output.images[0]
        # Known SDXL fp16 VAE failure mode: occasional uniform/NaN (black)
        # frames. A cheap std-dev check catches it instead of silently
        # shipping a black shot; QC (V8) is the safety net if this misses one.
        array = np.asarray(image)
        if array.std() < 1.0:
            degraded = True

        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"{request.cache_key()[:16]}.png")
        image.save(path)
        return ImageGenerationResult(
            image_path=path,
            seed=request.seed,
            width=request.width,
            height=request.height,
            quality_tier=request.quality_tier,
            generation_ms=int((time.monotonic() - started) * 1000),
            degraded=degraded,
        )

    def _load(self) -> Any:
        if self._pipe is None:
            if not self.model_dir:
                raise RuntimeError(
                    "no local SDXL weights found (set KRONARA_SD_MODEL_DIR or "
                    "download to .kronara/models/sdxl-base-1.0)"
                )
            self._pipe = self._pipeline_loader(self.model_dir)
        return self._pipe

    def _set_tier(self, pipe: Any, tier: str) -> None:
        from diffusers import DPMSolverMultistepScheduler, EulerDiscreteScheduler

        if tier == "fast":
            if not self._lora_loaded:
                pipe.load_lora_weights(
                    self.lightning_lora_repo,
                    weight_name=self.lightning_lora_weight,
                    local_files_only=True,
                )
                self._lora_loaded = True
            pipe.scheduler = EulerDiscreteScheduler.from_config(
                pipe.scheduler.config, timestep_spacing="trailing"
            )
        else:
            if self._lora_loaded:
                pipe.unload_lora_weights()
                self._lora_loaded = False
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                pipe.scheduler.config, use_karras_sigmas=True
            )

    def _ensure_ip_adapter(self, pipe: Any) -> None:
        if not self._ip_adapter_loaded:
            pipe.load_ip_adapter(
                self.ip_adapter_repo,
                subfolder=IP_ADAPTER_SUBFOLDER,
                weight_name=IP_ADAPTER_WEIGHT,
                local_files_only=True,
            )
            self._ip_adapter_loaded = True

    def _default_loader(self, model_dir: str) -> Any:
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
        except ImportError as error:
            raise RuntimeError(
                "the 'visual' extra (diffusers, torch, accelerate) is required "
                "for local image generation"
            ) from error
        device = self.device
        dtype = torch.float16 if device == "cuda" else torch.float32
        kwargs: dict[str, Any] = dict(torch_dtype=dtype, local_files_only=True)
        if device == "cuda":
            kwargs["variant"] = "fp16"
        pipe = StableDiffusionXLPipeline.from_pretrained(model_dir, **kwargs)
        pipe.vae.enable_tiling()
        pipe.vae.enable_slicing()
        return pipe.to(device)
