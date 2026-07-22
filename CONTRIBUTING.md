# Colaborar en Kronara

## Instalación rápida

```powershell
npm.cmd install
python -m pip install -e ".[dev]"
python -m pip install edge-tts
npm.cmd run dev:web
```

Instala FFmpeg/ffprobe y deja ambos en `PATH`. Copia `.env.example` a `.env` y completa solo las claves que usarás.

## Para video real

- Voz: `edge-tts` instalado y red disponible.
- Render: FFmpeg/ffprobe.
- Imagen real: pesos SDXL locales con `KRONARA_SD_MODEL_DIR`; para pruebas rápidas usa `KRONARA_IMAGE_PROVIDER=placeholder`.
- Modelos: claves OpenRouter/Groq/Kimi/Qwen según `.env.example`.

## Flujo antes de subir

```powershell
npm.cmd run build
python -m pytest tests/test_program_narrative.py tests/test_routed_story_provider.py tests/test_story_engine.py tests/test_visual_production.py tests/test_operations_rpc.py
```

Las plantillas narrativas base están en `python/kronara/program_narrative.py`.
Los cambios manuales desde la UI se guardan en el runtime local y no deben
subirse como configuración global.
