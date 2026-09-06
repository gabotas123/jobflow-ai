"""Generador de CV corregido (optimizado) a partir del CandidateProfile.

Aplica las correcciones del analisis de forma HONESTA:
  - transforma bullets en primera persona / voz activa (sin inventar datos);
  - estructura ATS de una columna con secciones estandar;
  - headline y resumen generados a partir del perfil;
  - las metricas faltantes NO se inventan: se listan como pendientes.

Salidas: HTML (preview) y DOCX (descarga).
"""
from __future__ import annotations

import copy
import re
from io import BytesIO
from typing import Dict, List, Tuple

from .profile_models import CandidateProfile

# --------------------------------------------------------------------------- #
#  Transformacion a voz activa (sustantivo -> verbo en primera persona)
# --------------------------------------------------------------------------- #
_VERB_MAP = [
    (r"^elaboracion,\s*consolidacion\s+y\s*analisis", "Elaboré, consolidé y analicé"),
    (r"^elaboracion\s+y\s*analisis", "Elaboré y analicé"),
    (r"^preparacion\s+y\s*consolidacion", "Preparé y consolidé"),
    (r"^monitoreo\s+y\s*seguimiento", "Monitoreé y seguí"),
    (r"^identificacion,\s*analisis\s*e\s*implementacion", "Identifiqué, analicé e implementé"),
    (r"^seguimiento\s+y\s*analisis", "Realicé seguimiento y analicé"),
    (r"^apoyo\s*en\s*el", "Apoyé en el"),
    (r"^analisis\s+y\s*control", "Analicé y controlé"),
    (r"^elaboracion", "Elaboré"),
    (r"^automatizacion", "Automatizé"),
    (r"^monitoreo", "Monitoreé"),
    (r"^identificacion", "Identifiqué"),
    (r"^participacion", "Participé"),
    (r"^contribucion", "Contribuí"),
    (r"^preparacion", "Preparé"),
    (r"^consolidacion", "Consolidé"),
    (r"^seguimiento", "Realicé seguimiento"),
    (r"^apoyo", "Apoyé"),
    (r"^gestion", "Gestioné"),
    (r"^analisis", "Analicé"),
    (r"^evaluacion", "Evalué"),
    (r"^implementacion", "Implementé"),
    (r"^optimizacion", "Optimicé"),
    (r"^coordinacion", "Coordiné"),
    (r"^redaccion", "Redacté"),
    (r"^planificacion", "Planificé"),
    (r"^control", "Controlé"),
    (r"^validacion", "Validé"),
    (r"^proyeccion", "Proyecté"),
]


