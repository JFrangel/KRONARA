# Catálogo de agentes v0.4

Hay 24 manifiestos en `config/agents` y 35 habilidades versionadas en `config/skills/catalog.v1.json`. Una habilidad orienta el trabajo; no concede autoridad.

| Equipo | Agentes |
|---|---|
| Dirección | `executive_orchestrator`, `editorial_executive`, `context_engineer`, `operations_chat` |
| Oportunidad e investigación | `opportunity_intelligence`, `research_executive`, `evidence_analyst`, `rights_provenance` |
| Narrativa | `concept_architect`, `narrative_planner`, `writer_room`, `hook_retention`, `automated_qc` |
| Producción | `voice_director`, `visual_director`, `audio_director`, `video_composer`, `packaging`, `distribution` |
| Aprendizaje y conocimiento | `performance_scientist`, `memory_curator`, `rag_curator`, `evaluation_scientist`, `training_data_curator` |

## Reglas no anulables

- Opportunity Intelligence guarda señales abstractas, no bodies de Reddit.
- Rights and Provenance bloquea derechos insuficientes.
- Writer Room no se autocertifica: la crítica debe usar otra familia cuando exista alternativa sana.
- Distribution solo solicita una intención; Rust valida publicación, idempotencia y estado remoto.
- Training Data Curator solo acepta historias propias o licenciadas con evidencia.
- Memory Curator mantiene hipótesis rivales; no sobrescribe contradicciones.

Las herramientas son default-deny. El agente no puede invocar una tool que no esté en su manifest ni importar módulos, abrir shell o leer secretos.
