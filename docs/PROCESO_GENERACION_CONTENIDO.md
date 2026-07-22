# Proceso de generación de contenido, paso a paso

Documenta exactamente qué hace `content.run` de principio a fin: cada etapa,
qué código la ejecuta, qué variables de entorno la afectan, y dónde queda
cada archivo en disco. Ver también [`BUGS_CONOCIDOS.md`](BUGS_CONOCIDOS.md)
(estado real/bugs) y [`ARCHITECTURE.md`](ARCHITECTURE.md) (arquitectura
general Rust/Python).

Punto de entrada único: `ProductionContentPipeline.run(params)` en
[`python/kronara/content_pipeline.py`](../python/kronara/content_pipeline.py).
Tanto el botón "Crear episodio" de la UI, como el asistente de chat
(`action.approve`), como la parrilla automática (`schedule.tick`) llaman
exactamente a esta misma función — no hay tres caminos distintos, hay uno.

## Mapa de las 8 etapas

```text
1. Investigación (Reddit)      reddit.list_signals  -->  señal elegida
2. Contexto propio (RAG)       rag.retrieve         -->  fragmentos citados
3. Editorial                   model.complete        -->  título/premisa/tema
4. Guion (StoryEngine)         model.complete (x N)  -->  guion + QC
5. Voz (duración medida)       voice.synthesize       -->  audio + timings reales
6. Producción visual (V0-V8)   image_gen + render.py -->  video/portada
7. Persistencia                store.save_owned_...   -->  metadata guardada
8. Evento de finalización      store.append_event      -->  traza completa
```

## 1. Investigación: señal de Reddit

**Código:** `ProductionContentPipeline.run()`, líneas iniciales — llama a la
herramienta de autoridad `reddit.list_signals`.

- Primero intenta Reddit OAuth real (necesita `KRONARA_REDDIT_ENABLED=true`
  + `KRONARA_REDDIT_CLIENT_ID`/`KRONARA_REDDIT_CLIENT_SECRET`). Kronara está
  diseñado para que esto **nunca sea obligatorio**.
- Si falla (sin credenciales, que es el caso normal), cae automáticamente a
  `_rss_fallback_signals()`: lectura pública de RSS sin credenciales, primero
  desde el `OpportunityStore` (caché local, `opportunities.db`) y solo si
  está vacío hace una lectura RSS en vivo (`reddit_rss.py`).
- Los resultados se filtran con `RedditSignalFilters` (score mínimo,
  antigüedad máxima, idioma, autopost, etc. -- RSS no trae score/comentarios,
  así que esos filtros se relajan automáticamente en ese camino).
- Se elige UNA señal (`selected`) por una fórmula de velocidad/saturación.
  El cuerpo del post **nunca** se persiste ni se pasa al escritor -- solo un
  `theme_hint` (título limpio) y metadatos abstractos.

**Qué puede fallar:** sin red, sin señales que pasen el filtro → todo el run
falla con `ValueError("no Reddit signal passed the governed filters")`. No
degrada a texto inventado.

## 2. Contexto propio (RAG)

**Código:** `self.rag.retrieve(...)` sobre `RAGV3Index` (FTS5 + vectores +
grafo). Recupera hasta 8 fragmentos **propios** (`rights_mode` en
`owned_original`/`promoted_learning`) relacionados con el `theme_hint` --
nunca contenido externo con derechos ajenos.

## 3. Editorial: título, premisa, tema

**Código:** `router.complete(alias="planning_primary", task="editorial.brief", ...)`.
Primer uso del enrutador de modelos (ver sección de variables abajo). Genera
un título/premisa/tema **completamente originales** a partir de la señal
abstracta + los fragmentos propios -- nunca copia el post de Reddit.

## 4. Guion: `StoryEngine.run(brief)`

**Código:** [`python/kronara/story_engine.py`](../python/kronara/story_engine.py).
La etapa más larga, con su propio sub-pipeline:

1. `concepts()` -- 3 conceptos de historia candidatos.
2. `blueprint()` -- la cadena causal (beats) del concepto elegido.
3. `scenes()` -- escenas reales con narración.
4. Crítico independiente (`RoutedIndependentCritic`, familia de modelo
   distinta al generador) revisa: si pide cambios, `revise()` reescribe y
   se repite (contador en `revision_count`).
5. QC de duración (`DurationQCReport`), originalidad (`OriginalityReport`,
   4 métricas de similitud contra el corpus) y calidad narrativa
   (`NarrativeQualityReport`, rúbrica de oficio literario).

