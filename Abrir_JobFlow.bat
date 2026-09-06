@echo off
setlocal
cd /d "%~dp0"

rem ==== 1) Buscar Python (descarta el "stub" de la Microsoft Store) ====
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" "%PY%" --version >nul 2>&1
if not errorlevel 1 goto encontrado

set "PY=py -3"
py -3 --version >nul 2>&1
if not errorlevel 1 goto encontrado

set "PY=python"
python --version >nul 2>&1
if not errorlevel 1 goto encontrado

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

:encontrado
echo Python listo.
if exist ".venv\Scripts\python.exe" goto reutilizar

echo [JobFlow AI] Primer uso: instalando todo (1-5 min, espera)...
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto venv_error
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
".venv\Scripts\python.exe" -m playwright install chromium
goto listo

:venv_error
echo [ERROR] No se pudo crear el entorno virtual.
echo Verifica que "python --version" funcione en una terminal nueva.
pause
exit /b 1

:reutilizar
echo Entorno listo (reutilizado).
:listo
echo.
echo ============================================================
echo   JobFlow AI - Arrancando... EN UNOS SEGUNDOS SE ABRIRA EL
echo   NAVEGADOR CON LA APP. Cierra esta ventana para detener.
echo ============================================================
echo.
".venv\Scripts\python.exe" -m jobflow
if errorlevel 1 echo [ERROR] La app no arranco. Copia este texto y envialo al grupo.
pause
