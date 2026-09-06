# JobFlow AI · Copiloto IA de Búsqueda Laboral

**Proyecto para Innova ULIMA.** Reconstrucción según el documento de profundización técnica:

1. **Sistema XYZ de RRHH** — evaluación de CV con 4 componentes ponderados:
   Match de keywords (ATS) **30%** · Experiencia relevante **30%** · Competencias STAR
   (Logré X, medido por Y, haciendo Z) **25%** · Compatibilidad de formato ATS **15%**.
2. **Motor de autofill** agnóstico de plataforma:
   *Detector* → *Mapeador semántico* → *Generador de respuestas* → *Revisión humana* → *Ejecutor*.
3. **Monitoreo de correo** — OAuth2 / Gmail (scopes mínimos), clasificación con IA,
   resolución de cuestionarios con el mismo pipeline.
4. **Modelo de datos completo** — Usuario, PerfilBusqueda, CV, CandidateProfile
   (multi-perfil), GapAnalysis, Vacante, Postulacion, FormularioResuelto, EmailMonitoreado.

## 👤 Multi-perfil (CVs de cualquier persona)

- Sube un **PDF / DOCX / TXT** en la pestaña **Perfiles & CV** → se parsea automáticamente
  (contacto, experiencia, habilidades, idiomas, formación) y se crea un perfil de candidato.
- **Todo el pipeline funciona para ese perfil**: análisis XYZ, respuestas para formularios,
  autofill y tracker de postulaciones.
- Regla de honestidad: lo que el parser **no detecta** se marca para **confirmación manual**
  (disponibilidad, movilidad, etc.) — la app nunca inventa datos.
- El perfil de Gabriel queda como semilla **verificada** (con sus respuestas acordadas).

## ✅ Requisitos

- Python 3.10+ (instalado en este equipo: 3.12.10).
- El primer doble clic instala el entorno automáticamente.

## 🚀 Cómo usarlo

**Doble clic en `Abrir_JobFlow.bat`** → se abre el navegador en
`http://127.0.0.1:8000/` con la app (Dashboard, Perfiles & CV, Análisis, Autofill, Postulaciones, Correo).

Estructura de la UI inspirada en JobWizard: **hero + métricas → ¿Cómo funciona? (3 pasos) →
motores/funciones (7 módulos)** — todo funcional.

## ✨ Generación del CV corregido

En **Perfiles & CV → "Generar CV corregido"**:

1. El sistema aplica las correcciones del análisis: bullets a **voz activa** (ej.
   "Elaboración de escenarios…" → "Elaboré escenarios…"), head-line y resumen generados,
   formato **ATS de una columna**.
2. Verás la **lista de correcciones aplicadas** (antes → después) y una **vista previa**.
3. **Descarga en dos formatos**: **DOCX** y **LaTeX (`.tex`)** — el código LaTeX se
   puede pegar en **Overleaf** o compilar con `pdflatex` (documento A4, una columna,
   paquetes `babel` español, `titlesec`, `hyperref`).
4. Desde la vista previa puedes imprimir/guardar como PDF.

Regla de honestidad: las **métricas que faltan no se inventan** en el CV generado.

## 🔎 Búsqueda de empleo (pestaña Empleos)

Usa el **perfil analizado** (cargo principal + dominio) para generar la consulta y busca en
**Bumeran, Computrabajo, Indeed y LinkedIn**:

- Captura real con **Playwright/Chromium** (páginas con JavaScript) + extracción de
  tarjetas del DOM y JSON-LD.
- Cada vacante muestra **% de afinidad** con el perfil y enlace directo.
- Si una plataforma bloquea la captura (anti-bot/sesión), se entrega el **enlace directo**
  con la consulta para abrirla en tu navegador (**nunca se inventan vacantes**).

Desde terminal:
```bash
.venv\Scripts\activate
python -m jobflow                                    # app web + navegador
uvicorn jobflow.main:app --reload                    # solo API (docs en /docs)
```

## 🗂 Estructura

```
JobFlowAI/
├── Abrir_JobFlow.bat        # lanzador (doble clic)
├── requirements.txt
├── jobflow/
│   ├── main.py              # API FastAPI + SPA web (multi-perfil)
│   ├── __main__.py          # arranque + auto-abrir navegador
│   ├── config.py            # configuración (LLM, puerto, DB)
│   ├── models.py            # modelo de datos (SQLAlchemy)
│   ├── db.py                # motor SQLite/PostgreSQL
│   ├── schemas.py           # esquemas de la API (Pydantic)
│   ├── profile_models.py    # CandidateProfile (candidato genérico)
│   ├── cv_parser.py         # parser ADAPTATIVO: PDF/DOCX/TXT → perfil estructurado
│   ├── cv_generator.py      # genera el CV corregido (HTML preview + DOCX)
│   ├── knowledge.py         # perfil verificado (semilla) + reglas de honestidad
│   ├── answer_generator.py  # banco de respuestas GENÉRICO (por candidato)
│   ├── gap_analysis.py      # motor XYZ (30/30/25/15)
│   ├── autofill.py          # pipeline de autofill + formulario de prueba
│   ├── adapters.py          # adaptadores por plataforma (bumeran/computrabajo/linkedin/test)
│   ├── email_monitor.py     # clasificación de correo + bandeja simulada
│   └── seed.py              # datos demo + helpers de perfiles
└── web/                     # SPA (HTML/CSS/JS servida por FastAPI)
```

## 🔐 Reglas de honestidad (núcleo del proyecto)

- Nunca se inventan experiencia, títulos ni cifras: todo sale de la **base de conocimiento verificada**.
- Las keywords faltantes se listan **para confirmar con el usuario** antes de incorporarlas.
- La postulación **solo se registra tras aprobación humana** (human-in-the-loop).
- **LinkedIn**: solo copiloto (genera respuestas); el envío automático está **prohibido** (ToS).

## 🧭 Roadmap (sprints del documento)

| Sprint | Alcance | Estado |
|---|---|---|
| 1 | Perfil + CV + análisis XYZ (30/30/25/15) | ✅ implementado |
| 2 | Optimización de CV (reescrituras XYZ + verificación de keywords) | ✅ implementado |
| 3 | Búsqueda de vacantes (captura/registro) | 🟠 base (API) |
| 4 | Motor de autofill (una plataforma: formulario de prueba real) | ✅ demo / 🔜 adaptadores reales |
| 5 | Monitoreo de correo (OAuth2 + clasificación) | ✅ demo / 🔜 OAuth real |
| 6 | Dashboard y pulido para la sustentación | ✅ implementado |

## ⚙️ LLM opcional

Con `LLM_PROVIDER=deepseek` (y API key en `.env`) el motor usa el LLM para refinar
clasificaciones y textos. **Sin API key la app funciona con el motor determinístico**.
