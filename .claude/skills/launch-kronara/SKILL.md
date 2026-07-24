---
name: launch-kronara
description: Use when the user wants to launch/run/start Kronara (the content studio) or bring up the full local stack (web UI + Python sidecar + VoiceBox voice engine) so a generated video has real cloned voice. Covers starting, verifying, and troubleshooting the connected stack.
---

# Launch Kronara (web + sidecar + VoiceBox)

Kronara runs as a web app. One command brings up everything **connected**:

- **Vite dev server** (the UI, port 5173) — its `predev` step runs
  `scripts/dev-preflight.ps1`, which kills orphan sidecars **and** auto-starts
  the VoiceBox voice engine (`scripts/start-voicebox.ps1`).
- **Python sidecar** — spawned automatically by `vite.config.js`
  (`LocalSidecarHost`); handles content.run, styles, voice, RAG.
- **VoiceBox backend** (voice, port 17493) — started by the preflight script if
  installed; optional (voice degrades to a silent estimate when absent).

## Steps

1. **Start the stack.** Prefer the preview tool over a raw shell so the browser
   opens automatically:
   - Use `preview_start` with `{name: "vite-dev"}` (defined in
     `.claude/launch.json`). This runs `npm run dev`, which triggers `predev`
     (orphan cleanup + VoiceBox auto-start) and spawns the sidecar.
   - Or, in a terminal the user controls: `npm run dev`.

2. **Wait for connection.** The sidecar takes a few seconds to boot (it loads
   models). The UI shows a green "Web local" dot at the bottom-left when the
   sidecar is connected.

3. **Verify VoiceBox (optional but recommended).** Open **Configuración →
   Voces**. "VoiceBox conectado" = voice ready; "no detectado" = it's not
   installed/running (see `docs/VOICEBOX.md`) and generations will use the
   silent estimate. The panel also lists the available engines (qwen for
   Spanish, kokoro for ready-made English presets).

4. **Generate.** Create a video from **Estudio** (pick a style + voice) or the
   **Asistente** guided chat ("quiero crear un video"). content.run runs async;
   Estudio's "En vivo" tab streams progress.

## Notes / troubleshooting

- **Python changes need a full restart** — Vite HMR only reloads the frontend.
  After editing `python/kronara/*.py`, `preview_stop` then `preview_start` to
  reload the sidecar. (A stale sidecar looks like "broken in the browser but
  tests pass".)
- **VoiceBox not starting?** It needs its own install (Python 3.12 venv +
  ML deps + a cloned voice) — see `docs/VOICEBOX.md`. Config via env:
  `KRONARA_VOICEBOX_DIR` (default `D:\voicebox`), `KRONARA_VOICEBOX_URL`,
  `KRONARA_VOICEBOX_PROFILE`. Opt out of auto-start with
  `KRONARA_VOICEBOX_AUTOSTART=0`.
- **Never run the dev server with the Bash/PowerShell tools** — always use
  `preview_start` so the browser pane attaches and you can verify.
