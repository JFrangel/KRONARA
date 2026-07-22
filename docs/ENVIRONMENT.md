# Entorno y secretos

1. Copie `.env.example` como `.env` en la raíz del proyecto.
2. Complete solo las claves de proveedores que va a usar.
3. Mantenga `*_ENABLED=false` hasta tener autorización, sandbox y pruebas de fallo.
4. Nunca versiona `.env`; Git lo ignora.

## Instalación local recomendada

```powershell
npm.cmd install
python -m pip install -e ".[dev]"
python -m pip install edge-tts
npm.cmd run dev:web
```

Instale también FFmpeg/ffprobe y deje ambos binarios en `PATH`. Para imagen real local, descargue o apunte los pesos SDXL con `KRONARA_SD_MODEL_DIR`; para iterar sin GPU use `KRONARA_IMAGE_PROVIDER=placeholder`.

## Variables relevantes

| Grupo | Variables |
|---|---|
| Límites | `KRONARA_MAX_DAILY_COST_USD`, `KRONARA_MAX_RESEARCH_COST_USD` |
| Modelos | `KRONARA_QWEN_*`, `KRONARA_KIMI_*`, `KRONARA_OPENROUTER_*`, `KRONARA_GROQ_*` |
| Registro | `KRONARA_MODEL_REGISTRY`, `KRONARA_NEMOTRON_MODEL`, `KRONARA_HY3_MODEL` |
| RAG | `KRONARA_EMBEDDING_*`, `KRONARA_RERANKER_*` |
| Reddit | `KRONARA_REDDIT_ENABLED`, `KRONARA_REDDIT_CLIENT_ID`, `KRONARA_REDDIT_CLIENT_SECRET`, `KRONARA_REDDIT_CONTRACT_REFERENCE` |
| Meta | `KRONARA_META_ENABLED`, `KRONARA_META_PAGE_ID`, `KRONARA_META_PAGE_TOKEN` |
| Azure Speech | `KRONARA_AZURE_SPEECH_ENABLED`, `KRONARA_AZURE_SPEECH_KEY`, `KRONARA_AZURE_SPEECH_REGION` |
| Imagen/video | `KRONARA_IMAGE_PROVIDER`, `KRONARA_SD_MODEL_DIR`, `KRONARA_SD_LORA_DIR`, `KRONARA_FFMPEG` |
| Plantillas | `KRONARA_PROGRAM_TEMPLATE_OVERRIDES` |

Rust carga y redacta las credenciales. El sidecar recibe solamente el token efímero de RPC y un entorno limpio; no recibe las claves de proveedores. En producción, reemplace `.env` por el almacén de credenciales de Windows o un servicio equivalente controlado por Rust.

Reddit solo puede activarse cuando existen credenciales oficiales y una referencia contractual verificable. Configurar una variable no habilita scraping ni uso comercial de historias de usuarios.

Las plantillas manuales de programa se guardan por defecto en el runtime local (`program_narrative_templates.v1.json`). No contienen secretos; son reglas editoriales que el agente usa como contrato narrativo.
