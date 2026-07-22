# Kronara — Documentación de funcionalidades (v0.6)

> **Para quién:** el equipo visual/frontend y cualquiera que necesite conectar,
> integrar o extender Kronara. Documenta **qué hace cada pieza, sus entradas y
> salidas, y cómo se conectan**. Es el contrato entre el backend (cerebro) y la UI.

## 1. Mapa de la aplicación

Kronara es **una sola app con dos planos y dos modos**:

```text
Svelte web local  ──__kronara_rpc/__kronara_asset──>  Python sidecar local
     UI                                  secretos, red host-pinned,                                  agentes, narrativa,
     muestra/observa                     pausa global, gates,                                        RAG, memoria, voz,
     no guarda secretos                  herramientas de efecto                                      scheduler
```

- **Web local:** interfaz Svelte servida por Vite. Es la ruta activa para crear episodios.
- **Sidecar Python:** planifica, investiga, escribe, evalúa, recuerda, genera voz/video y guarda episodios locales. Las herramientas externas siguen allowlistadas y redactadas.
- **Modo Tarea (Agente A):** flujo lineal bajo demanda (`content.run`): una historia, un tipo de contenido.
- **Modo Red (Agente B) [fases futuras]:** una historia maestra → variantes multiplataforma, parrilla semanal, Kronara Pulse.

## 2. Métodos RPC (UI → Python, vía web local)

Lista cerrada en la web local (`vite.config.js: ALLOWED_RPC_METHODS`). La UI llama estos por `__kronara_rpc`.

| Método | Propósito | Entrada (clave) | Salida (clave) |
|---|---|---|---|
| `operations.chat` | Chat operativo con contexto, citas e intents | `message`, `session_id` | respuesta, citas, intents, estado parcial |

El chat operativo utiliza un prompt stack con capas separadas para política base, personalidad, perfil narrativo del agente, rol y contexto. El perfil narrativo guía tono, estilo de razonamiento, forma de respuesta y criterios de cierre sin modificar autoridad.
| `operations.context` | Paquete de contexto operativo (sin secretos) | — | cobertura, snapshot de workflow |
| `tools.timeline` | Trazas de herramientas de un run (para la UI) | `run_id` | eventos de herramienta redactados |
| `memory.search` | Buscar memorias por ámbito/tipo | `scope`, `kind`, `query` | registros de memoria |
| `rag.retrieve_v3` | Recuperar contexto propio citado | `text`, `language`, `scope`, `allowed_rights`, `limit` | fragmentos + citas + degradaciones |
| `story.test` | Prueba narrativa (solo motor de historia) | `brief` | `StoryRunResult` serializado |
| `content.run` | Vertical Reddit→RAG→historia propia→QC | `subreddits`, `target_duration_seconds`, `series_id?`, `part_number?`, `cliffhanger?` | historia, citas, QC, duración |
| `performance.learn` | Aprender de métricas de una pieza propia | `content_id`, `snapshots` | diagnóstico + decisión de reutilización |
| `run.cancel` | Cancelar cooperativamente un run | `run_id` | estado |
| `run.progress` | Progreso de un run en curso | `run_id` | fase, estado, porcentaje |
| `agent.capabilities` | Lista de agentes/herramientas (sin ejecución) | — | agentes, skills, herramientas |
| `programs.list` | Programas, calendario, plataformas y plantilla narrativa vigente | — | programas + `narrative_template` |
| `programs.template.save` | Guardar plantilla narrativa manual de un programa | `program_id`, `directives` | plantilla guardada |
| `programs.template.reset` | Restaurar plantilla narrativa base de un programa | `program_id` | plantilla base |
| `episodes.list` / `episodes.get` | Biblioteca local de episodios y detalle | `program_id?`, `story_id` | guion, video, música, SFX, QC |

La pestaña **Programas > Recursos** muestra las plantillas RAG visibles por programa (`knowledge/narrative/program-story-templates.md`). La pestaña **Programas > Configuración** permite editar reglas operativas que se guardan en runtime local.

