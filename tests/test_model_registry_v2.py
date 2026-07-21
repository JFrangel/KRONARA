import json
from datetime import date
from pathlib import Path

import pytest

from kronara.model_registry_v2 import (
    ModelCapabilityRegistryV2,
    ModelRequirements,
    NoHealthyModelError,
)


REGISTRY = Path("config/models/registry.v2.json")


def requirements(*capabilities: str) -> ModelRequirements:
    return ModelRequirements(
        required_capabilities=frozenset(capabilities or ("long_context",)),
        minimum_context_tokens=32000,
        structured_output=False,
        tool_calling=False,
    )


def test_hy3_never_resolves_without_healthy_fallbacks():
    registry = ModelCapabilityRegistryV2.load(REGISTRY, now=lambda: date(2026, 7, 20))
    route = registry.resolve(
        "experimental_hy3",
        requirements("long_context"),
        health={
            "tencent/hy3:free": "healthy",
            "nvidia/nemotron-3-super-120b-a12b:free": "healthy",
            "moonshotai/kimi-k2": "healthy",
        },
    )

    assert route.primary == "tencent/hy3:free"
    assert route.fallbacks
    assert "experimental" in route.selection_reasons


def test_expired_hy3_is_skipped_even_if_health_says_healthy():
    registry = ModelCapabilityRegistryV2.load(REGISTRY, now=lambda: date(2026, 7, 22))
    route = registry.resolve(
        "experimental_hy3",
        requirements("long_context"),
        health={
            "tencent/hy3:free": "healthy",
            "nvidia/nemotron-3-super-120b-a12b:free": "healthy",
            "moonshotai/kimi-k2": "healthy",
        },
    )

    assert route.primary != "tencent/hy3:free"
    assert "expired:tencent/hy3:free" in route.selection_reasons


def test_router_filters_capability_context_health_and_tool_calling():
    registry = ModelCapabilityRegistryV2.load(REGISTRY, now=lambda: date(2026, 7, 19))
    route = registry.resolve(
        "planning_primary",
        ModelRequirements(
            required_capabilities=frozenset({"planning", "structured_output"}),
            minimum_context_tokens=64000,
            structured_output=True,
            tool_calling=True,
        ),
        health={
            "qwen/qwen3-235b-a22b": "unavailable",
            "nvidia/nemotron-3-super-120b-a12b:free": "healthy",
            "moonshotai/kimi-k2": "healthy",
        },
    )

    assert route.primary == "nvidia/nemotron-3-super-120b-a12b:free"
    assert route.requested_alias == "planning_primary"
    assert "unhealthy:qwen/qwen3-235b-a22b" in route.selection_reasons


def test_registry_fails_closed_when_no_candidate_meets_requirements():
    registry = ModelCapabilityRegistryV2.load(REGISTRY)

    with pytest.raises(NoHealthyModelError, match="no healthy model"):
        registry.resolve(
            "fast_tools",
            requirements("video_generation"),
            health={"openai/gpt-oss-120b": "healthy"},
        )


def test_registry_contains_requested_models_including_groq_cascade():
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    model_ids = {item["model_id"] for item in payload["candidates"]}
    groq_ids = {
        item["model_id"] for item in payload["candidates"] if item["provider"] == "groq"
    }

    assert "nvidia/nemotron-3-super-120b-a12b:free" in model_ids
    assert "tencent/hy3:free" in model_ids
    # Real Groq-hosted models directly in the cascade (no more single-model
    # "groq-live-catalog" sentinel) -- each gets its own independent
    # per-model rate-limit bucket on Groq's side.
    assert groq_ids == {"openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.6-27b"}
    assert payload["aliases"]["experimental_hy3"][0] == "tencent/hy3:free"
    for alias, model_ids_for_alias in payload["aliases"].items():
        assert len(model_ids_for_alias) <= 5, f"{alias} exceeds Rust's 5-candidate request cap"


def test_environment_template_exposes_aliases_without_secrets():
    template = Path(".env.example").read_text(encoding="utf-8")

    assert "KRONARA_MODEL_REGISTRY=config/models/registry.v2.json" in template
    assert "KRONARA_NEMOTRON_MODEL=nvidia/nemotron-3-super-120b-a12b:free" in template
    assert "KRONARA_HY3_MODEL=tencent/hy3:free" in template
    assert "KRONARA_MODEL_HEALTH_TTL_SECONDS=300" in template

