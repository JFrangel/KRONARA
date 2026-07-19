# Integraciones y estado de producción

| Integración | Estado | Límite actual |
|---|---|---|
| Reddit Data API | Adaptador Rust implementado | Desactivado hasta OAuth oficial y referencia contractual; bodies descartados |
| Model registry | Implementado | Registro y health routing, no inferencia remota gobernada desde el chat todavía |
| BGE-M3, E5 y reranker BGE | Candidatos configurados | No promocionados sin evaluación local congelada |
| Azure Speech / Edge TTS | Planificado/experimental | No hay síntesis productiva conectada al pipeline |
| faster-whisper | Planificado | Sin alineación ni QC de audio reales |
| FFmpeg | Planificado | Timeline declarativa sin render Rust de producción |
| Meta/Facebook Reels | Abstracción y pruebas unitarias | Sin Page sandbox, upload ni insights remotos |

## Reddit

El adaptador usa OAuth y endpoints oficiales con validación de subreddit, orden, ventana temporal, rate limit y recibo. `TrendSignal` conserva título reducido, engagement, velocidad, saturación y URI; el cuerpo de la historia se descarta. La política de originalidad prohíbe convertir señales o historias externas en guiones plantilla, RAG creativo o entrenamiento.

## Modelos

Los aliases no se incrustan en prompts. El router considera capacidad, calidad medida, latencia, costo, privacidad y salud. Groq, Qwen, Kimi, Nemotron y Hy3 están registrados; la disponibilidad real se comprueba antes de uso. Un modelo retirado o sin health check se degrada o bloquea; nunca se declara saludable por nombre.

## Facebook Reels

El criterio de éxito final sigue siendo una publicación única, original y recuperable. Falta: proveer assets permitidos, generar audio, validar/reproducir un render 9:16, usar una Página sandbox, reconciliar upload ambiguo e importar métricas. Hasta entonces no se debe afirmar que Kronara publica Reels reales.
