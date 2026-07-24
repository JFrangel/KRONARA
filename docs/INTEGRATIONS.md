# Integraciones, APIs y cascadas (estado real)

Arquitectura web-first: el **Node authority** (`vite.config.js`) es la autoridad
de red (routing de modelos, publicación); el **sidecar Python** corre el pipeline
cognitivo/visual y llama a la autoridad por JSON-RPC sobre stdio. No hay Rust en
el camino web-crítico.

## Auditoría de llaves (nombres, nunca valores) y qué está cableado

| API | Llaves en `.env` | Cableada | Uso |
|---|---|---|---|
| **OpenRouter** | `KRONARA_OPENROUTER_API_KEY` ×3 | ✅ | Modelos de texto (Nemotron/Qwen/Kimi/Hy3) |
| **Groq** | `KRONARA_GROQ_API_KEY` ×2 | ✅ | Modelos de texto (gpt-oss, llama-3.3, qwen3) |
| **Qwen / Kimi** | `KRONARA_QWEN_*`, `KRONARA_KIMI_*` | ✅ | Enrutados como OpenRouter si su base_url lo es |
| **Pollinations** | `KNORA_POLLINATION_API_KEY` | ✅ | Imágenes (Flux), primer peldaño de la cascada |
| **Cloudflare Workers AI** | `KRONARA_CLOUDFLARE_ACCOUNT_ID`, `KRONARA_CLOUDFLARE_API_TOKEN` | ✅ imágenes · ⏳ i2v | Flux (fallback de imagen); Wan i2v pendiente de cablear |
| **Pexels** | `KRONARA_PEXELS_API_KEY`, `KRONARA_PEXELS_ENABLED` | ⏳ | `pexels.search_videos` existe en la autoridad; falta cosechar loops a la biblioteca |
| **Freesound** | OAuth completo (`KRONARA_FREESOUND_*`) | ⏳ | Ampliar biblioteca de música/SFX (hoy sembrada a mano) |
| **VoiceBox** | local (`KRONARA_VOICEBOX_URL`) | ✅ | Voz principal + clonación (CUDA local) |
| **Azure Speech** | `KRONARA_AZURE_SPEECH_*` | ⏳ | TTS alterno (no en el camino por defecto) |
| **Reddit** | `KRONARA_REDDIT_*` | ✅ (con fallback) | Descubrimiento; RSS sin login como respaldo |
| **Meta / Facebook** | `KRONARA_META_PAGE_ID`, `KRONARA_META_PAGE_TOKEN` | ⏳ | Métricas versionadas; upload/publicación real pendiente |
| **YouTube / TikTok** | `.env.example` | ❌ | Publicación pendiente (Fase 5/N) |

Leyenda: ✅ funciona · ⏳ keyeada pero no cableada del todo · ❌ no construida.

## Cascada de imágenes (`sidecar.py` + `image_gen.py::ImageProviderCascade`)

Por defecto (v0.8), **solo API**, primer éxito gana, fallo silencioso hasta que
todos caen:

```
Pollinations (Flux, ~5-10s)  →  Cloudflare Workers AI (Flux, ~3s)  →  Placeholder
```

- Solo se incluyen los proveedores para los que hay credenciales.
- SDXL local queda **fuera** del hot-path (era el cuello de ~7 min/imagen); se
  activa opt-in con `KRONARA_ENABLE_SDXL=1` o se fuerza con `KRONARA_IMAGE_PROVIDER=sdxl`.
- Overrides: `KRONARA_IMAGE_PROVIDER=pollinations|cloudflare|sdxl|placeholder`.

## Cascada de modelos de texto (`vite.config.js::completeModel`)

La autoridad arma la lista de `providers` desde **todas** las llaves disponibles
(3 OpenRouter + Qwen/Kimi-como-OpenRouter + 2 Groq). Para cada modelo candidato
que envía el router de Python:

1. Filtra los providers cuyo `provider` coincide con el candidato.
2. **Rota entre todas sus llaves**: un `response.ok=false` (402/429 por cuota) o
   un error hace `continue` a la siguiente llave del mismo proveedor.
3. Si el modelo se agota en todas sus llaves, pasa al siguiente candidato.
4. `fallback_used=true` cuando no ganó el primer intento; la salud del modelo se
   marca `healthy`/`degraded` para telemetría.

La rotación por cuota **ya existe en el código**; el límite real es la cuota
externa del free-tier de OpenRouter (≈50 req/día por cuenta con balance $0). Groq
es un proveedor aparte con su propia cuota → respaldo.
Solo se aceptan modelos en la allowlist (`ALLOWED_MODELS`) y peticiones acotadas
(`max_tokens ≤ 8192`, 1-5 candidatos, schema estructurado).

## Voz — VoiceBox

Servidor local FastAPI (`:17493`, CUDA). Voz principal y **clonación** (subir
audio + transcripción exacta). `EstimatingVoiceProvider` silencioso solo como
último recurso anti-crash. Edge TTS fue **eliminado**. Ver [VOICEBOX.md](VOICEBOX.md).

## Audio de ambientación — música y SFX

Biblioteca local en `.kronara/assets/` (hoy 7 pistas de música por mood + 8 SFX
reales). Música con **ducking** determinista bajo la narración; SFX anclados a
tiempos de palabra reales, con cooldown de 4 s por tag y tope de 15 cues, a
ganancia baja (0.032, "apenas perceptible"). El mapa palabra→SFX cubre el léxico
de los programas (~70 disparadores). Freesound queda para ampliar el catálogo.

## Movimiento y construcción de video

Tres niveles de movimiento, de gratis a premium:

1. **Ken Burns** (default, gratis): imagen fija con zoom/pan (`zoompan`) + crossfades
   (`xfade`), sesgo por `motion_bias` del estilo.
2. **Video-loops de Pexels** (gratis, real): metraje en movimiento (fuente
   `video_loop`, `video_clip_filter`). Cablear con `library.harvest_video_loops`
   (`KRONARA_PEXELS_ENABLED=1`). La composición ya lo renderiza con `-stream_loop -1`.
3. **i2v generativo** (opt-in, de pago): anima la propia imagen de una escena.
   **Investigado (jul-2026): Cloudflare Workers AI NO tiene i2v** (su changelog no
   lista modelos de video). El i2v real y barato es **fal.ai `fal-ai/wan-i2v`**
   (Wan 2.x, 9:16, ~1 min/clip, ~$0.20 480p / $0.40 720p). Provider `i2v.py`
   (`FalWanI2VProvider`, gated por `KRONARA_I2V_ENABLED=1` + `KRONARA_FAL_KEY`),
   expuesto como RPC **on-demand** `media.animate_scene` (deliberado, no automático,
   por costo/latencia). Sin key → apagado; el episodio usa loops o Ken Burns.

Render final 9:16 con FFmpeg, subtítulos y normalización de loudness a −19…−13 LUFS.

## Reddit

RSS público como camino sin credenciales (el descubrimiento nunca debe requerir
login); OAuth oficial opcional. `TrendSignal` conserva solo señales abstractas
(título reducido, engagement, velocidad, saturación, URI); el cuerpo externo se
descarta y nunca llega al escritor. La política de originalidad prohíbe convertir
señales externas en guiones plantilla, RAG creativo o datos de entrenamiento.

## Publicación

Meta/Facebook: métricas con versión de Graph fijada y token de Página custodiado
por la autoridad; falta Página sandbox, upload del asset y reconciliación. Hasta
entonces **no** se debe afirmar que Kronara publica Reels reales. YouTube/TikTok
pendientes (Fase 5/N).
