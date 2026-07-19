# Integraciones

## Reddit

El conector usará OAuth y endpoints oficiales. `SourcePost` existe solo durante la extracción; se persiste `TrendSignal` con URI, título reducido, engagement, velocity y `rights_mode=reference_only`. El cuerpo no se conserva. Uso comercial queda bloqueado hasta documentar autorización contractual aplicable.

## Modelos

`ModelCapabilityRegistry` selecciona aliases saludables por capability, quality, costo y presupuesto. Defaults: Qwen para planning/tools/structured, Kimi para research/critique/long context y Groq para clasificación rápida. IDs reales viven en configuración y health checks.

## Voz y Whisper

Azure es el proveedor estable. Edge TTS es experimental. Voces iniciales: Marcelo, Lorenzo, Sofía, Gonzalo y Salomé. `faster-whisper` será el adaptador de transcripción/alineación para comparar narración contra guion y producir timings.

## Media

`MediaTimeline` exige canvas vertical, duración positiva y voice track. Rust será responsable de traducir una timeline validada a argumentos FFmpeg, medir QC y registrar hashes/versiones.

## Meta/Facebook Reels

`PublicationIntent` incluye idempotency key. El transporte oficial implementará upload, consulta de estado, publicación y lectura de insights. Ante timeout, `MetaPublisher` consulta el estado remoto y retorna `ambiguous` si no puede demostrar resultado.

