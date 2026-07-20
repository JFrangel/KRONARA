# Fases futuras (post apartado visual)

> Se construyen después de conectar la UI. El **scheduler + lazo autónomo (R6)**
> ya las dispara solas en cuanto cada una cierra: el objetivo es que los agentes
> creen, analicen y publiquen sin intervención.

## FASE F1 — Render real de video
- `media.render` como herramienta de autoridad Rust (ffmpeg host-controlado, sin shell) sobre `MediaTimeline`.
- Master 16:9 + variante 9:16; Ken Burns sobre imágenes; ducking de música; loudness EBU R128.
- Subtítulos ASS quemados desde los `word_boundaries` de `voice.synthesize` (R4).
- QC de video: resolución, fps, duración, frames negros, aspect ratio, sincronía de subtítulos.

## FASE F2 — Publicación autónoma en vivo
- `publication.publish` como herramienta de autoridad Rust; **Facebook Reels primero** (Graph API, token de system-user, idempotencia + reconciliación por `idempotency_key`).
- Luego: YouTube Data v3, Spotify (RSS de podcast auto-hosteado), Instagram, TikTok.
- Gates antes de publicar: derechos ∧ originalidad ∧ QC ∧ presupuesto ∧ política. El `AutonomousRunAuthorizer` (R6) ya bloquea cuando corresponde; F2 conecta el efecto real.

## FASE F3 — Agente B (red editorial)
- Grafo supervisor `ExecutiveOrchestrator` (oportunidad→editorial→research→arquitectura→escritura→producción→QC→packaging→distribución) envolviendo el núcleo.
- **Fan-out master→N variantes** por plataforma (horizontal/vertical, reel/largo) desde un solo contenido maestro.
- **Parrilla semanal** con programas bajo la marca KRONARA (Decisiones Difíciles, Confesiones Anónimas, Crónicas de Justicia, Mentes Ocultas, Viernes Paranormal, Historias de Medianoche, El Caso de la Semana) — cada uno con su `ScheduleRule` (R6).

## FASE F4 — Multi-cuenta / multi-perfil ("clon del agente")
- Registro de cuentas + credenciales por marca (en Rust, secretas).
- El mismo contenido maestro replicado y adaptado a FB/TikTok/YouTube/Instagram/Spotify/Reddit por cuenta, cada una en su horario de la parrilla.

## FASE F5 — Kronara Pulse (inteligencia de rendimiento completa)
- Crecimiento/serie-temporal (seguidores, canal), dimensión de **programa/serie**, ingesta de **retención por-segundo**.
- Métricas **multi-plataforma** (no solo Facebook), resolución fina de horarios y día de semana.
- Ranker de potencial de tema (fusiona tendencias + rendimiento) y recomendaciones editoriales que retroalimentan la parrilla automática.

## Base ya construida en v0.6 que estas fases reutilizan
- Voz + `word_boundaries` (R4) → subtítulos de F1.
- `AutonomyGuard` + `Scheduler` (R6) → disparo y gate de F2/F3/F4.
- `KronaraGraph` + series (R3) → continuidad y canon del fan-out de F3.
- Router con Ultra (R5) y motor literario (R2) → calidad del contenido maestro.
