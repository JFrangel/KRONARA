# Vertical: tendencia a blueprint

## Flujo implementado

```text
Reddit OAuth (authority connector)
→ hot posts metadata
→ ephemeral SourcePost
→ TrendSignal reference_only (body discarded)
→ opportunity selection by velocity
→ FTS5 + sqlite-vec + graph expansion
→ RRF and cited context packet
→ Qwen/Kimi through OpenAI-compatible JSON Schema
→ originality comparison against source hint
→ NarrativeConcept@1
→ ten-stage NarrativeBlueprint@1
→ LangGraph SQLite checkpoints
```

`RedditClient` contiene la mecánica OAuth comprobable, pero el despliegue final debe ejecutarla como tool de autoridad para que el sidecar no reciba secretos. El método RPC `trend.extract` ya separa la extracción cognitiva y devuelve únicamente campos seguros.

## Política de datos

- `selftext` vive únicamente durante la llamada y nunca entra al índice.
- `reference_only` no se inserta en FTS5 ni en `sqlite-vec`.
- El contexto del modelo recibe un `theme_hint`, URI y conocimiento editorial propio.
- El prompt prohíbe reutilizar redacción, personajes o secuencia de eventos.
- Una similitud normalizada igual o superior a `0.82` bloquea el concepto.

## Configuración pendiente para red real

- Aplicación Reddit aprobada para el uso previsto.
- `client_id`, `client_secret` y user-agent almacenados por la autoridad Rust.
- Subreddits permitidos, frecuencia, presupuesto y retención configurados.
- Alias Qwen/Kimi y API key de un endpoint OpenAI-compatible.

