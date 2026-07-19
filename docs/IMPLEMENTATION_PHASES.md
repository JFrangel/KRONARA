# Fases de implementación

## Completado en la foundation v0.2

- Repositorio y documentación objetivo.
- UI Svelte/Vite y pausa global.
- Autoridad Rust probada.
- Sidecar Python empaquetable y RPC autenticado.
- LangGraph con checkpoints SQLite.
- Guardian, replay, artifacts, RRF y model registry.
- Abstracciones Reddit, voz, media, Meta y aprendizaje.

## Siguientes verticales

1. Configurar credenciales Reddit de desarrollo en la autoridad Rust y ejecutar una prueba autorizada.
2. Ampliar el golden set narrativo y conectar aliases Qwen/Kimi reales.
3. Evaluar embeddings y reranker multilingües con corpus español.
4. Integrar Azure/Edge TTS y faster-whisper con QC real.
5. Construir FFmpeg builder Rust, assets y Reel 9:16.
6. Configurar una Página de prueba Meta, upload privado y reconciliación.
7. Importar métricas y ejecutar el primer experimento de voz.
8. Activar `full_auto` primero en sandbox y después en producción con límites.

Ninguna fase externa se considera terminada sin credenciales de prueba, evidencia remota y pruebas de fallo.

## Segundo vertical implementado

- Cliente OAuth Reddit y manejo explícito de rate limit.
- `TrendSignal` sin cuerpo de historia y RPC seguro de extracción.
- Índice FTS5 + sqlite-vec + grafo + RRF.
- Transporte OpenAI-compatible con JSON Schema.
- LangGraph señal → contexto citado → concepto → blueprint.
- Bloqueo determinista por similitud con la señal fuente.
