@echo off
setlocal
cd /d "%~dp0"
set "GH=C:\Program Files\GitHub CLI\gh.exe"

echo ============================================================
echo   JobFlow AI - Publicar en GitHub (un solo clic)
echo ============================================================
echo.
"%GH%" auth status >nul 2>&1
if errorlevel 1 (
  echo [1/2] Necesitas iniciar sesion en GitHub. Se abrira tu navegador...
  echo       Sigue los pasos: GITHUB.COM - HTTPS - Login con navegador.
  "%GH%" auth login
)

echo [2/2] Creando repositorio PRIVADO y subiendo el codigo...
"%GH%" repo create jobflow-ai --private --source . --push --description "JobFlow AI - Copiloto IA de busqueda laboral (Innova ULIMA)"

echo.
echo ============================================================
echo   LISTO. Tu repo:  https://github.com/TU_USUARIO/jobflow-ai
echo.
echo   Para invitar a tu amigo (despues de que se cree):
echo     gh repo edit jobflow-ai --add-collaborator USUARIO --permission push
echo ============================================================
pause
