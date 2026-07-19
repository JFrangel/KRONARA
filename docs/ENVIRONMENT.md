# Configuración de entorno

## Desarrollo

1. Copie `.env.example` como `.env`.
2. Complete únicamente los proveedores que utilizará.
3. Mantenga `*_ENABLED=false` hasta disponer de aprobación, credenciales y pruebas sandbox.
4. Inicie Kronara desde el directorio raíz para que Rust encuentre `.env`.

`.env` está ignorado por Git. No debe adjuntarse a reportes, commits ni capturas. El token JSON-RPC se genera por sesión y no pertenece a este archivo.

## Proveedores de IA

Qwen y Kimi pueden usar endpoints OpenAI-compatible diferentes o compartir OpenRouter. Configure para cada alias `BASE_URL`, `API_KEY` y `MODEL`. Rust carga las claves y su representación de depuración siempre muestra `[REDACTED]`. Python recibe solicitudes autorizadas o callbacks; no debe leer el archivo.

Un proveedor sin clave queda `disabled_missing_credential`. Una clave presente solo significa “configurado”; un health check autenticado posterior determinará si está `ready`, `degraded` o `unavailable`.

## Reddit

`KRONARA_REDDIT_ENABLED` permanece `false` hasta que el uso tenga acceso oficial y base contractual aplicable. No use scraping ni endpoints alternativos para evitar restricciones. Aunque una historia se adapte, solo podrá entrenar si existe `TrainingRightsDecision` permitido con evidencia de licencia para entrenamiento y, cuando corresponda, uso comercial.

## Producción

`.env` es una facilidad local. Antes de producción, migre secretos al almacén de credenciales de Windows y entregue handles efímeros a los adaptadores Rust. Mantenga límites diarios, presupuesto de investigación, pausa global y bloqueos de derechos activos.
