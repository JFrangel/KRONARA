# Brechas y checklist de release v0.5 → v0.6

Fecha de auditoría: 2026-07-19.

## Cerrado en v0.6 (ronda "cerebro")

- [x] Motor narrativo a nivel literario: oficio (mostrar-no-contar, sensorial, subtexto, ritmo), evaluador de prosa con gate duro, prompts creativos/crítico reescritos, corpus de craft. (`narrative_craft.py`, `tests/test_narrative_craft.py`)
- [x] Nemotron 3 **Ultra** (1M ctx) en el registro y en los allowlists de Rust; alias `critic` explícito. (`config/models/registry.v2.json`, `src-tauri/src/model_gateway.rs`)
- [x] **Memoria de grafo bitemporal** (valid-time + transaction-time) y **continuidad de series multi-parte**. (`graph_memory.py`, `series.py`)
- [x] **Voz real edge-tts** como herramienta de autoridad y **duración medida** que reemplaza `palabras÷2.5` en el QC. (`voice.py`, `src-tauri/src/voice.rs`)
- [x] **Scheduler** de parrilla + **AutonomyGuard** instanciado para runs desatendidos. (`schedule.py`)
- [x] Documentación de funcionalidades por función para el frontend. (`docs/FUNCIONALIDADES.md`)

## Integrado y verificado en vivo (ronda de integración)

- [x] **edge-tts en vivo**: síntesis real con timings por palabra y duración medida (`EdgeTtsVoiceProvider`); verificado (15 palabras, ~3.6 s en una frase de muestra). Test de integración skip-if-offline.
- [x] **Render de video real (FFmpeg)**: `render.py` produce un MP4 real (Reel 9:16 / master 16:9) con subtítulos quemados y QC por ffprobe; **verificado de punta a punta** (voz edge-tts → subtítulos → reel 1080×1920 con audio, QC aprobado).
- [x] **Embeddings reales (ONNX)**: `FastEmbedProvider` con `multilingual_minilm_384`; verificado que rankea semántica real (par relacionado por encima del no relacionado, coseno > 0.5), sin torch.
- [x] **Publicación gobernada**: `IdempotentReelsPublisher` (intent persistido, sin doble publicación) + herramienta Rust `publication.publish` con URL host-pinned y reconciliación por marcador.

Sigue pendiente (requiere credenciales/entorno del usuario): **publicación Meta Reels EN VIVO** (necesita una Página sandbox autorizada + token, y app review de Meta), pesos **BGE-M3 1024-dim** completos (opcional; el path ONNX de 384-dim ya funciona), red multi-cuenta (F4) y Kronara Pulse completo (F5).

---


## Evidencia de release

- [x] Gate final: 212 pruebas Python, 7 Node, 28 Rust, formato Rust, build Vite y sidecar aprobados.
- [x] Prueba integral: Reddit abstracto → RAG → modelos enrutados → historia propia → QC.
- [x] Secret scan: `.env` no rastreado y sin claves reales en diff/trazas.
- [ ] `main` publicado y verificado contra `origin/main`.

## Cerrado en esta entrega

- [x] Contratos de operación, memoria, tools y aprendizaje con tests.
- [x] 24 agentes, personalidad y prompt stack estructurado.
- [x] Tool traces persistentes, redactadas y visibles en la UI.
- [x] Chat de operación con contexto, citas, intents y estado parcial honesto.
- [x] RAG v3 con FTS5, sqlite-vec, GraphRAG, RRF, deduplicación y golden español.
- [x] Motor de historia propia con Guardian, crítico independiente y cancelación.
- [x] Reddit Rust con OAuth, filtros y bodies descartados.
- [x] Bridge Tauri–Python autenticado con allowlist y entorno saneado.
- [x] Subprotocolo de herramientas Rust con `reddit.list_signals`, `model.complete`, `model.health` y `meta.metrics.read`.
- [x] Vertical `content.run`: filtros, deduplicación, oportunidad abstracta y RAG citado sin cuerpos externos.
- [x] Qwen para creación, Hy3 para ángulos, Nemotron como fallback y Kimi como crítico independiente.
- [x] Control de duración ±10 %, originalidad y Guardian narrativo antes de persistir el artefacto.
- [x] Embeddings BGE-M3/reranker locales con degradación explícita y sin descarga desde Python.
- [x] Métricas Meta versionadas, análisis por cohortes e intervalos y promoción reversible de historias propias.
- [x] UI para ejecutar el vertical y observar modelos, RAG, resultado y herramientas utilizadas.
- [x] Pausa global conservada por Rust.
- [x] Pausa global sincronizada que cancela cooperativamente runs activos y bloquea nuevos.
- [x] Conversación durable sin texto bruto de usuario o fuentes externas pegadas.

## Bloqueado o pendiente antes de producción pública

- [ ] Instalar y ejecutar benchmark real de BGE-M3/reranker en el equipo de producción.
- [ ] Síntesis Azure/Edge, Whisper y QC de audio.
- [ ] FFmpeg, assets autorizados y QC real de video vertical.
- [ ] Página Meta sandbox, publicación y reconciliación idempotente (la importación de métricas ya está implementada).
- [ ] Experimentos de voz/contenido con tráfico real y muestra suficiente.
- [ ] Activación gradual de publicación `full_auto`.

## Prohibiciones comprobables

- [x] No shell arbitrario para agentes.
- [x] No secretos en trazas, intents o UI.
- [x] No bodies de Reddit persistidos por el observatorio.
- [x] No aprendizaje o fine-tuning desde historias externas sin derechos.
- [x] No promesa de viralidad ni causalidad con muestra insuficiente.
- [x] No publicación automática ante derechos, presupuesto, render o estado remoto ambiguo.
