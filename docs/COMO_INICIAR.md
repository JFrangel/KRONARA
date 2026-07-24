# Cómo iniciar Kronara

Kronara es **web pura** (Vite + sidecar Python), sin Tauri ni Rust. Se lanza con
un doble-clic.

## Doble-clic (recomendado)

1. Doble-clic en **`Iniciar-Kronara.cmd`** (en la raíz del proyecto).

Eso deja todo conectado con un clic:
- mata sidecars huérfanos (evita el bug histórico "se cuelga en Guardando"),
- arranca **VoiceBox** si está instalado (voz clonada real; si no, voz estimada),
- levanta el servidor web (`npm run dev`), que **auto-spawnea el sidecar Python**,
- espera a Vite y **abre el navegador** en `http://localhost:5173`.

Cerrar la ventana de consola detiene el servidor. Para el ícono del acceso
directo, usa `assets/icon.ico`.

## Manual (equivalente)

```bash
npm install      # solo la primera vez
npm run dev      # predev limpia sidecars; vite spawnea el sidecar Python
```

Luego abre `http://localhost:5173`.

## Requisitos

- **Node.js** (para el servidor web / autoridad).
- **Python 3** con las dependencias del sidecar (`python/`).
- **FFmpeg** en el PATH (render de video).
- **`.env`**: copia `.env.example` y agrega tus claves. Todo el pipeline gratuito
  funciona sin claves de pago; las claves opcionales habilitan más (VoiceBox,
  Cloudflare, Pexels, Freesound, publicación). Ver [INTEGRATIONS.md](INTEGRATIONS.md).

## Notas

- La **autoridad de red** (routing de modelos, publicación) vive en el Node
  (`vite.config.js`), no en Rust. Migramos fuera de Tauri: `src-tauri/` fue
  eliminado y nada web-crítico dependía de él.
- VoiceBox se documenta aparte en [VOICEBOX.md](VOICEBOX.md).
