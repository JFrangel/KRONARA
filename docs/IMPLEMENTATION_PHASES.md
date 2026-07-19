# Fases de implementación v0.4

## Completado y probado localmente

1. Contratos versionados, SQLite, checkpoints, trazas y memorias.
2. Prompt stack, personalidad, 24 agentes y 35 habilidades.
3. Registro de modelos con aliases Qwen/Kimi/Groq/Nemotron/Hy3.
4. Herramientas observables, anti-loop y circuit breaker.
5. Chat operativo, contexto citado, intents administrativos y timeline UI.
6. Reddit Observatory, filtros, receipts y bloqueo por derechos.
7. RAG v3, índice persistente, GraphRAG, evaluación y candidatos de embeddings.
8. Reutilización segura de historias propias y motor narrativo completo.
9. Bridge Tauri–Python autenticado, pausa global Rust y cancelación cooperativa.

## Siguiente fase: primer Reel real

1. Implementar adaptador Rust de inferencia remota que use claves sin exponerlas al sidecar.
2. Integrar Azure/Edge TTS, Whisper y QC de pronunciación.
3. Implementar FFmpeg Rust sobre `MediaTimeline` y QC de video/subtítulos.
4. Configurar Página Meta sandbox, publicación idempotente e insights.
5. Ejecutar manual → supervised_auto → full_auto con límites diarios y rollback.

## Criterios de salida

- Las suites Python, Node, Rust y el empaquetado del sidecar pasan desde el tip de release.
- La UI muestra herramientas, evidencia y fallos sin secretos.
- Una historia propia completa se puede cancelar, reanudar o auditar.
- Reddit real continúa bloqueado sin autorización contractual.
- No se declara producción audiovisual o publicación real hasta demostrar evidencia remota en sandbox.
