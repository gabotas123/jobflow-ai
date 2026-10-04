# Aplika — guía para continuar el proyecto

> **Nombre:** el producto se llama **Aplika** desde el 04-10-2026 (antes «JobFlow AI»). Solo cambió lo que ve el usuario. Siguen llamándose `jobflow` el paquete de Python, el repositorio, las variables `JOBFLOW_*`, la cookie `jobflow_session` y el lanzador `Abrir_JobFlow.bat`: renombrarlos rompería instalaciones y sesiones.

Proyecto para la Universidad de Lima: un **sistema de decisión y automatización asistida** que busca vacantes, evalúa el encaje con un perfil verificado, adapta el CV, prepara respuestas, postula con autorización y audita todo. **No es un bot de postulación masiva**: nunca inventa experiencia ni datos.

Estado: **v0.6.1** en `main` (github.com/gabotas123/jobflow-ai), desplegada en Render (`https://jobflow-ai-7390.onrender.com`, plan gratuito, autoDeploy desde `main`). Historial en `CHANGELOG.md` y `CAMBIOS_V0x.md`.

## Reglas innegociables (el código las aplica; no las relajes)

1. No inventar experiencia, cargos, años, herramientas, certificaciones ni cifras. Un dato sin confirmar queda vacío o bloquea.
2. Una postulación solo es «postulada» con evidencia del portal (mensaje, correo o ID). Abrir o llenar un formulario no cuenta.
3. Nunca reenviar automáticamente un envío incierto: queda `intento_no_confirmado` hasta que el candidato confirme que no figura.
4. No resolver CAPTCHA, pruebas ni videos; no aceptar términos ni responder preguntas sensibles (DNI, salud…) por el candidato.
5. Sin duplicados: huella por URL normalizada + posible duplicado entre portales (empresa/puesto/ubicación) que requiere revisión.
6. Nunca guardar ni pedir contraseñas de portales. Las cuentas de portales se conectan con inicio de sesión personal en el navegador. (La contraseña de la **cuenta de Aplika** sí existe, pero solo como hash scrypt en `usuarios.password_hash`.)
7. Indeed no se automatiza (bloquea el acceso). LinkedIn sí («Solicitud sencilla»), pero solo tras aceptar explícitamente el riesgo para la cuenta, con límite diario bajo (`JOBFLOW_LINKEDIN_DAILY_LIMIT`, 8).
8. Las preguntas se responden con evidencia del CV confirmado (`cv_answers.py`): «Sí» citando la función real, años calculados con fechas mes/año. Nunca «No» ni supuestos; sin evidencia queda pendiente para el candidato.

## Arquitectura

FastAPI + SQLAlchemy (SQLite) + SPA sin framework en `web/` (JS compacto en `app.js`, una línea por bloque).

| Módulo | Qué hace |
|---|---|
| `jobflow/main.py` | App, rutas de perfiles, CV, búsqueda, importación, seguimiento. Incluye routers de `accounts`, `career`, `google_integration`, `portal_accounts`, `feed`. Sirve la web: `/` es la portada (`web/landing.html`) sin sesión y la aplicación (`web/index.html`) con sesión; `/app` es siempre la aplicación e `/inicio` siempre la portada. |
| `web/landing.html`, `landing.css` | Portada pública: 12 franjas (cabecera, portada, portales, producto en dos pestañas, conexiones, calculadora, cifras, reglas, misión, preguntas, cierre, pie). Mismos tokens que la app. **No lleva testimonios ni logos de clientes porque no existen**: no añadirlos hasta que sean reales. |
| `jobflow/accounts.py` | Cuentas de Aplika: registro/login/logout (`/api/auth/*`), sesiones (`app_sessions`, cookie `jobflow_session`), migración de columnas y reclamo de perfiles anteriores (`/api/account/*`). `AccessMiddleware` exige sesión en `/api` y fija `CURRENT_USER`. |
| `jobflow/cv_parser.py`, `cv_generator.py` | Lectura de CV (PDF/DOCX/TXT) y generación LaTeX/DOCX. |
| `jobflow/career.py` | Confirmación del perfil (hash), objetivos, CV adaptado y versionado por candidatura, reclutadores, agenda, resumen diario. |
| `jobflow/workflow.py` | `evaluate(profile, job, level)` (puntaje 0–100 con criterios desconocidos = 0 y exclusiones; `level` es el nivel de los objetivos, ver `LEVELS`/`title_levels`), `register()` con deduplicación y auditoría (`AuditEvent`). |
| `jobflow/job_extract.py` | Lee un aviso por enlace: JSON-LD `JobPosting` (Computrabajo, LinkedIn, otros) y API pública de Bumeran; `enrich()` detecta herramientas/años/formación. `fetch_public()` bloquea IPs privadas en cada redirección. |
| `jobflow/job_search.py` | Búsqueda: Bumeran (API `searchV2`), Computrabajo (tarjetas HTML), LinkedIn (listado público). Indeed: solo enlace. |
| `jobflow/autofill.py`, `answer_generator.py` | Mapeo de preguntas → hechos del perfil; respuestas solo con datos confirmados; aprobación humana. |
| `jobflow/cv_answers.py` | Respuestas a preguntas de postulación deducidas del CV confirmado (experiencia sí/no con evidencia, años por fechas, niveles). |
| `jobflow/headhunter.py` | Auditoría ATS estricta del CV frente a un aviso (`audit`), con veredicto, criterios y preguntas; redacción opcional con LLM (`rewrite`) validada por `_grounded`, que descarta cifras o herramientas ausentes del CV. No añade datos: pregunta. |
| `jobflow/salaries.py` | Referencia de sueldos por puesto: lee la página de salarios de Computrabajo Perú (media, rango, empresas, puestos parecidos) y los avisos vigentes con sueldo publicado. Caché en memoria de 6 h. Depende del marcado de esa página: si cambia, `parse_salary_page` devuelve `{}` y la pantalla lo dice. |
| `jobflow/learning.py` | Qué brechas se cierran estudiando (enlaces de búsqueda a cursos) y cuáles no (años, nivel, carrera). |
| `jobflow/portal_accounts.py` | Cuentas de Bumeran/Computrabajo y postulación automática (ver abajo). |
| `jobflow/google_integration.py` | OAuth Gmail/Calendar (requiere credenciales propias en el servidor). |

