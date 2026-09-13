# JobFlow 0.6 — Lectura de avisos y postulación automática

## Qué cambia para el candidato

1. **Oportunidades → Buscar** devuelve vacantes reales de Bumeran, Computrabajo y LinkedIn con compatibilidad, fecha y modalidad. Indeed bloquea la lectura automática: se ofrece su enlace.
2. **Guardar y evaluar** lee el aviso completo y abre la ficha. **Añadir con un enlace** hace lo mismo con cualquier aviso pegado (también HiringRoom, Pandapé o webs de empresas con datos estructurados).
3. **Conexiones → Cuentas de empleo → Conectar**: se abre una ventana del portal; inicias sesión tú (usa correo y contraseña; el botón de Google puede no funcionar en esa ventana). JobFlow detecta la sesión y la guarda cifrada.
4. En la ficha de una vacante de Bumeran o Computrabajo: **Postular automáticamente**. En **Postulaciones** puedes marcar varias y autorizarlas en lote.
5. Si el portal pregunta algo sin dato confirmado, la candidatura queda **Bloqueada** con esas preguntas en **Respuestas**. Al aprobarlas, **Reintentar** las usa.

## Reglas del ejecutor

- Completa solo datos del perfil confirmado o respuestas aprobadas para esa vacante. Nunca acepta términos, declaraciones ni preguntas sensibles (DNI, salud, etc.).
- Se detiene ante CAPTCHA, verificación, prueba técnica o psicométrica, video, o sesión cerrada.
- Marca **postulada** solo si el portal muestra la confirmación; guarda el texto y una captura (`data/evidencias/`).
- Nunca pulsa dos veces un botón de envío. Si no hay confirmación, queda **intento no confirmado** y solo se reintenta cuando confirmas que la postulación no figura en el portal. Si JobFlow se cierra en medio de una postulación, también queda como intento no confirmado.
- Una candidatura a la vez, con pausa de ~45 s entre envíos y máximo 20 en 24 horas (`JOBFLOW_APPLY_DELAY_SECONDS`, `JOBFLOW_APPLY_DAILY_LIMIT`).
- LinkedIn e Indeed no se automatizan (sus condiciones lo prohíben o lo bloquean).

## Dónde funciona

- **En tu computadora** (`Abrir_JobFlow.bat`): búsqueda, lectura de avisos, conexión de cuentas y postulación automática. La ventana del navegador es visible mientras postula; `JOBFLOW_APPLY_HEADLESS=true` la oculta.
- **En Render**: búsqueda y lectura de avisos. No hay ventana donde iniciar sesión, así que la conexión de cuentas y la postulación automática muestran cómo activarlas en la computadora.

## Seguridad

- Las sesiones se cifran con `JOBFLOW_TOKEN_KEY`; si no está definida, se crea `data/.jobflow_key` (excluida de Git). Quien tenga esa clave y la base puede usar tus sesiones: no compartas la carpeta `data/`.
- Desconectar borra la sesión de JobFlow; para invalidarla del todo, cierra sesión en el portal.
- Automatizar postulaciones puede ir contra las condiciones de uso de cada portal. JobFlow limita el ritmo y actúa solo con tu sesión, pero el riesgo sobre la cuenta existe.

## Límites honestos

- Los selectores se basan en textos visibles ("Postularme", "Enviar postulación") y se probaron contra un portal simulado. Con cuenta real no se han probado, porque requieren tu inicio de sesión: revisa las primeras postulaciones y su captura.
- Los años requeridos, las herramientas y la formación se detectan del texto del anuncio y pueden requerir corrección.

## Verificación

- 39 pruebas: extracción, búsqueda, plan de llenado, reglas de cola y ejecutor con Chromium real contra un portal simulado (confirmación, pregunta desconocida, CAPTCHA, sesión cerrada, sin confirmación, vacante cerrada y trabajador completo con evidencia).
- Búsqueda y extracción comprobadas contra Bumeran, Computrabajo y LinkedIn en vivo.
