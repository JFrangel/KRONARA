# Bugs conocidos y estado real (actualizado 2026-07-21)

## 🔴 Nuevo hallazgo real: SDXL tier premium ~25-35x más lento de lo esperado

Una generación fresca de UNA sola imagen tier `premium` (34 pasos, sin LoRA,
con IP-Adapter cargado) tardó **7 minutos 12 segundos**. El propio docstring
de `image_gen.py` documenta ~12-20s/imagen en tarjeta de 8GB para ese tier --
esta corrida fue 25-35x más lenta que lo documentado.

**Evidencia directa:** el log de progreso por paso muestra degradación
progresiva real, no un bloqueo puntual: pasos 1-17 a ~5-6s/paso (normal para
esta GPU), pasos 26-33 a 20-27s/paso. `nvidia-smi` durante la corrida:
**7836 MiB / 8188 MiB de VRAM (95.7%)**, GPU al 100%. Al matar el proceso,
la VRAM bajó a 657 MiB de inmediato -- confirma que es presión de memoria
del propio proceso (UNet+VAE+IP-Adapter+LoRA cargados a la vez dejan muy
poco margen en una tarjeta de 8GB), no un proceso zombie ni fuga permanente.

**No investigado todavía:** por qué la degradación empieza recién a mitad
de los pasos en vez de ser constante desde el principio, y si
`enable_model_cpu_offload()` (mencionado en el diseño original para casos
de OOM) se está activando aquí o no. Afecta directamente el cálculo de
"videos/día reales con las cuotas gratis actuales" hecho antes en la sesión,
que asumía las cifras del docstring, no esta medición real.

## 🟢 Confirmado con evidencia: las imágenes SÍ quedan en el video final

Verificado end-to-end evitando el costo de generación SDXL (ver hallazgo de
arriba): `ProductionContentPipeline` real, con 3 imágenes SDXL reales ya
generadas (no placeholders) inyectadas vía un `ReplayImageProvider` de
prueba, produjo un MP4 real de 88.8s (1080×1920, H264+AAC, `qc_passed:
true`, `mean_volume: -15.2dB`). Se extrajeron fotogramas reales en 5s, 40s
y 80s del video final y se inspeccionaron visualmente: las imágenes SDXL
reales aparecen correctamente compuestas, con subtítulos quemados
sincronizados al texto exacto de la narración en ese instante. No es un
supuesto ni una imagen de referencia aislada -- es el fotograma real
extraído del MP4 final.

Documento vivo: qué se arregló, qué sigue roto, qué bloquea qué. Léase junto a
[`docs/DIAGNOSTICO_PIPELINE_REAL.md`](DIAGNOSTICO_PIPELINE_REAL.md) (narrativa
detallada del transporte stdio) y [`GAP_ANALYSIS.md`](GAP_ANALYSIS.md)
(checklist de release).

## Estado actual de los bloqueos

Los bloqueos descritos más abajo sobre el sidecar y las dependencias visuales
son el registro histórico de la revisión inicial. Ya se reconstruyó el
ejecutable el 21-07-2026 y el stack SDXL quedó instalado en D. La única
verificación pendiente es abrir el ejecutable Tauri completo y reproducir allí
un MP4 real; la previsualización Vite y el sidecar por separado ya fueron
verificados.

**Confirmación adicional (independiente del punto anterior):** se relanzó el
binario nuevo (`kronara-sidecar-x86_64-pc-windows-msvc.exe`, 21-07-2026
20:42) y se le mandaron peticiones JSON-RPC reales por stdio otra vez, igual
que en la revisión inicial que encontró los bugs:
- `programs.list` → ahora devuelve los 7 programas reales (antes:
  `FileNotFoundError`). Bug de `resource_root()` confirmado arreglado en el
  binario empaquetado, no solo en el código fuente.
- `action.approve` → ahora responde `invalid params: 'idempotency_key'`
  (falta el parámetro, como se esperaba al mandar `{}`) en vez de
  `method not found`. El método existe y responde en el binario empaquetado.

Sigue pendiente solo lo que dice el párrafo de arriba: reproducir un MP4
real dentro de la ventana de escritorio de Tauri (no solo por RPC directo).

## 🔴 Bloqueante: el binario empaquetado del sidecar está desactualizado

