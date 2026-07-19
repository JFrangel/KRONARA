# Kronara v0.3 — Diseño de inteligencia analítica, investigación y RAG

Fecha: 2026-07-19
Estado: arquitectura aprobada; especificación escrita pendiente de revisión final

## 1. Objetivo

Kronara debe convertir preguntas editoriales y métricas en decisiones verificables. El agente analizará, investigará, interpretará y actuará mediante herramientas gobernadas; usará contexto amplio cuando aporte valor y lo comprimirá cuando sea redundante. La mejora se medirá con recuperación, evidencia, exactitud analítica, calidad narrativa, costo, latencia y resultados editoriales.

No se intentará aumentar capacidad mediante un prompt gigante ni mediante auto-modificación. El sistema combinará recuperación avanzada, modelos especializados, cálculos deterministas, crítica independiente, memoria con procedencia y evaluación continua.

## 2. Resultado vertical

El primer flujo completo será:

```text
ResearchQuestion
→ clasificación de intención y riesgo
→ descomposición en subpreguntas
→ plan de fuentes y consultas
→ recuperación local y conectores autorizados
→ normalización, deduplicación y extracción de afirmaciones
→ matriz y grafo de evidencia
→ análisis cuantitativo/cualitativo
→ hipótesis rivales y contradicciones
→ interpretación con incertidumbre
→ crítico independiente
→ Guardian
→ AnalyticalBrief citado
→ memoria episódica y propuesta de aprendizaje
```

El informe separará explícitamente hechos, cálculos, inferencias, hipótesis y recomendaciones. Ninguna recomendación se presentará como hecho.

## 3. Arquitectura cognitiva

### 3.1 Context Compiler

Construirá un paquete de contexto por tarea en lugar de concatenar documentos. Aplicará:

1. política y contrato de salida;
2. estado mínimo de ejecución;
3. evidencia verificada de alta prioridad;
4. memoria semántica vigente;
5. resultados externos delimitados como no confiables;
6. compresión extractiva con citas conservadas;
7. presupuesto dinámico por modelo y complejidad.

Cada fragmento tendrá identidad, fuente, confianza, fecha, vigencia, derechos, ámbito, tokens estimados y hash. El compilador reservará espacio para la respuesta y rechazará paquetes cuya evidencia crítica haya sido truncada. Las instrucciones encontradas en contenido recuperado nunca entrarán en la zona de política.

### 3.2 Research Planner

Clasificará la pregunta como factual, comparativa, causal, exploratoria, métrica o editorial. Generará subpreguntas no solapadas, criterios de terminación, fuentes preferidas y un presupuesto. La investigación terminará cuando se cubran las subpreguntas con evidencia suficiente, se agote el presupuesto o persistan contradicciones que requieran revisión.

Los conectores externos serán herramientas Rust autorizadas. Python recibirá resultados normalizados y nunca credenciales. Cada consulta tendrá cache, rate limit, timeout, procedencia y política de retención.

### 3.3 Evidence Engine

Extraerá afirmaciones atómicas y las conectará con evidencia compatible, evidencia contraria y dependencias. Calculará cobertura, diversidad de fuentes, vigencia, independencia y confianza calibrada. Las afirmaciones sensibles exigirán más de una fuente independiente cuando sea posible.

El motor detectará:

- fuentes que se citan entre sí y aparentan independencia;
- afirmaciones sin soporte o con fechas incompatibles;
- extrapolaciones de muestras pequeñas;
- correlación presentada como causalidad;
- métricas con denominadores distintos;
- evidencia eliminada, vencida o sin derechos suficientes.

### 3.4 Analytical Reasoner

El LLM formulará el problema y elegirá herramientas; los cálculos se realizarán mediante funciones deterministas. Herramientas iniciales:

- estadística descriptiva y distribuciones;
- tasas, cambios absolutos y relativos;
- intervalos de confianza y tamaño mínimo de muestra;
- comparación contra baseline;
- detección robusta de outliers y datos faltantes;
- segmentación por voz, tema, hook, duración, horario y audiencia;
- análisis de funnels de retención;
- correlación con advertencias causales;
- comparación de experimentos y bandits acotados;
- análisis de sensibilidad y escenarios;
- tablas y gráficos declarativos.

