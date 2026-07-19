# Kronara — Análisis de brechas y checklist maestro

Fecha de auditoría: 2026-07-19

## Estado comprobado

- [x] Tauri/Svelte y autoridad Rust mínima.
- [x] Sidecar Python autenticado por JSON-RPC.
- [x] LangGraph con checkpoints SQLite.
- [x] Runtime plan–act–critic–Guardian.
- [x] Allowlist de tools, anti-loop, timeout y circuit breaker.
- [x] 17 manifiestos de agentes y 24 habilidades.
- [x] Reddit OAuth básico con rate limit y señales sin cuerpo.
- [x] FTS5 + sqlite-vec + grafo + RRF.
- [x] ADN narrativo, rúbrica y golden set adversarial.
- [x] Publicación Meta idempotente como abstracción.
- [x] Aprendizaje básico por muestra y lift.
- [x] Especificación v0.3 aprobada.

## P0 — Necesario antes de conectar credenciales reales

- [x] Crear `.env.example` documentado y `.env` local ignorado.
- [x] Cargar variables exclusivamente en Rust y redactar secretos.
- [x] Validar configuración por proveedor sin imprimir valores.
- [ ] Añadir contratos v0.3 de investigación, evidencia, contexto y análisis.
- [x] Implementar `TrainingRightsDecision` y excluir datasets no autorizados.
- [x] Sustituir presupuesto por caracteres por presupuesto estimado de tokens en Context Compiler v1.
- [x] Garantizar que evidencia crítica no sea truncada silenciosamente.
- [ ] Añadir cache, health y circuit breaker por conector externo.
- [ ] Mantener Reddit `disabled_by_policy` sin acceso oficial aprobado.

## P1 — RAG v2

- [x] Chunking jerárquico estable documento → sección → fragmento.
- [x] Metadatos de idioma, ámbito, versión, derechos y vigencia en RAG v2.
- [ ] Deduplicación exacta y semántica (exacta implementada en cada documento).
- [ ] Query decomposition y expansión controlada.
- [x] Filtros previos obligatorios por derechos, fecha, idioma y ámbito.
- [ ] Reranker multilingüe configurable (interfaz inyectable implementada; falta modelo evaluado).
- [x] Selección diversa con máximo por documento.
- [ ] GraphRAG con relaciones tipadas y profundidad limitada (expansión de un salto implementada; faltan tipos).
- [x] Tombstones para eliminación y expiración.
- [ ] Benchmark español congelado (evaluador Recall@k, MRR y nDCG implementado; falta corpus juzgado).

## P1 — Investigador analítico

- [ ] Clasificar intención y riesgo de pregunta.
- [ ] Dividir en subpreguntas no solapadas.
- [ ] Planificar fuentes, consultas, presupuesto y condición de parada.
- [ ] Integrar Reddit oficial mediante Rust cuando existan credenciales aprobadas.
- [ ] Normalizar fuentes y detectar dependencia circular.
- [ ] Extraer afirmaciones atómicas.
- [ ] Construir matriz/grafo de evidencia favorable y contraria.
- [ ] Detectar contradicciones, vigencia y cobertura insuficiente.
- [ ] Producir `AnalyticalBrief` con hechos, inferencias e hipótesis separadas.
- [ ] Guardar replay, citas, costos y artefactos.

## P1 — Herramientas analíticas

- [x] Estadística descriptiva con unidades y missing data.
- [x] Cambios absolutos/relativos y baseline.
- [ ] Intervalos de confianza y muestra mínima (Wilson implementado; falta cálculo de muestra).
- [ ] Wilson/Bootstrap para tasas (Wilson implementado; falta bootstrap).
- [ ] Funnel y curva de retención (funnel implementado; falta curva temporal).
- [ ] Segmentación voz/tema/hook/duración/hora/audiencia.
- [ ] Outliers robustos y análisis de sensibilidad (MAD implementado; falta sensibilidad).
- [ ] Experimentos A/B y bandits acotados.
- [ ] Visualizaciones declarativas reproducibles.
- [x] `AnalysisTrace` con hash de entradas, unidades, supuestos y warnings.

## P2 — Viralización multiplataforma

- [ ] Ontología común de métricas Meta/YouTube/TikTok.
- [ ] Adaptadores que conserven la métrica original.
- [ ] `PlatformFeatureVector` por pieza y versión.
- [ ] Score con velocidad, aceleración, saturación y decaimiento.
- [ ] Baselines por plataforma, duración y audiencia.
- [ ] Modelo interpretable regularizado.
- [ ] Modelo jerárquico sin mezclar causalidad entre plataformas.
- [ ] Backtesting temporal y calibración de probabilidad.
- [ ] `ViralityForecast` con intervalo y factores desconocidos.
- [ ] Bloqueo de cualquier promesa de viralidad garantizada.

## P2 — Auto-mejora segura

- [ ] Error memory y taxonomía de fallos.
- [ ] Champion/challenger para prompts, RAG y modelos.
- [ ] Golden set congelado y regresiones de seguridad.
- [ ] Promoción con muestra, lift, estabilidad y costo.
- [ ] Rollback automático de cambios degradantes.
- [ ] Vigencia y expiración de aprendizajes.
- [ ] Hipótesis rivales en vez de sobrescritura silenciosa.
- [ ] Dataset cards y splits reproducibles.
- [ ] Fine-tuning solo `owned_original` o `licensed_adaptation`.
- [ ] Prohibición de auto-modificar política, derechos y permisos.

## P2 — Producción restante

- [ ] Azure/Edge TTS productivo y catálogo de voces versionado.
- [ ] faster-whisper para alineación, pronunciación y QC.
- [ ] FFmpeg Rust desde timeline declarativa.
- [ ] QC real de frames, audio, subtítulos y safe zones.
- [ ] Meta sandbox con publicación y reconciliación remota.
- [ ] YouTube Shorts y TikTok como adaptadores posteriores.
- [ ] Importación periódica de métricas.
- [ ] Primer experimento controlado de voz y hook.
- [ ] Activación progresiva manual → supervised → full_auto.

## Publicación del repositorio

- [x] Repositorio Git local con historial y rama de trabajo.
- [ ] GitHub CLI instalado y autenticado.
- [ ] Rama `main` creada e integración verificada.
- [ ] Repositorio GitHub privado creado.
- [ ] `main` publicada con tracking.
- [ ] Protección de rama y plantilla de pull request.
- [ ] Revisión de secretos e historial antes de publicación.

## Definición de terminado v0.3

- [ ] Una pregunta produce informe multi-fuente citado y recuperable.
- [ ] Ningún cálculo numérico depende exclusivamente del LLM.
- [ ] RAG v2 supera el baseline v0.2 en el corpus congelado.
- [ ] Reddit se bloquea sin acceso oficial y nunca entrena con historias no autorizadas.
- [ ] El científico interpreta métricas sin declarar causalidad injustificada.
- [ ] Una mejora champion/challenger puede promoverse y revertirse.
- [ ] Un Reel original puede publicarse una sola vez y aprender de sus métricas.
