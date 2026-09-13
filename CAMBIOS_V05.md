# JobFlow 0.5 — Espacio de búsqueda profesional

Implementación propia inspirada en la claridad de Simplify. No copia su marca ni sus activos.

## Recorrido implementado

1. Carga PDF/DOCX/TXT; revisión editable de contacto, formación, experiencia, herramientas, idiomas, proyectos y pendientes.
2. Confirmación explícita vinculada a una huella del perfil. Cualquier edición invalida la confirmación.
3. Elección explícita de hasta ocho puestos en orden de prioridad, modalidad, ubicación, rango y restricciones. No se crea automáticamente un puesto al subir CV. La búsqueda requiere perfil y objetivos confirmados.
4. Búsqueda por el puesto seleccionado. Importación manual de avisos con los controles existentes de puntuación y duplicados.
5. Ficha por candidatura: vacante, CV, respuestas, reclutador, historial.
6. CV específico por empresa/puesto: ordena las funciones y herramientas ya existentes, y compone un resumen extractivo a partir de funciones confirmadas. No inventa experiencia sectorial ni nuevos cargos. Conserva snapshots originales, cambios, aprobaciones y descargas LaTeX/DOCX. Una versión aprobada puede vincularse al registro de envío. No se altera retrospectivamente.
7. Contactos profesionales: búsqueda asistida externa por empresa y almacenamiento de formación, experiencia, fuente, fecha y relación con la vacante. Declarar un responsable exige evidencia. No hay extracción autónoma de perfiles ni envío de mensajes.
8. Agenda local con zona horaria, fechas confirmadas, edición, exportación ICS y control de duplicados. Sincronización real con Calendar cuando se configura y autoriza Google. El ID estable evita duplicar eventos después de una respuesta incierta. No envía invitaciones a terceros.
9. Resumen diario real del tracker: confirmadas hoy según evidencia, preparadas hoy, pendientes acumulados y próximos eventos.
10. Gmail: OAuth separado para lectura y envío; importación de hasta 50 correos de selección de los últimos 14 días por revisión. Fechas de correos requieren revisión manual; no se convierten automáticamente en reuniones confirmadas. Envío del resumen a la propia cuenta conectada, máximo una vez al día. Los intentos inciertos no se reenvían automáticamente.

## Configuración Google en Render

Habilitar Gmail API y Google Calendar API en el proyecto Google Cloud de JobFlow. Crear un cliente OAuth de tipo aplicación web y configurar pantalla de consentimiento/usuarios de prueba según corresponda.

Configurar estas variables privadas del servidor:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`: `https://jobflow-ai-7390.onrender.com/api/google/callback` (debe coincidir exactamente con la URI autorizada en Google Cloud).
- `JOBFLOW_TOKEN_KEY`: clave Fernet generada con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guardarla como secreto; nunca subirla al repositorio. Conservarla entre despliegues para abrir tokens existentes.
- `JOBFLOW_REQUIRE_AUTH=true`
- `JOBFLOW_ACCESS_PASSWORD`: contraseña privada del propietario. Usuario de acceso: `jobflow`.

Después, abrir Conexiones y preferencias en JobFlow y autorizar cada función requerida. Las conexiones de Google de ChatGPT no conectan automáticamente esta aplicación desplegada.

Si falta configuración, los botones muestran Configuración pendiente y las API responden con un error claro; nunca simulan que se conectó una cuenta.

OAuth utiliza estado de un solo uso con vencimiento y cookie HttpOnly, credenciales cifradas y permisos separados. Desconectar elimina credenciales locales y desactiva la automatización correspondiente; el acceso también puede revocarse desde Google.

## Ejecución diaria

- Opción sencilla: `JOBFLOW_SCHEDULER=true`, con un único proceso web siempre activo. Cada minuto revisa si corresponde enviar el resumen y cada 15 minutos revisa Gmail si el candidato lo autorizó.
- Opción independiente: `python -m jobflow.scheduler` en un worker con acceso a la misma base de datos. No lanzar además el programador dentro de la web. Para varios servicios usar una base compartida (por ejemplo PostgreSQL y su driver), no archivos SQLite independientes.
- El envío ocurre después de la hora elegida según la zona horaria. Si el servidor duerme o está apagado no puede cumplir la hora; debe utilizarse un servicio activo. No se ha contratado ni activado un worker en esta entrega.
- Cada resumen tiene una clave única por perfil y fecha; el estado se guarda antes del envío. Una respuesta incierta queda como intento no confirmado para revisión en Gmail.

## Datos y despliegue

Las tablas nuevas se crean de forma aditiva con `create_all`; se mantienen las tablas de CV, postulaciones y auditoría anteriores. Respaldar la base antes del despliegue. Se conserva el plan gratuito y el entorno Python de la configuración remota de Render. SQLite no tiene persistencia garantizada en ese plan: exportar los datos antes de reinicios o despliegues. Esta actualización no contrata servicios. La configuración incluye acceso privado; en servicios creados manualmente deben definirse las variables de autenticación en Render.

Para actualizar, subir este código a la rama conectada a Render y desplegarla. El healthcheck devuelve versión 0.5.0. Las dependencias agregadas son `cryptography` y `httpx`.

## Alcance honesto

- No se habilitaron envíos reales a ATS: continúa el envío manual en el portal. Tampoco se resuelven CAPTCHA o evaluaciones.
- Restricciones escritas y condiciones de cada anuncio requieren revisión; el buscador no garantiza su filtrado completo.
- Los CV generados se descargan en DOCX o fuente LaTeX. No se añade un compilador PDF ni se garantiza una página sin verificar el documento final.
- La app sigue siendo de un solo propietario con varios perfiles; no implementa cuentas SaaS de usuarios independientes.
- La búsqueda de reclutadores es asistida y con fuentes registradas, no una afirmación de que un contacto maneja la vacante.
- Google no está activado sin credenciales propias y consentimiento; pruebas de integración utilizan respuestas simuladas, sin correos reales.

## Referencias de integración

- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert

## Verificación de esta entrega

- 26 pruebas aprobadas: recorridos previos, objetivos, confirmación obsoleta, versiones de CV, evidencia, agenda, duplicados, OAuth y reintentos seguros.
- Arranque Uvicorn y respuestas HTTP 200 de inicio, perfil, preferencias, resumen, estado Google y archivos de interfaz.
- Sintaxis JavaScript y compilación Python verificadas.
- No se pudo ejecutar revisión visual con navegador: Chromium no está disponible y su descarga no finalizó. Revisar en laptop y móvil antes de habilitar la versión a otros usuarios.
- No se ejecutaron envíos externos, consentimiento Google real ni publicación en Render.
