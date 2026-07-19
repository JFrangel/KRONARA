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

1. Conectar credenciales Reddit de desarrollo y persistir señales reales.
2. Implementar proveedores LLM con structured outputs y golden set narrativo.
3. Añadir FTS5/sqlite-vec, embeddings y reranker evaluado en español.
4. Integrar Azure/Edge TTS y faster-whisper con QC real.
5. Construir FFmpeg builder Rust, assets y Reel 9:16.
6. Configurar una Página de prueba Meta, upload privado y reconciliación.
7. Importar métricas y ejecutar el primer experimento de voz.
8. Activar `full_auto` primero en sandbox y después en producción con límites.

Ninguna fase externa se considera terminada sin credenciales de prueba, evidencia remota y pruebas de fallo.

