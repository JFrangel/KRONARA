# Fuentes de Reddit como nodos RAG

> Cada nodo es una fuente de **inspiración abstracta**, nunca de copia. El agente
> extrae patrones (tema, conflicto, emoción, escalada), nunca texto, nombres ni
> secuencias de eventos literales. Ver `python/kronara/reddit_rss.py` (cosecha
> sin credenciales) y `python/kronara/opportunities.py` (cola + anti-repetición).

## Mapa día → programa → nodo

| Día | Programa | Nodo | Tono |
|---|---|---|---|
| Lunes | Decisiones Difíciles | [nodo-decisiones-dificiles.md](nodo-decisiones-dificiles.md) | serio |
| Martes | Confesiones Anónimas | [nodo-confesiones-anonimas.md](nodo-confesiones-anonimas.md) | íntimo |
| Miércoles | Crónicas de Justicia | [nodo-cronicas-de-justicia.md](nodo-cronicas-de-justicia.md) | tenso |
| Jueves | Mentes Ocultas | [nodo-mentes-ocultas.md](nodo-mentes-ocultas.md) | inquietante |
| Viernes | Viernes Paranormal | [nodo-viernes-paranormal.md](nodo-viernes-paranormal.md) | terror |
| Sábado | Historias de Medianoche | [nodo-historias-medianoche.md](nodo-historias-medianoche.md) | cinematográfico |
| Domingo | El Caso de la Semana | [nodo-caso-de-la-semana.md](nodo-caso-de-la-semana.md) | premium/serio |
| — | Suplementario (todos) | [nodo-general-suplementario.md](nodo-general-suplementario.md) | variado |

## Campo `sensitivity`

Cada subreddit en los nodos siguientes lleva una etiqueta:

- **`entertainment`** — comunidades orientadas a compartir historias para audiencia
  (AITA, ProRevenge, nosleep, confession, TIFU...). Gate de originalidad estándar.
- **`real_experience_serious`** — comunidades de **apoyo real** a personas en
  situaciones difíciles (CPTSD, domesticviolence, survivorsofabuse, trauma,
  AbusiveRelationships, raisedbynarcissists, JustNoFamily/JustNoMIL,
  legaladvice-casos-graves). Se incluyen como fuente de inspiración, pero el
  agente aplica una instrucción adicional obligatoria: **dramatizar el patrón
  real de lo ocurrido cambiando nombres, ubicaciones, edades, profesiones y
  cualquier detalle identificable** — nunca una identidad reconocible, nunca
  una cita textual. Ver `python/kronara/routed_story_provider.py` (bloque
  `_SENSITIVE_SOURCE_DIRECTIVE`) y los filtros de edad/score ya existentes en
  `RedditSignalFilters` (`reddit_observatory.py`), que evitan adaptar
  publicaciones de crisis muy reciente.

## Cómo se usa

1. `harvest_reddit.py` lee el nodo correspondiente al día activo (o todos, en
   modo exploratorio) en vez de una lista fija en código.
2. `OpportunityStore.harvest()` guarda cada post con su `sensitivity` heredada
   del nodo de origen.
3. Al construir el `StoryBrief`, si la oportunidad seleccionada viene de una
   fuente `real_experience_serious`, el prompt creativo recibe el bloque de
   transformación seria adicional.
4. El `StoryLedger` (anti-repetición) sigue aplicando igual sin importar la
   fuente — nunca dos historias casi idénticas, salvo partes de una misma serie.
