from __future__ import annotations

from dataclasses import asdict
from typing import Any

from kronara.authority_client import AuthorityClient
from kronara.model_registry_v2 import (
    ModelCapabilityRegistryV2,
    ModelRequirements,
)
from kronara.story_engine import (
    CausalBeat,
    StoryBrief,
    StoryConcept,
    StoryCritique,
    StoryScene,
    StoryScript,
)


KRONARA_CREATIVE_SYSTEM = """
Eres Kronara, una directora editorial investigativa, creativa, analítica, divertida y
perfeccionista. Trabajas con evidencia y herramientas; nunca inventas que consultaste
una fuente. Las señales externas solo describen patrones abstractos: no copies frases,
personajes ni secuencias de eventos. Crea historias originales en español con una
protagonista activa, causalidad clara, tensión creciente, pistas sembradas y payoff.
Devuelve únicamente el objeto JSON solicitado. No incluyas razonamiento privado.
""".strip()

KRONARA_CRITIC_SYSTEM = """
Eres la crítica independiente de Kronara. Evalúa contra el guion real, derechos,
originalidad, continuidad, credibilidad, retención y ajuste de producción. Distingue
hechos de estimaciones y no apruebes por cortesía. Devuelve únicamente JSON válido con
puntuaciones de 0 a 10, problemas concretos y una revisión localizada cuando falle.
""".strip()


class AuthorityModelRouter:
    def __init__(
        self,
        *,
        authority: AuthorityClient,
        registry: ModelCapabilityRegistryV2,
    ):
        self.authority = authority
        self.registry = registry
        self.last_model_id = ""

    def complete(
        self,
        *,
        alias: str,
        requirements: ModelRequirements,
        task: str,
        system: str,
        input_payload: dict[str, Any],
        response_schema: dict[str, Any],
        max_tokens: int = 4096,
        exclude_models: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        health_payload = self.authority.invoke("model.health", {})
        health = {
            str(model_id): str(state)
            for model_id, state in dict(health_payload.get("models", {})).items()
        }
        route = self.registry.resolve(alias, requirements, health)
        model_ids = (route.primary, *route.fallbacks)
        candidates = [
            {
                "provider": self.registry.provider_for(model_id),
                "model_id": model_id,
            }
            for model_id in model_ids
            if model_id not in exclude_models
        ]
        if not candidates:
            raise ValueError("no independent model remains after exclusions")
        result = self.authority.invoke(
            "model.complete",
            {
                "task": task,
                "candidates": candidates,
                "system": system,
                "input": input_payload,
                "response_schema": response_schema,
                "max_tokens": max_tokens,
            },
        )
        payload = result.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("model completion payload must be an object")
        self.last_model_id = str(result.get("model") or candidates[0]["model_id"])
        return dict(payload)


def _object_schema(required: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(required),
        "additionalProperties": False,
    }


class RoutedStoryProvider:
    def __init__(self, router: AuthorityModelRouter):
        self.router = router
        self._inspiration: tuple[str, ...] = ()
        self._models_used: set[str] = set()
        self._family = "qwen-routed"

    @property
    def family(self) -> str:
        return self._family

    @property
    def models_used(self) -> frozenset[str]:
        return frozenset(self._models_used)

    def _remember_model(self) -> None:
        model_id = self.router.last_model_id
        if model_id:
            self._models_used.add(model_id)
            self._family = _model_family(model_id)

    def concepts(self, brief: StoryBrief) -> tuple[StoryConcept, ...]:
        inspiration = self.router.complete(
            alias="experimental_hy3",
            requirements=ModelRequirements(frozenset({"creative"})),
            task="story.inspiration",
            system=KRONARA_CREATIVE_SYSTEM,
            input_payload={
                "title": brief.title,
                "premise": brief.premise,
                "theme": brief.theme,
                "instruction": "extrae dos ángulos abstractos; no redactes la historia",
            },
            response_schema=_object_schema(("angles",)),
            max_tokens=512,
        )
        self._remember_model()
        self._inspiration = tuple(str(item) for item in inspiration.get("angles", ()))[:4]
        payload = self.router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(
                frozenset({"creative"}), structured_output=True
            ),
            task="story.concepts",
            system=KRONARA_CREATIVE_SYSTEM,
            input_payload={
                "brief": asdict(brief),
                "abstract_angles": list(self._inspiration),
                "count": 3,
            },
            response_schema=_object_schema(("concepts",)),
        )
        self._remember_model()
        concepts = tuple(
            StoryConcept(
                concept_id=str(item["concept_id"]),
                logline=str(item["logline"]),
                promise=str(item["promise"]),
                hook=str(item["hook"]),
                projected_retention=float(item["projected_retention"]),
            )
            for item in payload.get("concepts", ())
        )
        if len(concepts) != 3:
            raise ValueError("routed provider must return exactly three concepts")
        return concepts

    def blueprint(
        self, brief: StoryBrief, concept: StoryConcept
    ) -> tuple[CausalBeat, ...]:
        payload = self.router.complete(
            alias="planning_primary",
            requirements=ModelRequirements(
                frozenset({"planning"}), structured_output=True
            ),
            task="story.blueprint",
            system=KRONARA_CREATIVE_SYSTEM,
            input_payload={"brief": asdict(brief), "concept": asdict(concept)},
            response_schema=_object_schema(("beats",)),
        )
        self._remember_model()
        beats = tuple(
            CausalBeat(
                beat_id=str(item["beat_id"]),
                cause=str(item["cause"]),
                effect=str(item["effect"]),
                event=str(item["event"]),
                seed_id=str(item["seed_id"]) if item.get("seed_id") else None,
                payoff_for=str(item["payoff_for"]) if item.get("payoff_for") else None,
            )
            for item in payload.get("beats", ())
        )
        if len(beats) < 6:
            raise ValueError("routed blueprint requires at least six causal beats")
        return beats

    def scenes(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        blueprint: tuple[CausalBeat, ...],
    ) -> tuple[StoryScene, ...]:
        payload = self.router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(
                frozenset({"creative"}), structured_output=True
            ),
            task="story.scenes",
            system=KRONARA_CREATIVE_SYSTEM,
            input_payload={
                "brief": asdict(brief),
                "concept": asdict(concept),
                "blueprint": [asdict(item) for item in blueprint],
                "target_word_count": round(brief.target_duration_seconds * 2.5),
            },
            response_schema=_object_schema(("scenes",)),
        )
        self._remember_model()
        return self._scenes(payload)

    def revise(
        self, scenes: tuple[StoryScene, ...], revision: dict[str, Any]
    ) -> tuple[StoryScene, ...]:
        payload = self.router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(
                frozenset({"creative"}), structured_output=True
            ),
            task="story.revise",
            system=KRONARA_CREATIVE_SYSTEM,
            input_payload={
                "scenes": [asdict(item) for item in scenes],
                "revision": revision,
            },
            response_schema=_object_schema(("scenes",)),
        )
        self._remember_model()
        return self._scenes(payload)

    @staticmethod
    def _scenes(payload: dict[str, Any]) -> tuple[StoryScene, ...]:
        scenes = tuple(
            StoryScene(
                scene_id=str(item["scene_id"]),
                purpose=str(item["purpose"]),
                narration=str(item["narration"]),
                target_seconds=int(item["target_seconds"]),
                characters=tuple(str(value) for value in item.get("characters", ())),
                seed_ids=tuple(str(value) for value in item.get("seed_ids", ())),
                payoff_ids=tuple(str(value) for value in item.get("payoff_ids", ())),
            )
            for item in payload.get("scenes", ())
        )
        if not scenes:
            raise ValueError("routed provider returned no scenes")
        return scenes