**`src-tauri/binaries/kronara-sidecar-x86_64-pc-windows-msvc.exe`** (2.7 GB,
compilado 2026-07-20 23:39) es la versión que corre la app de escritorio real.
Fue construido ANTES de todo lo hecho hoy (2026-07-21). Mientras no se
reconstruya, la app real seguirá fallando aunque el código fuente ya esté
arreglado.

**Confirmado directamente** (no supuesto): se lanzó el binario real y se le
mandaron peticiones JSON-RPC reales por stdio.
- `action.approve` → `{"error":{"code":-32601,"message":"method not found"}}`
  — el binario no tiene la función de aprobar-crear-episodio del asistente.
- `programs.list` → `FileNotFoundError` buscando
  `%TEMP%\config\programs\programs.v1.json` — bug real de resolución de rutas
  (ver siguiente sección), ya arreglado en el código fuente pero NO en este
  binario.

**Por qué no se reconstruyó ya:** PyInstaller necesita el entorno Python
completo (torch/diffusers/numpy) para no perder la generación de imágenes
SDXL. El `python` por defecto de este entorno NO tiene esas librerías
instaladas ahora mismo (`ModuleNotFoundError: No module named 'numpy'`), así
que reconstruir aquí produciría un binario peor (sin imágenes/video real) que
el actual. Reconstruirlo bien necesita el mismo entorno (venv/Python) que se
usó para el build de ayer, o instalar el stack completo de nuevo (varios GB,
varios minutos) — decisión que le corresponde al usuario, no algo para hacer
a ciegas.

**Cómo reconstruirlo cuando se tenga el entorno correcto:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-sidecar.ps1
```

## 🟢 Arreglado hoy: rutas de recursos rotas bajo el binario empaquetado

`programs.py`, `visual_style.py`, `reddit_source_map.py` y
`narrative_workflow.py` calculaban su carpeta `config/`/`knowledge/` cada uno
por su cuenta con `Path(__file__).resolve().parents[2]`. Correcto en
desarrollo, pero bajo PyInstaller ese `__file__` vive dentro de la carpeta de
extracción `_MEIxxxxxx`, y subir dos niveles desde ahí se sale del paquete y
cae en `%TEMP%` directo, que no tiene `config/`. `sidecar.py` ya sabía
resolver esto bien (mirando `sys._MEIPASS`) pero solo para sí mismo.

**Efecto real que esto tenía** (mientras el binario viejo siga en uso):
`programs.list` falla → Programas/Panel/Calendario no cargan nada.
`content.run` falla al construir el mapa de sensibilidad de Reddit → CADA
creación de episodio falla, botón o chat. Es decir: esto es, muy
probablemente, la causa real de "el botón de Asistente/Generar programa no
funciona".

**Arreglo:** un único `resource_root()` compartido
(`python/kronara/resource_root.py`), usado en los 5 sitios. Cubierto por
`tests/test_resource_root.py`, que simula el modo frozen con
`monkeypatch.setattr(sys, "_MEIPASS", ...)` — el único test de todo el suite
que corre en ese modo, por eso el bug pasó desapercibido en 450+ tests
verdes. **Completo en el código; falta el rebuild del binario (ver arriba)
para que llegue a la app real.**

## 🟡 Sin verificar: reproducción de video en la app real

Verificado: la lógica de `assetSrc()`/`<video>` funciona correctamente contra
un mock de navegador (el elemento `<video>` real se crea con `src`/`poster`
correctamente transformados a `asset://`). **NO verificado**: reproducir un
MP4 real generado por el pipeline, dentro de la app de escritorio real —
necesita el rebuild del binario primero, y luego que el usuario cree un
episodio real y lo reproduzca.

## 🟢 Resuelto: numpy/torch/diffusers ya están instalados

Ya no faltan. `torch 2.13.0+cu126` (con CUDA), `diffusers 0.39.0`, `numpy
2.5.1` y `PIL 12.3.0` están instalados en el `python` que resuelve por
defecto en este shell. Los 16 tests de `test_image_gen.py` pasan. Se generó
una imagen SDXL real de prueba (`.kronara/runtime/real_generation_test/`) y
se inspeccionó visualmente: calidad cinematográfica real (teléfono antiguo
en una mesa con luz de ventana, puerta entreabierta con niebla), sin señales
de degradación. Sigue faltando solo **PyInstaller** para el rebuild del
binario (sección roja de arriba) — eso es lo único que aún bloquea #50.

