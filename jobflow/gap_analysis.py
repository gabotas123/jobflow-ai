"""Motor de evaluacion de CV tipo RRHH (Gap Analysis) — generico.

Framework de 4 componentes ponderados (documento tecnico):

    A) Match de keywords (ATS)      -> 30 %
    B) Experiencia relevante        -> 30 %
    C) Competencias STAR            -> 25 %
    D) Compatibilidad de formato ATS -> 15 %

Trabaja con CUALQUIER `CandidateProfile` (perfil verificado o CV parseado).
Deterministico, auditable y con regla de honestidad: las keywords faltantes se
listan para CONFIRMAR con el usuario antes de incorporarlas.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Tuple

from .profile_models import CandidateProfile

WEIGHTS = {"keywords": 0.30, "experiencia": 0.30, "star": 0.25, "formato": 0.15}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _tokens(t: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", norm(t))


STOPWORDS = set("""
de la el los las y o u en con para por se su sus al a una un que es del para como más mas
también tambien entre sobre antes después despues desde hasta
""".split())

X_VERBS = [
    "reduj", "reduc", "aument", "mejor", "optimiz", "logr", "contribu", "recuper",
    "increment", "super", "implement", "elabor", "consolid", "regulariz", "automatiz",
]
Z_VERBS = [
    "analic", "segui", "segu", "priorice", "coordin", "valide", "identific", "prepare",
    "desarroll", "gestione", "revis", "depur", "organiz", "hice", "realice", "elabore",
    "construi", "disene", "modele", "concili", "factur",
]
TOOLS = ["excel", "power bi", "power query", "vba", "python", "sql", "sap", "stata", "dax", "pandas"]
DOMAIN = [
    "cobranza", "cobranzas", "cuentas por cobrar", "aging", "cartera", "facturacion",
    "recuperacion", "recaudacion", "credito", "vencido", "conciliacion", "partidas",
    "reaseguro", "broker", "saldos", "pagos",
]
SECTIONS = {
    "experiencia": ["experiencia", "experiencia profesional"],
    "educacion": ["educacion", "formacion", "estudios"],
    "habilidades": ["habilidades", "skills", "herramientas"],
    "idiomas": ["idiomas", "lenguajes"],
    "proyectos": ["proyectos", "portafolio"],
}


def cv_text(p: CandidateProfile) -> str:
    """Texto agregado del CV con marcadores de seccion (checks de formato ATS)."""
    parts = [f"EXPERIENCIA: {p.headline} {p.positioning} {p.summary}"]
    for e in p.experiencia:
        if not isinstance(e, dict):
            continue
        parts.append(f"EMPLEO: {e.get('cargo')} en {e.get('empresa')} "
                     f"({e.get('inicio')} - {e.get('fin')}). " + " ".join(e.get("bullets", [])))
    parts.append("EDUCACION: " + " | ".join(p.educacion))
    parts.append("HABILIDADES: " + ", ".join(s for s, _ in p.skills))
    parts.append("IDIOMAS: " + ", ".join(f"{k} {v}" for k, v in p.languages.items()))
    parts.append("PROYECTOS: " + " ".join(p.proyectos))
    return " ".join(parts)


def _has_metric(t: str) -> bool:
    return bool(re.search(r"\d|[%$]|USD|soles", t))


# --------------------------------------------------------------------------- #
#  A) Match de keywords (ATS) - 30%
# --------------------------------------------------------------------------- #
def extract_keywords(must: List[str], nice: List[str], jd_text: str) -> List[str]:
    kws = [k.strip() for k in (must + nice) if k.strip()]
    if jd_text:
        for tok in _tokens(jd_text):
            if tok not in STOPWORDS and len(tok) >= 4 and tok not in kws and not tok.isdigit():
                kws.append(tok)
    seen, out = set(), []
    for k in kws:
        k2 = norm(k)
        if k2 not in seen:
            seen.add(k2)
            out.append(k)
    return out


def keywords_component(p: CandidateProfile, must: List[str], nice: List[str], jd_text: str):
    kws = extract_keywords(must, nice, jd_text)
    text = cv_text(p)
    matched, missing = [], []
    for k in kws:
        if norm(k) in norm(text):
            matched.append(k)
        else:
            missing.append(k)
    score = round(len(matched) / len(kws) * 100, 1) if kws else 50.0
    return score, {"keywords_analizadas": len(kws), "coincidencias": matched,
                   "faltantes": missing, "score_parcial": score}


# --------------------------------------------------------------------------- #
#  B) Experiencia relevante - 30%
# --------------------------------------------------------------------------- #
def experiencia_component(p: CandidateProfile, must: List[str], nice: List[str], jd_text: str):
    req_text = " ".join(must + nice + [jd_text])
    req_domain = [d for d in DOMAIN if norm(d) in norm(req_text)]
    if not req_domain:
        req_domain = DOMAIN[:6]
    matched = [d for d in req_domain if norm(d) in norm(cv_text(p))]
    score = round(len(matched) / len(req_domain) * 100, 1)
    seniority_note = (
        "Afinidad de dominios (experiencia relevante vs requisitos del puesto). "
        "Si la vacante exige anos especificos de analista y el perfil es junior, "
        "complementar con experiencia transferible antes de aplicar."
    )
    return score, {"dominio_evaluado": req_domain, "dominio_cubierto": matched,
                   "alineacion_seniority": "junior/asistente" if p.seniority != "analista" else "analista",
                   "nota": seniority_note}


# --------------------------------------------------------------------------- #
#  C) Competencias STAR - 25%
# --------------------------------------------------------------------------- #
def star_component(p: CandidateProfile):
    bullets = p.all_bullets()
    complete, no_metric, no_action = 0, 0, 0
    details = []
    for b in bullets:
        X = any(v in norm(b) for v in X_VERBS)
        Y = _has_metric(b)
        Z = any(v in norm(b) for v in Z_VERBS) or any(t in norm(b) for t in TOOLS)
        if X and Y and Z:
            complete += 1
        if not Y:
            no_metric += 1
        if not Z:
            no_action += 1
        details.append({"bullet": b, "resultado_X": X, "metrica_Y": Y, "accion_Z": Z,
                        "estructurado_XYZ": bool(X and Y and Z)})
    score = round(complete / len(bullets) * 100, 1) if bullets else 0.0
    return score, {"bullets_totales": len(bullets), "bullets_xyz_completos": complete,
                   "bullets_sin_metrica": no_metric, "bullets_sin_accion": no_action,
                   "detalle": details}


# --------------------------------------------------------------------------- #
#  D) Formato ATS - 15%
# --------------------------------------------------------------------------- #
def formato_component(p: CandidateProfile):
    text = norm(cv_text(p))
    checks, missing = [], []
    for section, variants in SECTIONS.items():
        ok = any(v in text for v in variants)
        checks.append({"check": f"Seccion '{section}' presente", "ok": ok})
        if not ok:
            missing.append(section)
    if len(text) > 9000:
        checks.append({"check": "CV demasiado extenso (>2 paginas)", "ok": False})
        missing.append("extension")
    else:
        checks.append({"check": "Extension de una pagina", "ok": True})
    score = round(max(0.0, 100 - 100 * len(missing) / (len(SECTIONS) + 1)), 1)
    return score, {"checks": checks, "recomendaciones_adicionales": [
        "Usar una sola columna, fuente incrustada, sin tablas ni iconos ni foto.",
        "Texto seleccionable (validado con un parser ATS).",
    ]}


# --------------------------------------------------------------------------- #
#  Analisis completo
# --------------------------------------------------------------------------- #
def analyze(p: CandidateProfile, target_role: str, seniority: str = "analista_junior",
            must=None, nice=None, jd_text: str = "") -> Dict:
    must = must or []
    nice = nice or []

    s_kw, d_kw = keywords_component(p, must, nice, jd_text)
    s_exp, d_exp = experiencia_component(p, must, nice, jd_text)
    s_star, d_star = star_component(p)
    s_fmt, d_fmt = formato_component(p)

    scores = {"keywords": s_kw, "experiencia": s_exp, "star": s_star, "formato": s_fmt}
    score_global = round(sum(scores[k] * WEIGHTS[k] for k in scores), 1)

    gaps = []
    if d_kw["faltantes"]:
        gaps.append({
            "prioridad": "Alta" if s_kw < 50 else "Media",
            "titulo": "Keywords de la vacante ausentes en el CV",
            "detalle": "Faltan: " + ", ".join(d_kw["faltantes"][:5]),
            "sugerencia": "Incorporar SOLO si el usuario confirma que las maneja (preguntar antes).",
        })
    if d_star["bullets_sin_metrica"]:
        gaps.append({
            "prioridad": "Alta" if s_star < 45 else "Media",
            "titulo": f"{d_star['bullets_sin_metrica']} bullets sin resultados cuantificados",
            "detalle": "La Formula XYZ de Google exige Logro X + Metrica Y + Accion Z.",
            "sugerencia": "Reescribir agregando la metrica verificada (porcentaje, monto, cantidad).",
        })
    if s_exp < 70:
        gaps.append({
            "prioridad": "Media",
            "titulo": "Afinidad con el dominio del puesto mejorable",
            "detalle": d_exp["nota"],
            "sugerencia": "Destacar experiencia transferible y herramientas del puesto.",
        })
    if s_fmt < 100:
        gaps.append({
            "prioridad": "Baja",
            "titulo": "Compatibilidad de formato ATS mejorable",
            "detalle": "Revision de secciones estandar y legibilidad.",
            "sugerencia": " ".join(d_fmt["recomendaciones_adicionales"]),
        })

    rewrites = []
    for d in d_star["detalle"]:
        if not d["estructurado_XYZ"]:
            hints = []
            if not d["resultado_X"]:
                hints.append("explicar el resultado concreto logrado")
            if not d["accion_Z"]:
                hints.append("mencionar como se hizo (herramientas/estrategia)")
            if not d["metrica_Y"]:
                hints.append("agregar la metrica verificada (%, monto, cantidad)")
            rewrites.append({"original": d["bullet"],
                             "guia": "Reescribir en formato XYZ -> " + ", ".join(hints)})

    keywords_verificar = [{"keyword": k, "requiere_confirmacion": True} for k in d_kw["faltantes"]]

    resumen = (
        f"Score global {score_global}/100 para '{target_role}'. "
        f"Keywords {s_kw}/100 · Experiencia {s_exp}/100 · STAR {s_star}/100 · Formato ATS {s_fmt}/100. "
        + ("Perfil alineado; reforzar los puntos marcados." if score_global >= 60
           else "Perfil con brechas: priorizar logros con metrica y keywords confirmadas.")
    )

    return {
        "target_role": target_role,
        "score_global": score_global,
        "components": [
            {"name": "Match de keywords (ATS)", "key": "keywords", "peso": "30%", "score": s_kw, "detalle": d_kw},
            {"name": "Experiencia relevante", "key": "experiencia", "peso": "30%", "score": s_exp, "detalle": d_exp},
            {"name": "Competencias STAR (XYZ)", "key": "star", "peso": "25%", "score": s_star, "detalle": d_star},
            {"name": "Formato ATS", "key": "formato", "peso": "15%", "score": s_fmt, "detalle": d_fmt},
        ],
        "gaps": gaps,
        "reescrituras": rewrites,
        "keywords_para_verificar": keywords_verificar,
        "resumen": resumen,
    }
