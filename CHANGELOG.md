# 📜 CHANGELOG — JobFlow AI

Todos los cambios del proyecto, con fecha y commit. El historial vivo está en:
**https://github.com/gabotas123/jobflow-ai/commits/main**

---

## 09-14 · Postulación masiva y pruebas reales en Bumeran y Computrabajo
- **Postulación masiva**: en Oportunidades marcas vacantes (o todas sobre una compatibilidad
  mínima) y «Postular a N vacantes». JobFlow lee cada aviso, descarta las incompatibles y las
  pone en cola. En Postulaciones: avance en vivo, enlace a cada aviso y «Detener cola».
- **Preguntas por responder**: las preguntas que ninguna postulación pudo contestar se agrupan;
  respondes una vez y se completan todas (con sugerencias de tu CV o respuestas previas).
- **Verificado con postulaciones reales autorizadas**: Bumeran respondió las preguntas de People
  Analytics, Grupo Palmas y Koplast y registró una postulación nueva; Computrabajo detecta sus 6
  preguntas obligatorias y se detiene sin enviar cuando faltan datos tuyos.
- Computrabajo: una capa fija se tomaba por ventana emergente; los obligatorios se marcan con
  `data-rule-required`; respuestas recortadas al límite de caracteres.
- Bumeran: el recuadro es «Tienes preguntas sin responder»; «Responder» se reconstruye al escribir
  y ahora se espera a que el envío termine antes de cerrar el navegador.
- Sin mensaje de confirmación, JobFlow revisa el aviso: «Postulado» confirma; «Postularme»
  disponible significa que no se envió (se puede reintentar sin riesgo).
- Respuestas: «disponibilidad para trabajar presencial» ya no se contesta con la fecha de
  incorporación; «Sí» en texto requiere evidencia de al menos la mitad de los temas; años por
  tema exigen todos; «¿A qué nivel manejas…?»; carrera y grado sin cursos.
- Abrir JobFlow cierra las copias anteriores y un candado deja la cola a un solo proceso
  (varias ventanas ejecutaban la cola con código distinto). «Ver captura» → enlace al aviso.

## 09-13 · Postulación que sí rellena las preguntas + LinkedIn
- **Bumeran**: registra la postulación al pulsar «Postularme» y luego abre «Responde las
  preguntas». JobFlow no reconocía esa ventana (sin marca de diálogo), leía el contador
  «0 / 2000» como pregunta e ignoraba el botón «Responder» desactivado. Ahora detecta la
  confirmación «Postulado el…», lee bien cada pregunta y la responde.
- **Respuestas desde el CV confirmado** (`cv_answers.py`): «¿Tienes experiencia en X?» → «Sí»
  citando la función real; «¿Cuántos años…?» → calculado con las fechas (requiere mes y año);
  niveles de idioma/herramientas. Sin evidencia, la pregunta queda para ti.
- Las preguntas pendientes llegan a «Respuestas» con las deducidas ya propuestas; al
  aprobarlas, «Enviar respuestas al portal» las completa sin volver a postular.
- Las respuestas aprobadas se reutilizan en otras vacantes (salvo motivación o «esta empresa»).
- Espera hasta 15 s a que el portal cargue el botón de postular.
- **LinkedIn «Solicitud sencilla»** con aceptación explícita del riesgo, máximo 8 por día.

## 09-13 · Portales de empleo dentro de «Mi perfil»
- La sección **Portales de empleo** pasa de «Conexiones» a «Mi perfil» (paso 4 y
  enlace `#portals`). Bumeran y Computrabajo se conectan igual que antes.
- **LinkedIn, Indeed, HiringRoom y Pandapé** aparecen como «Solo preparación»: JobFlow no
  inicia sesión ni postula en ellos (condiciones de uso o formularios propios de cada
  empresa). LinkedIn muestra tu enlace de perfil y abre LinkedIn Empleos; Indeed abre el
  portal; HiringRoom y Pandapé llevan a pegar el aviso en Oportunidades.
- `GET /api/portals/{pid}` devuelve `prepared` con esos portales.

## 09-13 · Privacidad de las cuentas: sin perfil precargado ni reclamos públicos
- Una base nueva **ya no crea el perfil de ejemplo** con datos de una persona real:
  quedaba sin dueño y cualquier cuenta nueva podía reclamarlo. Solo se crea con
  `JOBFLOW_SEED_DEMO=true` (lo usan las pruebas).