Solo si TODO pasa se llega a `result.status == "completed"`. Si no, el run
completo aborta sin publicar nada (`error_code` explica por qué).

## 5. Voz: duración real medida

**Código:** `SceneDurationMeasurer` (usa el `voice_provider` inyectado en
`OperationsService`) mide -- no estima -- cuánto dura cada escena narrada.

- `EdgeTtsVoiceProvider`: síntesis real (Microsoft Edge neural voices),
  necesita el paquete `edge-tts` instalado y red. Devuelve audio real +
  `word_boundaries` (timing por palabra, usado luego para subtítulos y
  cues de SFX).
- `EstimatingVoiceProvider`: sin red -- estima con una tasa palabras/segundo
  (aprendida de mediciones reales pasadas vía `SpeechRateLearner`, o
  150 palabras/min por defecto) y, si hay `ffmpeg`, escribe un MP3 de
  **silencio puro** (`anullsrc`) de esa duración para que el resto del
  pipeline tenga un archivo que concatenar. Marca `degraded=True`.
- `FallbackVoiceProvider` envuelve ambos: intenta el real, y ante **cualquier**
  excepción (sin distinguir la causa) usa el de respaldo en silencio. Este
  es el mecanismo que causó el bug de audio silencioso documentado en
  `BUGS_CONOCIDOS.md` -- si `edge-tts` no está instalado, esto pasa siempre,
  sin ningún error visible.

## 6. Producción visual (V0-V8)

**Código:** `_produce_video()` en `content_pipeline.py`, que llama a
`produce_episode_video()` en
[`python/kronara/visual_production.py`](../python/kronara/visual_production.py).
Solo corre si HAY `image_provider` y `renderer` configurados (si no, el
episodio queda solo-texto, sin fallar) y si `voice_duration.audio_refs`
tiene un archivo real por escena.

1. **Storyboard**: `plan_shots_for_scene()` decide cuántas tomas por escena
   (3-7s cada una) y su `source_kind` (imagen IA / video de apoyo /
   overlay gráfico) según `visual_director.py`.
2. **Portada**: una imagen premium generada del gancho/logline de la
   historia (`generate_cover_image()`), independiente del resto.
3. **Imágenes**: por cada toma `image_kind=ai_image`, `image_provider.generate()`:
   - `DiffusersImageProvider`: SDXL local real (necesita `torch`+`diffusers`
     + pesos locales). Tier `fast` usa la LoRA Lightning (8 pasos); tier
     `premium` (gancho/clímax/cierre) usa 32-36 pasos sin LoRA.
   - `PlaceholderImageProvider`: sin GPU/pesos -- dibuja una composición
     ilustrada determinista (Pillow) en vez de fotografía real. Nunca se
     presenta como salida de IA.
4. **Subtítulos**: `cues_from_word_boundaries()` sobre los `word_boundaries`
   reales de la voz → archivo `.srt`.
5. **Continuidad visual**: la portada premium se usa como referencia para
   escenas AI cuando el proveedor soporta IP-Adapter; cada prompt también
   lleva contexto del episodio completo y negativos contra ubicaciones ajenas.
6. **Música/SFX**: si hay `asset_library` configurado, selecciona pistas por
   mood/programa con *ducking* real bajo la narración; si no, se omite (no
   se fabrica silencio de música).
7. **Composición + render**: `render.py` (FFmpeg real) compone
   imágenes+Ken Burns+subtítulos quemados+audio mezclado en un MP4 vertical
   9:16, y corre QC (frames negros, loudness EBU R128, duración).

## 7-8. Persistencia y evento final

Se guarda UN artefacto de texto (el guion, direccionado por su hash SHA-256)
+ metadata rica en `owned_story_artifacts` (SQLite, `kronara.db`): título,
hook, duración, familias de modelo generador/crítico, resultados de QC,
estado/ruta del video, ruta de portada, LUFS, número de escenas/tomas,
mezcla de fuentes visuales, música, SFX detectados/resueltos/faltantes,
issues de QC de video. `episodes.get` lee esto
mismo para mostrar el guion completo en la UI.

## Variables de entorno relevantes a generación

