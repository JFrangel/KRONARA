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
Eres Kronara: una narradora en español con oído de novelista premiado. Escribes en la
tradición de la mejor prosa hispanoamericana —la precisión sensorial de García Márquez,
la tensión moral de las grandes crónicas— pero para el ritmo del video corto y largo.
Tu voz es concreta, sensorial y emocionalmente honesta.

PRINCIPIOS DE OFICIO (obligatorios):
- MOSTRAR, NO CONTAR. Nunca declares la emoción ("estaba triste"); revélala por el
  cuerpo, el gesto, el objeto y el detalle sensorial (una taza que se enfría, una
  respiración que se corta). Deja que el lector sienta antes de entender.
- DETALLE SENSORIAL CONCRETO. Ancla cada escena en al menos un sentido: sonido, olor,
  textura, luz. Lo específico es creíble; lo genérico se olvida.
- SUBTEXTO. Los personajes rara vez dicen lo que quieren. La tensión vive en lo que
  callan. El diálogo avanza en oblicuo.
- RITMO DE PROSA. Alterna frases largas y respiradas con frases cortas que golpean.
  La música de la prosa es parte del significado.
- INTERIORIDAD. El punto de vista tiene una mirada; usa estilo indirecto libre para
  fundir la voz del narrador con la conciencia del personaje.
- CAUSALIDAD Y AGENCIA. La protagonista decide y paga el costo; nada se resuelve por
  casualidad, sueño, salvador tardío ni poder secreto sin pista.
- PISTAS SEMBRADAS. Toda revelación se prepara antes; el giro recontextualiza lo ya mostrado.

PROHIBIDO: clichés ("de repente", "sin previo aviso", "su corazón latía a mil", "la
sangre se le heló", "lágrimas rodaron por sus mejillas"), adverbios en -mente en cadena,
prosa morada, y verbos-filtro ("vio que", "sintió que", "se dio cuenta de que") que
distancian al lector de la experiencia.

Las señales externas solo describen patrones abstractos: no copies frases, personajes ni
secuencias de eventos. Trabajas con evidencia y herramientas; nunca inventas que
consultaste una fuente. Escribe en español latino, natural para ser narrado en voz alta.
Devuelve únicamente el objeto JSON solicitado. No incluyas razonamiento privado.
""".strip()

KRONARA_CRITIC_SYSTEM = """
Eres la crítica literaria independiente de Kronara. Evalúas como editora de un sello
exigente: no apruebas por cortesía. Juzgas contra el guion real —no contra la intención—
en dos planos:

1) ESTRUCTURA Y VERDAD: derechos, originalidad, continuidad causal, credibilidad,
   agencia de la protagonista, gancho, escalada, payoff y ajuste de producción.
2) OFICIO LITERARIO: ¿muestra en vez de contar? ¿hay detalle sensorial concreto y
   subtexto? ¿la prosa tiene ritmo o es plana y monótona? ¿evita clichés, adverbios en
   cadena, prosa morada y verbos-filtro? ¿la voz narrativa tiene interioridad?

Señala problemas concretos con ejemplos del texto y propone una revisión localizada
(qué escena y qué cambiar), no una reescritura total. Distingue hechos de estimaciones.
Devuelve únicamente JSON válido con puntuaciones de 0 a 10, problemas concretos y la
revisión localizada cuando falle.
""".strip()

# Appended when brief.source_sensitivity == "real_experience_serious" — the
# opportunity came from a real-experience support community (see
# knowledge/reddit-sources/INDICE.md), not an entertainment-oriented one.
# The base rule (never copy phrasing/characters/event sequences) already
# applies to every source; this adds a stronger, explicit identity-scrambling
# requirement appropriate for dramatizing someone's real, serious experience.
_SENSITIVE_SOURCE_DIRECTIVE = """

