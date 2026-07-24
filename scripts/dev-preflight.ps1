# Kill orphan Kronara sidecar processes before starting the dev server.
#
# Every run of `npm run tauri dev` used to leave behind a sidecar process
# whenever the parent crashed abnormally (WebView2 crashes, Ctrl+C from a
# bad state, EBUSY on target/debug/kronara.exe, etc.) -- confirmed on this
# machine by Get-Process kronara-sidecar returning multiple entries with
# different session tokens after a few restarts, each still holding a
# SQLite lock on kronara.db. That silently blocked the next real session's
# first write and looked like "the app hangs on Guardando".
#
# Runs preflight-safe: only touches processes whose name explicitly matches
# our sidecar. Never nukes an unrelated python.exe. Silent success (no
# output when nothing is found) so it doesn't spam `npm run dev` output.

$ErrorActionPreference = 'SilentlyContinue'

$killedNames = @()

# Frozen PyInstaller binary (kronara-sidecar-x86_64-pc-windows-msvc.exe)
Get-Process -Name 'kronara-sidecar*' | ForEach-Object {
    $killedNames += "$($_.Name) PID $($_.Id)"
    $_ | Stop-Process -Force
}

# Dev-mode: python.exe launched with `-m kronara.sidecar` (see
# KRONARA_SIDECAR_DEV_PYTHON in sidecar_bridge.rs). Also cover the pure
# `python -m kronara.sidecar` invocation from the fresh-content harness.
Get-CimInstance -ClassName Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine -match 'kronara\.sidecar'
} | ForEach-Object {
    $killedNames += "python.exe PID $($_.ProcessId) (kronara.sidecar)"
    Stop-Process -Id $_.ProcessId -Force
}

if ($killedNames.Count -gt 0) {
    Write-Host "dev-preflight: cleaned up $($killedNames.Count) orphan sidecar process(es):" -ForegroundColor Yellow
    foreach ($name in $killedNames) {
        Write-Host "  - $name" -ForegroundColor DarkYellow
    }
}

# v0.8 Fase 2: bring the VoiceBox voice engine up with Kronara so a generated
# video already has a real cloned voice. Best-effort, never blocks the dev
# server (see scripts/start-voicebox.ps1).
$startVoicebox = Join-Path $PSScriptRoot 'start-voicebox.ps1'
if (Test-Path $startVoicebox) { & $startVoicebox }
