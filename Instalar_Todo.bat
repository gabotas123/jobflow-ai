@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title JobFlow AI - Instalacion automatica

echo =====================================================================
echo   JOBFLOW AI - INSTALACION AUTOMATICA (un solo clic)
echo   NO CIERRES ESTA VENTANA. Todo se hace solo.
echo   Cuando termine, se abrira la pagina web.
echo =====================================================================
echo.
echo   Paso 1 de 5: revisando Python...
echo.

set "PYEXE="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe") do (
  if not defined PYEXE if exist "%%~P" ( "%%~P" --version >nul 2>&1 && set "PYEXE=%%~P" )
)
if not defined PYEXE ( py -3 --version >nul 2>&1 && set "PYEXE=py -3" )
if not defined PYEXE ( python --version >nul 2>&1 && set "PYEXE=python" )

if not defined PYEXE (
  echo   Python no esta instalado. LO INSTALO AHORA (3-5 minutos, espera)...
  where winget >nul 2>&1
  if not errorlevel 1 (
    winget install Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
  ) else (
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\python-3.12.10-amd64.exe'" >nul 2>&1
    "%TEMP%\python-3.12.10-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1
  )
  echo.
  echo   Python instalado correctamente.
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if exist "%PYEXE%" goto pyok
  where py >nul 2>&1 && (set "PYEXE=py -3" & goto pyok)
  where python >nul 2>&1 && (set "PYEXE=python" & goto pyok)
  echo.
  echo   [ERROR] No se pudo instalar Python. Hazlo a mano:
  echo   https://www.python.org/downloads/  (marca "Add python.exe to PATH")
  pause
  exit /b 1
)
:pyok
echo   OK - Python listo.

echo.
echo   Paso 2 de 5: instalando Git (para actualizar despues; 2 min)...
where winget >nul 2>&1
if not errorlevel 1 (
  winget install Git.Git --accept-package-agreements --accept-source-agreements --silent >nul 2>&1
  echo   OK - Git listo.
) else (
  echo   (Git no se pudo instalar; no es imprescindible para abrir la app.)
)

echo.
echo   Paso 3 de 5: creando el entorno del proyecto (1-2 min)...
if not exist ".venv\Scripts\python.exe" (
  %PYEXE% -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo   [ERROR] No se pudo crear el entorno. Repite esta ventana o
    echo   instala Python desde https://www.python.org/downloads/
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
  echo   Entorno y dependencias listos.
) else (
  echo   Entorno ya existia; reutilizado.
)

echo.
echo   Paso 4 de 5: descargando Chromium para la busqueda de empleos (2-4 min, solo la primera vez)...
".venv\Scripts\python.exe" -m playwright install chromium

echo.
echo   Paso 5 de 5: abriendo la aplicacion...
echo.
echo   =====================================================================
echo     EN UNOS SEGUNDOS SE ABRIRA HTTP://127.0.0.1:8000/ EN TU NAVEGADOR
echo     Si no se abre, escribelo tu mismo en la barra del navegador.
echo     Para cerrar la app: cierra esta ventana.
echo   =====================================================================
echo.
".venv\Scripts\python.exe" -m jobflow
pause
