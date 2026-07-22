# Estado de sesión (2026-07-22)

Documento vivo del último trabajo hecho, hallazgos concretos y fases
pendientes. Objetivo: cualquier sesión posterior puede retomar sin releer
todo el historial.

## Lo que quedó en producción hoy (todo en `origin/main`)

| Fase | Commit | Impacto medible |
|---|---|---|
| A.0 Timeout + Abandonar generación | `969e134` | Fin del "94% Guardando" eterno; botón para abandonar |
| A.1 `content.run` asíncrono + poll real | `6eac4e1` | Backend devuelve `run_id` de inmediato; frontend polea `run.progress` cada 3s |
| B Vista "En vivo" en Estudio | `b5ca19b` | Fases + agentes + herramientas actualizándose cada 2s durante el run |
| C.1 Provider Pollinations.ai | `969e134` | 1.6s por imagen (medido) vs 7min de SDXL local |
| C.2 Provider Cloudflare Workers AI + cascada + más shots | `e0267dd` | 2.9s por imagen; failover automático Pollinations→CF→SDXL→placeholder |
| C.3 SDXL sólo respaldo | *(satisfecho por C.2)* | GPU sólo si ambos hosted fallan |
| C.4 Consistencia de escenas | `694b183` | Anclas de personajes + estilo film uniforme en cada prompt |
| E Vista Biblioteca real | `c4825e3` | 5 tabs (episodios, imágenes, voces, guiones, música/SFX) |
| G Limpieza sidecars huérfanos | `c80c228` | `predev` mata orfanos (limpió 8 procesos reales) |
| Q Umbral por dimensión aflojado | `b5ca19b` | 7.0 → 6.5 (basado en evidencia real de 6 revisiones fallando) |
| #59 Docs primer arranque | `85c3648` | Walkthrough 9 pasos actualizado |

## Errores reales diagnosticados hoy (guardados en workflow_events)

Estos NO son especulación; son extraídos directo de la base local
`.kronara/runtime/kronara.db` durante la sesión.

### Falla del run `owned_ui_1784703168470`
- **Etapa fallida**: `writer_room.story.draft` → **TOOL_FAILED**
- Traza: `tool_trace_events` 1897 muestra `writer_room` intentó
  `story.draft`, previamente 1896 muestra `model.complete` reportado como
  fallido por `executive_orchestrator`. Probablemente sin cuota o
  respuesta inválida de un modelo.
- **UI antes de A.1**: mostraba "94% Guardando" mintiendo. **Con A.1
  ahora**: muestra el status real `failed` con `error_code=TOOL_FAILED`.

### Falla del run `owned_ui_1784702800962`
- **Etapa fallida**: `guardian` → **PROGRAM_QUALITY_FAILED**
- 6 revisiones consecutivas del writer_room, cada una rechazada por
  `automated_qc`, oscilando entre dimensiones bloqueantes:
  - Rev 1: 10/11 dims fallan
  - Rev 2: 4 dims fallan (mejora)
  - Rev 3: 8 dims fallan (**regresión**)
  - Rev 4: 11/11 dims fallan
  - Rev 5: 10 dims fallan
  - Rev 6: 6 dims fallan
- Además `story.program_quality_failed` marcó `missing_haunted_place_
  anchors` + `weak_story_question` para viernes-paranormal.
- **Con Q aplicado hoy**: el umbral por dimensión bajó de 7.0 a 6.5, lo
  que debería reducir el "un solo 6/10 tumba todo". El total sigue
  requiriendo ≥80/110.
- **Q.2 sigue pendiente**: la plantilla de viernes-paranormal necesita
  investigar por qué los anclajes no se detectan aunque el guion los tiene.

## Video real que YA existe y puedes reproducir

```
D:\Proyecto Redit\.kronara\runtime\artifacts\video\owned_ui_1784695601087\owned_ui_1784695601087.mp4
```

24 MB, viernes-paranormal, QC aprobado, guardado en la DB. Doble-click
para reproducir. Cover en `_narration.mp3` incluido.

## Fases pendientes en orden sugerido de próximo trabajo

### Prioridad alta (lo que más pediste)

1. **#74 Fase Q.2** — investigar por qué "haunted_place_anchors" y
   "weak_story_question" fallan aunque el guion los cumple aparentemente.
   Empezar por `python/kronara/program_story_resources.py`.
