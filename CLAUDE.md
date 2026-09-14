# JobFlow AI — guía para continuar el proyecto

Proyecto para la Universidad de Lima: un **sistema de decisión y automatización asistida** que busca vacantes, evalúa el encaje con un perfil verificado, adapta el CV, prepara respuestas, postula con autorización y audita todo. **No es un bot de postulación masiva**: nunca inventa experiencia ni datos.

Estado: **v0.6.1** en `main` (github.com/gabotas123/jobflow-ai), desplegada en Render (`https://jobflow-ai-7390.onrender.com`, plan gratuito, autoDeploy desde `main`). Historial en `CHANGELOG.md` y `CAMBIOS_V0x.md`.

## Reglas innegociables (el código las aplica; no las relajes)

1. No inventar experiencia, cargos, años, herramientas, certificaciones ni cifras. Un dato sin confirmar queda vacío o bloquea.
2. Una postulación solo es «postulada» con evidencia del portal (mensaje, correo o ID). Abrir o llenar un formulario no cuenta.
3. Nunca reenviar automáticamente un envío incierto: queda `intento_no_confirmado` hasta que el candidato confirme que no figura.
4. No resolver CAPTCHA, pruebas ni videos; no aceptar términos ni responder preguntas sensibles (DNI, salud…) por el candidato.
5. Sin duplicados: huella por URL normalizada + posible duplicado entre portales (empresa/puesto/ubicación) que requiere revisión.
6. Nunca guardar ni pedir contraseñas de portales. Las cuentas de portales se conectan con inicio de sesión personal en el navegador. (La contraseña de la **cuenta de JobFlow** sí existe, pero solo como hash scrypt en `usuarios.password_hash`.)
7. LinkedIn e Indeed no se automatizan (condiciones de uso / bloqueo): solo preparación.

## Arquitectura

FastAPI + SQLAlchemy (SQLite) + SPA sin framework en `web/` (JS compacto en `app.js`, una línea por bloque).

| Módulo | Qué hace |
|---|---|
| `jobflow/main.py` | App, rutas de perfiles, CV, búsqueda, importación, seguimiento. Incluye routers de `accounts`, `career`, `google_integration`, `portal_accounts`. |
| `jobflow/accounts.py` | Cuentas de JobFlow: registro/login/logout (`/api/auth/*`), sesiones (`app_sessions`, cookie `jobflow_session`), migración de columnas y reclamo de perfiles anteriores (`/api/account/*`). `AccessMiddleware` exige sesión en `/api` y fija `CURRENT_USER`. |
| `jobflow/cv_parser.py`, `cv_generator.py` | Lectura de CV (PDF/DOCX/TXT) y generación LaTeX/DOCX. |
| `jobflow/career.py` | Confirmación del perfil (hash), objetivos, CV adaptado y versionado por candidatura, reclutadores, agenda, resumen diario. |
| `jobflow/workflow.py` | `evaluate()` (puntaje 0–100 con criterios desconocidos = 0 y exclusiones), `register()` con deduplicación y auditoría (`AuditEvent`). |
| `jobflow/job_extract.py` | Lee un aviso por enlace: JSON-LD `JobPosting` (Computrabajo, LinkedIn, otros) y API pública de Bumeran; `enrich()` detecta herramientas/años/formación. `fetch_public()` bloquea IPs privadas en cada redirección. |
| `jobflow/job_search.py` | Búsqueda: Bumeran (API `searchV2`), Computrabajo (tarjetas HTML), LinkedIn (listado público). Indeed: solo enlace. |
| `jobflow/autofill.py`, `answer_generator.py` | Mapeo de preguntas → hechos del perfil; respuestas solo con datos confirmados; aprobación humana. |
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
.venv\Scripts\python.exe -m pytest -q                      # 50 pruebas
```

- Para probar sin tocar datos reales: `DATABASE_URL=sqlite:///<tmp>/v.db` y `JOBFLOW_DATA_DIR=<tmp>`.
- Las pruebas inician sesión con `sign_in()` de `tests/conftest.py` (cuenta compartida `pruebas`).
- Las pruebas del ejecutor usan un portal simulado con `context.route(...)` (servir HTML con `charset=utf-8`).
- En Windows el repo tiene `.bat` con CRLF (`.gitattributes`); no los conviertas a LF.

## Límites conocidos y pendientes

- Selectores de postulación probados contra un portal simulado; **falta validarlos con cuentas reales** (revisar las capturas de las primeras postulaciones y ajustar `APPLY_TEXT`, `CONFIRM_TEXT`).
- Bumeran bloquea la IP de Render: su búsqueda/lectura solo funciona en local.
- SQLite en Render no persiste entre despliegues (plan gratuito).
- Render no tiene contraseña configurada: activar `JOBFLOW_REQUIRE_AUTH=true` y `JOBFLOW_ACCESS_PASSWORD` en Environment.
- HiringRoom/Pandapé: solo lectura de avisos; sin postulación automática. Gmail/Calendar necesitan credenciales de Google Cloud (`CAMBIOS_V05.md`).
- Monetización discutida: planes por 30 días y licencias para universidades (idea, sin implementar).

## Datos que nunca se suben ni se comparten

`data/` (base con datos personales del CV, `data/navegador/` con **sesiones iniciadas** en los portales, `data/evidencias/`, `data/.jobflow_key`), `.env`, contraseñas de Render. Todo está en `.gitignore`. Para colaborar, clonar el repositorio: no compartir la carpeta local ni un ZIP de ella.

## Flujo de trabajo

- Cambios en una rama y PR a `main`; `main` despliega en Render automáticamente.
- Correr `pytest` antes de subir y verificar la interfaz en el navegador (claro/oscuro, celular).
- Mantener textos de la interfaz en español, tono amable y honesto sobre lo que la app no hace.