## 🔴 Encontrado y arreglado hoy: audio de narración completamente silencioso

**Esta era la causa real de "el audio no se está generando como debería".**
El paquete `edge-tts` (declarado en `pyproject.toml` como dependencia
opcional del grupo `media`, ya usado en todo el código) **no estaba
instalado**. `EdgeTtsVoiceProvider.synthesize()` lo importa dentro de un
`try/except ImportError` y, al fallar, `FallbackVoiceProvider` capturaba el
error silenciosamente y usaba `EstimatingVoiceProvider` -- que no sintetiza
nada: genera un MP3 de **silencio puro** vía
`ffmpeg -f lavfi -i anullsrc=r=24000:cl=mono` durante la duración estimada,
y marca el resultado `degraded=True` (una señal que hoy no se muestra en
ninguna parte de la UI). El video terminaba de "generarse" con éxito --
imágenes, subtítulos y estructura correctos -- pero **sin ninguna voz real**.

**Arreglo:** `pip install "edge-tts>=7,<8"` (el mismo paquete y versión ya
declarados en `pyproject.toml`). Verificado con una síntesis real después de
instalar: `EdgeTtsVoiceProvider` devuelve `degraded=False`, 12
`word_boundaries` reales, un MP3 de 25 KB con contenido real (no silencio).

**Pendiente de decisión (no se hizo hoy):** exponer `degraded` en la
metadata guardada del episodio y en la UI, para que un audio-de-respaldo
silencioso nunca vuelva a pasar desapercibido como si fuera narración real.

**Suite completa tras instalar edge-tts + confirmar torch/diffusers:**
`python -m pytest` → **483 passed, 1 skipped**, ~4 min (antes: 452 passed,
15 skipped -- los que ahora corren de verdad son los de SDXL/GPU real).

## 🟢 Aclarado: "las cosas se generan en la carpeta del programa en el disco D"

No es un bug del pipeline de producción. `scripts/create_fresh_visual_story.py`
(script nuevo, no forma parte de `content.run` ni de la app real) escribe
deliberadamente su salida en `<raíz del repo>/.kronara/runtime/<story_id>/` --
que, al estar el repo en `D:\Proyecto Redit`, cae en el disco D. Es un
fixture de desarrollo para generar un episodio de muestra sin depender de
créditos de modelos ni de la app empaquetada; `.kronara/` está en
`.gitignore` (línea 8), así que no hay riesgo de que termine en un commit.
El pipeline real (`content_pipeline.py` vía `content.run`) siempre escribe
bajo el `data_dir` real que Rust pasa por `--data-dir` -- nunca una ruta
relativa al repo.

## Gaps conocidos, no bugs (diseño deliberado, documentado)

- `content.run` es síncrono, sin `%` de progreso en vivo — evitado a propósito
  por una condición de carrera real en el stdio compartido (ver
  `content_pipeline.py` y el resumen de la sesión). El progreso en vivo solo
  existe hoy para el flujo de prueba viejo `story.test`.
- El intent `set_budget` del chat se propone pero nunca se ejecuta (a
  diferencia de `create_episode`, que sí tiene approve+execute reales) — gap
  preexistente, no se tocó esta sesión.
- Personajes/Recursos/Analíticas (en Programas y en Episodios) muestran
  mensajes honestos de "no conectado todavía" en vez de datos falsos —
  intencional, no pendiente de arreglo, pendiente de conexión real.

## Qué se hizo en la sesión de hoy (2026-07-21), en orden

1. Generación de imagen de portada por episodio + arreglo de un bug de orden
   (el video se guardaba en memoria pero nunca en el metadata persistido).
2. Protocolo `asset://` de Tauri habilitado (CSP + feature de Cargo) para
   servir imágenes/video reales al webview.
3. Portadas visibles en Panel y en las tarjetas/detalle/tabla de Programas.
4. Reproducción real de episodio (`<video controls>`) en el panel de detalle
   de Programas.
5. Las 7 pestañas de detalle de Programa son reales (antes solo Resumen);
   Calendario y Configuración muestran datos reales del programa.
6. Estudio: Resumen/Guion/Exportaciones ahora muestran señal investigada,
   señales descartadas, QC de duración/originalidad/calidad y detalle de QC
   de video — todo ya existía en la respuesta de `content.run`, solo no se
   mostraba.
