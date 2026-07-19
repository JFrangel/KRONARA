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

## Tercer vertical implementado

- Runtime plan–act–critic–Guardian con presupuestos y revisiones locales.
- Selección mínima de habilidades versionadas.
- Allowlist de herramientas, anti-loop y circuit breaker.
- Contexto citado con límites de confianza e identificación de prompt injection.
- 19 manifiestos de agente con modelos, fallbacks, tools y límites.
- ADN narrativo modular, continuidad y rúbrica 80/110 con piso por dimensión.
- Golden set adversarial para copia, inyección, giro no sembrado, protagonista pasivo y final inválido.
- RPC seguro de capacidades y evaluación narrativa.

## Cuarto vertical implementado — investigación y evidencia

- `ResearchQuestion@1`, `ResearchPlan@1`, `SourceRecord@1`, `EvidenceMatrix@1` y `AnalyticalBrief@1` cerrados y versionados.
- Clasificación determinista de intención y riesgo, descomposición por focos, presupuesto de fuentes y condición de parada.
- Evidencia favorable y contraria, dependencia por familia o cita explícita, contradicciones, derechos, vigencia y cobertura.
- Separación estricta entre hechos soportados, cálculos, inferencias, hipótesis y recomendaciones.
- RPC autenticado `research.plan` y `research.evaluate`.
- Reddit oficial con `new`, `hot`, `top`, time filter, cache metadata y bloqueo `disabled_by_policy` predeterminado.

Pendiente para completar la fase 6: ejecutar conectores externos exclusivamente desde Rust, automatizar extracción estructurada de afirmaciones con evaluación golden y persistir replay/costo/artefactos de cada investigación.
