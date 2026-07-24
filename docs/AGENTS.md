# Catálogo de agentes v0.8

Kronara consolidó los 24 manifiestos originales en **3 super-agentes** (clase
Agente B), cableados como **nodos LangGraph reales** con checkpointing
(`content_pipeline.run_graph` sobre `langgraph_runtime.persistent_graph`). El
mapeo 24→3 vive en `agents.py` (`LEGACY_TO_SUPER`, `super_agent()`), y la vista
**Agentes** los muestra (`agents.overview`).

| Super-agente | Rol | Absorbe (legacy) |
|---|---|---|
| **estratega** | Decide, investiga, aprende, mide | executive_orchestrator, editorial_executive, opportunity_intelligence, research_executive, context_engineer, evidence_analyst, rag_curator, operations_chat, performance_scientist, evaluation_scientist, memory_curator |
| **guionista** | Escribe y se autocritica | concept_architect, narrative_planner, writer_room, hook_retention, automated_qc, rights_provenance, training_data_curator |
| **productor** | Guion → video publicado | visual_director, video_composer, audio_director, voice_director, packaging, distribution |

## Agentes de capacidad (v0.8)

Lógica de agente pura, sobre el guion/datos (no tocan la red); se enchufan a la
conexión de red (Postiz/nativo):

- **Packaging** (`social_agent.platform_packaging`): título/descripción/hashtags
  por plataforma desde el guion — RPC `social.packaging`.
- **Community** (`social_agent.draft_comment_reply`): redacta respuestas a
  comentarios ancladas al guion; honesto (`grounded=false`) si el guion no lo
  respalda — RPC `social.comment_reply`.
- **Kronara Pulse** (`pulse_agent`): a partir de métricas/muestras da qué
  funciona, qué cambiar, fórmulas de título y tendencias — RPC `pulse.analyze` /
  `pulse.trends`.

## Ganchos y estilo

El guionista abre como expediente documental (no "un usuario de Reddit"): la
biblioteca de ganchos (`config/hooks/hooks.v1.json` + `hooks_library.py`) se
inyecta como `hook_playbook` sin exponer el texto de los ejemplos (anti-eco). En
modo reconstrucción fiel, el estratega trae el hilo real (`reddit_thread.py`) y el
guionista lo reconstruye anonimizado (`brief.source_case`).

## Reglas no anulables

- El estratega guarda señales abstractas; en reconstrucción fiel trae el hilo real
  pero anonimiza (nunca publica identidades).
- El guionista no se autocertifica: la crítica usa otra familia de modelo cuando
  existe alternativa sana. Solo dominio público en Bíblico; aforismos originales
  en Frases.
- El productor solo solicita una intención de publicación; **el Node authority**
  (`vite.config.js`) valida publicación, idempotencia y estado remoto, y la
  gobernanza de autonomía (`policy.py`) decide cuándo se dispara.

Las herramientas son default-deny: un agente no invoca una tool fuera de su
allowlist, ni importa módulos, abre shell o lee secretos. La autoridad de red y
los secretos viven en el Node, no en el sidecar cognitivo.
