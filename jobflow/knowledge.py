"""Base de conocimiento: perfil verificado (semilla) + reglas de honestidad.

`build_gabriel()` devuelve el CandidateProfile del usuario demo con datos
comprobados. Los demas perfiles se crean subiendo un CV (cv_parser.py).
"""
from __future__ import annotations

from .profile_models import CandidateProfile

FULL_NAME = "Gabriel Alberto Gutierrez Ayala"
EMAIL = "gabrielgutierrezayala20@gmail.com"
PHONE = "+51 947 272 093"
LOCATION = "Magdalena del Mar, Lima, Peru"
LINKEDIN = "https://www.linkedin.com/in/gabriel-gutierrez-ayala-641b5421a/"
EDUCATION = "Bachiller en Economia - Universidad de Piura (UDEP), 2025"
AVAILABILITY = "Inmediata"
OWN_TRANSPORT = "Si"

HEADLINE = "COBRANZAS B2B | CUENTAS POR COBRAR | ANALISIS DE CARTERA"
POSITIONING = "Bachiller en Economia | Cobranzas B2B LATAM | Cuentas por cobrar y analisis de cartera"

SUMMARY = (
    "Bachiller en Economia con casi dos anos de experiencia acumulada en areas financieras y "
    "operativas, incluyendo un ano directamente relacionado con cobranzas B2B y cuentas por "
    "cobrar en Liberty Seguros. Experiencia en analisis de cartera, aging, seguimiento de pagos, "
    "regularizacion de partidas, KPIs y automatizacion de reportes con Excel, Power Query, VBA y "
    "Power BI. Disponibilidad inmediata y movilidad propia."
)

EXPERIENCIA = [
    {
        "empresa": "Liberty Seguros / Liberty Specialty Markets",
        "cargo": "Practicante Profesional de Finanzas - Cobranzas LATAM",
        "inicio": "Jun. 2025", "fin": "Jun. 2026", "ubicacion": "Lima, Peru",
        "bullets": [
            "Contribui a reducir aproximadamente el 20 % de la cartera asignada mediante "
            "segmentacion, seguimiento de compromisos y regularizacion.",
            "Segui ~15 cuentas corporativas de Latinoamerica con volumen mensual de USD 300,000.",
            "Analice aging, saldos, vencimientos, pagos y partidas pendientes.",
            "Priorice cuentas vencidas por segmentacion (moneda, broker, antiguedad).",
            "Regularice partidas e inconsistencias coordinando con brokers y equipos regionales.",
            "Elabore KPIs de saldos, pagos, vencido y recuperacion multimoneda.",
            "Automatice reportes con Excel, Power Query, VBA y Power BI.",
        ],
    },
    {
        "empresa": "Los Portales S.A.C. - Grupo Raffo",
        "cargo": "Practicante de Costos y Operaciones",
        "inicio": "Ene. 2025", "fin": "Mar. 2025", "ubicacion": "Lima, Peru",
        "bullets": [
            "Consolide y valide semanalmente costos, valorizaciones y presupuestos EAC.",
            "Identifique desviaciones presupuestales para revision.",
            "Automatice verificaciones presupuestales con macros de Excel.",
            "Prepare informacion estandarizada para analistas y comites.",
        ],
    },
    {
        "empresa": "HAPI - fintech de inversiones",
        "cargo": "Practicante de Operaciones al Cliente",
        "inicio": "Jul. 2023", "fin": "Dic. 2023", "ubicacion": "Lima, Peru",
        "bullets": [
            "Valide identidad y documentacion de usuarios.",
            "Organice, depure y valide bases de clientes y operaciones.",
            "Dio seguimiento a solicitudes e incidencias.",
            "Aseguro integridad documental y trazabilidad de la informacion.",
        ],
    },
]

