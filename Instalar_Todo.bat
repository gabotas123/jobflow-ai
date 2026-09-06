@echo off
setlocal
cd /d "%~dp0"
title JobFlow AI - Instalacion automatica

echo ============================================================
echo   JOBFLOW AI - INSTALACION AUTOMATICA (un solo clic)
echo   NO CIERRES ESTA VENTANA. Todo se hace solo.
echo ============================================================
echo.

rem ==== 1) Python ====
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" "%PY%" --version >nul 2>&1
if not errorlevel 1 goto py_ok

set "PY=py -3"
py -3 --version >nul 2>&1
if not errorlevel 1 goto py_ok

set "PY=python"
python --version >nul 2>&1
if not errorlevel 1 goto py_ok

echo Python no esta instalado. LO INSTALO AHORA (3-5 minutos, espera)...
where winget >nul 2>&1
if not errorlevel 1 goto instalar_winget
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\python312.exe'"
"%TEMP%\python312.exe" /quiet InstallAllUsers=0 PrependPath=1
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto py_ok
set "PY=py -3"
goto py_check_installed

:instalar_winget
winget install Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto py_ok
set "PY=py -3"

:py_check_installed
%PY% --version >nul 2>&1
if not errorlevel 1 goto py_ok
py -3 --version >nul 2>&1
if not errorlevel 1 goto py_ok
echo [ERROR] No se pudo instalar Python. Hazlo a mano:
echo   https://www.python.org/downloads/   (marca "Add python.exe to PATH")
pause
exit /b 1

:py_ok
echo OK - Python detectado:
%PY% --version
echo.

echo Paso 2 de 5: instalando Git (para actualizar despues)...
where winget >nul 2>&1
if not errorlevel 1 winget install Git.Git --accept-package-agreements --accept-source-agreements --silent
if errorlevel 1 echo   (Git no se pudo instalar; no es imprescindible.)

echo.
echo Paso 3 de 5: creando el entorno del proyecto (1-2 min)...
if exist ".venv\Scripts\python.exe" goto env_ok
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto env_error
echo   + asegurando pip dentro del entorno (Python 3.13/3.14 ya no lo incluye)...
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo   [ERROR] pip no esta disponible dentro del entorno. Reinstala Python
  echo   marcando "Add python.exe to PATH" y repite.
  pause
  exit /b 1
)
echo   + instalando dependencias (esta linea puede tardar)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt > pip_install.log 2>&1
if errorlevel 1 (
  echo   [ERROR] No se pudieron instalar las dependencias. Causa exacta:
  echo   --------------------------------------------------------------
  type pip_install.log
  echo   --------------------------------------------------------------
  echo   Envia este texto al grupo para resolverlo.
  pause
  exit /b 1
)
goto env_ok2
:env_error
echo [ERROR] No se pudo crear el entorno. Repite esta ventana o
echo instala Python desde https://www.python.org/downloads/
pause
exit /b 1
:env_ok
echo   Entorno ya existia; reutilizado.
:env_ok2
echo   Entorno y dependencias listos.

echo.
echo Paso 4 de 5: descargando Chromium para la busqueda de empleos (2-4 min, solo la primera vez)...
".venv\Scripts\python.exe" -m playwright install chromium

echo.
echo Paso 5 de 5: abriendo la aplicacion...
echo.
echo ============================================================
echo   EN UNOS SEGUNDOS SE ABRIRA HTTP://127.0.0.1:8000/
echo   Si no se abre, escribelo en el navegador.
echo   Para cerrar la app: cierra esta ventana.
echo ============================================================
echo.
".venv\Scripts\python.exe" -m jobflow
if errorlevel 1 echo [ERROR] La app no arranco. Copia este texto y envialo al grupo.
pause
