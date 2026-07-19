# Autonomía y seguridad

`full_auto` es el modo predeterminado. `manual` añade gates de concepto, guion, render y publicación; `supervised_auto` conserva el gate de publicación.

## Bloqueos no anulables

- Derechos insuficientes.
- Credenciales inválidas.
- Violación de política de plataforma.
- Render defectuoso.
- Publicación ambigua.
- Presupuesto agotado.
- Riesgo reputacional crítico.

La pausa global se evalúa tanto en UI como en la autoridad Rust. Los límites diarios, presupuesto, horarios y temas prohibidos se vuelven a verificar justo antes del efecto.

## Amenazas controladas

- Prompt injection: datos delimitados, tool allowlist y Guardian posterior.
- Path traversal: Rust resuelve rutas dentro del workspace de proyecto.
- Command injection: FFmpeg se construye con argumentos tipados, nunca shell libre.
- Secret leakage: secretos en keyring/autoridad; Python recibe capacidades, no claves.
- Duplicate publishing: idempotency key y reconciliación remota.
- Memory poisoning: procedencia, confidence, vigencia y promoción por Memory Curator.

