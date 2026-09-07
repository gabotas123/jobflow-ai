# 📜 CHANGELOG — JobFlow AI

Todos los cambios del proyecto, con fecha y commit. El historial vivo está en:
**https://github.com/gabotas123/jobflow-ai/commits/main**

---

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