| Variable | Efecto en la generación |
|---|---|
| `KRONARA_OPENROUTER_API_KEY`, `_2`, `_3` | Claves en cascada para el enrutador de modelos (editorial, guion, crítico). Si una se queda sin crédito/cuota, la siguiente se intenta automáticamente. |
| `KRONARA_GROQ_API_KEY`, `_2` | Igual, para los modelos servidos por Groq (más rápidos, cuota diaria independiente de OpenRouter). |
| `KRONARA_QWEN_*`, `KRONARA_KIMI_*` | Endpoint/clave/modelo directos, fuera de la cascada OpenRouter/Groq. |
| `KRONARA_MODEL_REGISTRY` | Ruta alternativa a `config/models/registry.v2.json` (qué modelo responde a cada alias: `planning_primary`, `critic`, etc.). |
| `KRONARA_MAX_DAILY_COST_USD`, `KRONARA_MAX_RESEARCH_COST_USD` | Techos de presupuesto -- un run que los excedería se bloquea, no se permite "un poco más". |
| `KRONARA_REDDIT_ENABLED`, `_CLIENT_ID`, `_CLIENT_SECRET` | Habilitan Reddit OAuth real en la etapa 1. Sin ellas, cae al RSS público (sigue funcionando). |
| `KRONARA_AZURE_SPEECH_ENABLED`, `_KEY`, `_REGION` | Ruta de voz alternativa a edge-tts (no usada por defecto hoy). |
| `KRONARA_SD_MODEL_DIR` | Ruta local a los pesos SDXL base. Sin ella, busca en `.kronara/models/sdxl-base-1.0` relativo al directorio de trabajo. |
| `KRONARA_SD_LORA_DIR` | Ruta local a la LoRA Lightning (tier `fast`). Sin ella, busca en `.kronara/models/sdxl-lightning`; si tampoco existe, usa el repo de HuggingFace directo (puede requerir red). |
| `KRONARA_IMAGE_PROVIDER=placeholder` | Fuerza el proveedor de imagen ilustrado (Pillow) en vez de SDXL real -- para iterar rápido en composición/render sin esperar generación de imágenes. |
| `KRONARA_PEXELS_API_KEY`, `_ENABLED` | Video de apoyo real (`source_kind=video_loop`) en la mezcla visual. |
| `KRONARA_FREESOUND_*` | Música/SFX reales de la biblioteca de assets. |
| `KRONARA_DATA_DIR` | Raíz de datos de la app (`kronara.db`, artefactos, video, voz). En la app real, Rust la resuelve a un directorio de datos del sistema operativo -- nunca al checkout del repo. |
| `KRONARA_SIDECAR_DEV_PYTHON` | Atajo de desarrollo: corre `kronara.sidecar` desde código fuente en vez del binario empaquetado (ver `DIAGNOSTICO_PIPELINE_REAL.md`). Nunca activo en la app real. |
| `KRONARA_RPC_SESSION_TOKEN` | Token efímero de sesión entre Rust y Python -- lo genera Rust en cada arranque, nunca es una clave de proveedor. |

## Cómo generar un episodio manualmente para verificar todo el pipeline

`scripts/create_fresh_visual_story.py` (nuevo, no forma parte de `content.run`
ni de la app -- es una herramienta de desarrollo) ejercita el pipeline real
completo con datos deterministas (sin gastar crédito de modelos) para
producir un MP4 real de validación. Escribe en
`<repo>/.kronara/runtime/<story_id>/` (gitignored). Requiere `ffmpeg` en
PATH; usa `PlaceholderImageProvider` por defecto.

```powershell
python scripts/create_fresh_visual_story.py
```

Para probar con modelos y Reddit reales sin reconstruir el binario de
~2.7 GB, usar el atajo `KRONARA_SIDECAR_DEV_PYTHON` (ver
`DIAGNOSTICO_PIPELINE_REAL.md`, sección "atajo de desarrollo").

## Estado verificado hoy (2026-07-21)

- Guion (`StoryEngine`): probado end-to-end con datos deterministas y con
  modelos reales en sesiones anteriores; QC de duración/originalidad/calidad
  funcionando.
- Voz: `edge-tts` estaba ausente (bug de audio silencioso, ver
  `BUGS_CONOCIDOS.md`) -- **arreglado hoy**, verificado con síntesis real.
- Imágenes: `torch`/`diffusers` instalados hoy; dos imágenes SDXL reales
  inspeccionadas visualmente, calidad alta, sin degradación.
- Render: MP4 real de 88.8s, 1080×1920, audio AAC sincronizado, QC aprobado,
  producido con el harness de `scripts/create_fresh_visual_story.py`.
- Pendiente: reconstruir el binario empaquetado para que la app de
  escritorio real tenga todo esto (en curso).
