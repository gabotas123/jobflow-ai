# JobFlow AI 0.4 — preparación y seguimiento verificables

Base revisada: `09a6c9c`. Se conserva FastAPI, SQLAlchemy, el parser, el generador de CV y la interfaz existente. Los cambios están en la rama `feat/mobile-reviewable-workflow`.

## Funciones utilizables

- Cargar CV PDF/DOCX/TXT, editar datos básicos y descargar DOCX o LaTeX.
- Cuatro variantes que priorizan los bullets existentes por área; no inventan contenido ni cargos.
- Buscar mediante enlaces públicos y captura cuando el portal lo permite. Usa el puesto objetivo activo. Un bloqueo deja disponible el enlace para abrirlo personalmente.
- Pegar una oferta y sus requisitos para evaluar ocho criterios. Los datos ausentes puntúan cero y se informa la cobertura; el puntaje no es una probabilidad de contratación. La interpretación de requisitos es conservadora y no sustituye la lectura del aviso completo.
- Registrar oportunidades sin contarlas como postulaciones.
- Detectar URL duplicada, incluidos registros anteriores; advertir posibles duplicados entre portales para revisión humana. URLs diferentes de un mismo aviso aún pueden requerir revisión.
- Preparar preguntas pegadas desde un formulario y revisarlas antes de copiarlas. Las preguntas sensibles y evaluaciones se bloquean.
- Vincular preparación a una oportunidad, conservar copia del perfil, LaTeX y respuestas en el historial.
- Registrar cambios de estado y evidencia declarada por el candidato (mensaje del portal, correo o ID). Esta evidencia manual no se presenta como verificación automática del ATS.
- Clasificar correos pegados manualmente y evitar importaciones idénticas.
- Exportar seguimiento e historial como JSON.

## Defectos corregidos

- El botón de guardar ya no registra un envío ni dispara correos SMTP.
- Completar la demo no crea postulaciones; repetirla tampoco.
- Los adaptadores externos rechazan el envío mientras no esté conectado un ejecutor real.
- Marcar una casilla no simula una conexión de cuenta.
- No se usa otro idioma como nivel de inglés ni se supone nivel intermedio al leer un CV.
- No se asigna el cargo «Analista» cuando falta un cargo, ni se copian respuestas de Gabriel a otros perfiles verificados.
- La ausencia de una sección de experiencia no convierte proyectos en empleos.
- Se retiran los logros cuantificados y cursos no confirmados del perfil semilla. Los perfiles antiguos se marcan para revisión.
- La vista previa del CV escapa contenido HTML y usa un iframe aislado.
- Los perfiles inexistentes producen error, en lugar de usar silenciosamente otro candidato.
- La interfaz invalida respuestas al cambiar de perfil o editar un borrador aprobado.

## Pruebas realizadas

14 pruebas automatizadas de API y lógica, con una base SQLite temporal. Cubren carga de CV, exportación de las cuatro variantes, veracidad de idiomas, exclusiones, campos desconocidos, duplicados actuales e históricos, preparación con snapshot, confirmación manual, auditoría, bloqueo de envío real, demo repetida, preguntas sensibles, correos importados, aislamiento del HTML y protección de acceso. JavaScript revisado con `node --check`.

No se probaron sesiones reales de Bumeran/Computrabajo/LinkedIn, recepción Gmail, navegador Safari físico, compilación visual del PDF ni despliegue Docker/Codespaces. No se enviaron postulaciones ni correos reales.

## Nube y iPhone

`.devcontainer/devcontainer.json` instala dependencias y Chromium, inicia el servidor automáticamente y configura el puerto 8000 para abrirlo en el navegador. Crear el Codespace requiere una sesión GitHub del propietario. Mantener el puerto privado. Esta configuración solo estará disponible en GitHub después de subir esta rama.

También se incluyen `Dockerfile` y `render.yaml`. Render necesita una cuenta conectada y un plan con disco persistente; el archivo declara un servicio Starter con disco de 1 GB, por lo que no es una opción gratuita. La aplicación exige una contraseña en ese despliegue y el usuario de acceso es `jobflow`. No se creó ni contrató ningún servicio.

Documentación de referencia:
- https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/adding-a-dev-container-configuration/introduction-to-dev-containers
- https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace
- https://render.com/docs/blueprint-spec
- https://render.com/docs/disks

## Limitaciones que siguen pendientes

No hay envío real a ATS, OAuth de correo, resolución automática de formularios enlazados, modos lote/automático, acceso multiusuario independiente, cifrado de campos sensibles ni garantía visual de CV de una página. Esta versión es un copiloto asistido de un solo propietario. Las capturas públicas dependen del acceso permitido por cada portal. El scoring es heurístico y necesita campos del aviso; no comprende todos los requisitos expresados en lenguaje natural. Los datos de contacto y las afirmaciones del CV deben revisarse antes de enviarse a terceros.

Las tablas de auditoría son aditivas: no se eliminan las tablas ni los registros previos. Los estados históricos que decían enviado sin evidencia se muestran como intento no confirmado. Hacer una copia de la base de datos antes de instalar una actualización.

## Publicación pendiente

La lectura del repositorio público funcionó. La comprobación de escritura falló por ausencia de autenticación GitHub. No hay commit remoto, PR ni enlace de aplicación desplegada creado en esta sesión. El ZIP contiene la versión revisada, no la versión actual de GitHub.