7. El asistente de chat puede proponer crear un episodio nombrando un
   programa real; nuevo RPC `action.approve` lo ejecuta de verdad (antes solo
   se proponía y no pasaba nada al aprobar).
8. **Bug crítico de rutas de recursos encontrado y arreglado** (ver arriba).
9. Logo real de Kronara (`src-tauri/icons/kronara.svg`) en la barra lateral,
   reemplazando el cuadrado placeholder con una "K".
10. Nuevo RPC `episodes.get`: el guion completo de cualquier episodio guardado
    es visible en una pestaña "Guion" real dentro del detalle del episodio,
    junto con Recursos/Producción/Distribución/Analíticas.

## Qué falta (tareas #50, #53-59 en el tracker de la sesión)

- **#50 — Reconstruir el binario del sidecar** (bloqueante para que todo lo
  de hoy exista en la app real). El bloqueo se redujo hoy: torch/diffusers/
  numpy/edge-tts ya están instalados en este entorno; solo falta
  `pip install pyinstaller` y correr `scripts/build-sidecar.ps1`.
- #53-56 — Pulido visual de Panel/Calendario/Configuración/sidebar de
  Programa para acercarse a las capturas de referencia del usuario.
- #57 — Verificar reproducción de video con un MP4 real (post-rebuild).
- #58 — Auditar y documentar las rutas de almacenamiento en disco.
- #59 — Documentación de cómo arrancar el proyecto desde cero.
- #33-35 — Publicación real en redes (Facebook/YouTube/Spotify/TikTok).
- #34 — Orquestación completa del Agente B (langgraph).

## 🟢 Arreglado en fuente: previsualización web y reproducción por rangos

La interfaz conserva `asset://` mediante Tauri en la aplicación de escritorio.
Cuando se abre con Vite en `localhost`, `assetSrc()` usa el endpoint local
`/__kronara_asset` para servir únicamente `.kronara/runtime/**`.

Ese endpoint valida la ruta, devuelve el tipo MIME correcto y soporta `Range`
(respuestas `206 Partial Content`), requisito para que un `<video>` pueda
obtener metadatos, avanzar y buscar posiciones dentro del MP4. El panel de
episodios usa `controls`, `preload="metadata"`, `playsinline` y muestra la
portada si el navegador informa un error de carga.

Esto arregla la entrega de archivos en la previsualización de desarrollo. La
verificación de la aplicación empaquetada sigue dependiendo de reconstruir el
sidecar actualizado descrito en el bloque rojo de este documento.

## 🟢 Verificado en esta ronda: historia nueva y reproductor web

La vista previa local ya no fabrica un episodio por cada programa. Contiene
una única historia nueva de `Viernes Paranormal`, generada con el
`ProductionContentPipeline` local, guardada en su propio directorio y enlazada
al MP4 que realmente se reproduce. `content.run` permanece bloqueado en modo
preview, por lo que esta validación no ejecuta agentes productivos ni publica.

El MP4 final verificado mide 88,8 s, tiene 1080×1920, audio AAC, seis escenas,
18 tomas y QC aprobado. También se corrigieron la tarjeta visual blanca, los
subtítulos sobredimensionados y la repetición de una misma narración en todas
las escenas. La prueba del navegador confirmó `readyState=4`, sin error, y
avance de reproducción con el control de teclado.
## Actualización posterior: SDXL local y sidecar reconstruido

El bloqueo de dependencias visuales quedó resuelto el 21 de julio de 2026:

- Python tiene `numpy`, PyTorch `2.13.0+cu126`, `diffusers`, `transformers`, `accelerate`, `peft`, `safetensors` y Pillow.
- CUDA está operativo en la `NVIDIA GeForce RTX 4060 Ti`.
- Los pesos SDXL base (6,9 GB) y el LoRA SDXL-Lightning (394 MB) viven en `D:\Proyecto Redit\.kronara\models`.
- Las rutas premium y rápida generaron imágenes 768×1344 reales con `degraded=False`.
- El sidecar fue reconstruido con PyInstaller y respondió correctamente al handshake, `operations.context` y `programs.list`.

Sigue pendiente una comprobación manual dentro del ejecutable Tauri completo (no solo el navegador Vite) para confirmar que el `<video>` reproduce después de iniciar la aplicación empaquetada. La generación visual ya está lista en el sidecar nuevo; el modelo se lee desde D y no se copia dentro del ejecutable.
