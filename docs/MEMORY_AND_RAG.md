# Memoria y RAG v3

## Seis memorias

`MemoryRecord@2` separa memoria de ejecucion, episodica, semantica,
rendimiento, conversacion y error. Cada registro tiene procedencia, confianza,
derechos, vigencia, version, evidencia y estado. Las hipotesis incompatibles se
guardan como rivales hasta que un experimento las apoye o rechace.

La memoria de ejecucion no es memoria de largo plazo: los checkpoints recuperan
workflow; los aprendizajes pasan por Curator y gates antes de ser utilizables.

## Pipeline de recuperacion

```text
filtros de derechos/vigencia/idioma/ambito
-> descomposicion y clasificacion
-> FTS5 + vector local + expansion de grafo
-> RRF -> reranker opcional -> deduplicacion semantica -> diversidad -> citas
```

`RAGV3Index` persiste documentos, chunks, tombstones, aristas e indice vectorial
versionado. Los filtros se aplican antes del ranking. Resultados sin derechos
permitidos o vigencia valida no entran al contexto.

## Embeddings y evaluacion

- `BAAI/bge-m3`, `intfloat/multilingual-e5-large-instruct` y
  `BAAI/bge-reranker-v2-m3` estan registrados como candidatos locales.
- `ProductionEmbeddingFactory` intenta cargar BGE-M3 y `bge-reranker-v2-m3`
  solo desde pesos locales (`local_files_only`). Si faltan, utiliza
  `deterministic_dev` y declara `development_embedding_only`; nunca descarga
  modelos desde Python.
- El golden `benchmarks/rag/spanish-golden.v2.json` mide Recall@k, MRR, nDCG,
  precision de citas y redundancia.
- Un embedding o reranker solo se promueve si gana sobre baseline comparable
  sin regresiones; instalar un nombre de modelo no es promocion.

## Historias propias y aprendizaje

Una historia solo puede alimentar RAG cuando es `owned_original`, conserva el
hash del artefacto, supera derechos, narrativa, originalidad, seguridad y golden
set, y sus metricas comparables alcanzan muestra e intervalo de confianza
suficientes. `promote_owned_story` crea una version `promoted_learning` con
evidencia; un tombstone la revierte sin borrar la auditoria. Historias externas
de Reddit son rechazadas por esa compuerta y nunca se reutilizan como ejemplo
creativo.

## Plantillas visibles por programa

`knowledge/narrative/program-story-templates.md` contiene historias ejemplo y
moldes propios para cada programa: decisiones morales, confesiones, justicia,
mentes ocultas, paranormal, medianoche y caso premium. Estos documentos entran
al RAG como `owned_original` con `document_id=program_story_templates_v1`.

La UI los muestra en **Programas > Recursos** para que el operador pueda ver que
estructura esta disponible para los agentes. Esa pestana tambien permite pegar
texto, editar historias completas y guardar una version manual por programa en
el runtime local. Al guardar, `programs.resources.save` actualiza el documento
RAG activo sin convertir esas historias en texto obligatorio para el guion.

No son textos para copiar: son patrones de arranque, nudos, escalada, cierre,
anclas visuales y criterios de fallo. Las reglas duras siguen viviendo en
`python/kronara/program_narrative.py` y en **Programas > Configuracion**.

Cuando un guion no cumple esas reglas, el motor emite `PROGRAM_QUALITY_FAILED`;
el diagnostico debe atribuirlo a **Critica** y mostrar los `findings` para que
el siguiente reintento sepa que reparar.
