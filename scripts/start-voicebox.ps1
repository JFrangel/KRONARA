# Auto-start the VoiceBox backend alongside Kronara (v0.8 Fase 2).
#
# The idea (per the product owner): launching Kronara should bring the voice
# engine up automatically, so a video generated moments later already has a
# real cloned voice available instead of degrading to the silent estimate.
#
# Fully best-effort and non-fatal: if VoiceBox is already running, not
# installed, or anything errors, this prints a hint and returns -- it must
# never block `npm run dev`. VoiceBox itself is optional (FallbackVoiceProvider
# degrades gracefully when it's absent -- see docs/VOICEBOX.md).
#
# Config (env, all optional):
#   KRONARA_VOICEBOX_DIR   folder where `git clone voicebox` lives (default D:\voicebox)
#   KRONARA_VOICEBOX_URL   server origin (default http://127.0.0.1:17493)
#   KRONARA_VOICEBOX_AUTOSTART=0   opt out of auto-start entirely

$ErrorActionPreference = 'SilentlyContinue'

if ($env:KRONARA_VOICEBOX_AUTOSTART -eq '0') { return }

$voiceboxDir = if ($env:KRONARA_VOICEBOX_DIR) { $env:KRONARA_VOICEBOX_DIR } else { 'D:\voicebox' }
$url = if ($env:KRONARA_VOICEBOX_URL) { $env:KRONARA_VOICEBOX_URL } else { 'http://127.0.0.1:17493' }

# Derive the port from the URL (default 17493).
$port = 17493
try { $port = ([Uri]$url).Port } catch {}

# 1. Already up? Ping /health and bail out quietly if it answers.
try {
    $null = Invoke-WebRequest -Uri "$url/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "voicebox: already running on $url" -ForegroundColor DarkGray
    return
} catch {}

# 2. Installed? The backend needs its own venv (Python 3.12 -- see docs/VOICEBOX.md).
$venvPython = Join-Path $voiceboxDir 'backend\venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "voicebox: not installed at $voiceboxDir (voz caera al estimador silencioso)." -ForegroundColor Yellow
    Write-Host "          setup: docs/VOICEBOX.md  |  opt out: KRONARA_VOICEBOX_AUTOSTART=0" -ForegroundColor DarkYellow
    return
}

# 3. Spawn the backend detached (hidden window), cwd = voicebox dir so
#    `backend.main` imports. First run auto-downloads models (multi-GB), so we
#    do NOT wait on /health here -- Kronara starts immediately; the voice
#    provider polls VoiceBox when it actually synthesizes.
Write-Host "voicebox: starting backend on $url ..." -ForegroundColor Cyan
Start-Process -FilePath $venvPython `
    -ArgumentList '-m', 'uvicorn', 'backend.main:app', '--port', "$port" `
    -WorkingDirectory $voiceboxDir `
    -WindowStyle Hidden | Out-Null
