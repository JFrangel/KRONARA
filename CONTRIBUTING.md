# Colaborar en Kronara

Esta guia deja el proyecto listo para correr la web local, generar episodios,
depurar fallos y subir cambios sin depender de la maqueta Tauri.

## Instalacion rapida

Requisitos:

- Node.js 20+ con npm.
- Python 3.12+.
- FFmpeg y ffprobe disponibles en `PATH`.
- Git.
- Red disponible para voces `edge-tts` y modelos remotos.

```powershell
npm.cmd install
python -m pip install -e ".[dev]"
python -m pip install edge-tts
npm.cmd run dev:web
```

Abre `http://127.0.0.1:5173/`. Esa es la ruta recomendada para desarrollo:
la web local habla con Python por `__kronara_rpc` y sirve medios desde
`__kronara_asset`.

## Variables locales

Copia `.env.example` a `.env` y completa solo lo que uses. No subas `.env`.

Claves frecuentes:

- `KRONARA_OPENROUTER_API_KEY`, `_2`, `_3`: modelos Qwen, Kimi, Nemotron, Hy3.
- `KRONARA_GROQ_API_KEY`, `_2`, `_3`: fallback de modelos en Groq.
- `KRONARA_IMAGE_PROVIDER=placeholder`: pruebas rapidas de video sin SDXL.
- `KRONARA_SD_MODEL_DIR`: pesos SDXL locales para imagen real.
- `KRONARA_SD_LORA_DIR`: LoRA Lightning para imagen rapida.
- `KRONARA_FFMPEG`: ruta alternativa a FFmpeg si no esta en `PATH`.
- `KRONARA_PROGRAM_TEMPLATE_OVERRIDES`: archivo local donde se guardan
  plantillas editadas desde la UI. En desarrollo lo define `OperationsService`
  bajo `.kronara/runtime`.

## Flujo real de generacion

El boton **Crear episodio** ejecuta un solo camino:

```text
Investigacion Reddit/RSS
-> RAG propio
-> Brief editorial
-> Concepto
-> Guion
-> Critica independiente y plantilla del programa
-> Narracion y duracion real
-> Portada, imagenes, musica, SFX y video
-> Guardado en biblioteca local
```

Si algo falla, no se aprueba ni publica a la fuerza. Se usa **Reintentar**.

Codigos importantes:

- `QUALITY_FAILED`: la rubrica narrativa numerica no paso.
- `PROGRAM_QUALITY_FAILED`: el guion no respeto la plantilla del programa
  (por ejemplo, Viernes Paranormal sin amenaza paranormal clara).
- `DURATION_OUT_OF_RANGE`: la voz medida quedo fuera de duracion objetivo.
- `video_status=failed` o `qc_failed`: el guion puede estar guardado, pero el
  video no queda aprobado para publicar.

## Plantillas narrativas y recursos

Hay dos capas:

- Plantillas base de reglas: `python/kronara/program_narrative.py`.
- Plantillas RAG visibles: `knowledge/narrative/program-story-templates.md`.

La UI muestra:

- **Programas > Configuracion**: reglas editables por programa.
- **Programas > Recursos**: moldes/historias de referencia que alimentan al
  RAG y sirven para confirmar que el agente esta mirando el material correcto.

Las historias inspiradas en Reddit no son guiones para copiar. Se guardan como
estructura propia: tipo de arranque, nudos, decision, giro, cierre y anclas
visuales.

## Imagenes, portada, musica y SFX

- La portada premium es obligatoria.
- Las imagenes de escena reciben la portada como referencia visual cuando el
  proveedor lo soporta, para mantener personaje, lugar, paleta y amenaza.
- Los prompts deben usar contexto del guion completo. Si el guion habla de
  agua, muelle o casa antigua, no debe aparecer un desierto sin relacion.
- Musica y SFX aparecen en el detalle del episodio cuando la biblioteca local
  resuelve recursos. Si no hay recurso, se muestran etiquetas faltantes.

## Pruebas antes de subir

Rapidas:

```powershell
npm.cmd test
npm.cmd run build
```

Python enfocadas:

```powershell
python -m pytest tests/test_program_narrative.py tests/test_routed_story_provider.py tests/test_story_engine.py tests/test_visual_production.py tests/test_operations_rpc.py -q
```

Cuando cambies RAG, agentes o generaciones, corre tambien:

```powershell
python -m pytest tests/test_production_content_vertical.py tests/test_reddit_rss.py tests/test_operations_production_rpc.py -q
```

## Reglas de edicion

- No subas `.env`, `.kronara/runtime`, videos generados, pesos de modelos,
  caches ni `node_modules`.
- No copies cuerpos completos de posts externos a memoria promocionada.
- Si agregas un metodo RPC, actualiza:
  - `vite.config.js`
  - `src-tauri/src/sidecar_bridge.rs` si aplica
  - `docs/FUNCIONALIDADES.md`
  - pruebas de contrato.
- Si agregas un agente o skill, actualiza `config/agents`,
  `config/skills/catalog.v1.json` y docs de agentes.
- Si cambias una fase visible, actualiza `src/lib/generation-state.js`,
  `run.diagnostics` y pruebas.

## Depuracion frecuente

- `Failed to fetch`: la web local no pudo hablar con el backend. Revisa que
  `npm.cmd run dev:web` siga vivo.
- Vite cayendo por archivos bloqueados: `src-tauri/target/**` debe estar
  ignorado por el watcher.
- No aparece un episodio: si fallo antes de guardar, mira el run activo y
  usa Reintentar.
- Se ve `PROGRAM_QUALITY_FAILED`: no es guardado; es Critica del programa.
  Revisa la seccion de diagnostico y las reglas que fallaron.

## Push

Antes de push:

```powershell
git status --short
npm.cmd test
npm.cmd run build
```

Haz commit con mensaje claro y sube a `origin/main` solo cuando el repo quede
limpio y las pruebas relevantes pasen.
