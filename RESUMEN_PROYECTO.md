# 📄 RESUMEN DEL PROYECTO — JobFlow AI

> Documento para el **equipo** (compañeros de Innova ULIMA). Resumen de la
> conversación de desarrollo: qué es, cómo está construido, qué decisiones se
> tomaron, qué problemas ya se resolvieron y qué sigue.
> **Repositorio:** https://github.com/gabotas123/jobflow-ai (privado)

---

## 1. ¿Qué es JobFlow AI?

**Copiloto de IA para todo el proceso de búsqueda de empleo** en el mercado
peruano. El usuario sube su CV y el sistema:

1. **Analiza su afinidad** con los puestos objetivo (sistema propio de scoring).
2. **Detecta brechas** y **genera un CV corregido** (DOCX, **LaTeX** y vista previa).
3. **Busca vacantes reales** en Bumeran, Computrabajo, Indeed y LinkedIn.
4. **Autocompleta formularios** de postulación (con aprobación humana).
5. **Controla el proceso**: correo → solicitud → tracker con envío automático.

> Diferencial: **honestidad por diseño**. El sistema **nunca inventa** experiencia,
> cifras ni vacantes; y **nunca envía** algo sin aprobación del usuario.

---

## 2. Arquitectura (módulos en `jobflow/`)

| Módulo | Responsabilidad |
|---|---|
| `main.py` | API FastAPI + SPA web (Dashboard, Perfiles, Análisis, Autofill, Empleos, Postulaciones, Correo) |
| `knowledge.py` | Perfil canónico verificado + reglas de honestidad |
| `cv_parser.py` | **Parser adaptativo** PDF/DOCX/TXT → perfil estructurado (cualquier formato) |
| `gap_analysis.py` | **Motor XYZ**: keywords ATS **30%** · experiencia **30%** · STAR/XYZ **25%** · formato ATS **15%** |
| `cv_generator.py` | CV corregido: voz activa + estructura ATS → **DOCX + LaTeX (.tex)** + HTML |
| `autofill.py` | Pipeline: detector → mapeador semántico → generador → revisión humana → ejecutor |
| `adapters.py` | Bumeran/Computrabajo (autofill) · **LinkedIn (copiloto)** · formulario de prueba |
| `job_search.py` | Búsqueda real con **Playwright/Chromium** + JSON-LD + tarjetas DOM + match% |
| `email_monitor.py` | Clasificación de correo + conector correo ↔ solicitud + envío (SMTP opcional) |
| `models.py` | Datos: perfiles, puestos objetivo, vacantes, postulaciones, formularios, correos |
| `seed.py` / `db.py` / `schemas.py` | Datos demo, SQLite/PostgreSQL, esquemas API |

**Frontend:** SPA vanilla (HTML/CSS/JS) servida por FastAPI — estructura inspirada
en JobWizard: hero + métricas → ¿cómo funciona? (3 pasos) → motores/funciones.

---

## 3. Decisiones de diseño (por qué es así)

1. **Honestidad = feature**: lo que no está en el CV se marca `needs_input`
   (la UI lo resalta); nunca se fabrica. Conclusiones del análisis son auditables.
2. **Human-in-the-loop**: ningún envío sin aprobación previa (regla verificada: 400 si no se aprueba).
3. **LinkedIn es solo copiloto** (nunca bot): ToS prohíbe automatizar; Bumeran/
   Computrabajo sí usan autofill sobre la sesión del usuario, con throttle.
4. **Búsqueda real sin inventar**: si un sitio bloquea (403/anti-bot/sesión),
   se entrega el **enlace directo** con la consulta — nunca vacantes falsas.
5. **Información personal**: la base (`data/jobflow.db`) y `.env` **nunca** van a Git
   (`.gitignore`); el repo es privado.
6. **Fórmula XYZ de Google** (Logré X, medido por Y, haciendo Z) es el marco del
   motor de competencias, con reescrituras a **voz activa** en el CV generado.

---

## 4. Funcionalidades implementadas (estado actual)

- ✅ Multi-perfil: subir CV de **cualquier persona** → parseo adaptativo automático.
- ✅ Puestos objetivo por perfil (crear, activar, editar) + **rango salarial seleccionable**.
- ✅ Análisis XYZ (30/30/25/15) con brechas priorizadas y reescrituras.
- ✅ Generación de CV corregido: **DOCX + LaTeX (.tex)** + preview + correcciones listadas.
- ✅ Autofill agnóstico (formulario de prueba funciona end-to-end; adaptadores reales listos).
- ✅ Búsqueda de empleos real en **Bumeran, Computrabajo, Indeed y LinkedIn** (con match%).
- ✅ Correo ↔ solicitud: resolver cuestionarios con el pipeline; conector de envío (SMTP opcional, simulado por defecto).
- ✅ Tracker conectado a Empleos (Postular → vacante + postulación + correo automático).
- ✅ Conexiones de plataformas (checkboxes) y panel de motores.

---

## 5. Problemas ya resueltos (lecciones del proyecto)

| Problema | Solución aplicada |
|---|---|
| CV que el parser no detectaba (Mateo: ligaduras `ﬁ`, "Set.", "P&L", DNI, teléfono con paréntesis, "Logros" aparte) | **Parser adaptativo**: patrones anclados, word-boundary, limpieza de glitches, actualidad como fin de fecha |
| Buscadores bloquean scraping simple (403) | Playwright/Chromium (render JS) + extracción DOM/JSON-LD + **fallback honesto a enlaces** |
| "La ventana se abre y se cierra" al doble clic | `.bat` con **CRLF** (cmd.exe los exige) + `.gitattributes` + estructura simple `goto` + **puerto libre automático** |
| ToS LinkedIn | Copiloto (respuestas listas para pegar), nunca envío automático |

---

## 6. Cómo correrla (para todo el equipo)

**Windows:** doble clic en **`Instalar_Todo.bat`** (instala Python si falta, entorno,
Chromium y abre la app en `http://127.0.0.1:8000/`).
**Solo requiere Python 3.10+** (python.org, "Add to PATH").
Guía completa: `GUIA_COMPANEROS.md`.

---

## 7. Reglas para colaboradores (¡leer!)

- Trabajar en **ramas + Pull Requests**, nunca directo en `main`.
- **No subir a Git**: `data/*.db`, `.venv/`, `.env` (ya excluidos; no forcepear).
- No inventar datos: si un dato no está verificado, `needs_input=True`.
- No automatizar LinkedIn; no enviar sin aprobación humana.
- Los cambios de UI deben servir desde `/assets` (SPA estática) y probarse en
  `http://127.0.0.1:8000/`.

---

## 8. Próximos pasos / roadmap sugerido

- [ ] OCR para CVs escaneados (imagen) — vía PaddleOCR/Tesseract o LLM con visión.
- [ ] SMTP real documentado (Gmail app-password) para envío real del tracker.
- [ ] Plantillas de CV (2-3 estilos) + carta de presentación generada.
- [ ] Filtro de vacantes por match mínimo + ubicación/modalidad.
- [ ] Migrar web a React/Next.js y BD a PostgreSQL + Redis/Celery (producción).
- [ ] Multi-usuario real con login (hoy es mono-usuario local: cada instancia es personal).

---

*Resumen generado a partir de la conversación de desarrollo — JobFlow AI · Innova ULIMA.*
