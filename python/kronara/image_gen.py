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


class PlaceholderImageProvider:
    """No-GPU stand-in: a Pillow-drawn gradient PNG at the requested size, with
    the prompt text overlaid for visual debugging. Exists so the
    composition/audio/QC pipeline is fully testable without a GPU or weights."""

    def __init__(self, *, output_dir: str):
        self.output_dir = output_dir

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        import time

        from PIL import Image, ImageDraw

        started = time.monotonic()
        os.makedirs(self.output_dir, exist_ok=True)
        # Deterministic color derived from the seed so repeated seeds are
        # visually distinguishable in manual review without being random.
        rng_seed = request.seed or 1
        r = (rng_seed * 47) % 200 + 20
        g = (rng_seed * 89) % 200 + 20
        b = (rng_seed * 131) % 200 + 20
        image = Image.new("RGB", (request.width, request.height), (r, g, b))
        draw = ImageDraw.Draw(image)
        draw.text((40, request.height // 2), request.prompt[:60], fill=(255, 255, 255))
        draw.text((40, request.height // 2 + 30), f"tier={request.quality_tier}", fill=(220, 220, 220))
        path = os.path.join(self.output_dir, f"{request.cache_key()[:16]}.png")
        image.save(path)
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
        lightning_lora_repo: str = LIGHTNING_LORA_REPO,
        lightning_lora_weight: str = LIGHTNING_LORA_WEIGHT,
        ip_adapter_repo: str | None = IP_ADAPTER_REPO,
        output_dir: str,
        pipeline_loader: Callable[[str], Any] | None = None,
        device: str | None = None,
    ):
        self.model_dir = model_dir or find_sd_model_dir()
        self.lightning_lora_repo = lightning_lora_repo
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
