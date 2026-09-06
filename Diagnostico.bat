@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   DIAGNOSTICO DE JOBFLOW AI
echo   (ejecuta esto y envia TODO el texto al grupo)
echo ============================================================
echo.
echo 1) Versiones de Python en tu sistema:
py -3 --version 2>&1
python --version 2>&1
echo.
echo 2) Python que usaria el lanzador:
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" --version
) else (
  echo   (no hay Python 3.12 en la ruta estandar - usara "py" o "python")
)
echo.
echo 3) Entorno del proyecto (.venv):
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" --version
  ".venv\Scripts\python.exe" -m pip --version
) else (
  echo   (aun no existe el entorno - se creara al ejecutar el instalador)
)
echo.
echo 4) Ultimo error de instalacion (si existe pip_install.log):
if exist "pip_install.log" (
  type pip_install.log
) else (
  echo   (sin log todavia)
)
echo.
echo ============================================================
echo   Listo. Copia TODO el texto de arriba y envialo al grupo.
echo ============================================================
pause