### Postulación automática (`portal_accounts.py`)

- **Navegador real**: los portales bloquean el Chromium de Playwright y el modo headless (Cloudflare «you have been blocked», 403). `RealBrowser` lanza el Chrome/Edge instalado como proceso normal con `--user-data-dir=data/navegador/perfil_<id>` y se conecta por `connect_over_cdp`. No volver a `chromium.launch()` para los portales.
- **Conexión**: `login_worker` abre el login; el candidato inicia sesión y pulsa «Ya inicié sesión» (`/verify`). `session_state()` abre `probe_url`, espera la redirección JS y devuelve `activa | sin_sesion | bloqueado`.
- **Cola**: `queue_application()` valida reglas; un único hilo `worker_loop()` procesa de a una, con pausa (~45 s) y máximo diario. No corre mientras hay una ventana de login abierta (mismo perfil de navegador).
- **Ejecutor**: `apply_on_page()` busca el botón de postular, detecta campos (`FIELDS_JS`), decide con `plan_fields()` y se detiene ante preguntas pendientes, CAPTCHA, bloqueo o sesión cerrada. Cada botón de envío se pulsa una sola vez. `finish()` registra auditoría, captura y estado; las preguntas pendientes se convierten en un formulario revisable en «Respuestas».
- Solo funciona **en la computadora del usuario** (`Abrir_JobFlow.bat`). En Render (`RENDER` definido) se muestra cómo activarlo localmente.

### Cuentas y aislamiento

- Cada `CandidateProfileRow.usuario_id` es la cuenta dueña. `get_profile_row`, `list_profile_rows` (seed), `profile_row` y `application` (career) filtran por `CURRENT_USER`; **toda ruta nueva que reciba un id (perfil, candidatura, evento, versión de CV, run, formulario) debe resolverlo con esos helpers**, no con `db.get` directo.
- Fuera de una petición (worker de postulación, scheduler) `CURRENT_USER` es `None` y los helpers no filtran.
- Perfiles de un usuario sin contraseña (anteriores a las cuentas) se listan en «Mi perfil» para que su dueño los reclame.
- Máximo `MAX_PROFILES` (3, env `JOBFLOW_MAX_PROFILES`) perfiles por cuenta: `ensure_profile_slots()` al crear o reclamar. Subir un CV con `profile_id` actualiza ese perfil.
- `delete_profile()` (accounts.py) borra el perfil y todo lo que cuelga de él. **Si agregas una tabla con `profile_id` o `application_id`, añádela ahí**: SQLite puede reutilizar el id del último perfil borrado.

## Cómo ejecutar y probar

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe -m playwright install chromium   # solo para las pruebas del ejecutor
.venv\Scripts\python.exe -m jobflow                        # abre http://127.0.0.1:8000
.venv\Scripts\python.exe -m pytest -q                      # 54 pruebas
```

- Para probar sin tocar datos reales: `DATABASE_URL=sqlite:///<tmp>/v.db` y `JOBFLOW_DATA_DIR=<tmp>`.
- Las pruebas inician sesión con `sign_in()` de `tests/conftest.py` (cuenta compartida `pruebas`).
- Las pruebas del ejecutor usan un portal simulado con `context.route(...)` (servir HTML con `charset=utf-8`).
- En Windows el repo tiene `.bat` con CRLF (`.gitattributes`); no los conviertas a LF.

