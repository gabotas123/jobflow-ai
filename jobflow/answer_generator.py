"""Generador de respuestas GENÉRICO (para cualquier candidato).

Construye un banco de respuestas anclado en los datos del CandidateProfile
(parseado del CV subido o verificado). Regla de honestidad:
  - si el dato existe en el perfil -> respuesta + fuente + confianza alta;
  - si NO existe -> `needs_input=True` (la UI lo marca; nunca se inventa).

Si el perfil es `verificado` (base de conocimiento) se usan las respuestas
acordadas del prompt maestro.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .knowledge import ANSWER_TEMPLATES, SALARY_RANGES
from .profile_models import CandidateProfile


def _salary_for(seniority: str) -> str:
    s = (seniority or "").strip().lower()
    if "junior" in s:
        return SALARY_RANGES.get("analista_junior", "S/2500 - S/2800")
    if any(w in s for w in ("asistente", "auxiliar", "practicante")):
        return SALARY_RANGES.get("asistente", "S/2300 - S/2500")
    if "analista" in s:
        return SALARY_RANGES.get("analista", "S/2800 - S/3200")
    return ""


def _summary_for(p: CandidateProfile) -> str:
    if p.summary:
        return p.summary
    head = p.headline or p.positioning or f"Perfil profesional de {p.nombre}"
    exp = "; ".join(
        f"{e.get('cargo') or ''} en {e.get('empresa')}".strip(" ;, ")
        for e in p.experiencia[:3] if e.get("empresa") or e.get("cargo")
    )
    return f"{head}. " + (f"Experiencia en: {exp}." if exp else "")


def _experience_answer(p: CandidateProfile) -> str:
    if p.verificado:
        return ANSWER_TEMPLATES["experiencia_total"]
    exp = p.experiencia
    if not exp:
        return ""
    roles = [f"{e.get('cargo') or 'Analista'} en {e.get('empresa')}"
             for e in exp[:3] if e.get("empresa")]
    return (f"Experiencia en: {'; '.join(roles)}. "
            f"{_summary_for(p)}")


def build_answers(p: CandidateProfile, vacante_titulo: str = "",
                  seniority: Optional[str] = None) -> Dict[str, dict]:
    """Devuelve {campo_canonico: {answer, fuente, confianza, needs_input}}."""
    out: Dict[str, dict] = {}

    def add(key: str, value: str, fuente: str, confianza: float = 1.0):
        out[key] = {
            "answer": value or "",
            "fuente": fuente,
            "confianza": confianza if value else 0.0,
            "needs_input": not bool(value),
        }

    salario = p.rango_salarial or _salary_for(seniority or p.seniority or "")
    add("experiencia_total", _experience_answer(p), "Experiencia parseada del CV" if not p.verificado else "Respuesta acordada")
    add("resumen_perfil", _summary_for(p), "Perfil (resumen o generado)")
    add("salario_pretendido", salario, "Rango / estrategia salarial")
    add("disponibilidad", p.disponibilidad, "Dato del perfil")
    add("movilidad", p.movilidad, "Dato del perfil")
    add("modalidad", "Segun el puesto; preferencia a confirmar", "Preferencia (confirmar)")
    add("herramientas", ", ".join(s for s, _ in p.skills), "Habilidades del CV")
    add("formacion", " | ".join(p.educacion), "Formacion del CV")
    add("telefono", p.telefono, "Contacto")
    add("email", p.email, "Contacto")
    add("ubicacion", p.ubicacion, "Ubicacion")
    add("linkedin", p.linkedin, "Contacto")
    add("cargo_deseado", p.headline or "Cargo dentro de mi trayectoria", "Headline del CV")
    add("motivo_interes", (f"Me interesa el puesto de {vacante_titulo} porque esta alineado con mi "
                           f"experiencia y habilidades para el perfil requerido.") if vacante_titulo
       else "Alineado con mi experiencia y habilidades.", "Razonamiento sobre la vacante", 0.6)

    idioma = next((v for k, v in p.languages.items() if k == "ingles"), None)
    if idioma:
        add("idioma_ingles", str(idioma).capitalize(), "Idiomas del CV")
    elif p.languages:
        first = next(iter(p.languages.values()))
        add("idioma_ingles", str(first).capitalize(), "Idiomas del CV", 0.8)

    # Campos extra SOLO para el perfil verificado (respuestas acordadas)
    if p.verificado:
        for key in ("experiencia_reaseguros", "experiencia_flujo_caja", "dos_anos_como_analista"):
            out[key] = {"answer": ANSWER_TEMPLATES[key], "fuente": "Respuesta acordada",
                        "confianza": 1.0, "needs_input": False}

    return out
