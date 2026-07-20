import pytest

from kronara.image_gen import (
    FAST_STEPS,
    PREMIUM_STEPS,
    DiffusersImageProvider,
    ImageGenerationRequest,
    PlaceholderImageProvider,
    SDXL_BUCKET_9x16,
)


# ---- ImageGenerationRequest -------------------------------------------------


def test_request_defaults_to_sdxl_9x16_bucket():
    request = ImageGenerationRequest(prompt="a dim hallway at night")
    assert (request.width, request.height) == SDXL_BUCKET_9x16


def test_request_rejects_empty_prompt():
    with pytest.raises(ValueError):
        ImageGenerationRequest(prompt="   ")


def test_request_rejects_unknown_tier():
    with pytest.raises(ValueError):
        ImageGenerationRequest(prompt="x", quality_tier="ultra")


def test_cache_key_is_deterministic_and_seed_sensitive():
    base = dict(prompt="a locked door", negative_prompt="", width=768, height=1344)
    a = ImageGenerationRequest(seed=1, **base)
    b = ImageGenerationRequest(seed=1, **base)
    c = ImageGenerationRequest(seed=2, **base)
    assert a.cache_key() == b.cache_key()
    assert a.cache_key() != c.cache_key()


# ---- PlaceholderImageProvider (no GPU) --------------------------------------


def test_placeholder_provider_writes_correctly_sized_png(tmp_path):
    from PIL import Image

    provider = PlaceholderImageProvider(output_dir=str(tmp_path))
    request = ImageGenerationRequest(prompt="a foggy forest path", seed=7, quality_tier="premium")

    result = provider.generate(request)

    assert result.width == request.width
    assert result.height == request.height
    assert result.quality_tier == "premium"
    assert result.degraded is False
    image = Image.open(result.image_path)
    assert image.size == (request.width, request.height)


def test_placeholder_provider_different_seeds_produce_different_colors(tmp_path):
    provider = PlaceholderImageProvider(output_dir=str(tmp_path))
    a = provider.generate(ImageGenerationRequest(prompt="x", seed=1))
    b = provider.generate(ImageGenerationRequest(prompt="x", seed=2))
    from PIL import Image

    color_a = Image.open(a.image_path).getpixel((0, 0))
    color_b = Image.open(b.image_path).getpixel((0, 0))
    assert color_a != color_b


# ---- DiffusersImageProvider orchestration (fake pipe, no real GPU/weights) --


class FakeScheduler:
    def __init__(self):
        self.config = {"fake": True}

    @classmethod
    def from_config(cls, config, **kwargs):
        instance = cls()
        instance.config = config
        instance.from_config_kwargs = kwargs
        return instance


class FakeOutput:
    def __init__(self, image):
        self.images = [image]


class FakeSDXLPipeline:
    def __init__(self):
        self.scheduler = FakeScheduler()
        self.lora_calls: list[tuple] = []
        self.unload_calls = 0
        self.ip_adapter_calls: list[tuple] = []
        self.ip_adapter_scale: float | None = None
        self.offload_called = False
        self.call_kwargs: list[dict] = []
        self.raise_oom_once = False
        self._oom_raised = False

    def load_lora_weights(self, repo, weight_name):
        self.lora_calls.append((repo, weight_name))

    def unload_lora_weights(self):
        self.unload_calls += 1

    def load_ip_adapter(self, repo, subfolder, weight_name):
        self.ip_adapter_calls.append((repo, subfolder, weight_name))

    def set_ip_adapter_scale(self, scale):
        self.ip_adapter_scale = scale

    def enable_model_cpu_offload(self):
        self.offload_called = True

    def __call__(self, **kwargs):
        import torch

        if self.raise_oom_once and not self._oom_raised:
            self._oom_raised = True
            raise torch.cuda.OutOfMemoryError("fake oom")
        self.call_kwargs.append(kwargs)
        from PIL import Image

        image = Image.new("RGB", (kwargs["width"], kwargs["height"]), (80, 90, 100))
        return FakeOutput(image)


def _provider(tmp_path, pipe):
    return DiffusersImageProvider(
        model_dir="/fake/model/dir",
        output_dir=str(tmp_path),
        pipeline_loader=lambda _: pipe,
    )


