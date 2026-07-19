# Investigación analítica y evidencia

## Resultado implementado

Kronara convierte una `ResearchQuestion@1` en un plan acotado antes de usar conectores o modelos. El plan clasifica intención y riesgo, divide el trabajo por focos no solapados, asigna presupuestos de fuentes y fija condiciones de parada. Esto evita búsquedas indefinidas, loops de herramientas y conclusiones que excedan el presupuesto.

El flujo disponible es:

```text
ResearchQuestion@1
→ ResearchPlan@1
→ SourceRecord@1 normalizados
→ EvidenceMatrix@1
→ AnalyticalBrief@1
```

## Planificación

`ResearchPlanner` clasifica preguntas como factual, comparativa, causal, exploratoria, métrica o editorial. Cada subpregunta tiene un foco exclusivo, presupuesto máximo y mínimo de fuentes independientes. El plan conserva cobertura mínima, costo máximo, máximo de consultas y bloqueo ante contradicciones críticas no resueltas.

La clasificación determinista es el fallback seguro. Qwen o Kimi podrán proponer una descomposición más rica, pero esa propuesta tendrá que validar contra `ResearchPlan@1`; el modelo no podrá ampliar presupuesto, herramientas ni fuentes autorizadas.

## Matriz de evidencia

`EvidenceEngine` recibe registros normalizados, no páginas ni instrucciones sin aislar. Cada afirmación declara tipo, postura, subpregunta y confianza. El motor:

- excluye fuentes vencidas o con derechos `denied`/`unknown`;
- agrupa evidencia favorable y contraria;
- une fuentes de la misma familia o que dependen explícitamente una de otra;
- evita contar una republicación como corroboración independiente;
- conserva contradicciones en vez de sobrescribirlas;
- calcula cobertura y enumera subpreguntas faltantes;
- reduce confianza cuando la evidencia es débil o disputada.

Una afirmación factual solo entra en `facts` cuando tiene soporte de dos grupos independientes y no tiene oposición. Las afirmaciones disputadas permanecen como hipótesis y fuerzan estado `partial`.

## Reddit

El adaptador usa OAuth y endpoints oficiales; admite `new`, `hot` y `top`, filtros temporales válidos, ETag, cache metadata y rate limits. Está bloqueado por política de forma predeterminada y requiere referencia contractual explícita. Solo conserva señales abstractas `reference_only`; los cuerpos de historias no se devuelven ni se convierten en datos de entrenamiento.

La conexión de producción aún debe migrar a una herramienta Rust para que Python nunca reciba credenciales. Hasta entonces, el adaptador funciona como contrato probado y no como autoridad de producción.

## RPC seguro

- `research.plan`: genera el plan estructurado.
- `research.evaluate`: evalúa `SourceRecord` normalizados y devuelve plan, matriz e informe.

Ambos métodos requieren handshake autenticado. No ejecutan shell, scraping, código arbitrario ni publicación.

## Pendiente

- tool Rust para OAuth, cache y consultas externas;
- extracción de afirmaciones con salida estructurada y golden set adversarial;
- conectores multi-fuente autorizados;
- persistencia de replay, costo, citas y artefactos;
- crítico y Guardian sobre el informe completo;
- evaluación end-to-end con preguntas reales y fuentes independientes.
