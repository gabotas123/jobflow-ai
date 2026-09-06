# 📘 GUÍA PARA COMPAÑEROS — Instalar y usar JobFlow AI

> Proyecto: **JobFlow AI** · Repositorio: https://github.com/gabotas123/jobflow-ai
> Tiempo total: **15–20 minutos** (la mayoría esperando descargas).

---

## 📋 Antes de empezar (10 segundos de lectura)

Necesitas **Windows 10 u 11** y **conexión a internet**. No hace falta saber programar:
el lanzador hace todo, pero Python se instala a mano en un paso.

---

## PASO 1 — Instalar Python (5 min)

1. Abre tu navegador y entra a: **https://www.python.org/downloads/**
2. Haz clic en el botón verde **"Download Python 3.12.x"**.
3. Cuando termine la descarga, abre el archivo `python-3.12.x-amd64.exe`.
4. **MUY IMPORTANTE:** en la primera pantalla marca la casilla **"Add python.exe to PATH"** (abajo).
5. Haz clic en **"Install Now"** y espera a que diga **"Setup was successful"** → Cerrar.

**Verifica que quedó instalado:**
- Presiona `Win + R`, escribe `cmd` y Enter.
- Escribe: `python --version`
- ✅ **Debe mostrar** `Python 3.12.x`. Si muestra "Microsoft Store", ve al apartado *Problemas*.
- Cierra la ventana (cmd).

---

## PASO 2 — Instalar Git (3 min) *(solo para actualizar sin descargar todo de nuevo)*

1. Entra a: **https://git-scm.com/download/win**
2. Descarga e instala con los valores **por defecto** (siguiente, siguiente, instalar).
3. Verifica: abre `cmd` → `git --version` → debe mostrar `git version 2.x`.

> ¿No quieres Git? Puedes usar la **Opción B del Paso 3** (descargar el ZIP).

---

## PASO 3 — Traer el código

### Opción A — con Git (recomendada: podrás actualizar con 1 comando)
1. Abre **PowerShell** (menú Inicio → escribe "PowerShell" → Enter). Se abre en `C:\Users\TUNOMBRE`.
2. Pega y ejecuta:
   ```powershell
   git clone https://github.com/gabotas123/jobflow-ai
   cd jobflow-ai
   ```
3. ✅ Al terminar, la carpeta `jobflow-ai` existe en `Documentos` o en tu carpeta de usuario.

