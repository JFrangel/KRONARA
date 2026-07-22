# Kronara OS v0.6

Kronara es una fábrica editorial local-first para Windows. Su propósito es investigar oportunidades permitidas, crear historias originales, evaluar su calidad y aprender de resultados sin copiar fuentes ni ampliar sus propios permisos.

**Novedades v0.6 (cerebro):** motor narrativo a nivel literario (oficio: mostrar-no-contar, sensorial, subtexto, ritmo), Nemotron 3 **Ultra** (1M contexto) + alias `critic`, **memoria de grafo bitemporal** con continuidad de **series multi-parte**, **voz real (edge-tts)** que mide la **duración real** de la narración, y **scheduler + autonomía** para que los agentes trabajen solos. Contrato para el frontend en [`docs/FUNCIONALIDADES.md`](docs/FUNCIONALIDADES.md).

**Integración verificada en vivo:** narración real con edge-tts, **render de video FFmpeg** (Reel 9:16 con subtítulos quemados, QC aprobado de punta a punta), **embeddings semánticos reales** (fastembed ONNX, sin torch) y **publicación gobernada e idempotente** (la publicación en vivo requiere una Página Meta autorizada). Detalle en [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md).

## Estado real

| Capacidad | Estado | Evidencia principal |
|---|---|---|
| Chat operativo y trazas visibles | Implementado | `tests/test_operations_rpc.py` |
| 24 agentes y 35 habilidades | Implementado | `config/agents`, `config/skills/catalog.v1.json` |
| Vertical Reddit → historia propia | Implementado y trazable | `tests/test_production_content_vertical.py` |
| Historia propia con crítica, originalidad, duración y recuperación | Implementado | `tests/test_story_duration_qc.py` |
| RAG v3: FTS5, vectores, grafo, filtros y promoción reversible | Implementado | `tests/test_story_learning_pipeline.py` |
| Reddit OAuth oficial y filtros | Implementado; activación sujeta a credenciales y términos | `src-tauri/tests/reddit.rs` |
| Qwen, Kimi, Groq, Nemotron Super/**Ultra** y Hy3 | Inferencia gobernada por Rust con fallback; alias `critic` | `src-tauri/tests/model_gateway.rs` |
| Motor narrativo literario (oficio + rúbrica) | Implementado | `tests/test_narrative_craft.py` |
| Memoria de grafo bitemporal + series multi-parte | Implementado | `tests/test_graph_memory.py`, `tests/test_series.py` |
| Voz real (edge-tts) y **duración medida** | Herramienta de autoridad + medición; síntesis en vivo requiere binario edge-tts | `tests/test_voice_duration.py`, `src-tauri/src/voice.rs` |
| Scheduler + autonomía (agentes desatendidos) | Implementado | `tests/test_schedule.py` |
| BGE-M3 y reranker BGE | Carga local productiva; degradación explícita si faltan pesos | `tests/test_production_embeddings.py` |
| Métricas Meta y aprendizaje | Lectura versionada y promoción prudente implementadas | `tests/test_performance_learning.py` |
| Voz real y FFmpeg local | Integrado; el sidecar empaquetado debe reconstruirse | `docs/INTEGRATIONS.md`, `docs/BUGS_CONOCIDOS.md` |
| Whisper y publicación Meta Reels | Pendiente | `docs/INTEGRATIONS.md` |
| Fine-tuning automático | Bloqueado por diseño | `tests/test_story_reuse.py` |

`full_auto` es el modo previsto, pero no elimina compuertas: derechos, originalidad, presupuesto, credenciales, políticas, calidad de render y ambigüedad remota bloquean el avance. Kronara ya crea historias propias desde señales abstractas y puede generar/reproducir un Reel local; la primera publicación real en Facebook todavía requiere una Página sandbox autorizada, upload y reconciliación remota.

## Uso local

```powershell
npm.cmd install
npm.cmd test
npm.cmd run build

python -m pip install -e ".[dev]"
python -m pytest -q --basetemp=.test-tmp

cargo test --manifest-path src-tauri/Cargo.toml
```

Para empaquetar el sidecar:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-sidecar.ps1
```

Copie `.env.example` a `.env`; ese archivo no se versiona. No pegue claves en el chat, documentación ni commits.

## Arquitectura

```text
Svelte UI ── comandos Tauri ──> Rust authority
                                 │ secretos, red, pausa, efectos
                                 │ RPC autenticado, allowlist
                                 ▼
                           Python cognitive sidecar
                           agentes, RAG, memoria, Guardian
```

Rust crea un token de sesión, limpia el entorno heredado del sidecar y solo permite métodos cognitivos acotados. Python no recibe las claves del proveedor ni ejecuta shell o publicación. La UI muestra resúmenes y argumentos redactados, nunca razonamiento privado ni secretos.

## Documentación

- [Funcionalidades por función (para el frontend)](docs/FUNCIONALIDADES.md)
- [Proceso de generación de contenido, paso a paso](docs/PROCESO_GENERACION_CONTENIDO.md)
- [Bugs conocidos y estado real](docs/BUGS_CONOCIDOS.md)
- [Fases futuras](docs/roadmap/FASES-FUTURAS.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Runtime y modelos](docs/AGENT_RUNTIME.md)
- [Catálogo de agentes](docs/AGENTS.md)
- [Memoria y RAG](docs/MEMORY_AND_RAG.md)
- [Integraciones](docs/INTEGRATIONS.md)
- [Entorno](docs/ENVIRONMENT.md)
- [Fases y criterios](docs/IMPLEMENTATION_PHASES.md)
- [Brechas comprobables](docs/GAP_ANALYSIS.md)
- [ADR de autoridad Rust/Python](docs/adr/002-rust-python-authority.md)
- [Plan v0.4 con checks](docs/superpowers/plans/2026-07-19-kronara-v0.4-agent-operations-implementation.md)
- [Plan v0.5 con checks](docs/superpowers/plans/2026-07-19-kronara-v0.5-production-intelligence-implementation.md)
