# ADR-002: Rust controla autoridad; Python controla cognición

Fecha: 2026-07-19  
Estado: aceptado e implementado parcialmente

## Contexto

Kronara necesita agentes capaces de investigar, recuperar contexto, crear historias y aprender. Esas capacidades no deben permitir lectura de secretos, shell libre ni publicación directa.

## Decisión

Rust es la autoridad para secretos, red, archivos, pausas y efectos externos. Python es un plano cognitivo aislado, alcanzado por JSON-RPC autenticado y versionado. Python recibe resultados tipados y solo devuelve análisis o intents declarativos.

## Consecuencias

- El bridge Rust genera token de sesión, usa allowlist y limpia el entorno del proceso hijo.
- El chat y la UI muestran trazas resumidas, no credenciales ni razonamiento privado.
- `ActionIntent@1` requiere validación Rust y aprobación administrativa; no muta estado por sí mismo.
- Reddit OAuth y una futura publicación Meta pertenecen a adaptadores Rust.
- Los workflows Python siguen siendo reemplazables, testeables y recuperables mediante SQLite.

## Estado de implementación

El bridge, handshake, allowlist, pausa global, intents y trazas están implementados. El adaptador de inferencia remota gobernado por Rust y los efectos de media/publicación siguen pendientes.
