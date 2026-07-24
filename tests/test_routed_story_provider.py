from datetime import date
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
            "nvidia/nemotron-3-ultra-550b-a55b:free": "healthy",
            "tencent/hy3:free": "healthy",
            "openai/gpt-oss-120b": "healthy",
            "llama-3.3-70b-versatile": "healthy",
            "qwen/qwen3.6-27b": "healthy",
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


class SpanishScoreAuthority(FakeAuthority):
    def invoke(self, tool_id, arguments):
        result = super().invoke(tool_id, arguments)
        if tool_id == "model.complete" and arguments["task"] == "story.critique":
            result["payload"]["scores"] = {
                "gancho": 8.5,
                "claridad": 8.4,
                "conflicto": 8.3,
                "escalada": 8.2,
                "agencia": 8.1,
                "coherencia": 8.0,
                "credibilidad": 7.9,
                "originalidad": 7.8,
                "retención": 7.7,
                "remate": 7.6,
                "ajuste de producción": 7.5,
            }
        return result


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


def program_brief(program_id):
    base = brief()
    return StoryBrief(
        story_id=base.story_id,
        title=base.title,
        premise=base.premise,
        theme=base.theme,
        target_duration_seconds=base.target_duration_seconds,
        rights_mode=base.rights_mode,
        source_uri=base.source_uri,
        evidence_refs=base.evidence_refs,
        program_id=program_id,
    )


def router(authority):
    registry = ModelCapabilityRegistryV2.load(
        ROOT / "config" / "models" / "registry.v2.json",
        now=lambda: date(2026, 7, 22),
    )
    return AuthorityModelRouter(authority=authority, registry=registry)


def test_story_provider_skips_expired_hy3_and_uses_groq_first_with_qwen_fallback():
    """HY3 expired in the registry on 2026-07-21, so the inspiration route
    falls through to Groq's gpt-oss-120b. Groq also leads creative_primary:
    a real run showed qwen (via OpenRouter) doesn't reliably honor strict
    structured output for this task, while Groq is both faster and more
    likely to comply. qwen stays in the chain as a fallback."""
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    concepts = provider.concepts(brief())

    completion_calls = [args for tool, args in authority.calls if tool == "model.complete"]
    assert len(concepts) == 3
    assert completion_calls[0]["task"] == "story.inspiration"
    assert completion_calls[0]["candidates"][0]["model_id"] == "openai/gpt-oss-120b"
    assert completion_calls[1]["candidates"][0]["model_id"] == "openai/gpt-oss-120b"
    assert completion_calls[1]["candidates"][0]["provider"] == "groq"
    assert any(
        item["model_id"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
        for item in completion_calls[1]["candidates"]
    )
    assert any(
        item["model_id"] == "qwen/qwen3-235b-a22b"
        for item in completion_calls[1]["candidates"]
    )
    assert provider.family == "groq-routed"


def test_story_provider_sends_program_template_to_concept_agent():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    provider.concepts(program_brief("decisiones-dificiles"))

    concept_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.concepts"
    ][0]
    contract = concept_call["input"]["program_contract"]
    assert any("dos opciones malas" in item for item in contract)
    assert any("pregunta final sin respuesta facil" in item for item in contract)


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