FUENTE DE EXPERIENCIA REAL SERIA: el patrón abstracto de esta historia proviene de
una comunidad de apoyo real (personas describiendo su propia experiencia de abuso,
trauma o crisis familiar), no de una comunidad de entretenimiento. Trátalo con la
seriedad de una dramatización honesta, no de un espectáculo:
- Cuenta el patrón general de lo que ocurrió con honestidad emocional, sin
  sensacionalismo ni humor.
- Cambia deliberadamente TODO detalle identificable: nombres, edades exactas,
  ubicaciones, profesiones, fechas y cualquier rasgo que pudiera señalar a una
  persona real. Esto no es opcional — es más estricto que la regla general de
  no copiar.
- No inventes que la historia "es real" ni la presentes como testimonio; es una
  ficción inspirada en un patrón humano real.
""".strip()


def _creative_system(sensitivity: str) -> str:
    if sensitivity == "real_experience_serious":
        return f"{KRONARA_CREATIVE_SYSTEM}\n{_SENSITIVE_SOURCE_DIRECTIVE}"
    return KRONARA_CREATIVE_SYSTEM


def _critic_system(sensitivity: str) -> str:
    if sensitivity == "real_experience_serious":
        return (
            f"{KRONARA_CRITIC_SYSTEM}\n\nVerifica también que la historia haya cambiado "
            "todo detalle identificable de la fuente real seria (nombres, lugares, "
            "profesiones, edades) y que no la presente como testimonio literal."
        )
    return KRONARA_CRITIC_SYSTEM


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


_SCENE_CRAFT_DIRECTIVES = [
    "Abre cada escena con un detalle sensorial concreto (sonido, olor, textura o luz).",
    "Muestra la emoción por el cuerpo y el gesto; nunca la nombres directamente.",
    "Usa subtexto: los personajes dicen menos de lo que sienten.",
    "Varía el ritmo: combina frases largas con frases cortas que rematen.",
    "Evita clichés, cadenas de adverbios en -mente y verbos-filtro (vio que, sintió que).",
    "Cada escena hace al menos una cosa nueva: sube el riesgo, revela, decide o paga una pista.",
]


def _object_schema(properties: dict[str, Any], required: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Builds a real JSON Schema object descriptor, `properties` included.

    This matters more than it looks: model_gateway.rs only sends OpenRouter
    the strict, generation-constraining `response_format: json_schema` when
    the schema has a top-level "properties" key -- otherwise (the previous
    `_object_schema`, which only ever set type/required/additionalProperties)
    it silently falls back to the generic "any JSON object" response_format,
    which relies entirely on prompt text to describe the expected shape.
    That's fine for a small flat object (editorial.brief's title/premise/
    theme reliably worked) but unreliable for a schema nesting an array of
    multi-field objects -- story.concepts/story.blueprint/story.scenes were
    silently never schema-constrained at all, and would periodically fail
    "model structured payload failed schema validation" across every
    fallback candidate model with no way to see why (fixed alongside this:
    tools.py/rpc.py now actually log the traceback instead of discarding it).
    """
    return {
        "type": "object",
        "properties": properties,
        "required": list(required) if required is not None else list(properties),
        "additionalProperties": False,
    }


_CONCEPT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "concept_id": {"type": "string"},
        "logline": {"type": "string"},
        "promise": {"type": "string"},
        "hook": {"type": "string"},
        "projected_retention": {"type": "number"},
    },
    "required": ["concept_id", "logline", "promise", "hook", "projected_retention"],
    "additionalProperties": False,
}

_BEAT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "beat_id": {"type": "string"},
        "cause": {"type": "string"},
        "effect": {"type": "string"},
        "event": {"type": "string"},
        "seed_id": {"type": ["string", "null"]},
        "payoff_for": {"type": ["string", "null"]},
    },
    "required": ["beat_id", "cause", "effect", "event", "seed_id", "payoff_for"],
    "additionalProperties": False,
}