**Eventos hacia la UI (para observar sin intervenir):** cada herramienta emite `started` y un evento final con argumentos redactados, evidencia y resumen; los runs emiten progreso. La UI se suscribe para dibujar el timeline y el panel de "runs automáticos".

## 3. Herramientas externas gobernadas

Lista cerrada de herramientas que el sidecar puede pedir. El resultado se muestra como logs resumidos, sin secretos ni razonamiento privado.

| Herramienta | Propósito | Entrada | Salida |
|---|---|---|---|
| `model.health` | Estado de salud de los modelos | — | `{models: {id: healthy\|degraded}}` |
| `model.complete` | Completar con JSON estructurado + fallback | `task`, `candidates`, `system`, `input`, `response_schema` | `{payload, provider, model, fallback_used}` |
| `reddit.list_signals` | Señales abstractas de Reddit (sin cuerpos) | `subreddits`, `sort`, `limit` | señales + receipt |
| `meta.metrics.read` | Métricas de una pieza remota (solo lectura) | `remote_id` | snapshot de métricas |
| `voice.synthesize` | **(v0.6)** Sintetizar voz y medir duración real | `text`, `voice_id`, `rate`, `pitch` | `{duration_ms, word_boundaries, audio_ref}` |
| `publication.publish` | **(v0.6)** Publicar/reconciliar con idempotencia (gobernada) | `mode`, `idempotency_key`, `video_ref`, `description` | `{status, remote_id}` (`not_configured` sin Página autorizada) |

## 4. Referencia por subsistema (funciones públicas)

### 4.1 Narrativa — `story_engine.py`
- **`StoryEngine(store, generator, critic, cancellation_requested?, duration_measurer?)`** — orquesta el ciclo creativo: concepto → blueprint causal → escenas → originalidad → **crítico independiente** (familia de modelo distinta) → revisión localizada → duración → calidad → **oficio literario** → packaging → memoria. Con checkpoints (reanudable) y Guardian anti-inyección.
  - `run(brief: StoryBrief) -> StoryRunResult` — ejecuta el ciclo completo.
  - `resume(run_id) -> StoryResumeStatus` — reanuda desde el último checkpoint.
- **`StoryBrief`** — entrada de una historia. Campos nuevos v0.6: `series_id`, `part_number`, `series_context` (canon heredado para historias multi-parte).
- **`StoryRunResult`** — salida. Campos nuevos v0.6: `craft` (métricas de prosa), `voice_duration` (duración real medida).
- **`DeterministicStoryProvider` / `DeterministicIndependentCritic`** — proveedores golden/offline para pruebas.

### 4.2 Oficio literario — `narrative_craft.py` (nuevo v0.6)
- **`LiteraryCraftEvaluator(craft_threshold?, min_sensory_density?)`**
  - `assess(text) -> CraftReport` — mide prosa: densidad sensorial, verbos-filtro, clichés, adverbios en -mente, variación de ritmo; detecta antipatrones (`cliche_pileup`, `purple_prose`, `telling_emotion`, `adverb_overload`, `monotone_rhythm`). `blocking=True` en fallos graves (lo usa el StoryEngine como gate duro).
  - `detect_craft_antipatterns(text) -> tuple[str,...]`.
- **`CraftReport.as_dict()`** — para exponer las métricas en la UI.

### 4.3 Calidad narrativa (rúbrica) — `narrative_quality.py`
- **`NarrativeQualityEvaluator`** — 11 dimensiones (hook, clarity, conflict, escalation, agency, coherence, credibility, originality, retention, payoff, production_fit). `evaluate(scores) -> NarrativeQualityReport`; `detect_antipatterns(text)`. Gate: total ≥ 80/110 y cada dimensión ≥ 7.

### 4.4 Proveedor creativo enrutado — `routed_story_provider.py`
- **`AuthorityModelRouter(authority, registry)`** — resuelve alias→modelo por salud/capacidad y llama `model.complete`.
- **`RoutedStoryProvider(router)`** — genera conceptos/blueprint/escenas con el sistema creativo literario (`KRONARA_CREATIVE_SYSTEM`) y directivas de oficio por escena; inyecta el canon de la serie.
- **`RoutedIndependentCritic(router, generator?)`** — crítica con el alias `critic`, excluyendo los modelos que usó el generador (independencia).

