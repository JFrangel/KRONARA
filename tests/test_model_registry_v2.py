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
            health={"groq-live-catalog": "healthy"},
        )


def test_registry_contains_requested_models_and_dynamic_groq_route():
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    model_ids = {item["model_id"] for item in payload["candidates"]}

    assert "nvidia/nemotron-3-super-120b-a12b:free" in model_ids
    assert "tencent/hy3:free" in model_ids
    assert "groq-live-catalog" in model_ids
    assert payload["aliases"]["experimental_hy3"][0] == "tencent/hy3:free"


def test_environment_template_exposes_aliases_without_secrets():
    template = Path(".env.example").read_text(encoding="utf-8")

    assert "KRONARA_MODEL_REGISTRY=config/models/registry.v2.json" in template
    assert "KRONARA_NEMOTRON_MODEL=nvidia/nemotron-3-super-120b-a12b:free" in template
    assert "KRONARA_HY3_MODEL=tencent/hy3:free" in template
    assert "KRONARA_MODEL_HEALTH_TTL_SECONDS=300" in template

