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

### B. Créditos de OpenRouter agotados (bloqueo externo, confirmado, no arreglable en código)

Verificado corriendo `produce_episode.rs` real varias veces (nuevo atajo dev
`KRONARA_SIDECAR_DEV_PYTHON`, ver abajo): qwen/kimi devuelven `402` incluso con
`max_tokens` ya bajado varias veces ("requested up to 6144, but can only afford
759") — el saldo actual es tan bajo que **ningún** `max_tokens` razonable lo
arregla; es un tope de cuenta, no un bug de tamaño de request. `tencent/hy3:free`
sigue en `404` (expiró). Los `:free` de Nemotron (Ultra/Super) devolvieron
finalmente `429 Rate limit exceeded: free-models-per-day` con el mensaje
explícito de OpenRouter: **"Add 10 credits to unlock 1000 free model requests
per day"** — con saldo $0 el límite gratis diario es solo 50 requests, y las
pruebas de esta misma sesión ya lo agotaron hoy. Conclusión: el código ya está
verificado y listo; lo único que falta es que el usuario recargue saldo (basta
un mínimo, según OpenRouter) o que se reinicie la cuota diaria.

### C. Razonamiento visible de Nemotron (bug de código real, arreglado)

Con el transporte y la codificación ya arreglados, una corrida real llegó hasta
`story.blueprint`/`story.scenes` pero falló con `"model returned invalid
structured content"`. Añadido diagnóstico (`model_gateway.rs` ahora loguea el
texto crudo no-JSON) reveló la causa real: el modelo gratis (`nvidia/nemotron
:free`) devolvía su **razonamiento interno visible como texto plano** ("We need
to produce a JSON object... Let's count words... El(1) amanecer2 se3...") en
vez de la respuesta JSON directa, agotando `max_tokens` sin llegar nunca a
escribir el JSON. Arreglado añadiendo `"reasoning": {"enabled": false}`
(parámetro unificado de OpenRouter) a cada request — los modelos sin modo de
razonamiento (qwen/kimi/hy3) lo ignoran sin problema. Con esto corregido, el
mismo modelo escribió prosa literaria genuinamente elaborada (ver ejemplo real
más abajo) — lo cual a su vez obligó a recalibrar `max_tokens` una segunda vez
(ver `routed_story_provider.py::_scene_max_tokens` y el flat de
`story.blueprint`, ambos documentados inline con la evidencia real exacta que
los motivó).

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
4. ✅ **Modelos**: `max_tokens` recalibrado dos veces contra corridas reales
   (no adivinado); ruta a los gratis confirmada correcta (Ultra→Super en
   orden, ambos responden cuando la cuota diaria no está agotada); bug real
   de razonamiento visible encontrado y arreglado (sección C). Bloqueo
   restante: cuota/saldo de la cuenta (sección B), no arreglable en código.
5. ⏳ **Rebuild final** del binario y corrida real definitiva desde el ejemplo
   Rust — pendiente de que el usuario recargue saldo o se reinicie la cuota
   diaria de OpenRouter.
6. ✅ Documentado en memoria: patrón de aislamiento stdio (stdout Y stdin) y el
   gate de cuota gratis de OpenRouter a saldo $0.

## Nuevo: atajo de desarrollo para probar contra Rust+OpenRouter+Reddit reales sin rebuild

`KRONARA_SIDECAR_DEV_PYTHON=<ruta al intérprete>` (env var leída por
`SidecarProcess::spawn()` en `sidecar_bridge.rs`) hace que Rust corra
`kronara.sidecar` desde código fuente (vía ese intérprete) en vez de buscar el
binario PyInstaller empaquetado. Permite ejecutar
`cargo run --manifest-path src-tauri/Cargo.toml --example produce_episode`
contra la autoridad Rust real (OpenRouter, Reddit reales) en segundos, sin el
rebuild de ~5 min. Nunca se activa en la app empaquetada (solo cuando la env
var está presente). Así se encontraron y verificaron los tres bugs de las
secciones A/C y la recalibración de la sección B en esta misma sesión.
