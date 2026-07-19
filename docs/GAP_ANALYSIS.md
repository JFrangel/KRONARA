# Brechas y checklist de release v0.4

Fecha de auditoría: 2026-07-19.

## Evidencia de release

- [x] Gate final: 194 pruebas Python, 6 pruebas Node, pruebas/build Rust y build Vite aprobados.
- [x] Sidecar empaquetado: handshake y `operations.context` verificados.
- [x] Secret scan: `.env` no rastreado y sin coincidencias de claves reales.
- [x] `main` publicado y verificado contra `origin/main` en `265e8aa`.

## Cerrado en esta entrega

- [x] Contratos de operación, memoria, tools y aprendizaje con tests.
- [x] 24 agentes, personalidad y prompt stack estructurado.
- [x] Tool traces persistentes, redactadas y visibles en la UI.
- [x] Chat de operación con contexto, citas, intents y estado parcial honesto.
- [x] RAG v3 con FTS5, sqlite-vec, GraphRAG, RRF, deduplicación y golden español.
- [x] Motor de historia propia con Guardian, crítico independiente y cancelación.
- [x] Reddit Rust con OAuth, filtros y bodies descartados.
- [x] Bridge Tauri–Python autenticado con allowlist y entorno saneado.
- [x] Pausa global conservada por Rust.
- [x] Pausa global sincronizada que cancela cooperativamente runs activos y bloquea nuevos.
- [x] Conversación durable sin texto bruto de usuario o fuentes externas pegadas.

## Bloqueado o pendiente antes de producción pública

- [ ] Adaptador de LLM remoto gobernado por Rust para usar claves configuradas sin exponerlas a Python.
- [ ] Benchmark real y promoción de BGE/E5/reranker en corpus español.
- [ ] Síntesis Azure/Edge, Whisper y QC de audio.
- [ ] FFmpeg, assets autorizados y QC real de video vertical.
- [ ] Página Meta sandbox, publicación, reconciliación e importación de métricas.
- [ ] Experimentos de voz/contenido con tráfico real y muestra suficiente.
- [ ] Activación gradual de publicación `full_auto`.

## Prohibiciones comprobables

- [x] No shell arbitrario para agentes.
- [x] No secretos en trazas, intents o UI.
- [x] No bodies de Reddit persistidos por el observatorio.
- [x] No aprendizaje o fine-tuning desde historias externas sin derechos.
- [x] No promesa de viralidad ni causalidad con muestra insuficiente.
- [x] No publicación automática ante derechos, presupuesto, render o estado remoto ambiguo.