### 4.5 Router de modelos — `model_registry_v2.py` + `config/models/registry.v2.json`
- **`ModelCapabilityRegistryV2.load(path)`** → `.resolve(alias, requirements, health) -> ModelRoute`. Aliases: `creative_primary`, `planning_primary`, `long_context_primary`, `deep_reasoning_primary`, `experimental_hy3`, `critic`, `fast_tools`. Modelos: Qwen, Kimi, **Nemotron 3 Ultra (1M ctx)**, Nemotron 3 Super, Hy3 (expira 2026-07-21). Filtra por expiración, salud, capacidad, contexto y salida estructurada.

### 4.6 Memoria de grafo — `graph_memory.py` (nuevo v0.6)
- **`KronaraGraph(db).initialize()`** — grafo de conocimiento **bitemporal** (valid-time + transaction-time) sobre SQLite.
  - `upsert_entity(GraphEntity)`, `add_relation(GraphRelation)`, `supersede_entity(id, nuevo, at)` (cambia canon sin borrar historia).
  - `entities(series_id?, entity_type?, as_of?)`, `relations(...)`, `neighbors(id, max_hops?)` (BFS), `canon(series_id, as_of?) -> CanonSnapshot`.
- Tipos de entidad: character, place, object, topic, voice, program, series, fact.

### 4.7 Series multi-parte — `series.py` (nuevo v0.6)
- **`SeriesCanonBuilder(graph)`**
  - `ingest(part, characters, facts, now)` / `ingest_story_result(series_id, part_number, result, now, cliffhanger?, is_final?)` — vuelca el canon de una parte al grafo (personajes recurrentes = un solo nodo).
  - `context_for_part(series_id, next_part, now) -> SeriesContext` — reconstruye el canon (personajes, hechos, preguntas abiertas) y un `context_block` promptable para la siguiente parte.
- **`StoryPart`** — valida que toda parte no-final cierre con cliffhanger.

### 4.8 RAG híbrido — `rag_v3.py`
- **`RAGV3Index(db, descriptor, embedder).retrieve(RetrievalQueryV3) -> RetrievalPacketV3`** — FTS5 + vectores (sqlite-vec) + expansión de grafo de documentos + RRF + reranker opcional; filtros de derechos/vigencia **antes** del ranking; citas.
- **`promote_owned_story(...)` / `tombstone(id)`** — promoción reversible con auditoría.

### 4.9 Voz y duración — `voice.py` (ampliado v0.6)
- **`VoiceRegistry` / `DEFAULT_VOICES`** — voces neurales es-* (Marcelo, Lorenzo, Sofía, Gonzalo, Salomé).
- **`EdgeTtsVoiceProvider(audio_dir?)`** — **síntesis real en vivo** (edge-tts) con timings por palabra (`WordBoundary`) y duración real; degrada si edge-tts/red faltan.
- **`AuthorityVoiceProvider(authority)`** — llama `voice.synthesize` (con caché por hash de contenido); **`EstimatingVoiceProvider`** — fallback sin red.
- **`SceneDurationMeasurer(provider, voice_id).measure(scenes) -> MeasuredDuration`** — duración real total + por escena + timings de palabra (para subtítulos).

### 4.9b Render de video — `render.py` (nuevo, integración)
- **`FfmpegRenderer(ffmpeg?, ffprobe?)`** — `render(audio_path, output_path, preset, subtitle_path?) -> RenderResult`; produce un MP4 real (Reel 9:16 / master 16:9) y QC por ffprobe (resolución, audio, duración). Binario vía `KRONARA_FFMPEG`/PATH.
- **`build_srt` / `cues_from_word_boundaries`** — subtítulos desde los timings de voz. Presets: `REEL_9x16`, `MASTER_16x9`.

