# Publicación en redes vía Postiz (agregador, auto-hospedado local)

Kronara publica a las redes con **un solo agregador**: **Postiz** (open-source,
gratis, auto-hospedable). Una sola API key publica a FB/IG/TikTok/YouTube/Reddit/
Threads/etc., evitando el OAuth y la auditoría de cada plataforma. Los agentes de
Kronara (packaging, community, Pulse) ya están listos para enchufarse.

## 1. Hospedar Postiz local (Docker)

Requiere Docker + ~2-4 GB RAM (levanta 6-9 contenedores). La compose oficial
expone el backend en `http://localhost:4007`.

```bash
# Ver docs oficiales para el docker-compose completo:
# https://docs.postiz.com  (self-hosting)
docker compose up -d
```

Abre `http://localhost:4007`, crea tu cuenta local y **conecta tus redes** desde
la UI de Postiz (ahí completás el OAuth de cada plataforma — eso lo hacés vos).

## 2. Conectar Kronara a tu Postiz

En `.env`:

```
POSTIZ_URL=http://localhost:4007
KRONARA_AGGREGATOR_API_KEY=<tu API key de Postiz>
```

La API key se copia desde **Postiz → Settings → API Key**. Kronara la usa contra
`{POSTIZ_URL}/public/v1` con el header `Authorization: <apiKey>` (la autoridad Node
es la única que la lee; nunca se muestra en la interfaz).

## 3. Cómo publica Kronara

La autoridad (`vite.config.js`) implementa `publication.publish`:
- `GET /public/v1/integrations` → mapea la plataforma pedida a tu canal conectado.
- `POST /public/v1/upload` → sube el MP4 del episodio (solo archivos bajo `.kronara`).
- `POST /public/v1/posts` (`type:"now"`) → crea el post con la descripción/hashtags
  que arma el agente de packaging.

Sin `KRONARA_AGGREGATOR_API_KEY`, `publication.publish` devuelve `not_configured`
(no se afirma que se publica). La gobernanza de autonomía (`policy.py`) decide
**cuándo** se dispara una publicación.

## Nativo (alternativa)

Si preferís sin intermediario: Meta Graph (FB+IG), YouTube Data API (Google) y
TikTok Content Posting API (auditoría 1-2 semanas). Más control, mucho más setup.
Ver la tabla comparativa en el chat / [INTEGRATIONS.md](INTEGRATIONS.md).

## Verificación

El primer `publish` real se prueba contra **tu** Postiz corriendo: crea un
episodio, y desde la UI de Publicación (o el agente) dispara la publicación a un
canal de prueba. Hasta tener Postiz arriba, Kronara reporta `not_configured` con
honestidad.
