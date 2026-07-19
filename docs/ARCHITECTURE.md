# Kronara v0.2 — Arquitectura

## Límites de autoridad

```text
Svelte/Tauri UI
    │ comandos y eventos
Rust Authority Plane
    ├── policy, jobs, secrets, filesystem, FFmpeg, publication
    └── authenticated JSON-RPC
            │
Python Cognitive Sidecar
    ├── LangGraph + SQLite checkpoints
    ├── agents + model router + Guardian
    ├── hybrid retrieval + memories
    └── plans and effect requests (never raw effects)
```

Rust es la única capa autorizada para efectos irreversibles. Python produce solicitudes declarativas; Rust vuelve a validar política, idempotencia, presupuesto y estado remoto. El token RPC es efímero, se entrega al proceso hijo y nunca se registra.

## Grafo cognitivo

El workflow objetivo conserva nodos explícitos:

1. Opportunity Intelligence.
2. Editorial Decision.
3. Research and Rights.
4. Story Architecture.
5. Writing Room.
6. Production Direction.
7. Automated QC.
8. Packaging and Distribution.
9. Performance Learning.

Cada transición crea evento y checkpoint. Un reinicio reanuda desde el último estado confirmado. El máximo de pasos y las herramientas se definen por tarea; ningún agente invoca shell.

## Persistencia

- SQLite: fuente transaccional, eventos, checkpoints, publicaciones y métricas.
- FTS5: recuperación léxica.
- `sqlite-vec`: índice vectorial local reconstruible.
- Relaciones editoriales: grafo derivado con nodos y aristas versionadas.
- Artifact store: blobs direccionados por SHA-256.

Los índices son derivados y pueden reconstruirse desde SQLite y los artefactos. Una futura implementación PostgreSQL/pgvector respetará los mismos repositorios.

## Recuperación y efectos

- Toda publicación usa clave `episode:variant:platform:version`.
- Tras timeout de upload se consulta el estado remoto antes de reintentar.
- Un resultado ambiguo se bloquea; nunca se declara éxito ni se duplica.
- Las herramientas inestables pueden entrar en circuit breaker y rehabilitarse tras cooldown.
- Guardian exige evidencia para afirmaciones operativas.

## Runtime cognitivo

El sidecar separa cinco responsabilidades internas: registro de habilidades, constructor de contexto con niveles de confianza, registro cerrado de herramientas, ciclo cognitivo acotado y evaluadores deterministas. El generador y el crítico usan familias distintas; el Guardian contrasta el resultado final con evidencia real. Los detalles, contratos y límites están en [AGENT_RUNTIME.md](AGENT_RUNTIME.md).
