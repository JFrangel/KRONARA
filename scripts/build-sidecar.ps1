$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = if ($env:KRONARA_PYTHON) { $env:KRONARA_PYTHON } else { 'python' }
$PackageRoot = Join-Path $ProjectRoot 'python'
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$PackageRoot;$env:PYTHONPATH" } else { $PackageRoot }

& $Python -m PyInstaller `
  --onefile `
  --clean `
  --noconfirm `
  --paths $PackageRoot `
  --collect-submodules 'kronara' `
  --add-data "$(Join-Path $ProjectRoot 'config');config" `
  --add-data "$(Join-Path $ProjectRoot 'knowledge');knowledge" `
  --add-data "$(Join-Path $ProjectRoot 'benchmarks');benchmarks" `
  --distpath (Join-Path $ProjectRoot 'src-tauri\binaries') `
  --workpath (Join-Path $ProjectRoot '.pyinstaller-build') `
  --specpath (Join-Path $ProjectRoot '.pyinstaller-spec') `
  --name 'kronara-sidecar-x86_64-pc-windows-msvc' `
  (Join-Path $ProjectRoot 'python\kronara\sidecar.py')
