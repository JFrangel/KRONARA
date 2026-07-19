# Kronara v0.2 — Contrato de agentes

Todo agente tiene input/output versionado, tools permitidas, presupuesto, timeout, máximo de pasos, modelo preferido, fallbacks, evidencia, confidence y pruebas.

| Agente | Responsabilidad | Efectos prohibidos |
|---|---|---|
| Opportunity Intelligence | señales, velocidad, saturación | copiar o entrenar con historias |
| Rights and Provenance | licencia, procedencia, atribución | aprobar derechos inexistentes |
| Editorial Executive | oportunidad, formato, duración | publicar directamente |
| Concept Architect | conceptos originales | reproducir una fuente |
| Narrative Planner | escenas, tensión, pistas | redactar publicación |
| Writing Room | escritura y crítica separadas | autocertificar evidencia |
| Hook and Retention | hook y abandono esperado | clickbait contrario al contenido |
| Voice Director | voz, ritmo y emoción | fijar ganador sin muestra |
| Visual/Audio Directors | storyboard y mezcla | usar assets sin rights status |
| Video Composer | timeline declarativa | ejecutar comandos LLM |
| Automated QC | narrativa, audio, video, políticas | corregir políticas globales |
| Packaging | metadata y CTA por plataforma | duplicar copy sin adaptar |
| Distribution | API oficial e idempotencia | reintentar resultado ambiguo |
| Performance Scientist | hipótesis y experimentos | confundir correlación con causalidad |
| Memory Curator | promover conocimiento válido | borrar contradicciones silenciosamente |

Los críticos usan una familia de modelo distinta al generador cuando existe una alternativa sana y dentro de presupuesto. Toda salida recuperada se trata como datos no confiables para prevenir prompt injection.

Los manifiestos ejecutables están en `config/agents` y el catálogo versionado de habilidades en `config/skills/catalog.v1.json`. El runtime selecciona el conjunto mínimo de habilidades que cubre la tarea y bloquea una capacidad desconocida; una habilidad aporta instrucciones y criterios, nunca autoridad adicional.

## Tool governance

Una tool declara nombre, schema, permisos, timeout, side effects e idempotency strategy. El runtime registra input hash, resultado resumido, latencia, error, fallback y trace id. Secretos y contenido sensible se redactan.

La ejecución cognitiva sigue `plan → tools → crítica independiente → revisión local → Guardian`. Exceder pasos, llamadas, costo o revisiones produce un resultado bloqueado. Se persisten el plan y un resumen de decisión para auditoría, no razonamiento privado. Véase [Runtime cognitivo](AGENT_RUNTIME.md).
