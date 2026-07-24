"""The three super-agents (Kronara v0.8, Fase 3).

Kronara used to attribute work to 24 fine-grained agent ids. v0.8 collapses them
into three capable "Agente B"-class super-agents, each owning a coherent slice of
the pipeline:

- **estratega**  -- decides, researches, remembers, learns (opportunity,
  editorial, research, RAG, evidence, context, memory, performance, evaluation,
  operations chat).
- **guionista**  -- writes and critiques the story (concept, blueprint, draft,
  hook, QC/originality, rights, training-data curation).
- **productor**  -- turns a script into a published video (visuals, audio, voice,
  packaging, distribution).

This module is the single source of truth for the 24->3 mapping. Attribution
choke-points (``_agent``/``_agent_for_tool``/``_agent_log`` and the few direct
``agent_id=`` sites) route every legacy id through :func:`super_agent`, so a
real run only ever emits these three ids -- no call site hardcodes a super-agent
name of its own.
"""

from __future__ import annotations

ESTRATEGA = "estratega"
GUIONISTA = "guionista"
PRODUCTOR = "productor"

SUPER_AGENTS: tuple[str, ...] = (ESTRATEGA, GUIONISTA, PRODUCTOR)

# Every legacy agent id -> its super-agent. Keep exhaustive: a legacy id missing
# here would leak through super_agent() unchanged and show up in the UI as a
# fourth "agent", which the Agentes view / tests would (correctly) flag.
LEGACY_TO_SUPER: dict[str, str] = {
    # estratega
    "executive_orchestrator": ESTRATEGA,
    "editorial_executive": ESTRATEGA,
    "opportunity_intelligence": ESTRATEGA,
    "research_executive": ESTRATEGA,
    "context_engineer": ESTRATEGA,
    "evidence_analyst": ESTRATEGA,
    "rag_curator": ESTRATEGA,
    "operations_chat": ESTRATEGA,
    "performance_scientist": ESTRATEGA,
    "evaluation_scientist": ESTRATEGA,
    "memory_curator": ESTRATEGA,
    # guionista
    "concept_architect": GUIONISTA,
    "narrative_planner": GUIONISTA,
    "writer_room": GUIONISTA,
    "hook_retention": GUIONISTA,
    "automated_qc": GUIONISTA,
    "rights_provenance": GUIONISTA,
    "training_data_curator": GUIONISTA,
    # productor
    "visual_director": PRODUCTOR,
    "video_composer": PRODUCTOR,
    "audio_director": PRODUCTOR,
    "voice_director": PRODUCTOR,
    "packaging": PRODUCTOR,
    "distribution": PRODUCTOR,
}


# Rich metadata for the Agentes view / agents.overview RPC. The 24 legacy
# configs still exist (code loads some by name), but these three are the surface
# a run actually emits and the user sees.
SUPER_AGENT_PROFILES: tuple[dict, ...] = (
    {
        "id": ESTRATEGA,
        "name": "Estratega",
        "role": "Decide, investiga, recuerda y aprende",
        "description": (
            "Elige la oportunidad, hace la investigación y el RAG, arma el brief "
            "editorial y gestiona memoria, rendimiento y evaluación. Es el que "
            "responde el chat de operación."
        ),
        "capabilities": (
            "Oportunidad y señales de Reddit",
            "RAG e investigación",
            "Brief editorial original",
            "Memoria corto/largo plazo",
            "Métricas, rendimiento y evaluación",
        ),
    },
    {
        "id": GUIONISTA,
        "name": "Guionista",
        "role": "Escribe y critica la historia",
        "description": (
            "Concepto, blueprint causal, guion por escenas, gancho/retención y "
            "QC/originalidad, cuidando derechos. Escribe y se auto-critica hasta "
            "pasar la calidad."
        ),
        "capabilities": (
            "Concepto y blueprint causal",
            "Guion por escenas",
            "Gancho y retención",
            "QC de calidad y originalidad",
            "Derechos y procedencia",
        ),
    },
    {
        "id": PRODUCTOR,
        "name": "Productor",
        "role": "Convierte el guion en video publicado",
        "description": (
            "Estilo visual, imágenes por escena con consistencia de personajes, "
            "voz clonada, música/SFX, composición y render, empaquetado y "
            "distribución."
        ),
        "capabilities": (
            "Dirección visual y estilos",
            "Voz clonada (VoiceBox)",
            "Música y SFX",
            "Composición y render",
            "Empaquetado y distribución",
        ),
    },
)


def super_agent_overview() -> list[dict]:
    """The 3 super-agents with the legacy agent ids each one absorbs -- the data
    behind the Agentes view and the agents.overview RPC (makes the 24->3
    consolidation visible)."""
    absorbs: dict[str, list[str]] = {name: [] for name in SUPER_AGENTS}
    for legacy, sup in LEGACY_TO_SUPER.items():
        absorbs[sup].append(legacy)
    return [
        {
            **profile,
            "capabilities": list(profile["capabilities"]),
            "absorbs": sorted(absorbs[profile["id"]]),
        }
        for profile in SUPER_AGENT_PROFILES
    ]


def super_agent(agent_id: str) -> str:
    """Map any agent id to its super-agent. A value that is already a
    super-agent (or an unknown id) passes through unchanged, so this is safe to
    apply idempotently at every attribution choke-point."""
    if agent_id in SUPER_AGENTS:
        return agent_id
    return LEGACY_TO_SUPER.get(agent_id, agent_id)
