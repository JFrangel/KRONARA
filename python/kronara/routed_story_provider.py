from __future__ import annotations

from dataclasses import asdict
from typing import Any

from kronara.authority_client import AuthorityClient
from kronara.hooks_library import load_hooks
from kronara.model_registry_v2 import (
    ModelCapabilityRegistryV2,
    ModelRequirements,
)
from kronara.program_narrative import narrative_contract
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
Devuelve únicamente JSON válido. Dentro de `scores`, usa exactamente estas llaves
en inglés, aunque razones en español: hook, clarity, conflict, escalation, agency,
coherence, credibility, originality, retention, payoff, production_fit. Todas las
puntuaciones van de 0 a 10. Incluye problemas concretos y la revisión localizada
cuando falle.
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

_CONTENT_KIND_CONTRACTS = {
    "reflection": [
        "Es una REFLEXIÓN breve (30-60s), no una historia: una idea que reencuadra una preocupación cotidiana.",
        "Voz cercana y serena; una sola idea central desarrollada con imágenes concretas, sin trama ni personajes con nombre.",
        "Cierra con una vuelta que resignifique la apertura; nada de clichés de superación.",
    ],
    "scripture": [
        "Es una lectura BÍBLICA devocional breve. Usa SOLO texto de dominio público (Reina-Valera 1909); no cites versiones con derechos.",
        "Distingue el texto bíblico de la interpretación/dramatización; no afirmes como hecho lo que es lectura.",
        "Tono reverente y sobrio; una enseñanza central, aplicable, sin sensacionalismo.",
    ],
    "quote": [
        "Es un AFORISMO ORIGINAL (nunca una frase con derechos ajenos ni atribuida a otra persona real).",
        "Una sola sentencia memorable + un breve desarrollo que la sostenga (20-40s).",
        "Especificidad emocional; evita frases motivacionales gastadas.",
    ],
}


def _content_kind_contract(content_kind: str) -> list[str]:
    return _CONTENT_KIND_CONTRACTS.get(content_kind, [])


_RECONSTRUCTION_CONTRACT = [
    "Modo RECONSTRUCCIÓN FIEL: source_case es el caso REAL (cuerpo del hilo + bloques [UPDATE]/[SEGUIMIENTO DEL AUTOR]). Reconstruye ESOS hechos: respeta cronología, evidencias, giros y el desenlace real de las actualizaciones.",
    "NO inventes eventos, pruebas ni personajes que no estén en source_case; si el caso queda abierto, no cierres con un final fabricado.",
    "ANONIMIZA: cambia nombres, lugares, fechas exactas y detalles identificables (no copies frases textuales del original). El resultado debe ser irreconocible como la persona real pero fiel a los hechos.",
    "Mantén el tono documental; si el caso no es verificable, no afirmes que lo es (usa el fraseo de disclaimers del hook_playbook).",
]

_CONCEPT_AGENT_CONTRACT = [
    "Transforma la senal externa en una premisa original; no reutilices secuencia, identidad ni fraseo.",
    "Dale a la protagonista una decision activa en el gancho o en la promesa.",
    "Cada concepto debe prometer una revelacion preparada por pistas, no por sorpresa gratuita.",
    # Apertura documental (ver hook_playbook): reconstruimos un caso, no leemos Reddit.
    "El 'hook' abre como un expediente (evidencia, contradiccion, cuenta regresiva, dilema...), no anunciando 'un usuario de Reddit'; la procedencia va DESPUES, no en la primera frase.",
    "Elige el mecanismo de hook_playbook segun selection_rules y la naturaleza real de la historia; construye una apertura ORIGINAL con hechos concretos, sin copiar ni parafrasear de cerca ningun ejemplo.",
    "No repitas el mismo mecanismo de apertura del episodio anterior (hook_playbook.avoid_mechanisms) ni uses formulas gastadas ('no creeras lo que paso').",
]