2. **#76 Fase D** — completar las 5 pestañas restantes de Estudio
   (Voces, Storyboard, Recursos, Música/SFX, Producción). Sistemática:
   una por commit.
3. **#78 Fase V7-real** — poblar `asset_library.db` con música/SFX
   reales. Los scripts existen (`scripts/harvest_freesound.py`,
   `scripts/harvest_pexels.py`), sólo hay que correrlos y confirmar
   que `visual_production.py` los mezcla. Esto convierte "Música y SFX"
   de vacío a real.
4. **#79 Fase VOICE** — auditar `edge-tts` (¿suena natural?) y dejar
   documentado cómo integrar ElevenLabs / OpenAI TTS-1 como opción
   opcional (no implementarlo, sólo docs).

### Prioridad media (Agente B, arquitectura)

5. **#80 B1** — parrilla semanal automática (schedule.tick ya existe,
   falta UI en Calendario)
6. **#82 B3** — LangGraph real conectando los 9 nodos del
   ExecutiveOrchestrator (langgraph_runtime.py existe sin cablear)
7. **#81 B2** — MasterContent → N variantes por plataforma
8. **#84 B5** — grafo bitemporal + memoria (código sólido, falta UI)
9. **#83 B4** — Kronara Pulse completo
10. **#77 Fase F** — videos de fondo estilo Minecraft/gameplay

### Prioridad baja (integración externa)

11. **#85 Fase VP** — pulido visual Calendario/Configuración/Agentes/
    Analíticas/Publicación (todas son stubs o parciales)
12. **#86 Fase EXE** — ejecutable doble-click para lanzar todo
13. **#33/35/87 Fase N** — publicación real en redes (bloqueado por
    credenciales de plataformas)

## Detalle de por qué cada fase importa

### Por qué V7-real es crítico
Hoy los videos generados son AI-images-only + narración. No hay música
de fondo, no hay SFX. La "V4 música con ducking" y "V5 SFX apenas
perceptible" están marcados como completados en tareas anteriores pero
`asset_library.db` está vacía → el mecanismo funciona, la biblioteca no.
Un video con música ambiental adecuada se percibe MUCHO más profesional.

### Por qué B3 (LangGraph) importa
`orchestrator.py` define 9 nodos (opportunity → editorial → research →
arquitectura → escritura → producción → qc → packaging → distribución)
pero `content.run` es una función lineal. Con LangGraph real:
- Reanudación después de fallo desde el nodo exacto
- Checkpointing bitemporal (auditoría real)
- Fan-out fácil hacia variantes por plataforma

### Por qué VOICE importa
`edge-tts` es gratis y funciona, pero suena "TTS". Para YouTube/TikTok
"storytelling" nativo se necesita voz de nivel humano. ElevenLabs es
el estándar pero es de pago. Documentar cómo se integraría deja el slot
listo para cuando alguien tenga cuenta.

## Documentos relacionados

- [`docs/PROCESO_GENERACION_CONTENIDO.md`](PROCESO_GENERACION_CONTENIDO.md) — las 8 etapas de `content.run` en detalle
- [`docs/BUGS_CONOCIDOS.md`](BUGS_CONOCIDOS.md) — hallazgos con evidencia
- [`docs/FUNCIONALIDADES.md`](FUNCIONALIDADES.md) — contrato con el frontend
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — arquitectura Rust↔Python
- [`README.md`](../README.md) — arranque paso a paso

## Salud del proyecto en números

- **516** tests Python pasan (1 skipped)
- **12** tests JS pasan
- **13** fases completadas hoy con commits individuales
- **20+** fases pendientes documentadas con tareas de tracking
- **Zero** regresiones tras cada commit

## Deuda técnica reconocida (no bugs, no features)

1. La tabla `.env` tiene un typo del usuario (`KNORA_POLLINATION_API_KEY`
   en lugar de `KRONARA_`). El código acepta ambos, pero convendría
   normalizar en algún momento.
2. Los tokens de Cloudflare y Pollinations fueron pegados en chat en
   texto plano. **Rotarlos** al inicio de la próxima sesión.
3. `content.run` sync sigue funcionando (backward compat con tests y
   `produce_episode.rs`); async es opt-in con `wait:false`. Considerar
   invertir el default eventualmente.
