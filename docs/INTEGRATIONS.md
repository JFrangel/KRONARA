# Integraciones y estado de producción

| Integración | Estado | Límite actual |
|---|---|---|
| Reddit Data API | Integrada en `content.run` mediante Rust | Requiere OAuth oficial y referencia contractual; bodies descartados |
| Qwen/Kimi/Nemotron/Hy3 | Gateway Rust e inferencia estructurada | Depende de credenciales, salud y vigencia del modelo; Hy3 free expira 2026-07-21 |
| BGE-M3 y reranker BGE | Carga local productiva | Degrada de forma visible si no están instalados/evaluados |
| Azure Speech / Edge TTS | Planificado/experimental | No hay síntesis productiva conectada al pipeline |
| faster-whisper | Planificado | Sin alineación ni QC de audio reales |
| FFmpeg | Planificado | Timeline declarativa sin render Rust de producción |
| Meta/Facebook Reels | Insights versionados mediante Rust | Sin Page sandbox, upload ni reconciliación de publicación |

## Reddit

El adaptador usa OAuth y endpoints oficiales con validación de subreddit, orden, ventana temporal, rate limit y recibo. `TrendSignal` conserva título reducido, engagement, velocidad, saturación y URI; el cuerpo de la historia se descarta. La política de originalidad prohíbe convertir señales o historias externas en guiones plantilla, RAG creativo o entrenamiento.

## Modelos

Los aliases no se incrustan en prompts. El router considera capacidad, calidad medida, latencia, costo, privacidad y salud. Groq, Qwen, Kimi, Nemotron y Hy3 están registrados; la disponibilidad real se comprueba antes de uso. Un modelo retirado o sin health check se degrada o bloquea; nunca se declara saludable por nombre.

## Facebook Reels

El adaptador de métricas usa `graph.facebook.com`, una versión fijada explícitamente, token de Página custodiado por Rust y un mapeo normalizado de reproducciones, finalizaciones, tiempo medio, alcance y compartidos. El criterio de éxito final sigue siendo una publicación única, original y recuperable. Falta: proveer assets permitidos, generar audio, validar/reproducir un render 9:16, usar una Página sandbox y reconciliar uploads ambiguos. Hasta entonces no se debe afirmar que Kronara publica Reels reales.
