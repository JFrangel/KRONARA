# Científico de rendimiento

## Propósito

El Performance Scientist convierte snapshots oficiales de métricas en diagnósticos reproducibles e hipótesis para experimentar. No promete viralidad ni afirma que una voz, tema u horario causó el resultado observado.

## Contratos

`MetricSnapshot@1` registra plataforma, pieza, ventana de medición, impresiones, inicios, finalizaciones, repeticiones, compartidos, watch time, duración, voz, tema, hook, hora y audiencia. Sus invariantes bloquean denominadores imposibles, métricas negativas y snapshots observados antes de publicar.

`PerformanceDiagnosis@1` incluye:

- hash reproducible de las entradas;
- tasa global e intervalo Wilson;
- segmentos con piezas, inicios, finalizaciones, lift y elegibilidad;
- hipótesis no causales;
- muestra mínima por variante;
- experimento controlado recomendado;
- warnings y estado `insufficient_data`, `descriptive` o `ready_for_experiment`.

## Segmentación

Cada diagnóstico pertenece a una sola plataforma. No se mezclan Meta, YouTube o TikTok porque sus métricas, distribución y audiencias no son causalmente equivalentes. Dentro de la plataforma se comparan:

- voz;
- tema;
- hook;
- duración `00-30s`, `31-60s` o `61s+`;
- franja horaria de seis horas;
- segmento de audiencia.

Un segmento solo puede originar hipótesis cuando supera el mínimo de inicios y piezas. Además debe existir otro segmento elegible y el lift debe superar el umbral configurado.

## Herramientas deterministas

- `compare_rates`: lift absoluto/relativo e intervalos Wilson.
- `funnel`: conversiones y abandono entre etapas.
- `retention_curve`: retención por checkpoint y mayor tramo de abandono.
- `robust_outliers`: mediana y MAD.
- `minimum_sample_size`: aproximación para dos proporciones con alpha y power explícitos.

Los modelos Qwen/Kimi pueden interpretar el resultado y diseñar una prueba, pero no recalculan números ni pueden remover `observational_not_causal`.

## RPC

`performance.diagnose` recibe únicamente snapshots estructurados y devuelve el diagnóstico. El método requiere handshake, no ejecuta código libre y rechaza el pooling entre plataformas.

## Pendiente

- importar snapshots desde APIs oficiales mediante Rust;
- curvas reales por cohortes y ventanas comparables;
- bootstrap y análisis de sensibilidad;
- asignación persistente de experimentos;
- comparación causal después de aleatorización;
- promoción o rollback mediante el motor de mejora continua.
