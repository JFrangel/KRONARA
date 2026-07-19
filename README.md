# Kronara OS v0.3 (en desarrollo)

Fábrica editorial autónoma, local-first y auditable para Windows. Tauri/Rust controla los efectos externos; el sidecar Python ejecuta LangGraph, memoria, RAG, agentes y aprendizaje.

## Estado implementado

- Shell Svelte/Vite con modo `full_auto` y pausa global.
- Autoridad Rust con bloqueos no anulables y pruebas.
- Sidecar Python empaquetable, protocolo JSON-RPC autenticado y heartbeat.
- LangGraph persistente sobre SQLite.
- Checkpoints, replay, Guardian de evidencia y artefactos por hash.
- Señales abstractas de Reddit sin conservar el cuerpo de historias.
- Fusión RRF, router por capacidades Qwen/Kimi/Groq y health status.
- Timeline de Reel, publicación Meta idempotente y reconciliación tras timeout.
- Catálogo inicial Marcelo, Lorenzo, Sofía, Gonzalo y Salomé.
- Aprendizaje experimental que impide promover muestras insuficientes.
- OAuth Reddit, rate limits y señales `reference_only` sin cuerpo de historia.
- RAG híbrido operativo con FTS5, sqlite-vec, grafo y RRF.
- Proveedor OpenAI-compatible con JSON Schema para Qwen/Kimi.
- Vertical LangGraph de tendencia a concepto y blueprint narrativo.
- Runtime cognitivo con habilidades mínimas, herramientas gobernadas, crítica independiente y Guardian.
- Catálogo de 19 agentes, ADN narrativo modular y golden set adversarial.
- Investigador analítico con clasificación de intención, subpreguntas no solapadas, presupuesto de fuentes y reglas de parada.
- Matriz de evidencia que conserva contradicciones, dependencia entre fuentes, vigencia, derechos y cobertura incompleta.
- Reddit bloqueado por política de forma predeterminada hasta registrar autorización contractual.
- Científico de rendimiento que segmenta voz, tema, hook, duración, horario y audiencia con Wilson, muestra mínima y advertencias no causales.
- Forecast de viralidad separado por plataforma con modelo regularizado, holdout temporal, intervalo y abstención.
- Mejora continua reversible con champion/challenger, golden set congelado, scopes de autoridad, error memory y dataset cards con derechos.

Los conectores de red permanecen sin credenciales y no publican contenido real hasta configurarse. Los adaptadores implementados fijan sus contratos y semántica segura.

Repositorio remoto: [JFrangel/Proyecto-Redit](https://github.com/JFrangel/Proyecto-Redit). La rama `main` está integrada y verificada localmente; su publicación remota permanece pendiente de autenticación de GitHub CLI.

## Desarrollo

```powershell
npm.cmd install
npm.cmd test
npm.cmd run build
python -m pip install -e ".[dev]"
python -m pytest -q --basetemp .test-tmp
```

Para Rust, ejecute desde un Developer Command Prompt de Visual Studio:

```powershell
cargo test --manifest-path src-tauri/Cargo.toml
```

Empaquetado del sidecar y de la app:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-sidecar.ps1
npm.cmd run tauri build
```

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md)
- [Agentes](docs/AGENTS.md)
- [Runtime cognitivo](docs/AGENT_RUNTIME.md)
- [Investigación y evidencia](docs/RESEARCH_AND_EVIDENCE.md)
- [Científico de rendimiento](docs/PERFORMANCE_SCIENTIST.md)
- [Forecast de viralidad](docs/VIRALITY_FORECASTING.md)
- [Mejora continua](docs/CONTINUOUS_IMPROVEMENT.md)
- [Configuración de entorno](docs/ENVIRONMENT.md)
- [Análisis de brechas](docs/GAP_ANALYSIS.md)
- [Plan v0.3 con checks](docs/superpowers/plans/2026-07-19-kronara-v0.3-implementation.md)
- [Autonomía y seguridad](docs/AUTONOMY_AND_SECURITY.md)
- [Memoria y RAG](docs/MEMORY_AND_RAG.md)
- [Integraciones](docs/INTEGRATIONS.md)
- [Tendencia a blueprint](docs/TREND_TO_BLUEPRINT.md)
- [Fases](docs/IMPLEMENTATION_PHASES.md)