## Estado y pendientes (al 04-10-2026)

**Hecho y en `main`:** portada pública, feed diario «Para ti», postulación masiva, cursos para cerrar
brechas (`learning.py`), revisión de headhunter ATS (`headhunter.py`), pantalla de sueldos
(`salaries.py`), lector de CV para plantillas a dos columnas, 120 pruebas. Detalle en `CHANGELOG.md`.

**Pendiente, por orden sugerido:**
1. **«Nunca dejar un campo en blanco» al postular** (pedido del dueño, sin resolver): hoy una pregunta
   sin evidencia en el CV detiene el envío. Propuesta acordada a medias: rellenar todo como propuesta
   y enviar con un clic de aprobación. No relajar la regla 1 sin decisión explícita.
2. **CV de Kimi Yi Kudaka** (prueba en curso; es un CV de un tercero, no versionarlo): faltan sus
   respuestas — si maneja Word y PowerPoint, cifras para sus logros, si las fechas solapadas son
   correctas, y pasar cada empleo de una frase a 3–5 logros. Puestos: prácticas legales y de comercio exterior.
3. **Recuperación de contraseña**: no existe; quien la olvida pierde la cuenta (no se pide correo).
4. **Duplicados entre portales en el feed**: la misma vacante puede salir dos veces.
5. **Copiloto conversacional** y **redacción con LLM** del headhunter: escritos pero sin modelo
   configurado (`LLM_PROVIDER`, `LLM_API_KEY`); la redacción no se probó contra un modelo real.
6. **Nombre «Aplika»**: falta verificar dominio (`aplika.pe`, `.com`) e INDECOPI.
7. **Gmail**: la confirmación por correo no se pudo verificar (el Gmail conectado no es el del perfil).

## Límites conocidos

- **Depende del marcado de los portales** (búsqueda, postulación y sueldos de Computrabajo): si
  cambian su página, esa parte falla hasta ajustarla. Es el mayor riesgo del producto.
- Automatizar postulaciones probablemente incumple los términos de uso de los portales; revisar
  antes de crecer. Con usuarios reales aplica la ley peruana de protección de datos personales.
- Bumeran bloquea la IP de Render: su búsqueda/lectura solo funciona en local.
- Render es solo demostración: SQLite no persiste entre despliegues y no tiene contraseña
  configurada (`JOBFLOW_REQUIRE_AUTH=true` y `JOBFLOW_ACCESS_PASSWORD` en Environment).
- La postulación automática solo funciona en la computadora del usuario, con la ventana abierta.
- HiringRoom/Pandapé: solo lectura de avisos. Gmail/Calendar necesitan credenciales de Google Cloud.
- Los CV subidos antes del 04-10 guardan las fechas sin mes: volver a subirlos o corregirlas a mano.

## Cuidados al trabajar aquí

- **Nunca `git add -A`**: en esta carpeta viven otras cosas que no son del repositorio (`livora/`,
  una copia vieja `JobFlowAI/`). Añadir los archivos por nombre. El repositorio es **público**.
- El dueño suele tener la app abierta mientras se trabaja: reiniciar el servidor le corta la sesión.
- Para probar con datos reales, crear una cuenta temporal y borrarla al terminar (perfil por la
  API, luego la fila de `usuarios`); nunca tocar los perfiles 1 y 2, que son los reales.

## Datos que nunca se suben ni se comparten

`data/` (base con datos personales del CV, `data/navegador/` con **sesiones iniciadas** en los portales, `data/evidencias/`, `data/.jobflow_key`), `.env`, contraseñas de Render. Todo está en `.gitignore`. Para colaborar, clonar el repositorio: no compartir la carpeta local ni un ZIP de ella.

## Diseño de la interfaz

- **`DESIGN.md`** (raíz) es la fuente de verdad visual: tokens de color, tipografía, espaciado,
  componentes y reglas de producto. Léelo antes de tocar `web/`.
- **Skills de diseño** en `.agents/skills/` (instaladas con `npx skills add Leonxlnx/taste-skill`).
  Los enlaces de `.claude/skills/` no se versionan: si al clonar no aparecen, vuelve a correr
  ese comando. Útiles: `redesign-existing-projects`, `high-end-visual-design`, `image-to-code`.
- **`/web-interface-guidelines web/index.html web/app.js web/styles.css`** revisa la interfaz
  contra las guías de Vercel Labs antes de subir cambios de UI.
- Referencias de sistemas de diseño reales (74 ejemplos) en
  `../referencias-diseno/awesome-design-md/design-md/`, fuera del repo.

## Flujo de trabajo

- Cambios en una rama y PR a `main`; `main` despliega en Render automáticamente.
- Correr `pytest` antes de subir y verificar la interfaz en el navegador (claro/oscuro, celular).
- Mantener textos de la interfaz en español, tono amable y honesto sobre lo que la app no hace.
