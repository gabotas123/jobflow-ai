@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem ==== 1) Buscar Python REAL (descarta el "stub" de la Microsoft Store) ====
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe") do (
  if not defined PY if exist "%%~P" ( "%%~P" --version >nul 2>&1 && set "PY=%%~P" )
)
if not defined PY ( py -3 --version >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python --version >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [ERROR] No se encontro Python 3 real en este equipo.
  echo.
  echo   Solucion (2 minutos):
  echo   1. Abre  https://www.python.org/downloads/
  echo   2. Boton verde  "Download Python 3.12.x"
  echo   3. Al instalarlo, MARCA la casilla  "Add python.exe to PATH"
  echo   4. Cierra esta ventana y vuelve a hacer doble clic aqui.
  echo.
  pause
  exit /b 1
)

rem ==== 2) Primera vez: entorno virtual + dependencias + Chromium ====
if not exist ".venv\Scripts\python.exe" (
  echo [JobFlow AI] Primer uso: instalando todo (1-5 min, espera)...
  %PY% -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se pudo crear el entorno virtual.
    echo Verifica que "python --version" funcione en una terminal nueva.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
  ".venv\Scripts\python.exe" -m playwright install chromium
) else (
  echo [JobFlow AI] Entorno listo (reutilizado).
)

echo.
echo ============================================================
echo   JobFlow AI - Arrancando... EN UNOS SEGUNDOS SE ABRIRA EL
echo   NAVEGADOR CON LA APP (boton "CIERRA ESTA VENTANA" al final).
echo ============================================================
echo.
".venv\Scripts\python.exe" -m jobflow
if errorlevel 1 (
  echo.
  echo [ERROR] La app no arranco. Copia TODO este texto y env?alo al grupo.
  echo   Causa mas tipica: ya hay otra ventana de JobFlow abierta.
)
pause