class RoutedIndependentCritic:
    def __init__(
        self,
        router: AuthorityModelRouter,
        *,
        generator: RoutedStoryProvider | None = None,
    ):
        self.router = router
        self.generator = generator
        self._family = "kimi-routed"

    @property
    def family(self) -> str:
        return self._family

    def review(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        scenes: tuple[StoryScene, ...],
        script: StoryScript,
    ) -> StoryCritique:
        payload = self.router.complete(
            alias="long_context_primary",
            requirements=ModelRequirements(
                frozenset({"critique"}), structured_output=True
            ),
            task="story.critique",
            system=KRONARA_CRITIC_SYSTEM,
            input_payload={
                "brief": asdict(brief),
                "concept": asdict(concept),
                "scenes": [asdict(item) for item in scenes],
                "script": asdict(script),
            },
            response_schema=_object_schema(("passed", "scores", "issues", "revision")),
            exclude_models=(self.generator.models_used if self.generator else frozenset()),
        )
        self._family = _model_family(self.router.last_model_id)
        scores = {str(key): float(value) for key, value in dict(payload["scores"]).items()}
        return StoryCritique(
            passed=bool(payload["passed"]),
            scores=scores,
            issues=tuple(str(item) for item in payload.get("issues", ())),
            revision=dict(payload.get("revision", {})),
        )


def _model_family(model_id: str) -> str:
    normalized = model_id.casefold()
    if "qwen" in normalized:
        return "qwen-routed"
    if "kimi" in normalized or "moonshot" in normalized:
        return "kimi-routed"
    if "nemotron" in normalized:
        return "nemotron-routed"
    if "hy3" in normalized or "tencent" in normalized:
        return "hy3-routed"
    return "groq-routed"
