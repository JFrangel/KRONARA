from pathlib import Path

from kronara.model_registry_v2 import ModelCapabilityRegistryV2
from kronara.routed_story_provider import (
    AuthorityModelRouter,
    RoutedIndependentCritic,
    RoutedStoryProvider,
)
from kronara.story_engine import StoryBrief, StoryConcept, StoryScript


ROOT = Path(__file__).resolve().parents[1]


class FakeAuthority:
    def __init__(self):
        self.calls = []
        self.health = {
            "qwen/qwen3-235b-a22b": "healthy",
            "moonshotai/kimi-k2": "healthy",
            "nvidia/nemotron-3-super-120b-a12b:free": "healthy",
            "tencent/hy3:free": "healthy",
        }

    def invoke(self, tool_id, arguments):
        self.calls.append((tool_id, arguments))
        if tool_id == "model.health":
            return {"models": self.health}
        task = arguments["task"]
        payloads = {
            "story.inspiration": {
                "angles": ["decisión irreversible", "evidencia incompleta"]
            },
            "story.concepts": {
                "concepts": [
                    {
                        "concept_id": f"concept_{index}",
                        "logline": f"Concepto original número {index} con conflicto verificable.",
                        "promise": "Cada decisión cambia el costo de revelar la verdad.",
                        "hook": f"Una anomalía concreta abre el concepto {index}.",
                        "projected_retention": 0.80 + index / 100,
                    }
                    for index in range(1, 4)
                ]
            },
            "story.blueprint": {
                "beats": [
                    {
                        "beat_id": f"beat_{index}",
                        "cause": f"causa {index}",
                        "effect": f"efecto {index}",
                        "event": f"evento_{index}",
                        "seed_id": f"seed_{index}" if index <= 3 else None,
                        "payoff_for": f"seed_{index - 3}" if index > 3 else None,
                    }
                    for index in range(1, 7)
                ]
            },
            "story.scenes": {
                "scenes": [
                    {
                        "scene_id": f"scene_{index}",
                        "purpose": f"evento_{index}",
                        "narration": "Mara verifica una pista y toma una decisión irreversible.",
                        "target_seconds": 15,
                        "characters": ["Mara"],
                        "seed_ids": [f"seed_{index}"] if index <= 3 else [],
                        "payoff_ids": [f"seed_{index - 3}"] if index > 3 else [],
                    }
                    for index in range(1, 7)
                ]
            },
            "story.critique": {
                "passed": True,
                "scores": {
                    key: 8.5
                    for key in (
                        "hook", "clarity", "conflict", "escalation", "agency",
                        "coherence", "credibility", "originality", "retention",
                        "payoff", "production_fit",
                    )
                },
                "issues": [],
                "revision": {},
            },
        }
        if task == "story.revise":
            payloads[task] = {"scenes": arguments["input"]["scenes"]}
        selected = arguments["candidates"][0]
        return {
            "payload": payloads[task],
            "provider": selected["provider"],
            "model": selected["model_id"],
            "fallback_used": False,
            "usage": {"total_tokens": 100},
        }


def brief():
    return StoryBrief(
        story_id="owned-routed-1",
        title="El audio incompleto",
        premise="Una restauradora encuentra una decisión familiar oculta.",
        theme="verdad y lealtad",
        target_duration_seconds=90,
        rights_mode="owned_original",
        source_uri="kronara://artifacts/owned-routed-1",
        evidence_refs=("ev-owned",),
    )


def router(authority):
    registry = ModelCapabilityRegistryV2.load(
        ROOT / "config" / "models" / "registry.v2.json"
    )
    return AuthorityModelRouter(authority=authority, registry=registry)