_BLUEPRINT_AGENT_CONTRACT = [
    "Cada beat debe tener causa, efecto y costo visible para la protagonista.",
    "Marca que pista se siembra y que payoff paga; evita beats decorativos.",
    "Mantiene una progresion de riesgo: intimidad, amenaza, decision, consecuencia, revelacion.",
    "Incluye continuidad de temporada cuando el canon tenga preguntas abiertas.",
]

_SCENE_AGENT_CONTRACT = [
    *_SCENE_CRAFT_DIRECTIVES,
    "Preserva continuidad de temporada si existe canon: no cierres preguntas abiertas sin sembrarlas.",
    "Escribe pensando en produccion vertical: cada escena debe tener una imagen concreta posible.",
]

_REVISION_AGENT_CONTRACT = [
    "Corrige exactamente los fallos reportados por critica o duracion sin romper el blueprint.",
    "Si bajas duracion, compacta frases repetidas antes de borrar pistas o agencia.",
    "Si subes calidad, agrega acciones concretas, subtexto y detalles sensoriales medibles.",
]

_CRITIC_AGENT_CONTRACT = [
    "Si falla, identifica la fase real culpable: concepto, guion, critica, narracion o produccion.",
    "Devuelve problemas accionables: escena afectada, dimension fallida y cambio local pedido.",
    "No apruebes por promedio si hay un bloqueo de derechos, originalidad, agencia o produccion.",
]


_CRITIC_SCORE_DIMENSIONS = (
    "hook",
    "clarity",
    "conflict",
    "escalation",
    "agency",
    "coherence",
    "credibility",
    "originality",
    "retention",
    "payoff",
    "production_fit",
)

_CRITIC_SCORE_KEY_ALIASES = {
    "gancho": "hook",
    "claridad": "clarity",
    "conflicto": "conflict",
    "escalada": "escalation",
    "agencia": "agency",
    "coherencia": "coherence",
    "credibilidad": "credibility",
    "originalidad": "originality",
    "retencion": "retention",
    "retención": "retention",
    "pago": "payoff",
    "remate": "payoff",
    "ajuste_produccion": "production_fit",
    "ajuste_producción": "production_fit",
    "ajuste_de_produccion": "production_fit",
    "ajuste_de_producción": "production_fit",
    "ajuste de produccion": "production_fit",
    "ajuste de producción": "production_fit",
    "production fit": "production_fit",
}


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
        "purpose": {"type": "string", "description": "Función dramática de la escena en una frase."},
        "narration": {
            "type": "string",
            "minLength": 60,
            "description": (
                "OBLIGATORIO y NUNCA vacío: el texto narrativo COMPLETO en español "
                "que se leerá en voz alta en esta escena — varias frases de prosa "
                "sensorial y concreta (no un resumen, no viñetas, no markdown), "
                "listo para narración. Escribe el guion real de la escena aquí."
            ),
        },
        "target_seconds": {"type": "integer"},
        "characters": {"type": "array", "items": {"type": "string"}},
        "seed_ids": {"type": "array", "items": {"type": "string"}},
        "payoff_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scene_id", "purpose", "narration", "target_seconds", "characters", "seed_ids", "payoff_ids"],
    "additionalProperties": False,
}

_SCENES_SCHEMA = _object_schema({
    "scenes": {"type": "array", "items": _SCENE_ITEM_SCHEMA, "minItems": 1},
})