def test_independent_critic_normalizes_spanish_score_keys_and_constrains_schema():
    authority = SpanishScoreAuthority()
    critic = RoutedIndependentCritic(router(authority))

    result = critic.review(
        brief(),
        StoryConcept("concept_1", "Una logline suficientemente original.", "promesa", "hook", 0.9),
        (),
        StoryScript("Guion propio verificable.", 3, 1.2),
    )

    call = [args for tool, args in authority.calls if tool == "model.complete"][-1]
    score_schema = call["response_schema"]["properties"]["scores"]
    assert set(score_schema["required"]) == {
        "hook", "clarity", "conflict", "escalation", "agency",
        "coherence", "credibility", "originality", "retention",
        "payoff", "production_fit",
    }
    assert result.scores["hook"] == 8.5
    assert result.scores["retention"] == 7.7
    assert result.scores["production_fit"] == 7.5


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
    # Groq's gpt-oss-120b leads creative_primary regardless of qwen's health
    # (it isn't even reached) -> concepts() uses gpt-oss-120b -> critic's own
    # alias excludes that specific model and lands on its own first
    # remaining healthy candidate, kimi.
    assert critique_call["candidates"][0]["model_id"] == "moonshotai/kimi-k2"
    assert not any(
        item["model_id"] == "openai/gpt-oss-120b"
        for item in critique_call["candidates"]
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


def test_revise_reinjects_series_canon_so_a_revision_cannot_break_established_facts():
    """revise() used to send only scenes+revision, dropping the series canon —
    so a quality/duration revision could silently contradict established
    characters/facts. It must re-inject the canon cached from concepts()."""
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    series_brief = StoryBrief(
        story_id="owned-series-1",
        title="El caso del faro",
        premise="Ana retoma un caso que dejó abierto.",
        theme="verdad",
        target_duration_seconds=90,
        rights_mode="owned_original",
        source_uri="kronara://artifacts/owned-series-1",
        evidence_refs=("ev-owned",),
        series_context="CANON: Ana es detective; su hermano murió en el incendio del faro.",
    )
    provider.concepts(series_brief)
    blueprint = provider.blueprint(series_brief, StoryConcept("c1", "logline", "promise", "hook", 0.9))
    scenes = provider.scenes(series_brief, StoryConcept("c1", "logline", "promise", "hook", 0.9), blueprint)

    provider.revise(scenes, {"scene_index": 0})

    revise_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.revise"
    ][0]
    assert "hermano murió en el incendio" in revise_call["input"]["series_canon"]
    assert "canon" in revise_call["input"]["series_instruction"].casefold()


def test_revise_keeps_scenes_coherent_even_without_series_canon():
    """A standalone (non-series) revision still gets a coherence instruction so
    it doesn't drift characters/place/facts between scenes."""
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))
    provider.concepts(brief())  # no series_context
    blueprint = provider.blueprint(brief(), StoryConcept("c1", "logline", "promise", "hook", 0.9))
    scenes = provider.scenes(brief(), StoryConcept("c1", "logline", "promise", "hook", 0.9), blueprint)

    provider.revise(scenes, {"scene_index": 0})

    revise_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.revise"
    ][0]
    assert "coherentes" in revise_call["input"]["series_instruction"].casefold()


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


def reconstruction_brief():
    base = brief()
    return StoryBrief(
        story_id=base.story_id,
        title=base.title,
        premise=base.premise,
        theme=base.theme,
        target_duration_seconds=base.target_duration_seconds,
        rights_mode=base.rights_mode,
        source_uri=base.source_uri,
        evidence_refs=base.evidence_refs,
        source_case="Cuerpo real del caso.\n\n[UPDATE] apareció el responsable.",
    )


def test_reconstruction_mode_forwards_source_case_and_contract_to_writer():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    provider.concepts(reconstruction_brief())

    concept_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.concepts"
    ][0]
    assert "[UPDATE]" in concept_call["input"]["source_case"]
    contract = concept_call["input"]["reconstruction_contract"]
    assert any("RECONSTRUCCIÓN FIEL" in item for item in contract)
    assert any("ANONIMIZA" in item for item in contract)


def test_original_mode_omits_reconstruction_material():
    authority = FakeAuthority()
    provider = RoutedStoryProvider(router(authority))

    provider.concepts(brief())  # sin source_case -> modo original

    concept_call = [
        args for tool, args in authority.calls
        if tool == "model.complete" and args["task"] == "story.concepts"
    ][0]
    assert "source_case" not in concept_call["input"]
    assert "reconstruction_contract" not in concept_call["input"]