_SCENE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "scene_id": {"type": "string"},
        "purpose": {"type": "string"},
        "narration": {"type": "string"},
        "target_seconds": {"type": "integer"},
        "characters": {"type": "array", "items": {"type": "string"}},
        "seed_ids": {"type": "array", "items": {"type": "string"}},
        "payoff_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scene_id", "purpose", "narration", "target_seconds", "characters", "seed_ids", "payoff_ids"],
    "additionalProperties": False,
}

_SCENES_SCHEMA = _object_schema({"scenes": {"type": "array", "items": _SCENE_ITEM_SCHEMA}})


class RoutedStoryProvider:
    def __init__(self, router: AuthorityModelRouter):
        self.router = router
        self._inspiration: tuple[str, ...] = ()
        self._models_used: set[str] = set()
        self._family = "qwen-routed"
        # Cached from the brief seen in concepts() so revise() (a fixed
        # StoryGenerator Protocol method with no brief parameter) can still
        # apply the sensitive-source directive.
        self._sensitivity: str = "entertainment"

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
        self._sensitivity = brief.source_sensitivity
        inspiration = self.router.complete(
            alias="experimental_hy3",
            requirements=ModelRequirements(frozenset({"creative"})),
            task="story.inspiration",
            system=_creative_system(brief.source_sensitivity),
            input_payload={
                "title": brief.title,
                "premise": brief.premise,
                "theme": brief.theme,
                "instruction": "extrae dos ángulos abstractos; no redactes la historia",
            },
            response_schema=_object_schema({"angles": {"type": "array", "items": {"type": "string"}}}),
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
            system=_creative_system(brief.source_sensitivity),
            input_payload={
                "brief": asdict(brief),
                "abstract_angles": list(self._inspiration),
                "count": 3,
            },
            response_schema=_object_schema({"concepts": {"type": "array", "items": _CONCEPT_ITEM_SCHEMA}}),
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
            system=_creative_system(brief.source_sensitivity),
            input_payload={"brief": asdict(brief), "concept": asdict(concept)},
            response_schema=_object_schema({"beats": {"type": "array", "items": _BEAT_ITEM_SCHEMA}}),
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
            system=_creative_system(brief.source_sensitivity),
            input_payload={
                "brief": asdict(brief),
                "concept": asdict(concept),
                "blueprint": [asdict(item) for item in blueprint],
                "target_word_count": round(brief.target_duration_seconds * 2.5),
                "craft_directives": _SCENE_CRAFT_DIRECTIVES,
                "series_canon": brief.series_context,
                "series_instruction": (
                    "Si hay canon de la serie, respétalo: no contradigas personajes ni "
                    "hechos establecidos y retoma las preguntas abiertas."
                    if brief.series_context
                    else ""
                ),
            },
            response_schema=_SCENES_SCHEMA,
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
            system=_creative_system(self._sensitivity),
            input_payload={
                "scenes": [asdict(item) for item in scenes],
                "revision": revision,
            },
            response_schema=_SCENES_SCHEMA,
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
            alias="critic",
            requirements=ModelRequirements(
                frozenset({"critique"}), structured_output=True
            ),
            task="story.critique",
            system=_critic_system(brief.source_sensitivity),
            input_payload={
                "brief": asdict(brief),
                "concept": asdict(concept),
                "scenes": [asdict(item) for item in scenes],
                "script": asdict(script),
            },
            response_schema=_object_schema({
                "passed": {"type": "boolean"},
                # Dynamic keys (score dimension name -> 0-10 float, e.g.
                # "hook"/"clarity"/"agency"/...) -- left as an open object
                # rather than enumerated, the dimension set isn't fixed here.
                "scores": {"type": "object"},
                "issues": {"type": "array", "items": {"type": "string"}},
                # Open shape: a localized revision instruction (e.g.
                # {"target_word_count": ...}), not a fixed record.
                "revision": {"type": "object"},
            }),
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