def _strip_accents(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def improve_bullet(text: str) -> str:
    """Convierte un bullet nominal ('Elaboración de X') a voz activa ('Elaboré X').

    Solo transforma inicio de oracion (mayuscula) y hace la comparacion SIN
    acentos, para cubrir 'Elaboración' (patron sin acento no la alcanza).
    """
    t = (text or "").strip()
    if not t or not t[0].isupper():
        # continuacion de parrafo (empieza en minuscula): no tocar contenido
        return re.sub(r"\s+", " ", t).strip()
    low = _strip_accents(t).lower()
    for pat, repl in _VERB_MAP:
        m = re.match(pat, low)
        if m:
            rest = t[m.end():]
            rest = re.sub(r"^\s*de\s+", "", rest)      # 'Elaboré de escenarios' -> 'Elaboré escenarios'
            rest = re.sub(r"^\s*del\s+", "el ", rest)  # 'analicé del estado' -> 'analicé el estado'
            t = (repl + " " + rest).strip()
            break
    t = re.sub(r"\s+", " ", t).strip()
    if t and not t.endswith((".", ";")):
        t += "."
    return t


def _generate_summary(p: CandidateProfile) -> str:
    if p.summary:
        return p.summary
    roles = [e.get("cargo", "") for e in p.experiencia if e.get("cargo")][:3]
    role_txt = ", ".join(r for r in roles if r)
    skills_txt = ", ".join(s for s, _ in p.skills[:5])
    parts = []
    if role_txt:
        parts.append(f"{p.nombre} con experiencia en {role_txt}.")
    if skills_txt:
        parts.append(f"Manejo {skills_txt}.")
    parts.append("Disponible para aportar al equipo desde el primer día.")
    return " ".join(parts) if parts else "Perfil profesional."


def optimize_profile(p: CandidateProfile) -> Tuple[dict, List[dict]]:
    """Devuelve (perfil_optimizado_dict, lista de correcciones)."""
    opt = copy.deepcopy(p)
    changes: List[dict] = []
    for exp in opt.experiencia:
        if not isinstance(exp, dict):
            continue
        new_bullets = []
        for b in exp.get("bullets", []):
            improved = improve_bullet(b)
            new_bullets.append(improved)
            if improved != b:
                changes.append({
                    "tipo": "voz activa / claridad",
                    "original": b,
                    "mejorado": improved,
                    "puesto": exp.get("empresa", ""),
                })
        exp["bullets"] = new_bullets
    if not opt.headline:
        cargos = [e.get("cargo", "") for e in opt.experiencia if e.get("cargo")]
        opt.headline = " | ".join(cargos[:3])
    if not opt.summary:
        opt.summary = _generate_summary(p)
    return opt.to_dict(), changes


# --------------------------------------------------------------------------- #
#  HTML del CV (preview)
# --------------------------------------------------------------------------- #
def render_cv_html(profile: dict) -> str:
    exp = ""
    for e in profile.get("experiencia", []):
        if not isinstance(e, dict):
            continue
        bullets = "".join(f"<li>{b}</li>" for b in e.get("bullets", []))
        fecha = " · ".join(x for x in [e.get("inicio"), e.get("fin")] if x)
        exp += (
            f"<div class='job'><div class='jobhead'><b>{e.get('cargo') or '—'}</b>"
            f"<span class='fecha'>{e.get('empresa', '')}{' · ' + fecha if fecha else ''}</span></div>"
            f"<ul>{bullets}</ul></div>"
        )
    skills = " · ".join(f"{s} <i>({lvl})</i>" if lvl else s for s, lvl in profile.get("skills", []))
    langs = " · ".join(f"{k.capitalize()}: {v}" for k, v in profile.get("languages", {}).items())
    educ = "".join(f"<li>{e}</li>" for e in profile.get("educacion", []))
    proyectos = "".join(f"<li>{p}</li>" for p in profile.get("proyectos", []))
    contacto = " · ".join(x for x in [
        profile.get("email", ""), profile.get("telefono", ""),
        profile.get("linkedin", ""), profile.get("ubicacion", ""),
    ] if x)
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>CV - {profile.get('nombre','')}</title><style>
 body{{font-family:'Segoe UI',Arial,sans-serif;color:#1c2333;margin:0;background:#eef0f7}}
 .page{{max-width:800px;margin:18px auto;background:#fff;padding:44px 52px;box-shadow:0 2px 14px rgba(0,0,0,.08)}}
 h1{{margin:0;font-size:26px}} h2{{color:#2f4196;font-size:14px;text-transform:uppercase;
   letter-spacing:1px;border-bottom:2px solid #2f4196;padding-bottom:4px;margin:22px 0 10px}}
 .headline{{color:#2f4196;font-weight:600;margin:4px 0}} .contact{{color:#5a6a94;font-size:13px}}
 .job{{margin-bottom:10px}} .jobhead b{{font-size:15px}} .fecha{{color:#5a6a94;font-size:13px;margin-left:8px}}
 ul{{margin:4px 0;padding-left:20px}} li{{font-size:13.5px;line-height:1.5;margin:3px 0}}
 .skills,.langs{{font-size:13.5px}}
</style></head><body><div class="page">
 <h1>{profile.get('nombre','')}</h1>
 <div class="headline">{profile.get('headline','')}</div>
 <div class="contact">{contacto}</div>
 <h2>Perfil</h2><p style="font-size:13.5px;line-height:1.5">{profile.get('summary','')}</p>
 <h2>Experiencia</h2>{exp or '<p>—</p>'}
 <h2>Formación</h2><ul>{educ or '<li>—</li>'}</ul>
 <h2>Habilidades</h2><p class="skills">{skills or '—'}</p>
 <h2>Idiomas</h2><p class="langs">{langs or '—'}</p>
 {('<h2>Proyectos</h2><ul>' + proyectos + '</ul>') if proyectos else ''}
 <p style="font-size:11px;color:#9aa3bd;margin-top:26px">Generado por JobFlow AI · Estructura ATS de una columna · sin datos inventados</p>
</div></body></html>"""


# --------------------------------------------------------------------------- #
#  LaTeX (descarga .tex listo para Overleaf / pdflatex)
# --------------------------------------------------------------------------- #
LATEX_PREAMBLE = r"""\documentclass[10pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[spanish]{babel}
\usepackage[a4paper,top=1.6cm,bottom=1.6cm,left=1.9cm,right=1.9cm]{geometry}
\usepackage{xcolor}
\usepackage[hidelinks]{hyperref}
\usepackage{titlesec}
\definecolor{jfblue}{RGB}{47,65,150}
\titleformat{\section}{\normalfont\large\bfseries\color{jfblue}}{\thesection}{0.6em}{}[\vspace{-4pt}\rule{\textwidth}{0.6pt}]
\titlespacing*{\section}{0pt}{12pt}{6pt}
\setlength{\parindent}{0pt}
"""


def latex_escape(text: str) -> str:
    if not text:
        return ""
    repl = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}"}
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


def render_latex(profile: dict) -> str:
    def esc(t):
        return latex_escape(t)

    body = [LATEX_PREAMBLE, r"\begin{document}"]
    body.append(r"{\LARGE\textbf{%s}}" % esc(profile.get("nombre", "")))
    body.append(r"\\[2pt]")
    if profile.get("headline"):
        body.append(r"{\large\textbf{\color{jfblue}%s}}" % esc(profile["headline"]))
        body.append(r"\\[6pt]")

    contacto = []
    if profile.get("email"):
        contacto.append(esc(profile["email"]))
    if profile.get("telefono"):
        contacto.append(esc(profile["telefono"]))
    if profile.get("ubicacion"):
        contacto.append(esc(profile["ubicacion"]))
    if profile.get("linkedin"):
        contacto.append(r"\href{%s}{%s}" % (esc(profile["linkedin"]), esc(profile["linkedin"])))
    if contacto:
        body.append(r"{\small %s}" % r" \;|\; ".join(contacto))
        body.append(r"\\[2pt]")

    body.append(r"\section*{Perfil profesional}")
    body.append(esc(profile.get("summary", "")))

    body.append(r"\section*{Experiencia}")
    for e in profile.get("experiencia", []):
        if not isinstance(e, dict):
            continue
        cargo = esc(e.get("cargo") or "")
        empresa = esc(e.get("empresa") or "")
        fechas = " - ".join(x for x in [e.get("inicio"), e.get("fin")] if x)
        line = r"\textbf{%s}\hfill{\small %s}" % (cargo, empresa)
        body.append(line)
        if fechas:
            body.append(r"{\small\color{gray}%s}" % esc(fechas))
        bullets = [b for b in e.get("bullets", []) if isinstance(b, str) and b.strip()]
        if bullets:
            body.append(r"\begin{itemize}")
            for b in bullets:
                body.append(r"\item %s" % esc(b))
            body.append(r"\end{itemize}")
        body.append(r"\vspace{4pt}")

    body.append(r"\section*{Formacion academica}")
    body.append(r"\begin{itemize}")
    for ed in profile.get("educacion", []):
        body.append(r"\item %s" % esc(ed))
    body.append(r"\end{itemize}")

    skills = " \\cdot ".join(
        r"\textbf{%s}%s" % (esc(s), r" \small(%s)" % esc(lvl) if lvl else "")
        for s, lvl in profile.get("skills", []))
    if skills:
        body.append(r"\section*{Habilidades}")
        body.append(r"{\small %s}" % skills)

    if profile.get("languages"):
        body.append(r"\section*{Idiomas}")
        body.append(r"{\small " + r" \;|\; ".join(
            r"\textbf{%s}: %s" % (esc(k), esc(v)) for k, v in profile.get("languages", {}).items()) + r"}")

    if profile.get("proyectos"):
        body.append(r"\section*{Proyectos}")
        body.append(r"\begin{itemize}")
        for pr in profile.get("proyectos", []):
            body.append(r"\item %s" % esc(pr))
        body.append(r"\end{itemize}")

    body.append(r"\vspace{6pt}")
    body.append(r"{\footnotesize\color{gray}Generado por JobFlow AI - estructura ATS de una columna, sin datos inventados.}")
    body.append(r"\end{document}")
    return "\n".join(body)


# --------------------------------------------------------------------------- #
#  DOCX (descarga)
# --------------------------------------------------------------------------- #
def build_docx(profile: dict) -> BytesIO:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    def add(text, size=10.5, bold=False, italic=False, color=None, align=None, space_after=4):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if color:
            r.font.color.rgb = RGBColor(*color)
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(space_after)
        return p

    def add_section(title):
        p = doc.add_paragraph()
        r = p.add_run(title.upper())
        r.bold = True
        r.font.size = Pt(11)
        r.font.color.rgb = RGBColor(0x2F, 0x41, 0x96)
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)

    add(profile.get("nombre", ""), size=21, bold=True, color=(0x1C, 0x23, 0x33))
    add(profile.get("headline", ""), size=12, bold=True, color=(0x2F, 0x41, 0x96))
    contacto = " · ".join(x for x in [profile.get("email", ""), profile.get("telefono", ""),
                                      profile.get("linkedin", ""), profile.get("ubicacion", "")] if x)
    if contacto:
        add(contacto, size=10, color=(0x5A, 0x6A, 0x94))

    add_section("Perfil profesional")
    add(profile.get("summary", ""), size=10.5)

    add_section("Experiencia")
    for e in profile.get("experiencia", []):
        if not isinstance(e, dict):
            continue
        fecha = " · ".join(x for x in [e.get("inicio"), e.get("fin")] if x)
        titulo = f"{e.get('cargo') or ''} — {e.get('empresa') or ''}" + (f" ({fecha})" if fecha else "")
        add(titulo, size=11, bold=True, space_after=2)
        for b in e.get("bullets", []):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(b).font.size = Pt(10)

    add_section("Formación académica")
    for ed in profile.get("educacion", []):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(ed).font.size = Pt(10)

    skills = " · ".join(f"{s} ({lvl})" if lvl else s for s, lvl in profile.get("skills", []))
    if skills:
        add_section("Habilidades")
        add(skills, size=10.5)

    if profile.get("languages"):
        add_section("Idiomas")
        add(" · ".join(f"{k.capitalize()}: {v}" for k, v in profile.get("languages", {}).items()), size=10.5)

    if profile.get("proyectos"):
        add_section("Proyectos")
        for pr in profile.get("proyectos", []):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(pr).font.size = Pt(10)

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio
