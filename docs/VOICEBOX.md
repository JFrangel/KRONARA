# VoiceBox — voz clonada (Kronara v0.8, Fase 2)

VoiceBox ([github.com/jamiepine/voicebox](https://github.com/jamiepine/voicebox),
MIT) es la **voz principal** de Kronara desde v0.8. Reemplaza a edge-tts: clonas
tu voz una vez y cada programa narra con esa identidad. Es un servidor
FastAPI que corre **en tu equipo** (gratis, sin cuota por episodio).

Si VoiceBox no está corriendo, la generación **no se cae**: cae al estimador
silencioso (`EstimatingVoiceProvider`) como respaldo anti-crash — el video sale,
pero sin voz audible hasta que levantes el servidor.

## Requisito importante: Python 3.12

Los paquetes ML de VoiceBox (PyTorch y motores TTS) **no soportan Python 3.14**
(el intérprete por defecto de este equipo). Instala Python 3.12 solo para el venv
de VoiceBox; Kronara sigue usando el suyo.

## Instalar y correr (solo el backend)

Kronara solo necesita el **backend** de VoiceBox (la API en `:17493`), no la app
de escritorio Tauri.

```bash
git clone https://github.com/jamiepine/voicebox
cd voicebox
py -3.12 -m venv backend/venv
backend/venv/Scripts/python -m pip install --upgrade pip
backend/venv/Scripts/python -m pip install -r backend/requirements.txt
# GPU NVIDIA (opcional, recomendado): instala torch CUDA antes de requirements
#   backend/venv/Scripts/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
backend/venv/Scripts/python -m uvicorn backend.main:app --port 17493
```

Los modelos se **auto-descargan** en el primer `/generate` (varios GB). Docs de la
API en `http://127.0.0.1:17493/docs`. Con `just` instalado, el atajo equivalente
es `just dev-backend`.

## Clonar tu voz

1. Levanta VoiceBox (arriba) y abre su app/`/docs`.
2. Crea un *profile* subiendo unos segundos de audio de referencia (clonación
   zero-shot), o usa uno de los 50+ presets.
3. Copia el `id` del profile. En Kronara aparece en **Configuración → Voces**.

## Configurar Kronara

Variables de entorno (en tu `.env`):

| Variable | Default | Qué hace |
|---|---|---|
| `KRONARA_VOICEBOX_URL` | `http://127.0.0.1:17493` | URL del servidor VoiceBox |
| `KRONARA_VOICEBOX_PROFILE` | *(vacío)* | `id` del profile (voz) por defecto |
| `KRONARA_VOICEBOX_LANGUAGE` | `es` | Idioma de síntesis |
| `KRONARA_VOICEBOX_ENGINE` | *(default de VoiceBox: `qwen`)* | Motor TTS |

Sin `KRONARA_VOICEBOX_PROFILE`, el provider usa el `voice_id` por-programa como
`profile_id`; si tampoco hay, la síntesis falla y cae al estimador.

## Cómo lo usa Kronara (contrato)

`VoiceBoxVoiceProvider` ([`python/kronara/voice.py`](../python/kronara/voice.py)):

1. `POST /generate {profile_id, text, language}` → devuelve un `id` (async).
2. Poll `GET /audio/{id}` (404 mientras renderiza) hasta recibir el audio.
3. La duración se mide del audio real con **ffprobe** (misma fuente de verdad que
   el resto del pipeline), no se confía en el campo del API.
4. Devuelve `degraded=False` con el `.wav` guardado en el `audio_dir` de runtime.

`FallbackVoiceProvider(VoiceBox, Estimating)` garantiza que un servidor caído o
sin instalar nunca rompa `content.run`.

## Verificación

- **Configuración → Voces** muestra "VoiceBox conectado" y lista tus profiles.
- Una generación real produce narración con tu voz clonada (`degraded=False`).
- Con el servidor apagado: la pestaña muestra la guía de setup y la generación
  degrada al estimador sin crashear.
