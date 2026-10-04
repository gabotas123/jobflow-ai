"""Que hacer con cada brecha de un aviso: cuales se cierran estudiando y cuales no.

Una herramienta que falta se puede aprender; anos de experiencia o un titulo
no se consiguen con un curso, y decirlo con claridad evita que el candidato
pierda tiempo. Los cursos se entregan como busquedas en plataformas reales:
aqui no se inventa ningun curso, titulo ni certificado.

Completar un curso no cambia el CV por si solo: el candidato lo anade a su
perfil y lo confirma, como cualquier otro dato.
"""
from __future__ import annotations

from urllib.parse import quote, quote_plus

from .workflow import norm

GAP_PREFIX = "Herramienta por verificar: "
# Herramientas de Microsoft: su formacion oficial y gratuita esta en Microsoft Learn.
MICROSOFT = ("excel", "power bi", "powerbi", "power query", "sql server", "word", "powerpoint",
             "access", "azure", "dynamics", "vba", "macros", "outlook", "teams", "sharepoint")
MAX_SKILLS = 5


def courses(skill: str) -> list:
    """Donde aprender una habilidad. Solo enlaces de busqueda: el candidato elige el curso."""
    skill = " ".join((skill or "").split())
    if not skill:
        return []
    links = []
    if any(m in norm(skill) for m in MICROSOFT):
        links.append({"plataforma": "Microsoft Learn", "nota": "Gratis, oficial",
                      "url": f"https://learn.microsoft.com/es-es/training/browse/?terms={quote(skill)}"})
    links += [
        {"plataforma": "Coursera", "nota": "Cursos con certificado",
         "url": f"https://www.coursera.org/search?query={quote(skill)}"},
        {"plataforma": "edX", "nota": "Cursos de universidades",
         "url": f"https://www.edx.org/search?q={quote(skill)}"},
        {"plataforma": "YouTube", "nota": "Gratis",
         "url": f"https://www.youtube.com/results?search_query={quote_plus('curso ' + skill)}"},
    ]
    return links


def plan(analysis: dict) -> dict:
    """Separa las brechas de un analisis en las que se cierran estudiando y las que no."""
    analysis = analysis or {}
    skills, seen = [], set()
    for gap in analysis.get("brechas") or []:
        if not str(gap).startswith(GAP_PREFIX):
            continue
        skill = str(gap)[len(GAP_PREFIX):].strip()
        if skill and norm(skill) not in seen:
            seen.add(norm(skill))
            skills.append({"habilidad": skill, "cursos": courses(skill)})
    fixed = []
    for reason in analysis.get("motivos_exclusion") or []:
        low = norm(reason)
        if "experiencia" in low or "anos" in low:
            fixed.append({"motivo": reason,
                          "nota": "No se resuelve con un curso: se gana trabajando. Busca el mismo puesto "
                                  "en un nivel menor o prácticas, y vuelve a esta vacante más adelante."})
        elif "nivel" in low:
            fixed.append({"motivo": reason,
                          "nota": "El aviso apunta a otro nivel de carrera. Si te interesa, cambia el nivel "
                                  "en tus objetivos."})
    for part in analysis.get("componentes") or []:
        if part.get("criterio") == "Formación" and part.get("conocido") and not part.get("puntos"):
            fixed.append({"motivo": "La formación que pide el aviso no coincide con la que declaraste",
                          "nota": "Un curso corto no reemplaza una carrera. Revisa si el aviso la pide como "
                                  "indispensable o solo como deseable."})
    return {"habilidades": skills[:MAX_SKILLS], "no_se_cierra_con_cursos": fixed,
            "aviso": ("Cuando termines un curso, añádelo a tu perfil y confírmalo: Aplika solo usa lo que "
                      "tú declaras.") if skills else ""}
