# Consistencia narrativa y visual entre escenas (v0.8)

Plan para que cada escena sea coherente con las anteriores **y** futuras, y para
cablear los 3 super-agentes como nodos LangGraph reales. Sale de un análisis de
`story_engine.py`, `routed_story_provider.py`, `visual_production.py`,
`character_visual.py`, `graph_memory.py` y `langgraph_runtime.py`.

## Hallazgo clave
La **continuidad narrativa dentro de un episodio ya está** en gran parte: **todas
las escenas se generan en UNA sola llamada** (`RoutedStoryProvider.scenes`), así
que el modelo ve el blueprint completo. Los huecos reales son visuales y de
revisión, no de "el modelo no ve las otras escenas".

## Incrementos (orden de valor/riesgo)

1. **Identidad visual de personajes (mayor win, ya construido pero SIN cablear).**
   `character_visual.py` (V2: seed estable por personaje + descripción de
   apariencia persistida + hoja de referencia IP-Adapter) tiene tests pero cero
   llamadas en producción. Cablearlo en `visual_production.py` detrás de un
   parámetro opcional `character_visual_store` (default None = comportamiento
   actual, cero regresión): inyectar la descripción canónica en
   `_episode_visual_context` (:189-192) y por escena en `_resolve_scene_asset`
   (:341-353), y usar el seed estable por personaje. En proveedores hosted
   (Pollinations/Cloudflare, el default) el lever principal es la **descripción
   de texto**; el IP-Adapter solo lo honra SDXL local. Falta resolver la fuente
   de la descripción para historias standalone (una llamada barata al router o
   derivarla de narración/personajes).

2. **✅ HECHO — Revisión no rompe el canon.** `revise()` sólo enviaba
   scenes+revision y descartaba el canon; una revisión de calidad/duración podía
   contradecir personajes/hechos. Ahora reinyecta `series_canon` (cacheado en
   `concepts()`) + una instrucción de coherencia (también para standalone).

3. **Bloque de continuidad en el draft inicial.** Serializar el `ContinuityLedger`
   (facts + seeds/payoffs pendientes) a un bloque español e inyectarlo como
   `continuity_so_far` en `scenes` input_payload + una línea en
   `_SCENE_AGENT_CONTRACT`.

4. **Forzar seeds/payoffs pendientes.** Cuando el crítico/ledger detecta
   `unresolved_facts/seeds`, alimentarlos como instrucción de revisión al path
   `revise()` existente (una fase de revisión dirigida) en vez de solo
   reportarlos en `StoryRunResult`.

5. **RAG aterriza las escenas.** Reenviar el `owned_context`/citations ya
   recuperado (content_pipeline.py:291-301) al `scenes` input_payload como un
   `grounding` compacto, no solo al brief editorial.

6. **LangGraph 3 nodos (último, ortogonal a consistencia).** Partir
   `ProductionContentPipeline.run` en `_node_estratega`/`_node_guionista`/
   `_node_productor` (mismos cuerpos, seams limpios en content_pipeline.py),
   correr sobre `persistent_graph` (langgraph_runtime.py, SqliteSaver real,
   thread_id=run_id) con `run_graph`/`resume_graph`, opt-in vía `params['graph']`.
   Da reanudación + progreso por super-agente. Cuidar: idempotencia del release
   de lease (estratega), serializar StoryBrief/StoryResult vía asdict/from_dict
   (no pickle), y no divergir `run()` de `run_graph()` (compartir los 3 cuerpos).

## Riesgos anotados
- Standalone no tiene fuente de descripción de apariencia (bloqueante de V2).
- IP-Adapter solo lo honra SDXL local; en hosted el lever es el texto.
- Seed estable por personaje puede repetir composición: usarlo como base y variar
  por prompt/scene_position.
- Reinyectar canon en revise sube el costo de tokens: mantener el bloque compacto.
- `graph_memory` guarda `recorded_at` pero no hay read path bitemporal real
  todavía: no construir lógica que asuma consultas "as of T".
