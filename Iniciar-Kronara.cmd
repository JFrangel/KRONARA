@echo off
REM Doble-clic para lanzar Kronara (web puro). Abre el navegador con todo conectado.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Iniciar-Kronara.ps1"
if errorlevel 1 (
  echo.
  echo Kronara termino con un error. Revisa el mensaje de arriba.
  pause
)
