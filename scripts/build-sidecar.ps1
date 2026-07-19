$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = if ($env:KRONARA_PYTHON) { $env:KRONARA_PYTHON } else { 'python' }

& $Python -m PyInstaller `
  --onefile `
  --clean `
  --noconfirm `
  --paths (Join-Path $ProjectRoot 'python') `
  --distpath (Join-Path $ProjectRoot 'src-tauri\binaries') `
  --workpath (Join-Path $ProjectRoot '.pyinstaller-build') `
  --specpath (Join-Path $ProjectRoot '.pyinstaller-spec') `
  --name 'kronara-sidecar-x86_64-pc-windows-msvc' `
  (Join-Path $ProjectRoot 'python\kronara\sidecar.py')