def test_story_provider_uses_hy3_inspiration_then_qwen_with_nemotron_fallback():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    concepts = provider.concepts(brief())

    completion_calls = [args for tool, args in authority.calls if tool == "model.complete"]
    assert len(concepts) == 3
    assert completion_calls[0]["candidates"][0]["model_id"] == "tencent/hy3:free"
    assert completion_calls[1]["candidates"][0]["model_id"] == "qwen/qwen3-235b-a22b"
    assert any(
        item["model_id"] == "nvidia/nemotron-3-super-120b-a12b:free"
        for item in completion_calls[1]["candidates"]
    )
    assert provider.family == "qwen-routed"


def test_independent_critic_routes_to_kimi_and_returns_structured_scores():
    authority = FakeAuthority()
    critic = RoutedIndependentCritic(router(authority))

    result = critic.review(
        brief(),
        StoryConcept("concept_1", "Una logline suficientemente original.", "promesa", "hook", 0.9),
        (),
        StoryScript("Guion propio verificable.", 3, 1.2),
    )

    call = [args for tool, args in authority.calls if tool == "model.complete"][-1]
    assert call["candidates"][0]["model_id"] == "moonshotai/kimi-k2"
    assert result.passed
    assert result.scores["originality"] == 8.5
    assert critic.family == "kimi-routed"


def test_critic_excludes_the_actual_generator_fallback_family():
    authority = FakeAuthority()
    authority.health["qwen/qwen3-235b-a22b"] = "unavailable"
    story_router = router(authority)
    provider = RoutedStoryProvider(story_router)
    provider.concepts(brief())
    critic = RoutedIndependentCritic(story_router, generator=provider)

    critic.review(
        brief(),
        StoryConcept("concept_1", "Logline original.", "promesa", "hook", 0.9),
        (),
        StoryScript("Guion propio verificable.", 3, 1.2),
    )

    critique_call = [
        args
        for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.critique"
    ][0]
    assert critique_call["candidates"][0]["model_id"] == (
        "nvidia/nemotron-3-super-120b-a12b:free"
    )


def test_entertainment_source_gets_no_sensitive_directive():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    provider.concepts(brief())  # default source_sensitivity="entertainment"

    concepts_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.concepts"
    ][0]
    assert "FUENTE DE EXPERIENCIA REAL SERIA" not in concepts_call["system"]


def test_sensitive_source_injects_serious_transformation_directive():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    sensitive_brief = StoryBrief(
        story_id="owned-sensitive-1",
        title="El silencio en casa",
        premise="Un patrón familiar difícil, inspirado en experiencias reales.",
        theme="sanar y reconstruir",
        target_duration_seconds=90,
        rights_mode="owned_original",
        source_uri="kronara://artifacts/owned-sensitive-1",
        evidence_refs=("ev-owned",),
        source_sensitivity="real_experience_serious",
    )

    provider.concepts(sensitive_brief)

    concepts_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.concepts"
    ][0]
    assert "FUENTE DE EXPERIENCIA REAL SERIA" in concepts_call["system"]
    assert "cambia deliberadamente todo detalle identificable".casefold() in concepts_call["system"].casefold()


def test_sensitive_directive_persists_through_revise_without_a_brief_param():
    """revise() is a fixed StoryGenerator Protocol method (scenes, revision only) —
    it must still apply the directive via the sensitivity cached from concepts()."""
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    sensitive_brief = StoryBrief(
        story_id="owned-sensitive-2",
        title="La carta que no envié",
        premise="Un patrón familiar difícil, inspirado en experiencias reales.",
        theme="sanar y reconstruir",
        target_duration_seconds=90,
        rights_mode="owned_original",
        source_uri="kronara://artifacts/owned-sensitive-2",
        evidence_refs=("ev-owned",),
        source_sensitivity="real_experience_serious",
    )
    provider.concepts(sensitive_brief)
    blueprint = provider.blueprint(sensitive_brief, StoryConcept("c1", "logline", "promise", "hook", 0.9))
    scenes = provider.scenes(sensitive_brief, StoryConcept("c1", "logline", "promise", "hook", 0.9), blueprint)

    provider.revise(scenes, {"scene_index": 0})

    revise_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.revise"
    ][0]
    assert "FUENTE DE EXPERIENCIA REAL SERIA" in revise_call["system"]


