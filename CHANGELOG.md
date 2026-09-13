# 📜 CHANGELOG — JobFlow AI

Todos los cambios del proyecto, con fecha y commit. El historial vivo está en:
**https://github.com/gabotas123/jobflow-ai/commits/main**

---

## 09-13 · v0.6.1 — Inicio de sesión que sí conecta
- El login se quedaba cargando: los portales bloquean el navegador de automatización.
  Ahora JobFlow abre **tu Chrome/Edge** con un perfil propio, y hay botones
  **«Ya inicié sesión»** y **«Cancelar»**. La verificación reconoce páginas de bloqueo.

## 09-13 · v0.6 — Lectura de avisos, cuentas de empleo y postulación automática
- **Búsqueda real**: Bumeran (API pública), Computrabajo y LinkedIn vuelven a
  devolver vacantes (antes 0 resultados en todos los portales, también en Render).
- **Leer aviso por enlace** (`POST /api/jobs/extract`): empresa, puesto,
  descripción, ubicación, modalidad, fecha, herramientas, años y formación.
  Solo lee páginas públicas y bloquea direcciones internas.
- **Cuentas de Bumeran y Computrabajo**: inicias sesión en una ventana real del
  portal; JobFlow guarda solo la sesión cifrada, nunca la contraseña.
- **Postulación automática** individual o por lote con una autorización. Se
  detiene ante CAPTCHA, pruebas, términos o preguntas sin dato confirmado; marca
  "postulada" solo con la confirmación del portal y guarda captura. Un envío
  incierto nunca se repite solo. Detalle en `CAMBIOS_V06.md`.
- **Paleta verde claro** (modo claro por defecto).

## 09-06 01:10 · `09a6c9c` — fix crítico: Python de la Microsoft Store
- El instalador ahora **detecta el Python de la Microsoft Store** (no puede crear
  entornos virtuales) y lo **reemplaza automáticamente por el Python oficial** de
  python.org (vía winget), con **reintento** si el entorno falla.
- Mensajes claros con pasos manuales si `winget` no existe.

## 09-06 01:05 · `2ecbdd8` — Compatible con Python 3.13/3.14
- El entorno ahora **instala `pip` explícitamente** (`ensurepip`), porque Python
  3.13/3.14 ya no lo incluyen.
- Errores de instalación **visibles** en pantalla (log `pip_install.log`).
- Nuevo **`Diagnostico.bat`** para reportar el estado exacto de una máquina.

## 09-06 01:02 · `de3a804` — Resumen del proyecto para el equipo
- **`RESUMEN_PROYECTO.md`**: arquitectura, decisiones de diseño, problemas
  resueltos, reglas para colaboradores y roadmap.

## 09-06 00:59 · `996280e` — Lanzadores a prueba de balas
- `.bat` reescritos en estructura simple (`goto`, ASCII puro, CRLF) y **verificados**:
  la app arranca con doble clic.

## 09-06 00:55 · `a52afc9` — Fix crítico: `.bat` con CRLF
- `cmd.exe` fallaba con archivos en LF ("la ventana se abre y se cierra").
- Se añade **`.gitattributes`** para que Git entregue los `.bat` en CRLF a todos.

## 09-06 00:54 · `6515909` — Puerto libre automático
- La app **elige sola un puerto libre** (8000, 8001…) y muestra la URL correcta.
- Lanzadores **validan que Python sea real** (descartan el "stub" de la Store).

## 09-06 00:48 · `d7fba54` — Instalador de un solo clic
- **`Instalar_Todo.bat`**: instala Python/Git si faltan, entorno, dependencias y
  Chromium, y abre la app. **`GUIA_COMPANEROS.md`** simplificada.

## 09-06 00:43 · `1861652` — Guía paso a paso para compañeros
- **`GUIA_COMPANEROS.md`** con opciones ZIP/Git, verificación y tablas de errores.

## 09-06 00:37 · `7cdd424` — Lanzador robusto
- `Abrir_JobFlow.bat` detecta Python 3 en varias rutas, instala Chromium en la
  primera ejecución y abre la web.

## 09-06 00:02 · `ba4e19a` — Colaboración Git/GitHub
- Guía de colaboración en el README + **`Publicar_GitHub.bat`**.

## 09-06 00:02 · `3f5d7c3` — JobFlow AI v0.3 (primera versión pública)
- Motor XYZ (30/30/25/15) · parser adaptativo multi-perfil · generación de CV
  corregido (DOCX + **LaTeX**) · autofill agnóstico · **búsqueda real de empleos**
  (Bumeran, Computrabajo, Indeed, LinkedIn) · puestos objetivo con rango salarial ·
  conector correo↔solicitud · tracker con envío automático · SPA funcional.

---

## 🔎 Cómo ver los cambios (para todo el equipo)

| Ver | Cómo |
|---|---|
| **Historial completo (web)** | <https://github.com/gabotas123/jobflow-ai/commits/main> |
| **Qué cambió en un archivo** | En GitHub: abrir el archivo → pestaña **History** → clic a cada commit |
| **Cambios sin subir (locales)** | Terminal: `git status` y `git diff` |
| **Últimos commits** | Terminal: `git log --oneline -10` |
| **Traer cambios de otros** | Terminal: `git pull` |
