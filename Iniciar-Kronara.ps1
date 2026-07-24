# Lanzador de Kronara (web puro, sin Tauri).
#
# Doble-clic en Iniciar-Kronara.cmd -> este script deja TODO conectado con un
# clic: mata sidecars huérfanos, arranca VoiceBox si está instalado, levanta el
# servidor web (que auto-spawnea el sidecar Python), espera a Vite y abre el
# navegador. Cerrar esta ventana detiene el servidor.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== Kronara ==" -ForegroundColor Cyan

# 1) Limpieza de sidecars huérfanos (reutiliza el preflight existente).
if (Test-Path "$root\scripts\dev-preflight.ps1") {
  try { & powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\dev-preflight.ps1" } catch {}
}

# 2) .env presente?
if (-not (Test-Path "$root\.env")) {
  Write-Host "Aviso: no hay .env -- copia .env.example y agrega tus claves." -ForegroundColor Yellow
}

# 3) VoiceBox (opcional): si está instalado, arráncalo para voz clonada real.
if (Test-Path "$root\scripts\start-voicebox.ps1") {
  try {
    Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$root\scripts\start-voicebox.ps1" -WindowStyle Minimized
    Write-Host "VoiceBox: arrancando (ventana minimizada)." -ForegroundColor DarkGray
  } catch { Write-Host "VoiceBox no se pudo arrancar (se usará voz estimada)." -ForegroundColor DarkGray }
}

# 4) Dependencias del front instaladas?
if (-not (Test-Path "$root\node_modules")) {
  Write-Host "Instalando dependencias (npm install)..." -ForegroundColor Yellow
  npm install
}

# 5) Servidor web (npm run dev -> predev limpia sidecars, vite spawnea el sidecar).
$vite = Start-Process npm -ArgumentList 'run','dev' -PassThru -NoNewWindow

# 6) Espera a que Vite responda en :5173 y abre el navegador.
$url = 'http://localhost:5173'
Write-Host "Esperando a Vite en $url ..." -ForegroundColor DarkGray
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { break }
  } catch {}
}
Start-Process $url
Write-Host "Kronara abierto en $url. Cierra esta ventana para detener el servidor." -ForegroundColor Green

# 7) Mantén la ventana viva junto al servidor.
if ($vite) { Wait-Process -Id $vite.Id }