Toda operación producirá `AnalysisTrace@1`: función, entradas referenciadas, supuestos, salida, unidades, warnings y hash reproducible. No se permitirá ejecutar código arbitrario ni SQL de escritura.

### 3.5 Deliberación profunda

El orquestador asignará una clase de complejidad:

- `direct`: herramienta o regla determinista;
- `standard`: plan corto, recuperación y una crítica;
- `deep`: hipótesis rivales, dos pasadas de recuperación, crítico adversarial y síntesis;
- `blocked`: falta de autoridad, evidencia o presupuesto.

La deliberación profunda no guardará cadena de pensamiento. Persistirá un resumen de decisiones, alternativas consideradas, evidencia usada y motivos verificables de descarte.

### 3.6 Learning Flywheel

Después de cada tarea se registrarán resultado, feedback, métricas, errores, costos y evaluaciones. Memory Curator podrá proponer:

- nuevos ejemplos aprobados;
- cambios acotados de recuperación o prompt;
- preferencias de modelo por tipo de tarea;
- hipótesis de contenido, voz o distribución;
- casos de regresión para el golden set.

Las promociones usarán champion/challenger, conjunto congelado y rollback. El agente no cambiará permisos, política, derechos, identidad editorial ni presupuesto máximo.

El fine-tuning será una fase posterior. Solo admitirá guiones propios, artefactos autorizados, decisiones aprobadas y resultados verificados. Se conservarán dataset cards, licencias, splits congelados y comparación contra el baseline RAG. Si no supera el baseline de forma material, no se despliega.

## 4. RAG v2

### 4.1 Ingesta

- parsers por tipo de documento;
- normalización Unicode y de metadatos;
- chunking semántico jerárquico: documento, sección, fragmento y afirmación;
- deduplicación exacta y semántica;
- embeddings multilingües versionados;
- extracción de entidades, relaciones, fechas y derechos;
- almacenamiento del texto autorizado por hash;
- tombstones para eliminación y expiración.

### 4.2 Recuperación

```text
Intent classification
→ query decomposition and expansion
→ domain/rights/freshness filters
→ FTS5 + vector retrieval
→ graph traversal
→ RRF fusion
→ multilingual cross-encoder reranking
→ diversity selection
→ evidence sufficiency check
→ cited context compilation
```

La recuperación admitirá filtros obligatorios y opcionales, fechas `valid_from/valid_until`, idioma, tipo, ámbito y nivel de confianza. La selección diversa reducirá fragmentos redundantes. Si la cobertura es baja, el Research Planner reformulará la consulta dentro de un límite.

### 4.3 Evaluación RAG

El corpus español incluirá consultas narrativas, métricas, políticas, derechos, contradicciones y ataques de inyección. Métricas:

- Recall@k, nDCG@k y MRR;
- precisión de citas y cobertura de afirmaciones;
- diversidad y redundancia;
- vigencia y cumplimiento de derechos;
- tasa de respuesta abstencionista correcta;
- latencia, tokens y costo;
- resistencia a prompt injection y documentos contaminados.

## 5. Contratos nuevos

- `ResearchQuestion@1`, `ResearchPlan@1`, `SubQuestion@1`.
- `SourceQuery@1`, `SourceRecord@1`, `Claim@1`, `EvidenceLink@1`.
- `EvidenceMatrix@1`, `Contradiction@1`, `ResearchCoverage@1`.
- `AnalysisRequest@1`, `AnalysisTrace@1`, `AnalyticalBrief@1`.
- `ContextFragment@1`, `ContextBudget@1`, `CompiledContext@1`.
- `RetrievalQuery@2`, `RetrievalResult@2`, `RAGEvaluation@1`.
- `PromptCandidate@1`, `ModelEvaluation@1`, `ErrorMemory@1`.
- `DatasetManifest@1`, `TrainingRun@1`, `DeploymentDecision@1`.