### 4.9c Publicación — `distribution.py` (ampliado, integración)
- **`IdempotentReelsPublisher(publisher, intents)`** — persiste el intent antes del efecto y **no re-publica** un intent ya publicado (sin Reels duplicados al reanudar).
- **`AuthorityMetaTransport(authority)`** — enruta upload/reconcile por `publication.publish`. `MetaPublisher` maneja timeout→reconciliación. *(La publicación EN VIVO requiere una Página Meta autorizada.)*

### 4.10 Scheduler y autonomía — `schedule.py` (nuevo v0.6) + `policy.py`
- **`Scheduler(rules).due(now, last_fired) -> tuple[DueRun,...]`** — qué runs programados tocan ahora (cadencia interval/daily/weekly = parrilla). Lógica pura; la web local entrega el momento actual.
- **`AutonomousRunAuthorizer(policy)`** — instancia el `AutonomyGuard`: pausa global, temas prohibidos y riesgo crítico detienen el run desatendido.
- **`AutonomyGuard(policy).authorize(action, risk) -> AuthorizationDecision`** — gate por modo (`manual`/`supervised_auto`/`full_auto`) y códigos no-anulables.

### 4.11 Vertical de producción — `content_pipeline.py`
- **`ProductionContentPipeline(authority, store, rag, model_registry, artifact_root, graph?)`**
  - `run(params) -> dict` — Reddit (señal abstracta) → filtros → RAG citado → brief editorial → `StoryEngine` → artefacto propio. Con `graph` + `series_id`, reutiliza canon antes de escribir e ingesta después (historias multi-parte).

### 4.12 Rendimiento / Pulse (base) — `performance.py`, `analytics.py`, `virality.py`, `performance_learning.py`
- **`PerformanceScientist.diagnose(...)`** — hipótesis observacionales (voz, tema, gancho, duración, horario) con intervalos de Wilson; nunca causalidad con muestra insuficiente.
- **`PerformanceLearningService.learn(...)`** — cohortes comparables → decisión de reutilización reversible.
- *(Kronara Pulse completo —crecimiento, dimensión de programa, retención por-segundo, multiplataforma— es fase futura F5.)*

## 5. Cómo conectar el frontend (resumen)

1. **Iniciar un run:** llamar `content.run` (o `story.test`) por `__kronara_rpc`; recibir `run_id`.
2. **Observar:** suscribirse a los eventos de progreso y a `tools.timeline` para dibujar el timeline (herramientas, evidencia, modelo usado).
3. **Cancelar/reanudar:** `run.cancel` / el run se reanuda solo desde checkpoint tras reabrir la app.
4. **Chat operativo:** `operations.chat` para preguntar por el estado con contexto citado.
5. **Autonomía:** un panel de "runs automáticos" (programados/en curso/bloqueados) refleja el `Scheduler` + `AutonomyGuard`; los gates bloqueados se muestran con su razón.
6. **Nunca** exponer secretos en la UI: todo llega redactado desde el puente local.

Si `run.diagnostics` devuelve `PROGRAM_QUALITY_FAILED`, la fase correcta es **Crítica**. No es un error de Guardando: el guion no cumplió una regla del programa, por ejemplo amenaza paranormal clara o anclas visuales de lugar en Viernes Paranormal.

## 6. Estado por fase (v0.6)

- **Hecho (esta ronda):** motor narrativo literario (R2), Nemotron Ultra + alias critic (R5), memoria de grafo bitemporal + series multi-parte (R3), voz real + duración medida (R4), scheduler + autonomía (R6).
- **Siguiente (post-visual):** render real de video (F1), publicación autónoma en vivo — Facebook Reels primero (F2), Agente B de red editorial (F3), multi-cuenta (F4), Kronara Pulse completo (F5). Ver `docs/roadmap/`.

### Nota de auditoría visual 2026-07-21

El pipeline local ya genera el MP4 9:16 y la UI lo reproduce mediante el
protocolo local de assets. En Vite, `assetSrc()` usa
`/__kronara_asset`, restringido a `.kronara/runtime/**` y compatible con
rangos HTTP. Lo que sigue pendiente es la publicación remota real, no la
creación ni la reproducción local del MP4.
