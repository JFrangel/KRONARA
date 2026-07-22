# Kronara OS v0.6

Kronara es una fábrica editorial local-first para Windows. Su propósito es investigar oportunidades permitidas, crear historias originales, evaluar su calidad y aprender de resultados sin copiar fuentes ni ampliar sus propios permisos.

**Novedades v0.6 (cerebro):** motor narrativo a nivel literario (oficio: mostrar-no-contar, sensorial, subtexto, ritmo), Nemotron 3 **Ultra** (1M contexto) + alias `critic`, **memoria de grafo bitemporal** con continuidad de **series multi-parte**, **voz real (edge-tts)** que mide la **duración real** de la narración, y **scheduler + autonomía** para que los agentes trabajen solos. Contrato para el frontend en [`docs/FUNCIONALIDADES.md`](docs/FUNCIONALIDADES.md).

**Integración verificada en vivo:** narración real con edge-tts, **render de video FFmpeg** (Reel 9:16 con subtítulos quemados, QC aprobado de punta a punta), **embeddings semánticos reales** (fastembed ONNX, sin torch) y **publicación gobernada e idempotente** (la publicación en vivo requiere una Página Meta autorizada). El estado práctico está resumido abajo para la web local.

## Estado real

| Capacidad | Estado | Evidencia principal |
|---|---|---|
| Chat operativo y trazas visibles | Implementado | `tests/test_operations_rpc.py` |
| 24 agentes y 35 habilidades | Implementado | `config/agents`, `config/skills/catalog.v1.json` |
| Vertical Reddit → historia propia | Implementado y trazable | `tests/test_production_content_vertical.py` |
| Historia propia con crítica, originalidad, duración y recuperación | Implementado | `tests/test_story_duration_qc.py` |
| RAG v3: FTS5, vectores, grafo, filtros y promoción reversible | Implementado | `tests/test_story_learning_pipeline.py` |
| Reddit RSS/OAuth y filtros | Implementado; activación sujeta a credenciales y términos | `tests/test_production_content_vertical.py` |
| Qwen, Kimi, Groq, Nemotron Super/**Ultra** y Hy3 | Inferencia por puente web local con fallback; alias `critic` | `frontend-tests/local-web.test.js` |
| Plantillas/historias RAG editables en Recursos | Implementado | `knowledge/narrative/program-story-templates.md`, `tests/test_operations_rpc.py`, `frontend-tests/local-web.test.js` |
| Motor narrativo literario (oficio + rúbrica) | Implementado | `tests/test_narrative_craft.py` |
| Memoria de grafo bitemporal + series multi-parte | Implementado | `tests/test_graph_memory.py`, `tests/test_series.py` |
| Voz real (edge-tts) y **duración medida** | Medición integrada; síntesis en vivo requiere binario edge-tts | `tests/test_voice_duration.py` |
| Scheduler + autonomía (agentes desatendidos) | Implementado | `tests/test_schedule.py` |
| BGE-M3 y reranker BGE | Carga local productiva; degradación explícita si faltan pesos | `tests/test_production_embeddings.py` |
| Métricas Meta y aprendizaje | Lectura versionada y promoción prudente implementadas | `tests/test_performance_learning.py` |
| Voz real y FFmpeg local | Integrado en web local; requiere binarios en `PATH` | `tests/test_voice_duration.py`, `tests/test_visual_production.py` |
| Whisper y publicación Meta Reels | Pendiente | README, sección de fallos |
| Fine-tuning automático | Bloqueado por diseño | `tests/test_story_reuse.py` |

`full_auto` es el modo previsto, pero no elimina compuertas: derechos, originalidad, presupuesto, credenciales, políticas, calidad de render y ambigüedad remota bloquean el avance. Kronara ya crea historias propias desde señales abstractas y puede generar/reproducir un Reel local; la primera publicación real en Facebook todavía requiere una Página sandbox autorizada, upload y reconciliación remota.

## Uso local web

Requisitos recomendados en Windows:

- Node.js 20+ y npm.
- Python 3.12+ con `pip`.
- FFmpeg/ffprobe en `PATH` para render, mezcla, QC y video.
- `edge-tts` para voz neural real; sin esto el sistema puede degradar a medición estimada.
- Pesos locales SDXL si se quiere imagen real con Diffusers; sin pesos se puede usar el proveedor placeholder para pruebas.
- Claves de modelos en `.env` para generación real; Reddit OAuth es opcional porque existe fallback RSS gobernado.

```powershell
npm.cmd install
python -m pip install -e ".[dev]"
python -m pip install edge-tts
npm.cmd run dev:web
```

### Primer arranque paso a paso

1. **Clona el repo** e instala como arriba. Requisitos duros: Node 20+, Python 3.12+, ffmpeg/ffprobe en PATH.
2. **Copia `.env.example` a `.env`** y llena al menos una clave de modelo (OpenRouter, Groq o Qwen). Sin ninguna, la generación no puede pasar de la etapa de guion.
3. **(Opcional pero muy recomendado)** Agrega credenciales de proveedores de imagen gratuitos:
   - `KRONARA_POLLINATION_API_KEY` (o el spelling original `KNORA_POLLINATION_API_KEY`) — Pollinations.ai, gratis sin registro, ~5-10s por imagen.
   - `KRONARA_CLOUDFLARE_ACCOUNT_ID` + `KRONARA_CLOUDFLARE_API_TOKEN` — Cloudflare Workers AI Flux, gratis con cuenta, ~3s por imagen, 10 000 Neurons/día.
   - Si ambas están presentes el pipeline las usa en cascada (Pollinations → Cloudflare → SDXL local → placeholder). Con ninguna, cae a SDXL local (necesita pesos en `.kronara/models/sdxl-base-1.0/` y ~7min por imagen en tarjeta de 8GB VRAM).
4. **Arranca la web local**: `npm.cmd run dev:web` (o `npm.cmd run dev`). El comando `predev` mata primero cualquier sidecar huérfano de sesiones anteriores. Vite spawn el sidecar Python automáticamente en `stdin/stdout`.
5. **Abre `http://localhost:5173`** en tu navegador (Chrome/Edge). Ya no se necesita ventana nativa Tauri — todo funciona en el navegador.
6. **Crea el primer episodio**: Programas → clic en cualquier programa (ej. Viernes Paranormal) → **Crear episodio**. Con `wait:false` el backend devuelve enseguida y el frontend polea `run.progress` cada 3s, así que ves el progreso real (no el timer falso viejo).
7. **Duración esperada** con la cascada de imágenes hosted: 5-10 minutos para un episodio típico (6 escenas, 18 tomas). Sin hosted providers y solo SDXL local: 20-60 minutos.
8. **Video final**: aparece en `.kronara/runtime/artifacts/video/<story_id>/<story_id>.mp4` y se muestra en Programas → detalle del episodio → **Ver en Estudio** (reproductor embebido).
9. **Si algo falla**: revisa el log en `.kronara/runtime/sidecar-stderr.log` y usa el botón **Abandonar** en Programas para limpiar el estado local antes de reintentar. Con la cascada activa, casi cualquier problema de red en un proveedor cae automáticamente al siguiente.

### Providers de imagen (para probar por separado)

```powershell
# Forzar solo Pollinations
$env:KRONARA_IMAGE_PROVIDER = "pollinations"; npm.cmd run dev:web

# Forzar solo Cloudflare Workers AI
$env:KRONARA_IMAGE_PROVIDER = "cloudflare"; npm.cmd run dev:web

# Forzar solo SDXL local (lento)
$env:KRONARA_IMAGE_PROVIDER = "sdxl"; npm.cmd run dev:web

# Placeholder ilustrado sin GPU/red (rápido para debugging)
$env:KRONARA_IMAGE_PROVIDER = "placeholder"; npm.cmd run dev:web

# Modo por defecto: cascada (todos los que tengan creds, en orden)
$env:KRONARA_IMAGE_PROVIDER = "cascade"; npm.cmd run dev:web
```

Ver [`docs/PROCESO_GENERACION_CONTENIDO.md`](docs/PROCESO_GENERACION_CONTENIDO.md) para el detalle de las 8 etapas del pipeline, y [`docs/BUGS_CONOCIDOS.md`](docs/BUGS_CONOCIDOS.md) para hallazgos abiertos.

Abre `http://127.0.0.1:5173/`. Esa es la ruta recomendada: la interfaz web llama al sidecar Python por `__kronara_rpc` y sirve medios locales por `__kronara_asset`. No hay datos falsos; si Python o las claves no responden, la app muestra el fallo.

En Programas > Configuración cada programa expone su plantilla narrativa de reglas. Si se guarda manualmente, queda en el runtime local y las siguientes generaciones usan esa versión para aprobar o bloquear. En Programas > Recursos se ven y editan las historias/plantillas RAG del programa; puedes pegar historias completas, guardarlas manualmente y el sidecar las reinyecta en `program_story_templates_v1` para las próximas generaciones. La producción visual usa la portada premium como referencia de continuidad para las imágenes de escena, además del contexto completo del episodio. En Episodios > Recursos se muestran visuales, música y SFX resueltos o faltantes.

Si una generación falla:

- `QUALITY_FAILED` significa que la rúbrica narrativa no aprobó.
- `PROGRAM_QUALITY_FAILED` significa que el guion no cumplió la plantilla del programa; se muestra como fallo de Crítica, no de Guardando.
- `DURATION_OUT_OF_RANGE` significa que la voz medida quedó fuera de la duración objetivo.
- Un video `failed` o `qc_failed` no se aprueba: se reintenta desde la UI.

Para validar cambios:

```powershell
npm.cmd test
npm.cmd run build

python -m pip install -e ".[dev]"
python -m pytest -q --basetemp=.test-tmp
```

Copie `.env.example` a `.env`; ese archivo no se versiona. No pegue claves en el chat, documentación ni commits.

## Arquitectura

```text
Svelte web local ── __kronara_rpc / __kronara_asset ──> Python cognitive sidecar
                                                        agentes, modelos, RAG,
                                                        memoria, render y episodios
```

Vite levanta el sidecar Python en desarrollo, carga `.env` localmente y mantiene una lista cerrada de métodos permitidos. La UI muestra resúmenes y argumentos redactados, nunca razonamiento privado ni secretos.

## Documentación

- [Funcionalidades por función (para el frontend)](docs/FUNCIONALIDADES.md)
- [Proceso de generación de contenido, paso a paso](docs/PROCESO_GENERACION_CONTENIDO.md)
- [Memoria y RAG](docs/MEMORY_AND_RAG.md)
- [Entorno](docs/ENVIRONMENT.md)
- [Colaborar / instalación de desarrollo](CONTRIBUTING.md)
