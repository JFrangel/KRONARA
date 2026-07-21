# Diagnóstico: la corrida real de extremo a extremo de content.run

> Documento de investigación, separado del roadmap (`architecture.md`). Registra
> por qué el pipeline completo (Reddit → guion → voz → imágenes → video) no
> producía un MP4 pese a estar "construido", y cómo se resolvió.

## El malentendido de fondo

Cada etapa (V0–V8) se construyó y **se probó en aislamiento con mocks**. Lo que
NUNCA se había corrido hasta esta sesión es la **cadena real completa**: Reddit
real → modelos reales (OpenRouter) → voz real (edge-tts) → imágenes reales
(SDXL) → video real (ffmpeg), todo manejado a través del **transporte real
Rust↔Python por stdio**. Correrla de verdad destapó una cascada de bugs de
integración que los mocks no podían ver.

## Bugs de integración encontrados y arreglados (en orden de aparición)

| # | Etapa | Síntoma | Causa raíz | Estado |
|---|-------|---------|-----------|--------|
| 1 | Investigación | `content.run` fallaba de inmediato | Exigía credenciales OAuth de Reddit que por diseño nunca se configuran | ✅ fallback a RSS público |
| 2 | Investigación | 0 señales aceptadas siempre | Filtro de idioma default `es` rechazaba subreddits en inglés (todos los reales lo son) | ✅ sin filtro por defecto |
| 3 | (todas) | Errores genéricos, sin traza | `rpc.py`/`tools.py` tragaban la excepción a "internal error" sin loguear | ✅ traceback a stderr → archivo |
| 4 | Guion | `schema validation failed` | `_object_schema` no incluía `properties`, OpenRouter nunca activaba modo estricto | ✅ esquemas JSON reales |
| 5 | Guion | conceptos != 3 | El array no tenía `minItems/maxItems` | ✅ conteos exactos |
| 6 | Guion | `TOOL_TIMEOUT` | 30s no alcanza para una cadena de fallback de 5 modelos | ✅ 120s |
| 7 | Guion (revise) | **`invalid RPC response` / crash** | **Transporte stdio frágil** (ver abajo) | ✅ resuelto y verificado |

## Hallazgo clave: la LÓGICA del pipeline ya está probada

El test `test_content_run_produces_a_real_video_when_visual_stage_is_configured`
**pasa**: hace `content.run` completo (Reddit→guion→voz→`produce_episode_video`→
MP4 real con ffmpeg) usando fakes a nivel de herramienta. Es decir, la estructura
guion→voz→imágenes→composición→video **funciona de punta a punta**. Lo único que
ese test NO ejercita:

1. Modelos OpenRouter reales (vs `FakeProductionAuthority`) — **bloqueado por créditos**.
2. edge-tts real — funciona, probado aparte.
3. SDXL real — funciona, probado aparte (43 tests GPU en verde).
4. **El transporte real stdio Rust↔Python** — **AQUÍ está el crash #7**.

Conclusión: el fallo actual **no está en la lógica del pipeline** (esa está
probada), sino en la **capa de transporte** y en un **bloqueo externo de créditos**.

## Los dos bloqueos actuales

### A. Transporte stdio frágil (bug de código real)

El sidecar usa **stdout** para el protocolo JSON-RPC. Problema: es un canal
compartido y vulnerable. La secuencia del crash:

1. Python (durante `story.draft`) llama a `model.complete` vía autoridad anidada
   escribiendo a `sys.stdout`.
2. Algo escribe una línea **no-JSON** a ese mismo stdout (warning de librería, o
   un write grande que Windows corta), **o** el write grande de `revise` (todas
   las escenas) falla en modo texto de Windows con `[Errno 22]`.
3. Rust lee esa línea de stdout de Python, `serde_json::from_str` falla →
   "invalid RPC response" → Rust hace `guard.take()` → **mata el proceso Python**.
