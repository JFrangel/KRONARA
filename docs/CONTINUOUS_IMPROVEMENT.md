# Mejora continua reversible

## Principio

Kronara puede aprender continuamente sin auto-modificar sus reglas globales. Cada cambio es un candidato versionado que compite contra un champion sobre un conjunto congelado. La promoción es una decisión estructurada, persistida y reversible.

## Gates de promoción

`ImprovementEngine` evalúa en este orden:

1. evaluation set congelado y con hash;
2. candidato vigente;
3. muestra mínima;
4. ausencia de regresiones de seguridad;
5. costo dentro del límite;
6. estabilidad por plataforma/segmento;
7. lift material;
8. autoridad requerida por el parámetro.

Un lift alto nunca compensa una regresión de derechos, seguridad u originalidad.

## Autoridad

El scope se deriva del parámetro y no puede ser elegido por el LLM.

- Automático: voz, duración, horario, hook, packaging, ranking RAG, query expansion y alias de modelo dentro de límites.
- Supervisado: prompt base, catálogo de habilidades y modelo de embeddings.
- Administrativo: derechos, autonomía, presupuesto, identidad, fuentes autorizadas y despliegue de fine-tuning.

Los cambios supervisados o administrativos devuelven `requires_approval`; nunca se promueven desde `full_auto`.

## Memoria y rollback

SQLite conserva decisiones, versión champion/challenger, evaluation set, reason y estado. Solo una versión realmente promovida puede generar `RollbackReceipt`. El recibo conserva la versión restaurada y la causa.

`ErrorMemory` registra taxonomía, firma, evidencia y versión que resolvió el problema. `LearningHypothesis` conserva rivales, evidencia, estado y vigencia; registrar una hipótesis no elimina su alternativa.

## Datos de entrenamiento

`DatasetCardBuilder` revisa cada ejemplo con `TrainingRightsPolicy`. Una historia `reference_only` se bloquea incluso si fue adaptada creativamente. Se admiten:

- guiones `owned_original` con procedencia `kronara://artifacts/...`;
- `licensed_adaptation` con permiso, scope de entrenamiento y uso comercial cuando aplique.

La card registra hash del manifiesto, splits, modos de derechos y evidencias. Fine-tuning sigue siendo una fase posterior y necesita superar RAG/prompt baseline.

## RPC

- `improvement.status`: scopes y umbrales públicos del motor.
- `improvement.evaluate`: evaluación stateless de un candidato; no despliega ni cambia políticas.
- `performance.learn`: importa métricas oficiales, persiste el diagnóstico y puede promover únicamente una historia propia como documento RAG reversible.

La promoción editorial al RAG ya persiste evidencia y versión; los efectos de deployment de modelos, prompts o políticas seguirán ejecutándose únicamente mediante autoridad Rust y aprobación adecuada.

## Pendiente

- traffic assignment real y análisis secuencial;
- model/prompt registry persistente;
- monitoreo post-promoción;
- trigger automático de rollback ante degradación confirmada;
- UI para aprobaciones supervisadas/administrativas;
- dataset lineage completo y firmas de artefactos.
