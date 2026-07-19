# Runtime cognitivo v0.4

Kronara aumenta capacidad mediante contexto útil, herramientas gobernadas, evaluación y memoria verificable; no mediante un prompt ilimitado ni razonamiento privado persistido.

## Prompt y contexto

`PromptStackCompiler` fija este orden: política base, personalidad, rol, objetivo, autoridad/presupuesto, contexto delimitado como datos, habilidades, contrato de tools, esquema de salida y verificación. La personalidad `kronara@1` es divertida, independiente, investigativa, perfeccionista, creativa y analítica; no puede cambiar permisos.

El Context Compiler usa evidencia, estado, memorias válidas y trazas. Distingue hechos, inferencias, hipótesis y vacíos. El contenido externo nunca pasa a ser instrucción.

## Ejecución gobernada

```text
plan → tools permitidas → crítica de familia distinta → revisión local → Guardian → checkpoint/replay
```

Cada agente tiene entrada/salida estructurada, herramientas mínimas, presupuesto, timeout, reintentos y criterios de aprobación. El registro anti-loop, circuit breaker y presupuesto se aplican antes del efecto. Se guardan decisiones resumidas, artefactos, prompts hash, costos y evidencia; no cadena de pensamiento privada.

## Modelos

`ModelCapabilityRegistry@1` resuelve aliases configurables y health checks:

- Qwen: planificación, estructura y tareas multilingües.
- Kimi: contexto largo, investigación y crítica.
- Groq/OpenRouter: baja latencia y fallback.
- `nvidia/nemotron-3-super-120b-a12b:free`: razonamiento profundo experimental.
- `tencent/hy3:free`: fallback creativo experimental y de disponibilidad limitada.

El registro no convierte automáticamente una API configurada en una ejecución de producción. El chat operativo actual usa un resumen local determinista y citado; el adaptador de inferencia remoto gobernado por Rust es una fase pendiente. Esto evita que Python lea claves de `.env`.

## Calidad narrativa

El motor de historias propias exige tres conceptos, blueprint causal, escenas, continuidad, similitud léxica/semántica/estructural/secuencial, crítico independiente y a lo sumo una revisión localizada. Detecta inyección antes de las tools, admite cancelación cooperativa y persiste las trazas del run.

## Chat operativo

El chat consulta `operations.status` y `tools.timeline`, compila contexto, cita evidencia y devuelve `partial` cuando no puede cubrir lo necesario. Una solicitud de presupuesto produce `ActionIntent@1` con `requires_approval`; no cambia el límite.

Los turnos se conservan para auditoría mediante hash, rol y longitud; el texto bruto del usuario o de la respuesta no entra a la memoria durable.