> ⚠️ Si pide usuario/contraseña: **primero acepta la invitación** que te llegó por correo de GitHub
> (o en <https://github.com/gabotas123/jobflow-ai> → botón **"Accept invitation"**).

### Opción B — sin Git (ZIP)
1. Entra a <https://github.com/gabotas123/jobflow-ai>.
2. Botón verde **"Code"** → **"Download ZIP"**.
3. Descomprime el ZIP y **entra dentro de la carpeta** `jobflow-ai`.
4. *Para actualizar a futuro: vuelve a descargar el ZIP (se pierden solo los datos locales).*

---

## PASO 4 — Abrir la app (el paso importante)

1. Entra a la carpeta `jobflow-ai` que acabas de crear.
2. **Doble clic en `Abrir_JobFlow.bat`** (si Windows pregunta por seguridad: **"Más información" → "Ejecutar de todas formas"**).
3. Se abre una **ventana negra**. La primera vez verás, en orden:
   ```
   [JobFlow AI] Instalando entorno virtual y dependencias (primera vez, 1-2 min)...
   [JobFlow AI] Descargando Chromium para la búsqueda de empleos (solo esta vez, 2-4 min)...
   JobFlow AI -> http://127.0.0.1:8000/
   Uvicorn running on http://127.0.0.1:8000
   ```
4. ✅ **Se abre tu navegador solo** con la app (Dashboard, Análisis, Autofill, Empleos, Postulaciones, Correo).
   - Si no se abre: escribe **http://127.0.0.1:8000/** en la barra del navegador.
5. **Para cerrar:** haz clic en la X de la ventana negra (o Ctrl+C dentro de ella).

> 🔒 La app corre **solo en tu computadora** (localhost). Nadie más puede entrar a tu instancia.

---

## PASO 5 — Tu data es tuya (y de nadie más)

- La base de datos (`data/jobflow.db`) **no está en GitHub**: cada uno tiene sus CVs y postulaciones.
- Al abrir por primera vez verás un **perfil de ejemplo** (Gabriel). Puedes subir tus propios CVs
  en la pestaña **Perfiles & CV**.
- **Nunca subas a GitHub** la carpeta `.venv`, la base de datos ni el archivo `.env`
  (el `.gitignore` ya los bloquea; no los arrastres manualmente).

---

## PASO 6 — Flujo de trabajo en equipo (para los que editan código)

Siempre (desde la carpeta `jobflow-ai`, en PowerShell):
```powershell
git pull                                    # 1. traer los cambios de los demás
git checkout -b feature/tu-nombre-de-tarea  # 2. rama propia
git add . ; git commit -m "qué hiciste"
git push origin feature/tu-nombre-de-tarea  # 3. subir
```
4. En GitHub: abre el **Pull Request** → espera revisión → se fusiona a `main`.

> Regla de oro: **nunca** trabajes directo en `main`; cada uno en su rama y luego Pull Request.

---

## 🛠 PROBLEMAS COMUNES (solución exacta)

| # | Qué pasa | Qué hacer |
|---|---|---|
| 1 | `python --version` abre la **Microsoft Store** | El "alias" de la Store bloquea. Solución: instala Python igual (Paso 1) y usa `py --version`; si sigue, desinstala el alias: Configuración → Aplicaciones → Alias de ejecución de aplicaciones → apaga `python.exe` y `py.exe` |
| 2 | `python --version` no muestra nada | **Cierra y abre una terminal nueva** (el PATH se refresca) y verifica que marcaste "Add python.exe to PATH". Reboot opcional |
| 3 | La ventana negra dice "Python no encontrado" | Instala Python (Paso 1) y verifica con `python --version` en cmd antes de repetir |
| 4 | La ventana negra se cierra sola | Abre PowerShell en la carpeta y corre `.\Abrir_JobFlow.bat` para ver el error completo |
| 5 | SmartScreen bloquea el .bat | "Más información" → "Ejecutar de todas formas" |
| 6 | Antivirus avisa por pip/Chromium | Permitir la excepción (es el navegador headless del proyecto, verificado por GitHub) |
| 7 | `git clone` pide usuario/contraseña | Acepta antes la invitación de colaborador (correo de GitHub o botón "Accept invitation" en el repo) |
| 8 | Descarga de Chromium falla | Repite el doble clic del .bat (retoma); si no, la pestaña Empleos igual funciona con los enlaces directos |
| 9 | Error `ModuleNotFoundError` al abrir | El entorno quedó incompleto: elimina la carpeta `.venv` y vuelve a ejecutar `Abrir_JobFlow.bat` |
| 10 | El navegador no abre solo | Escribe manualmente **http://127.0.0.1:8000/** |
| 11 | "Port 8000 already in use" | Ya hay otra instancia abierta: ciérrala (ventana negra) o reinicia la PC |
| 12 | No puedo descargar nada | Revisa conexión; Chromium pesa ~200 MB (la app funciona igual sin él, con menos vacantes automáticas) |

---

## 🍎 ¿Mac/Linux? (opcional, mismo código)

```bash
git clone https://github.com/gabotas123/jobflow-ai
cd jobflow-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m jobflow
```
(El lanzador `.bat` es solo Windows; aquí es todo por terminal.)

---

*Guía generada por el equipo de JobFlow AI · Innova ULIMA. Si algo sale distinto a lo descrito,
copia el error exacto de la ventana negra y compártelo en el chat del equipo.*