def test_fast_tier_loads_lightning_lora_and_uses_euler_scheduler(tmp_path):
    pipe = FakeSDXLPipeline()
    provider = _provider(tmp_path, pipe)

    result = provider.generate(ImageGenerationRequest(prompt="a tense hallway", quality_tier="fast", seed=1))

    assert len(pipe.lora_calls) == 1
    assert pipe.call_kwargs[0]["num_inference_steps"] == FAST_STEPS
    assert result.quality_tier == "fast"
    assert result.degraded is False


def test_premium_tier_skips_lora_and_uses_dpm_scheduler(tmp_path):
    pipe = FakeSDXLPipeline()
    provider = _provider(tmp_path, pipe)

    result = provider.generate(ImageGenerationRequest(prompt="the climax reveal", quality_tier="premium", seed=1))

    assert pipe.lora_calls == []
    assert pipe.call_kwargs[0]["num_inference_steps"] == PREMIUM_STEPS
    assert result.quality_tier == "premium"


def test_switching_from_fast_to_premium_unloads_the_lora(tmp_path):
    pipe = FakeSDXLPipeline()
    provider = _provider(tmp_path, pipe)

    provider.generate(ImageGenerationRequest(prompt="a", quality_tier="fast", seed=1))
    provider.generate(ImageGenerationRequest(prompt="b", quality_tier="premium", seed=2))

    assert pipe.unload_calls == 1


def test_reference_image_triggers_ip_adapter_conditioning(tmp_path):
    from PIL import Image

    ref_path = tmp_path / "character_sheet.png"
    Image.new("RGB", (256, 256), (10, 20, 30)).save(ref_path)
    pipe = FakeSDXLPipeline()
    provider = _provider(tmp_path, pipe)

    provider.generate(
        ImageGenerationRequest(
            prompt="Mara walks down the corridor", seed=1, reference_image_path=str(ref_path),
            reference_strength=0.7,
        )
    )

    assert len(pipe.ip_adapter_calls) == 1
    assert pipe.ip_adapter_scale == 0.7
    assert "ip_adapter_image" in pipe.call_kwargs[0]


def test_ip_adapter_loaded_only_once_across_multiple_calls(tmp_path):
    from PIL import Image

    ref_path = tmp_path / "character_sheet.png"
    Image.new("RGB", (256, 256), (10, 20, 30)).save(ref_path)
    pipe = FakeSDXLPipeline()
    provider = _provider(tmp_path, pipe)

    provider.generate(ImageGenerationRequest(prompt="a", seed=1, reference_image_path=str(ref_path)))
    provider.generate(ImageGenerationRequest(prompt="b", seed=2, reference_image_path=str(ref_path)))

    assert len(pipe.ip_adapter_calls) == 1  # loaded once, reused


def test_oom_triggers_cpu_offload_retry_and_marks_degraded(tmp_path):
    pipe = FakeSDXLPipeline()
    pipe.raise_oom_once = True
    provider = _provider(tmp_path, pipe)

    result = provider.generate(ImageGenerationRequest(prompt="a", seed=1))

    assert pipe.offload_called is True
    assert result.degraded is True


def test_uniform_black_frame_is_marked_degraded(tmp_path):
    class BlackFramePipeline(FakeSDXLPipeline):
        def __call__(self, **kwargs):
            from PIL import Image

            return FakeOutput(Image.new("RGB", (kwargs["width"], kwargs["height"]), (0, 0, 0)))

    provider = _provider(tmp_path, BlackFramePipeline())
    result = provider.generate(ImageGenerationRequest(prompt="a", seed=1))
    assert result.degraded is True


def test_release_clears_pipe_and_lora_state(tmp_path):
    pipe = FakeSDXLPipeline()
    provider = _provider(tmp_path, pipe)
    provider.generate(ImageGenerationRequest(prompt="a", quality_tier="fast", seed=1))

    provider.release()

    assert provider._pipe is None
    assert provider._lora_loaded is False


def test_missing_model_dir_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("KRONARA_SD_MODEL_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # ensure no local .kronara/models/sdxl-base-1.0 is found
    provider = DiffusersImageProvider(
        model_dir=None, output_dir=str(tmp_path), pipeline_loader=lambda _: FakeSDXLPipeline(),
    )
    with pytest.raises(RuntimeError, match="no local SDXL weights"):
        provider.generate(ImageGenerationRequest(prompt="a", seed=1))
