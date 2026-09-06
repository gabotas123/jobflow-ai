@echo off
setlocal
cd /d "%~dp0"

rem ==== 1) Localizar Python 3 ====
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [ERROR] Python 3 no encontrado.
  echo Instala Python desde https://www.python.org/downloads/
  echo IMPORTANTE: marca la casilla "Add python.exe to PATH".
  pause
  exit /b 1
)

rem ==== 2) Primera ejecucion: entorno virtual + dependencias ====
if not exist ".venv\Scripts\python.exe" (
  echo [JobFlow AI] Instalando entorno virtual y dependencias (primera vez, 1-2 min)...
  %PY% -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se pudo crear el entorno virtual. Verifica que Python 3 funcione.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
  echo [JobFlow AI] Descargando Chromium para la busqueda de empleos (solo esta vez, 2-4 min)...
  ".venv\Scripts\python.exe" -m playwright install chromium
)

echo ============================================
echo   JobFlow AI - Abriendo la app en tu navegador...
echo   http://127.0.0.1:8000/
echo   Cierra esta ventana cuando termines.
echo ============================================
echo.
"%~dp0.venv\Scripts\python.exe" -m jobflow
pause
