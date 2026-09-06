@echo off
setlocal
cd /d "%~dp0"
title JobFlow AI - Instalacion automatica

echo ============================================================
echo   JOBFLOW AI - INSTALACION AUTOMATICA (un solo clic)
echo   NO CIERRES ESTA VENTANA. Todo se hace solo.
echo ============================================================
echo.

rem ==== 1) Buscar un Python REAL (jamas el de la Microsoft Store) ====
set "PYEXE="
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do if not defined PYEXE if exist "%%~P" "%%~P" --version >nul 2>&1 && set "PYEXE=%%~P"
if defined PYEXE goto py_ok

py -3 --version >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto py_ok

python --version >nul 2>&1
if errorlevel 1 goto no_python
where python 2>nul | find /i "WindowsApps" >nul 2>&1
if not errorlevel 1 goto auto_install
set "PYEXE=python"
goto py_ok

:no_python
echo [Paso 1 de 5] Python no encontrado: LO INSTALO AHORA...
goto auto_install_do

:auto_install
echo [Paso 1 de 5] Tu Python es el de la Microsoft Store (no sirve para este
echo        proyecto). LO REEMPLAZO por el Python oficial de Python.org...

:auto_install_do
where winget >nul 2>&1
if errorlevel 1 goto winget_no
winget install Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PYEXE%" "%PYEXE%" --version >nul 2>&1
if errorlevel 1 set "PYEXE=py -3"
%PYEXE% --version >nul 2>&1
if not errorlevel 1 goto py_ok
echo [ERROR] No se pudo instalar Python oficial. HAZLO A MANO:
echo   1. Desinstala el Python que viene de la Microsoft Store:
echo      Configuracion - Aplicaciones - Python (o "Python Software Foundation").
echo   2. Instala desde https://www.python.org/downloads/ (boton verde).
echo      IMPORTANTE: marca la casilla "Add python.exe to PATH".
echo   3. Vuelve a ejecutar este archivo.
pause
exit /b 1
:winget_no
echo [ERROR] Windows no tiene el instalador "winget". HAZLO A MANO:
echo   https://www.python.org/downloads/  (boton verde, marcar "Add python.exe to PATH")
pause
exit /b 1

:py_ok
echo OK - Python oficial detectado:
%PYEXE% --version
echo.

echo Paso 2 de 5: instalando Git (para actualizar despues)...
where winget >nul 2>&1
if not errorlevel 1 winget install Git.Git --accept-package-agreements --accept-source-agreements --silent
if errorlevel 1 echo   (Git no se pudo instalar; no es imprescindible.)

echo.
echo Paso 3 de 5: creando el entorno del proyecto (1-2 min)...
if exist ".venv\Scripts\python.exe" goto env_ok
set "RETRYED="
:crear_env
%PYEXE% -m venv .venv
if exist ".venv\Scripts\python.exe" goto env_created
if not defined RETRYED (
  echo   El Python actual no pudo crear el entorno. Instalando Python oficial...
  set "RETRYED=1"
  goto auto_install
)
echo [ERROR] No se pudo crear el entorno de ninguna forma.
echo   Desinstala el Python de la Microsoft Store y usa el de python.org.
pause
exit /b 1
:env_created
echo   + asegurando pip dentro del entorno (Python 3.13/3.14 ya no lo incluye)...
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo   [ERROR] pip no esta disponible. Reinstala Python desde python.org y repite.
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
  echo   Envia este texto al grupo.
  pause
  exit /b 1
)
goto env_ok2
:env_ok
echo   Entorno ya existia; reutilizado.
:env_ok2
echo   Entorno y dependencias listos.

echo.
echo Paso 4 de 5: descargando Chromium para la busqueda de empleos (2-4 min)...
".venv\Scripts\python.exe" -m playwright install chromium

echo.
echo Paso 5 de 5: abriendo la aplicacion...
echo ============================================================
echo   EN UNOS SEGUNDOS SE ABRIRA HTTP://127.0.0.1:8000/
echo   Si no se abre, escribelo en el navegador.
echo   Para cerrar la app: cierra esta ventana.
echo ============================================================
echo.
".venv\Scripts\python.exe" -m jobflow
if errorlevel 1 echo [ERROR] La app no arranco. Copia este texto y envialo al grupo.
pause
