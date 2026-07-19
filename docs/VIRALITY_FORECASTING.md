# Forecast de viralidad por plataforma

## Qué significa

Kronara estima la probabilidad de que una pieza supere un threshold de rendimiento definido para su plataforma y ventana de medición. No conoce ni intenta reconstruir algoritmos privados. Un forecast no garantiza distribución, alcance ni ingresos.

## Señales

`PlatformFeatureVector@1` contiene señales observables y reproducibles:

- finalización, compartidos y repeticiones;
- velocidad por hora y aceleración;
- saturación del tema o formato;
- edad de la pieza y decaimiento de frescura;
- duración.

Las tasas deben provenir de denominadores oficiales normalizados. El outcome `viral` deberá definirse por percentil histórico, plataforma, formato y ventana; no por un número universal.

## Modelo

El baseline es una regresión logística regularizada escrita con funciones deterministas. Cada plataforma tiene intercepto, pesos, muestra y backtest propios. Facebook Reels, YouTube Shorts, Instagram Reels y TikTok nunca comparten directamente un modelo causal.

Las observaciones se ordenan por tiempo. El bloque más reciente queda reservado como holdout y nunca participa en el entrenamiento. Se registra Brier score, fecha final de entrenamiento y comienzo de validación para demostrar ausencia de fuga temporal básica.

## Forecast seguro

`ViralityForecast@1` devuelve:

- `estimated` o `abstained`;
- probabilidad e intervalo;
- versión de modelo y plataforma;
- factores desconocidos;
- explicación explícita de que no es garantía;
- `guaranteed=false` fijado por schema y código.

El modelo se abstiene si la plataforma no alcanza la muestra mínima o si no contiene suficientes resultados positivos y negativos.

## RPC

`virality.evaluate` recibe observaciones normalizadas y un candidato, entrena un modelo efímero y devuelve versión más forecast. No persiste pesos ocultos ni permite bajar los mínimos mediante parámetros de usuario.

## Pendiente antes de producción

- thresholds de outcome calculados desde métricas propias;
- backtesting walk-forward;
- calibration curves y error esperado por rango;
- drift de audiencia, plataforma y definición de métricas;
- model registry persistente con champion/challenger y rollback;
- auditoría de fairness editorial y sensibilidad a features faltantes.
