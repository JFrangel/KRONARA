from __future__ import annotations

from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from kronara.agent_catalog import AgentCatalog
from kronara.llm import NarrativeConcept
from kronara.resource_root import resource_root
from kronara.trends import TrendSignal


class OriginalityViolation(RuntimeError):
    pass


class KnowledgeSearch(Protocol):
    def search(self, query: str, limit: int = 8) -> list[Any]: ...


class ConceptProvider(Protocol):
    def generate_concept(self, context: str) -> NarrativeConcept: ...


class NarrativeState(TypedDict, total=False):
    signals: list[dict[str, Any]]
    target_duration_seconds: int
    selected_signal: dict[str, Any]
    context_packet: str
    citations: list[str]
    concept: dict[str, Any]
    blueprint: dict[str, Any]


STAGES = (
    ("hook", 5),
    ("minimum_context", 10),
    ("first_incident", 10),
    ("escalation", 20),
    ("point_of_no_return", 10),
    ("investigation", 15),
    ("revelation", 10),
    ("climax", 10),
    ("consequences", 7),
    ("emotional_close", 3),
)


def _normalized(value: str) -> str:
    return " ".join("".join(character.lower() if character.isalnum() else " " for character in value).split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


class NarrativeWorkflow:
    def __init__(self, database: Path, knowledge: KnowledgeSearch, provider: ConceptProvider):
        self.database = Path(database)
        self.knowledge = knowledge
        self.provider = provider
        self._runtime_profiles = {}

    def _runtime_profiles_for(self, agent_id: str, config_root: Path | None = None) -> tuple[Any, Any]:
        if agent_id in self._runtime_profiles:
            return self._runtime_profiles[agent_id]
        root = config_root or resource_root() / "config"
        persona, narrative = AgentCatalog.load_runtime_profiles(
            agent_id,
            root / "agents",
            root / "personas",
        )
        self._runtime_profiles[agent_id] = (persona, narrative)
        return persona, narrative

    def _build(self, checkpointer: SqliteSaver):
        builder = StateGraph(NarrativeState)

        def select_opportunity(state: NarrativeState) -> dict[str, Any]:
            if not state.get("signals"):
                raise ValueError("at least one trend signal is required")
            selected = max(state["signals"], key=lambda item: float(item["velocity"]))
            return {"selected_signal": selected}

        def retrieve_context(state: NarrativeState) -> dict[str, Any]:
            selected = state["selected_signal"]
            results = self.knowledge.search(str(selected["theme_hint"]), limit=8)
            citations = [item.citation_uri for item in results]
            knowledge_lines = [f"- {item.title} [{item.citation_uri}]" for item in results]
            packet = "\n".join(
                [
                    "UNTRUSTED TREND SIGNAL (abstract pattern only):",
                    f"theme_hint: {selected['theme_hint']}",
                    f"source_ref: {selected['source_uri']}",
                    "OWNED EDITORIAL KNOWLEDGE:",
                    *knowledge_lines,
                    "Create a new premise; do not reuse wording, characters, or event sequence.",
                ]
            )
            return {"context_packet": packet, "citations": citations}

        def generate_concept(state: NarrativeState) -> dict[str, Any]:
            concept = self.provider.generate_concept(state["context_packet"])
            source_title = str(state["selected_signal"]["theme_hint"])
            if max(
                _similarity(concept.logline, source_title),
                _similarity(concept.originality_angle, source_title),
            ) >= 0.82:
                raise OriginalityViolation("concept is too similar to source signal")
            return {"concept": asdict(concept)}

        def create_blueprint(state: NarrativeState) -> dict[str, Any]:
            duration = int(state["target_duration_seconds"])
            allocated: list[dict[str, Any]] = []
            consumed = 0
            for index, (name, percentage) in enumerate(STAGES):
                seconds = duration - consumed if index == len(STAGES) - 1 else int(duration * percentage / 100)
                consumed += seconds
                allocated.append(
                    {
                        "position": index + 1,
                        "name": name,
                        "target_seconds": seconds,
                        "purpose": f"Advance {name.replace('_', ' ')} without resolving later stages.",
                    }
                )
            return {
                "blueprint": {
                    "schema": "NarrativeBlueprint@1",
                    "target_duration_seconds": duration,
                    "stages": allocated,
                }
            }

        builder.add_node("opportunity_intelligence", select_opportunity)
        builder.add_node("knowledge_retrieval", retrieve_context)
        builder.add_node("concept_architect", generate_concept)
        builder.add_node("narrative_planner", create_blueprint)
        builder.add_edge(START, "opportunity_intelligence")
        builder.add_edge("opportunity_intelligence", "knowledge_retrieval")
        builder.add_edge("knowledge_retrieval", "concept_architect")
        builder.add_edge("concept_architect", "narrative_planner")
        builder.add_edge("narrative_planner", END)
        return builder.compile(checkpointer=checkpointer)

    def run(
        self,
        episode_id: str,
        signals: list[TrendSignal],
        target_duration_seconds: int,
    ) -> NarrativeState:
        if target_duration_seconds < 30:
            raise ValueError("target duration must be at least 30 seconds")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        safe_signals = [
            {
                "source_id": signal.source_id,
                "source_uri": signal.source_uri,
                "theme_hint": signal.theme_hint,
                "velocity": signal.velocity,
                "engagement": signal.engagement,
                "rights_mode": signal.rights_mode,
            }
            for signal in signals
        ]
        with SqliteSaver.from_conn_string(str(self.database)) as checkpointer:
            graph = self._build(checkpointer)
            return graph.invoke(
                {
                    "signals": safe_signals,
                    "target_duration_seconds": target_duration_seconds,
                },
                {"configurable": {"thread_id": episode_id}},
            )

