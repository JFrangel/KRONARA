# Memoria y RAG híbrido

## Memorias

- Ejecución: estado temporal y checkpoints LangGraph.
- Episódica: decisiones y resultados por pieza.
- Semántica: ADN narrativo, estilos, reglas y aprendizajes promovidos.
- Rendimiento: voz, tema, hook, duración, horario y métricas.

Cada registro conserva `source_uri`, versión, confidence, scope, fecha, vigencia y evidencia. Las hipótesis contradictorias conviven hasta que un experimento las resuelve.

## Recuperación

```text
domain filters → FTS5 → vector search → graph expansion
→ reciprocal rank fusion → rerank → rights/freshness filter
→ cited context packet
```

RRF ya está implementado como primitiva determinista. El índice vectorial y el grafo son adaptadores reconstruibles; SQLite continúa siendo la fuente de verdad. Historias externas completas no se recuperan como plantillas.

## Aprendizaje

Estados: `hypothesis`, `testing`, `supported`, `promoted`, `rejected`, `expired`. La promoción automática solo afecta parámetros acotados —voz, hook, duración, horario y packaging— y exige muestra mínima y lift material. Política, derechos, identidad y presupuesto máximo requieren autoridad administrativa.