SKILLS = [
    ("Excel", "avanzado"), ("Power Query", "avanzado"), ("VBA y macros", "avanzado"),
    ("Power BI", "intermedio-avanzado"), ("Python", "aplicado"), ("SQL", "aplicado"),
    ("SAP", "usuario"), ("Stata", "intermedio"),
]
LANGUAGES = {"ingles": "Avanzado", "japones": "Intermedio", "portugues": "Basico"}
EDUCACION = [
    "Bachiller en Economia - Universidad de Piura (UDEP), 2025 (tercio superior)",
    "Power BI avanzado - PUCP",
    "Python y Stata intermedio - UDEP",
    "LISA Institute: analisis de inteligencia, informes y sesgos cognitivos",
]
PROYECTOS = [
    "Scoring de prioridad de cobranza B2B (Python + SQL; datos simulados)",
    "Dashboard de aging multimoneda (Power BI, DAX, Power Query)",
    "Forecast de recaudo a ocho semanas (Excel + Python, escenarios base/estres)",
]

SALARY_RANGES = {
    "asistente": "S/2300 - S/2500",
    "analista_junior": "S/2500 - S/2800",
    "analista": "S/2800 - S/3200",
}

TARGET_ROLES_DEFAULT = [
    "Analista de Cobranzas",
    "Analista Junior de Cobranzas",
    "Asistente de Creditos y Cobranzas",
    "Analista de Cuentas por Cobrar",
    "Analista de Recuperaciones",
    "Analista de Recaudacion",
]

# Respuestas acordadas para preguntas filtro (solo aplican al perfil verificado)
ANSWER_TEMPLATES = {
    "experiencia_total": (
        "Cuento con casi dos anos de experiencia acumulada en funciones financiero-operativas, "
        "cobranzas B2B, cuentas por cobrar, control presupuestal y analisis de datos, desarrolladas "
        "en los sectores de seguros, inmobiliario y fintech."
    ),
    "experiencia_reaseguros": (
        "Si. En Liberty Specialty Markets trabaje en el seguimiento financiero de operaciones "
        "vinculadas con seguros y reaseguros a nivel LATAM, revisando polizas, endosos, "
        "vencimientos, pagos, saldos y partidas pendientes, ademas de coordinar regularizaciones "
        "con brokers y equipos regionales."
    ),
    "experiencia_flujo_caja": (
        "Si, desde la perspectiva de cuentas por cobrar y gestion de ingresos. Realice seguimiento "
        "de saldos, vencimientos, pagos y partidas pendientes, elaborando reportes de aging y "
        "priorizando la recuperacion de cartera."
    ),
    "dos_anos_como_analista": (
        "Cuento con casi dos anos acumulados realizando funciones de analisis financiero, "
        "reporting, control presupuestal, cobranzas y seguimiento de indicadores. Si bien parte de "
        "mi experiencia tuvo la denominacion de practicante profesional, asumi responsabilidades "
        "analiticas y trabaje directamente con informacion utilizada por analistas y equipos "
        "regionales."
    ),
    "cargo_deseado": "Cobranzas B2B, cuentas por cobrar y analisis de cartera",
    "disponibilidad": "Inmediata",
    "movilidad": "Si, cuento con movilidad propia",
    "modalidad": "Presencial o hibrido, segun el puesto",
    "ingles": "Avanzado",
}

HONESTY_RULES = {
    "never_claim": [
        "anos formales como analista no sostenibles",
        "experiencia laboral a partir de proyectos (siempre portafolio)",
        "cifras o certificaciones no defendibles",
    ],
    "no_execute": [
        "evaluaciones", "pruebas tecnicas", "psicometricas", "entrevistas",
        "videos", "preguntas legales/personales sensibles",
    ],
    "no_auto_send_without": "confirmacion visible de la plataforma",
}


def build_gabriel() -> CandidateProfile:
    return CandidateProfile(
        nombre=FULL_NAME,
        email=EMAIL,
        telefono=PHONE,
        ubicacion=LOCATION,
        linkedin=LINKEDIN,
        headline=HEADLINE,
        positioning=POSITIONING,
        summary=SUMMARY,
        seniority="analista_junior",
        rango_salarial=SALARY_RANGES["analista_junior"],
        disponibilidad=AVAILABILITY,
        movilidad="Si, movilidad propia",
        experiencia=EXPERIENCIA,
        skills=SKILLS,
        languages=LANGUAGES,
        educacion=EDUCACION,
        proyectos=PROYECTOS,
        verificado=True,
        fuente_cv="Perfil verificado (base de conocimiento)",
    )
