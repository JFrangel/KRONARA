# Integraciones

## Reddit

El cliente OAuth y los endpoints oficiales están implementados detrás de un transporte probado. `SourcePost` existe solo durante la extracción; se persiste `TrendSignal` con URI, título reducido, engagement, velocity y `rights_mode=reference_only`. El cuerpo no se conserva. En producción, OAuth se ejecutará como tool Rust para mantener secretos fuera de Python. Uso comercial queda bloqueado hasta documentar autorización contractual aplicable.

## Modelos

`ModelCapabilityRegistry` selecciona aliases saludables por capability, quality, costo y presupuesto. Defaults: Qwen para planning/tools/structured, Kimi para research/critique/long context y Groq para clasificación rápida. El transporte OpenAI-compatible inyecta credenciales mediante un proveedor de secretos, solicita `json_schema` y valida nuevamente el resultado. IDs reales viven en configuración y health checks.

## Voz y Whisper

Azure es el proveedor estable. Edge TTS es experimental. Voces iniciales: Marcelo, Lorenzo, Sofía, Gonzalo y Salomé. `faster-whisper` será el adaptador de transcripción/alineación para comparar narración contra guion y producir timings.

## Media

`MediaTimeline` exige canvas vertical, duración positiva y voice track. Rust será responsable de traducir una timeline validada a argumentos FFmpeg, medir QC y registrar hashes/versiones.

## Meta/Facebook Reels

`PublicationIntent` incluye idempotency key. El transporte oficial implementará upload, consulta de estado, publicación y lectura de insights. Ante timeout, `MetaPublisher` consulta el estado remoto y retorna `ambiguous` si no puede demostrar resultado.