Todos serán versionados, con `additionalProperties: false` en fronteras RPC y hashes sobre entradas relevantes.

## 6. Agentes y herramientas

Se añadirán:

- `Research Executive`: plan, cobertura y terminación.
- `Source Analyst`: normalización y calidad de fuente.
- `Evidence Analyst`: afirmaciones, soporte y contradicciones.
- `Quantitative Analyst`: cálculos y experimentos reproducibles.
- `Interpretation Analyst`: significado editorial e incertidumbre.
- `RAG Curator`: ingesta, chunks, metadatos y evaluación.
- `Evaluation Scientist`: benchmarks de modelos, prompts y RAG.

Herramientas Rust autorizadas:

- `research.search`, `research.fetch`, `research.cache_read`;
- `metrics.query_readonly`, `analytics.compute`, `analytics.visualize`;
- `rag.ingest_authorized`, `rag.retrieve`, `rag.evaluate`;
- `model.complete`, `model.embed`, `model.rerank`;
- `artifact.read_scoped`, `artifact.write_scoped`.

No se añadirá shell libre, imports arbitrarios, SQL de escritura ni acceso directo a secretos desde Python.

## 6.1 Reddit Trend Observatory

Kronara observará historias actuales únicamente mediante accesos oficiales autorizados. Existirán dos adaptadores explícitos:

- `reddit_data_api`: OAuth tradicional sujeto a registro, aprobación, términos y posibles acuerdos comerciales;
- `reddit_devvit_bridge`: integración futura instalada dentro de Reddit, cuya autenticación administra Devvit.

No se implementarán scraping, endpoints JSON no autorizados ni servicios que eludan restricciones. Si no existe acceso oficial válido, el conector quedará `disabled_by_policy` y el vertical podrá trabajar con señales propias, fixtures o fuentes alternativas autorizadas.

El observatorio consultará listados permitidos por subreddit, periodo y orden, y conservará solamente lo necesario:

- ID, título, URL, subreddit, fecha, score y comentarios cuando el contrato lo permita;
- velocidad, aceleración, engagement relativo, edad, saturación y vida útil estimada;
- temas, emociones, conflictos, preguntas y patrones abstractos;
- estado de eliminación, procedencia, atribución y snapshot de términos;
- hash efímero para deduplicación y auditoría.

El cuerpo completo y los comentarios no entrarán al dataset de entrenamiento. Una historia podrá mostrarse como referencia enlazada y convertirse en `TrendSignal`, pero no en plantilla narrativa. Las eliminaciones y restricciones se propagarán mediante tombstones. El uso comercial permanecerá bloqueado hasta registrar la base contractual aplicable.

Referencias oficiales verificadas al diseñar esta fase:

- <https://developers.reddit.com/docs/capabilities/server/reddit-api>
- <https://redditinc.com/policies/developer-terms>
- <https://redditinc.com/policies/data-api-terms>

## 6.2 Inteligencia de viralización multiplataforma

Kronara no intentará reconstruir ni afirmar conocer algoritmos privados de recomendación. Aprenderá un modelo empírico y calibrado a partir de métricas autorizadas, resultados propios y señales públicas permitidas.

Plataformas objetivo por orden:

1. Facebook Reels e Instagram Reels mediante Meta;
2. YouTube Shorts mediante Data API y Analytics API;
3. TikTok mediante Content Posting API y métricas autorizadas disponibles;
4. podcast y video largo como extensiones.

Cada pieza producirá `PlatformFeatureVector@1` con tema, género, tipo de hook, duración, densidad de palabras, ritmo, voz, emoción, estructura, CTA, subtítulos, composición visual, hora, región, audiencia y versión creativa. Cada snapshot se normalizará a una ontología común, conservando también la métrica original de la plataforma.

Modelos iniciales, por complejidad creciente:

- score de oportunidad con decaimiento temporal, velocidad y saturación;
- baseline por plataforma, formato, duración y tamaño de audiencia;
- intervalos de Wilson o bootstrap para tasas;
- regresión regularizada para asociaciones interpretables;
- modelos jerárquicos para compartir señal sin confundir plataformas;
- survival analysis para vida útil y tiempo hasta abandono;
- contextual bandits acotados para seleccionar variantes;
- calibración de probabilidad y backtesting temporal.

