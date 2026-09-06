# 👋 GUÍA PASO A PASO (súper fácil) — Abre JobFlow AI en tu computadora

> **Cuánto tarda:** 10–25 minutos. **Todo se instala solo** gracias al botón
> `Instalar_Todo.bat`. Solo tienes que hacer 3 cosas: **aceptar la invitación**,
> **descargar el código** y **hacer doble clic en un botón**.

---

## ✅ REQUISITO UNO — Acepta la invitación (1 min, la primera vez)

Te llegó un **correo de GitHub** con el título **"[gabotas123/jobflow-ai] Invitation to collaborate"**.

1. Abre ese correo.
2. Presiona el botón **"Accept invitation"** (Aceptar invitación).
3. Entra a: **https://github.com/gabotas123/jobflow-ai**
4. Debes poder ver la página del proyecto (si te pide "Accept", apriétalo).

> **¿Por qué?** Sin esto, la descarga pedirá una contraseña y no funcionará.

---

## ✅ REQUISITO DOS — Descarga el código (elige UNA opción)

### OPCIÓN A — la más fácil: descargar el ZIP (sin programas)
1. Abre: **https://github.com/gabotas123/jobflow-ai**
2. Presiona el botón verde **“Code”** (arriba a la derecha).
3. Presiona **“Download ZIP”**.
4. Se descarga `jobflow-ai-main.zip`.
5. Ve a la carpeta **Descargas**, haz clic derecho sobre el ZIP y elige **“Extraer todo…”** → **Extraer**.
6. Entra a la carpeta **`jobflow-ai-main`** que se creó. Esa es tu carpeta del proyecto.

> Para tener novedades después, puedes re-descargar el ZIP (y volver a hacer el paso 3) — tu
> información no se pierde.

### OPCIÓN B — con Git (si prefieres actualizar con un clic)
1. Abre el menú **Inicio** → escribe `PowerShell` → ábrelo.
2. Copia y pega estas dos líneas, presionando ENTER al final de cada una:
   ```
   git clone https://github.com/gabotas123/jobflow-ai
   cd jobflow-ai
   ```
3. Cuando termine, la carpeta `jobflow-ai` está en tu carpeta de usuario.

---

## ✅ PASO TRES — Abre la app (el botón mágico)

1. Entra a la carpeta del proyecto (carpeta `jobflow-ai` o `jobflow-ai-main`).
2. **Haz doble clic en `Instalar_Todo.bat`** (o `Abrir_JobFlow.bat`).
   - Si Windows muestra una advertencia azul: presiona **“Más información”** y luego **“Ejecutar de todas formas”**.
3. Se abre una **ventana negra**. **NO la cierres.** Vas a ver:
   - `Paso 1 de 5: revisando Python...`
   - `Paso 2 de 5: instalando Git...`
   - `Paso 3 de 5: creando el entorno...`
   - `Paso 4 de 5: descargando Chromium...` ← esta parte es la larga (2-4 minutos)
   - `Paso 5 de 5: abriendo la aplicacion...` y `Uvicorn running on http://127.0.0.1:8000`
4. ✅ **Se abre tu navegador con la app.** 
   - Si NO se abre: abre Chrome/Edge y escribe en la barra: `http://127.0.0.1:8000/`
5. **Ya puedes usarla** (Dashboard, Análisis, Empleos, Postulaciones...).

> ⚠️ **Para cerrar la app:** haz clic en la X de la **ventana negra** (no en el navegador).
> La ventana negra debe quedar abierta **mientras usas la app**.

---

## ✅ PASO CUATRO — Ya funciona, ¿lo compruebo?

1. En el **Dashboard** (al abrir) debe aparecer el perfil **Gabriel Alberto Gutiérrez Ayala**.
2. En la pestaña **Empleos**, presiona **“🔎 Buscar empleos para este perfil”**.
   Debe listar vacantes reales de Computrabajo/Indeed/LinkedIn (puede tardar ~40 segundos).
3. En **Perfiles & CV** puedes subir tu propio CV (PDF).

Si las tres cosas pasan, quedó todo perfecto.

---

## 🛟 ¿ALGO SALE MAL? Mirá aquí (los 5 más comunes)

| Qué ves / qué pasa | Qué hacer |
|---|---|
| **La ventana negra dice "Python no encontrado"** | Instala Python desde **python.org/downloads** → botón verde → instalar con la casilla **“Add python.exe to PATH”** marcada → darle doble clic de nuevo al `Instalar_Todo.bat` |
| **Dice "Descarga de Chrome/Chromium" y tarda mucho** | Es normal la primera vez (200 MB, 2-4 min). No toques nada. Si falla, cierra todo y vuelve a hacer doble clic al `.bat` |
| **El navegador no se abre** | Escribe tú mismo en la barra del navegador: `http://127.0.0.1:8000/` |
| **Pide contraseña al descargar** | No completaste el **Requisito uno** (aceptar la invitación). Hacelo y vuelve a descargar |
| **"puerto 8000 ya está en uso"** | Ya tienes la app abierta en otra ventana negra. Cierra la vieja (X) |

---

## 🔁 Actualizar el código (cuando les avisemos)

- **Si descargaste el ZIP:** vuelve a GitHub → **Code → Download ZIP** → extraer (tus postulaciones locales se conservan si usas la misma carpeta o copias la base).
- **Si usaste Git:** abre PowerShell en la carpeta y escribe: `git pull`

---

## ♥️ IMPORTANTE (seguridad)

- La app corre **solo en tu computadora**. Nadie más puede ver tu instancia.
- **No subas** a GitHub nada de lo que aparece en `.gitignore` (la base de datos con los CVs, la carpeta `.venv`, el archivo `.env`).
- Tus CVs y postulaciones están **en tu máquina**, no en el servidor.

---

*Dudas: copien el texto completo de la **ventana negra** y envíenlo al grupo. Eso nos dice exactamente qué pasó.*
