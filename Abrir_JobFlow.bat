@echo off
setlocal
cd /d "%~dp0"

rem Localizar Python (instalado via winget o PATH)
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

rem Primera ejecucion: crear entorno e instalar dependencias
if not exist ".venv\Scripts\python.exe" (
  echo [JobFlow AI] Instalando entorno virtual (primera vez)...
  "%PY%" -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

echo ============================================
echo   JobFlow AI - Abriendo la app en el navegador...
echo   Se abrira http://127.0.0.1:8000/
echo   Cierra esta ventana cuando termines.
echo ============================================
echo.
"%~dp0.venv\Scripts\python.exe" -m jobflow
pause