`ViralityForecast@1` devolverá probabilidad calibrada por umbral, intervalo, factores contribuyentes, factores desconocidos, comparables y advertencias. Nunca prometerá viralidad. Un pronóstico no publicará por sí mismo: Editorial Executive y la política de autonomía decidirán.

Métricas primarias normalizadas:

- retención por posición, finalización y tiempo visto;
- repeticiones y compartidos;
- comentarios y guardados cuando estén disponibles;
- conversión a seguidor/suscriptor;
- alcance, impresiones y velocidad temprana;
- costo y tiempo de producción.

YouTube ofrece métricas oficiales como `averageViewDuration`, `engagedViews`, `shares`, `subscribersGained`, `audienceWatchRatio` y retención relativa; sus dimensiones permiten analizar la curva por proporción de tiempo. TikTok ofrece publicación directa o borrador mediante su Content Posting API, sujeto a consentimiento y revisión de la aplicación. Los adaptadores solo usarán campos documentados y tolerarán diferencias o ausencia de métricas.

Referencias oficiales verificadas:

- <https://developers.google.com/youtube/analytics/metrics>
- <https://developers.google.com/youtube/analytics/dimensions>
- <https://developers.google.com/youtube/v3/docs/search/list>
- <https://developers.tiktok.com/products/content-posting-api>

## 6.3 Auto-mejora continua y segura

El aprendizaje se ejecutará después de cada ventana de métricas, pero la promoción será deliberada:

```text
observación → diagnóstico → error memory → hipótesis rival
→ experimento acotado → ventana de medición → análisis con incertidumbre
→ evaluación congelada → promover, rechazar o continuar probando
```

Tres velocidades de cambio:

- automática: ranking RAG, query expansion, selección de modelo, hook, voz, duración, horario y packaging dentro de rangos;
- supervisada: cambios de prompts base, incorporación de nuevas habilidades y migraciones de embeddings;
- administrativa: política, derechos, fuentes autorizadas, identidad, presupuesto y despliegue de fine-tuning.

El sistema conservará champion y challenger, porcentaje de tráfico, versión, evidencia y rollback. Un cambio se promoverá solo con muestra suficiente, mejora material, ausencia de regresiones de seguridad y rendimiento estable por plataforma. Los aprendizajes caducarán cuando cambie la audiencia, la plataforma o su vigencia estadística.

## 7. Variables de entorno y secretos

Se crearán dos archivos:

- `.env.example`: nombres, comentarios y valores seguros de ejemplo; se versiona.
- `.env`: valores locales vacíos; queda ignorado por Git.

Grupos previstos:

- aplicación: `KRONARA_ENV`, `KRONARA_DATA_DIR`, `KRONARA_LOG_LEVEL`;
- presupuestos: `KRONARA_MAX_DAILY_COST_USD`, `KRONARA_MAX_RESEARCH_COST_USD`;
- Qwen/Kimi/OpenRouter/Groq: base URL, alias de modelo y API key;
- embeddings y reranker: proveedor, alias y dimensiones;
- Reddit: client ID, client secret y user agent;
- Meta: page ID y token de página;
- Azure Speech: key y región;
- feature flags para conectores, nunca para desactivar seguridad.

En desarrollo, Rust cargará `.env` y redactará secretos de logs. En producción, los secretos migrarán al almacén de credenciales del sistema operativo. Python solo recibirá respuestas de herramientas o handles efímeros con alcance mínimo. El RPC token se generará por sesión, no se almacenará en `.env`.

## 8. Fases de implementación

### Fase 4 — Contexto y contratos

Contratos v2, Context Compiler, presupuestos dinámicos, separación de confianza, compresión citada y pruebas adversariales.

Criterio de salida: una tarea larga conserva todas las citas críticas, excluye instrucciones externas y respeta el presupuesto.

### Fase 5 — RAG v2

Chunking jerárquico, metadatos, filtros, expansión, reranking, diversidad y benchmark español.

