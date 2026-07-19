# Memoria y RAG híbrido

## Memorias separadas

- Ejecución: estado temporal y checkpoints LangGraph.
- Episódica: decisiones, artefactos y resultados por pieza.
- Semántica: ADN narrativo, estilos, reglas y aprendizajes promovidos.
- Rendimiento: voz, tema, hook, duración, horario y métricas.
- Error memory: fallos observados y correcciones verificadas, sin guardar razonamiento privado.

Cada registro conserva procedencia, versión, confianza, ámbito, vigencia, derechos y evidencia. Las hipótesis contradictorias conviven hasta que un experimento las resuelve; nunca se reemplazan silenciosamente.

## RAG v2 implementado

```text
filtros de derechos/vigencia/idioma/ámbito
→ expansión controlada y acotada
→ búsqueda léxica + vectorial
→ expansión de grafo por relación y profundidad
→ RRF
→ reranker opcional
→ diversidad por documento
→ paquete citado
```

`RAGV2Index` produce IDs estables por documento, sección y fragmento. Aplica los filtros antes de rankear, elimina duplicados exactos en todo el catálogo, limita resultados por documento y excluye rankings sin señal para evitar que empates arbitrarios contaminen RRF.

El grafo acepta relaciones tipadas (`supports`, `contradicts`, `derived_from`, `same_topic`, `related`) y profundidad máxima de tres saltos. SQLite conserva documentos, tombstones y aristas como fuente transaccional; chunks y vectores se reconstruyen de forma determinista al reiniciar. El adaptador `LocalHybridIndex` mantiene FTS5 y sqlite-vec para el índice nativo local.

## Evaluación y promoción

El corpus congelado `benchmarks/rag/spanish-golden.v1.json` cubre ADN narrativo, derechos, métricas, contradicciones e inyección de prompt. `RAGEvaluator` calcula Recall@k, MRR, nDCG, precisión de citas y redundancia.

`RAGPromotionGate` bloquea una variante si no aporta lift material de nDCG, usa conjuntos no comparables, contiene métricas no finitas, reduce recall, baja la precisión de citas o supera la redundancia permitida. El RPC autenticado `rag.evaluate` ejecuta la comparación reproducible con límites de documentos, casos, caracteres y `k`; el agente `rag_curator` puede proponerla, pero no modificar políticas ni derechos.

El golden actual supera el baseline v0.2 registrado en la prueba automatizada con `k=1`. Es un corpus mínimo de ingeniería, no evidencia de calidad general; debe crecer con consultas reales juzgadas y particiones congeladas antes de producción.

## Límites pendientes

- Deduplicación semántica multilingüe evaluada; hoy la deduplicación exacta es global.
- Reranker y embeddings multilingües reales comparados contra el fallback local determinista.
- Conectar los metadatos completos de RAG v2 directamente al índice FTS5/sqlite-vec persistente, evitando el rebuild en memoria para catálogos grandes.
- Query decomposition específica de recuperación; la descomposición de investigación ya existe en `ResearchPlanner`.
- Monitoreo de drift del corpus y expansión del golden set.

Historias externas completas no se recuperan como plantillas ni entran a entrenamiento. Solo artefactos propios o con licencia verificable pueden alimentar dataset cards.