def test_critic_gets_sensitive_verification_instruction():
    authority = FakeAuthority()
    critic = RoutedIndependentCritic(router(authority))
    sensitive_brief = StoryBrief(
        story_id="owned-sensitive-3",
        title="El eco de una decisión",
        premise="Un patrón familiar difícil, inspirado en experiencias reales.",
        theme="sanar y reconstruir",
        target_duration_seconds=90,
        rights_mode="owned_original",
        source_uri="kronara://artifacts/owned-sensitive-3",
        evidence_refs=("ev-owned",),
        source_sensitivity="real_experience_serious",
    )

    critic.review(
        sensitive_brief,
        StoryConcept("concept_1", "Una logline suficientemente original.", "promesa", "hook", 0.9),
        (),
        StoryScript("Guion propio verificable.", 3, 1.2),
    )

    critique_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.critique"
    ][0]
    assert "detalle identificable" in critique_call["system"].casefold()


def test_concepts_request_uses_a_modest_flat_token_budget_not_the_old_4096():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    provider.concepts(brief())

    concepts_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.concepts"
    ][0]
    assert concepts_call["max_tokens"] == 1024


def test_blueprint_request_uses_a_generous_flat_token_budget():
    """Raised to 6144 after a real run truncated mid-beat-6 at 1536 tokens --
    real elaborate literary beats need real room (see the comment at the
    call site for the full story)."""
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    provider.blueprint(brief(), StoryConcept("c1", "logline", "promise", "hook", 0.9))

    blueprint_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.blueprint"
    ][0]
    assert blueprint_call["max_tokens"] == 6144


def test_critique_request_uses_a_modest_flat_token_budget_not_the_old_4096():
    authority = FakeAuthority()
    critic = RoutedIndependentCritic(router(authority))

    critic.review(
        brief(),
        StoryConcept("concept_1", "Una logline suficientemente original.", "promesa", "hook", 0.9),
        (),
        StoryScript("Guion propio verificable.", 3, 1.2),
    )

    critique_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.critique"
    ][0]
    assert critique_call["max_tokens"] == 1536


def test_scenes_request_scales_max_tokens_up_for_longer_targets():
    """90s -> 225 target words -> the 4096 floor (real elaborate literary
    scenes need real room -- see _scene_max_tokens' docstring for the two
    real-run recalibrations that produced this floor). Longer targets
    should still scale above the floor."""
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    concepts = provider.concepts(brief())
    blueprint = provider.blueprint(brief(), concepts[0])

    provider.scenes(brief(), concepts[0], blueprint)

    scenes_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.scenes"
    ][0]
    assert scenes_call["max_tokens"] == 4096


def test_revise_sizes_max_tokens_from_the_revision_target_word_count_when_present():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    concepts = provider.concepts(brief())
    blueprint = provider.blueprint(brief(), concepts[0])
    scenes = provider.scenes(brief(), concepts[0], blueprint)

    provider.revise(scenes, {"operation": "fit_duration", "target_word_count": 500})

    revise_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.revise"
    ][-1]
    assert revise_call["max_tokens"] == max(4096, min(8192, round(500 * 3.0) + 1536))


def test_revise_without_a_target_word_count_falls_back_to_existing_scene_length():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    concepts = provider.concepts(brief())
    blueprint = provider.blueprint(brief(), concepts[0])
    scenes = provider.scenes(brief(), concepts[0], blueprint)

    provider.revise(scenes, {"scene_index": 0})

    revise_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.revise"
    ][-1]
    existing_words = sum(len(scene.narration.split()) for scene in scenes)
    assert revise_call["max_tokens"] == max(4096, min(8192, round(existing_words * 3.0) + 1536))