Criterio de salida: mejora material sobre el baseline RRF en nDCG/citas sin violar derechos o vigencia.

### Fase 6 — Investigación y evidencia

Research Planner, Reddit Trend Observatory oficial, conectores gobernados, claim extraction, Evidence Matrix, contradicciones y suficiencia.

Criterio de salida: informe multi-fuente recuperable con cada afirmación clasificada y citada.

### Fase 7 — Herramientas analíticas

Estadística, funnels, experimentos, segmentación, escenarios y visualización declarativa.

Criterio de salida: cálculos reproducibles con unidades, supuestos y warnings; ninguna cifra inventada por el LLM.

### Fase 8 — Deliberación e interpretación

Clasificador de complejidad, hipótesis rivales, crítico adversarial, síntesis y calibración de confianza.

Criterio de salida: golden set demuestra mejor planificación, cobertura y abstención que el runtime v0.2.

### Fase 9 — Aprendizaje y optimización

Error memory, modelos de viralización por plataforma, evaluación de modelos/prompts, champion/challenger, promoción y rollback.

Criterio de salida: una mejora promovida supera el conjunto congelado sin regresiones de seguridad.

### Fase 10 — Fine-tuning opcional

Dataset propio autorizado, entrenamiento externo configurable, evaluación y registro de despliegue.

Criterio de salida: solo se adopta si supera RAG + prompt optimization en calidad ajustada por costo.

### Fase 11 — Integraciones editoriales restantes

TTS/Whisper real, FFmpeg Rust, Meta sandbox, métricas y primer experimento de voz.

Criterio de salida: Reel original publicado una vez, auditable y analizado tras su ventana de métricas.

## 9. Fallos y comportamiento seguro

- Fuente no disponible: usar cache vigente o declarar cobertura incompleta.
- Fuentes contradictorias: conservar ambas y reducir confianza.
- Reranker o embedding caído: fallback versionado y warning de calidad.
- Métrica sin denominador: no calcular tasa.
- Muestra insuficiente: mantener hipótesis en `testing`.
- Presupuesto agotado: producir resumen parcial claramente marcado o bloquear.
- Prompt injection: aislar fragmento, registrar finding y excluir instrucciones.
- Secreto ausente: conector deshabilitado sin afectar análisis local.
- Timeout ambiguo de efecto externo: reconciliación Rust antes de reintento.

## 10. Estrategia de pruebas

- unitarias para contratos, filtros, cálculos, presupuesto y confianza;
- propiedades para invariantes numéricas y RRF/reranking;
- integración SQLite/FTS5/sqlite-vec y checkpoints;
- golden RAG español con relevancia juzgada;
- adversariales de inyección, fuente contaminada y evidencia circular;
- fallos simulados de modelo, fuente, cache y presupuesto;
- replay determinista de análisis;
- benchmark v0.2 vs. v0.3 por calidad, citas, latencia y costo;
- pruebas empaquetadas del sidecar y autoridad Rust.

## 11. Fuera de alcance inmediato

- entrenamiento con contenido de terceros sin permiso verificable;
- navegación web o publicación fuera de herramientas Rust;
- auto-modificación de política o permisos;
- causalidad automática basada solo en observaciones;
- fine-tuning antes de disponer de dataset propio suficiente;
- worker remoto como requisito del MVP.

## 12. Decisiones cerradas

- Arquitectura local-first y Rust como autoridad.
- Python razona; las funciones deterministas calculan.
- Más contexto solo cuando mejora cobertura; siempre con presupuesto.
- RAG y evaluación preceden al fine-tuning.
- Crítico independiente y Guardian siguen siendo obligatorios.
- `.env` es únicamente para desarrollo y nunca se versiona con secretos.
- Se implementan A, B y C: investigador analítico, científico de rendimiento y RAG avanzado.
- Reddit aporta señales actuales oficiales; sus historias no entrenan el modelo sin permiso.
- La viralización se pronostica desde evidencia propia y métricas oficiales, no desde supuestos sobre algoritmos privados.
- La auto-mejora es continua pero versionada, evaluada y reversible.