4. Python, ya con el pipe roto, intenta escribir su respuesta final (línea 470 de
   `sidecar.py`) → `OSError: [Errno 22] Invalid argument`.

**El arreglo correcto (independiente de cuál librería sea la culpable):**
aislar el canal del protocolo. Al arrancar, reservar el stdout real **solo** para
el protocolo (envuelto en un writer binario UTF-8, inmune al bug de modo texto de
Windows) y redirigir `sys.stdout` → `sys.stderr`, de modo que cualquier `print`
de librería sea inofensivo y **nunca** pueda corromper el protocolo. Es el patrón
estándar de servidores stdio (LSP/MCP).

**Estado (verificado 2026-07-21):** implementado en `_isolate_protocol_stdout()`
(`sidecar.py`) + diagnóstico de lectura en `sidecar_bridge.rs::request()`.
Verificado con el harness rápido corriendo el pipeline completo end-to-end
(handshake → content.run → guion → voz real medida → imágenes placeholder →
composición → render ffmpeg → QC) sin ningún crash de transporte, produciendo
un MP4 real de 85.1s, H.264 1080x1920 + AAC, `qc_passed: true`,
`integrated_lufs: -16.16`. Este es el primer MP4 real de punta a punta de toda
la sesión de depuración.

### B. Créditos de OpenRouter agotados (bloqueo externo)

Los logs muestran `402 (This request requires more credits...)` en qwen/kimi y
`404` en `tencent/hy3:free` (expiró hoy, 2026-07-21). Los modelos **gratis** de
Nvidia Nemotron (`:free`) sí responden — de hecho, por eso el pipeline avanzó
hasta `story.draft`. Acciones:

- Bajar `max_tokens` en los pasos de guion (4096 es excesivo para salida
  estructurada; el saldo mínimo no alcanza para 4096 pero sí para menos).
- Confirmar que la cadena de fallback llega a los Nemotron gratis de forma fiable
  (ya lo hace; es lo que mantiene vivo el pipeline sin créditos).
- Nota para el usuario: para usar qwen/kimi (mejor calidad) hace falta recargar
  saldo en OpenRouter; sin recarga, opera solo con los gratis.

## La causa de la lentitud del diagnóstico (corregida)

Estuve reconstruyendo el binario PyInstaller (~2.7 GB con torch, ~5 min) por cada
cambio de Python. Innecesario. **Iteración rápida nueva:** correr `sidecar.py`
directo (código fuente, no binario) vía subproceso, con un relay de autoridad
Python que devuelve datos estructurados grandes y realistas al instante (sin
OpenRouter, sin créditos, sin rate-limit). 30 s por corrida en vez de 5 min. El
binario solo se reconstruye para la verificación final.

## Plan de ejecución

1. ✅ **Aislar el transporte stdio** (`sidecar.py`): canal de protocolo dedicado +
   `sys.stdout→stderr`. Elimina toda una clase de bugs.
2. ✅ **Harness rápido** (`scripts` / scratchpad): subproceso `sidecar.py` fuente +
   relay de autoridad fake fiel, corriendo el pipeline COMPLETO (guion→voz→
   imágenes→video) sin depender de créditos ni red. Reproduce y verifica.
3. ✅ **Verificar por etapas** con el harness: confirmado — sale un MP4 real
   (85.1s, QC en verde) usando la duración de voz REAL medida (edge-tts mide
   ~3.59 palabras/seg, no las ~2.5 que asume el estimado de respaldo del
   código — dato a tener en cuenta si se ajusta `estimated_seconds` en algún
   punto, aunque no bloquea nada porque el medidor real ya manda).
4. ⏳ **Modelos**: bajar `max_tokens`, confirmar ruta a los gratis (pendiente —
   requiere créditos/red reales, el harness usa respuestas fake).
5. ⏳ **Rebuild final** del binario y corrida real definitiva desde el ejemplo Rust.
6. ⏳ Documentar en memoria lo aprendido del transporte stdio (tras el rebuild final).