- **En servidores públicos** (Render o `JOBFLOW_REQUIRE_AUTH=true`) no se listan ni
  reclaman perfiles anteriores; en la instalación local sí, para pasar tus datos a
  tu cuenta. `JOBFLOW_ALLOW_CLAIM` permite cambiarlo explícitamente.

## 09-13 · Niveles de prácticas y roles superiores; restricciones con opciones
- **Nivel** en «¿A qué puestos quieres postular?»: Practicante preprofesional,
  Practicante profesional, Asistente, Analista junior, Analista, Analista senior o
  especialista, Coordinador o supervisor, Jefe, Gerente o director.
- **La evaluación de vacantes usa el nivel elegido** (antes excluía siempre practicante,
  senior, jefe y gerente). Acepta avisos del mismo nivel o uno adyacente, detectado por
  la palabra principal del título («Asistente de gerencia» es asistente). La exclusión
  por pedir 3 o más años solo aplica hasta analista junior.
- **Restricciones**: casillas con opciones frecuentes más «Otras restricciones».
  Dejarlo en blanco significa que no hay restricciones.

## 09-13 · Fechas de experiencia con selector de mes y año
- **Inicio** y **Fin** de cada experiencia abren un menú con el año (‹ ›) y los 12
  meses. No permite meses futuros, un inicio posterior al fin ni un fin anterior al inicio.
- **Fin** incluye «Hasta la actualidad» y ambos permiten «Borrar fecha».
- Las fechas se guardan como «Mar. 2024» o «Actualidad», el mismo texto que usa el CV.
  Una fecha anterior sin mes (p. ej. «2022») se conserva y se marca para elegir el mes.

## 09-13 · Listas en «Mi perfil»: salario, disponibilidad y movilidad
- **Pretensión salarial** y **expectativa salarial** se eligen de rangos mensuales
  en soles (de «Hasta S/1,500» a «Más de S/8,000»).
- **Disponibilidad** (Inmediata, En 1 semana, En 2 semanas, En 1 mes, En más de 1 mes)
  y **movilidad** (con o sin movilidad propia) también son listas.
- Las opciones de movilidad empiezan por «Sí,»/«No» para que la postulación automática
  responda las preguntas Sí/No de los portales; del rango salarial se usa el mínimo.
- Un valor escrito antes que no esté en la lista se conserva como «(valor actual)».

## 09-13 · Cuentas de JobFlow con sesiones independientes
- **Crear cuenta e iniciar sesión** con usuario y contraseña propios de JobFlow.
  La contraseña se guarda solo como hash scrypt; la sesión es una cookie HttpOnly
  de 30 días. Tras 5 intentos fallidos el usuario se bloquea 5 minutos.
- **Cada cuenta ve solo lo suyo**: perfiles, postulaciones, CV, agenda, capturas y
  conexiones de portales/Google. Toda ruta `/api` exige sesión (401 si no hay).
- **Perfiles anteriores a las cuentas**: aparecen en «Mi perfil» para pasarlos a
  la cuenta de su dueño, con sus postulaciones. Después dejan de verse en las demás.
- **Subir otro CV ya no duplica perfiles**: «Extraer datos del CV» actualiza el
  perfil activo (tras confirmar) y exige revisar y confirmar sus datos otra vez.
  Solo se crea un perfil nuevo cuando la cuenta aún no tiene ninguno.
- **Máximo 3 perfiles por cuenta** (`JOBFLOW_MAX_PROFILES`). Al llegar al límite,
  «Crear perfil nuevo» se desactiva y el servidor responde 409; actualizar un perfil
  existente sigue permitido. Reclamar perfiles anteriores también respeta el límite.
- **Borrar perfiles** desde «Tus perfiles», uno o varios a la vez, con confirmación.
  Se borra todo lo del perfil: postulaciones y su historial, CV adaptados, respuestas,
  agenda, conexiones de portales y Google, capturas y la carpeta del navegador.
- Corregido un error 500 al abrir un perfil recién creado (dos peticiones creaban
  a la vez sus preferencias). Mostraba «El servidor no devolvió una respuesta válida».
- Menú de cuenta (avatar) con «Cerrar sesión». La base existente se migra sola
  (columnas `username`/`password_hash` y tabla `app_sessions`).

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