def _scene_max_tokens(word_count: int) -> int:
    """Size max_tokens off the same word-count math the duration QC already
    uses, scaling UP for long-form content instead of a flat cap regardless
    of target length -- while staying generous enough for real output.

    History, calibrated against real runs rather than guessed, twice over:

    1. An initial flat 4096 (every request, any length) made OpenRouter's
       paid candidates (qwen/kimi) reject pre-flight with 402 on a near-
       empty credit balance.
    2. A first proportional formula (1.6 tokens/word + 768, floor 1536)
       fixed that, but a real free-tier candidate (nvidia/nemotron:free)
       then truncated mid-JSON ("model returned invalid structured
       content") -- turned out to be the model narrating its own visible
       chain-of-thought ("We need to produce a JSON object... let's count
       words...") instead of answering directly, burning the whole budget
       before ever reaching the JSON. Fixed separately in model_gateway.rs
       (`reasoning: {enabled: false}`).
    3. With reasoning suppressed, the SAME real model then wrote genuinely
       elaborate, literary beats/scenes (the system prompt asks for
       sensorial, "show don't tell" prose throughout, and free models don't
       hold back) and hit a real, lower floor (1536) truncating mid-string.

    Conclusion: at the account's current near-zero credit balance, qwen/kimi
    are unaffordable at ANY reasonable content-completing budget anyway
    (their own 402s report affording only ~600-1150 tokens) -- so there is
    no longer a real trade-off to protect by staying small. Sized generously
    for the free models that actually respond, capped at Rust's own hard
    ceiling (model_gateway.rs allows up to 8192).
    """
    return max(4096, min(8192, round(word_count * 3.0) + 1536))


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
        self._program_id: str | None = None
        # Stashed from the brief so revise() (a Protocol method with no brief
        # param) can re-inject the series canon it would otherwise drop -- a
        # quality/duration revision must not silently contradict established
        # characters/facts.
        self._series_context: str = ""
        # Modo reconstrucción fiel: el caso real (cuerpo + actualizaciones) que el
        # guionista reconstruye anonimizado. "" = modo original (inventar desde la
        # señal abstracta). Se cachea para las etapas guion/revisión.
        self._source_case: str = ""

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
        self._program_id = brief.program_id
        self._series_context = brief.series_context or ""
        self._source_case = brief.source_case or ""
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
                "agent_contract": _CONCEPT_AGENT_CONTRACT,
                "program_contract": narrative_contract(brief.program_id),
                "hook_playbook": load_hooks().playbook(program_id=brief.program_id),
                **(
                    {"source_case": self._source_case, "reconstruction_contract": _RECONSTRUCTION_CONTRACT}
                    if self._source_case
                    else {}
                ),
                **(
                    {"content_kind": brief.content_kind, "content_kind_contract": _content_kind_contract(brief.content_kind)}
                    if brief.content_kind and brief.content_kind != "narrative_story"
                    else {}
                ),
            },
            response_schema=_object_schema({
                "concepts": {"type": "array", "items": _CONCEPT_ITEM_SCHEMA, "minItems": 3, "maxItems": 3},
            }),
            max_tokens=1024,
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
        # Con response_format json_object (Groq no soporta json_schema strict)
        # el modelo NO queda forzado a minItems/maxItems=3, así que puede
        # devolver más o menos de 3. Toleramos: usamos hasta 3 (el pipeline
        # elige el mejor) y solo fallamos si no vino ninguno.
        if not concepts:
            raise ValueError("routed provider returned no concepts")
        return concepts[:3]

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
            input_payload={
                "brief": asdict(brief),
                "concept": asdict(concept),
                "agent_contract": _BLUEPRINT_AGENT_CONTRACT,
                "program_contract": narrative_contract(brief.program_id),
            },
            response_schema=_object_schema({
                "beats": {"type": "array", "items": _BEAT_ITEM_SCHEMA, "minItems": 6},
            }),
            # Raised from 1536 after a real run truncated mid-beat-6: with
            # model reasoning suppressed (see model_gateway.rs), a real free
            # candidate still wrote genuinely elaborate, literary
            # cause/effect/event/payoff_for prose per beat (the system
            # prompt asks for sensorial "show don't tell" writing
            # throughout) -- 6 beats of that easily exceeds 1536 tokens.
            max_tokens=6144,
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
        # json_object no fuerza minItems=6 (Groq no soporta json_schema strict),
        # así que toleramos menos: con >=3 beats hay estructura narrativa
        # suficiente para producir el video; solo fallamos si vinieron muy pocos.
        if len(beats) < 3:
            raise ValueError("routed blueprint returned too few causal beats")
        return beats

    def scenes(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        blueprint: tuple[CausalBeat, ...],
    ) -> tuple[StoryScene, ...]:
        target_word_count = round(brief.target_duration_seconds * 2.5)
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
                "target_word_count": target_word_count,
                "craft_directives": _SCENE_CRAFT_DIRECTIVES,
                "agent_contract": _SCENE_AGENT_CONTRACT,
                "program_contract": narrative_contract(brief.program_id),
                "series_canon": brief.series_context,
                "series_instruction": (
                    "Si hay canon de la serie, respétalo: no contradigas personajes ni "
                    "hechos establecidos y retoma las preguntas abiertas."
                    if brief.series_context
                    else ""
                ),
                **(
                    {"source_case": brief.source_case, "reconstruction_contract": _RECONSTRUCTION_CONTRACT}
                    if brief.source_case
                    else {}
                ),
                **(
                    {"content_kind": brief.content_kind, "content_kind_contract": _content_kind_contract(brief.content_kind)}
                    if brief.content_kind and brief.content_kind != "narrative_story"
                    else {}
                ),
            },
            response_schema=_SCENES_SCHEMA,
            max_tokens=_scene_max_tokens(target_word_count),
        )
        self._remember_model()
        return self._scenes(payload)

    def revise(
        self, scenes: tuple[StoryScene, ...], revision: dict[str, Any]
    ) -> tuple[StoryScene, ...]:
        target_word_count = revision.get("target_word_count")
        if not isinstance(target_word_count, (int, float)):
            target_word_count = sum(len(item.narration.split()) for item in scenes)
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
                "agent_contract": _REVISION_AGENT_CONTRACT,
                "program_contract": narrative_contract(self._program_id),
                # Re-inject the series canon the initial draft honored, so this
                # revision can't contradict established characters/facts.
                "series_canon": self._series_context,
                "series_instruction": (
                    "Conserva el canon de la serie: no contradigas personajes ni "
                    "hechos ya establecidos y mantén coherentes las escenas entre sí."
                    if self._series_context
                    else "Mantén las escenas coherentes entre sí: mismos personajes, "
                    "lugar y hechos que ya quedaron establecidos."
                ),
            },
            response_schema=_SCENES_SCHEMA,
            max_tokens=_scene_max_tokens(int(target_word_count)),
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
                "agent_contract": _CRITIC_AGENT_CONTRACT,
                "program_contract": narrative_contract(brief.program_id),
            },
            response_schema=_object_schema({
                "passed": {"type": "boolean"},
                "scores": {
                    "type": "object",
                    "properties": {
                        key: {"type": "number", "minimum": 0, "maximum": 10}
                        for key in _CRITIC_SCORE_DIMENSIONS
                    },
                    "required": list(_CRITIC_SCORE_DIMENSIONS),
                    "additionalProperties": False,
                },
                "issues": {"type": "array", "items": {"type": "string"}},
                # Open shape: a localized revision instruction (e.g.
                # {"target_word_count": ...}), not a fixed record.
                "revision": {"type": "object"},
            }),
            exclude_models=(self.generator.models_used if self.generator else frozenset()),
            max_tokens=1536,
        )
        self._family = _model_family(self.router.last_model_id)
        scores = self._normalized_scores(dict(payload["scores"]))
        return StoryCritique(
            passed=bool(payload["passed"]),
            scores=scores,
            issues=tuple(str(item) for item in payload.get("issues", ())),
            revision=dict(payload.get("revision", {})),
        )

    @staticmethod
    def _normalized_scores(raw_scores: dict[str, Any]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for key, value in raw_scores.items():
            normalized_key = _CRITIC_SCORE_KEY_ALIASES.get(str(key).strip().casefold(), str(key))
            scores[normalized_key] = float(value)
        return scores


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
