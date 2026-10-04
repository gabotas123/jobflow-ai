"""Revision de un CV frente a un aviso, con el criterio de una headhunter senior experta en filtros ATS.

Dos capas:
  1. `audit()` — reglas estrictas, sin modelo de lenguaje. Funciona siempre. Decide si el CV pasa el
     filtro automatico y el vistazo de seis segundos de quien recluta, y dice que corregir primero.
  2. `rewrite()` — si hay un modelo configurado (LLM_PROVIDER / LLM_API_KEY), propone como redactar
     cada logro. Cada propuesta se valida contra el CV: una cifra o una herramienta que no estaba
     en el original se descarta. La candidata aprueba; nada se aplica solo.

Lo que esta revision nunca hace: anadir experiencia, cargos, anos, herramientas o cifras. Cuando
falta un dato que subiria las probabilidades, lo pregunta.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .career import CVVersion, application, profile_row
from .config import settings
from .cv_answers import covered_months, parse_month
from .db import get_db
from .profile_models import CandidateProfile
from .seed import profile_from_row
from .workflow import ApplicationDetail, norm

router = APIRouter(prefix='/api/headhunter')

HEADHUNTER_PROMPT = """Eres una headhunter senior con 15 años seleccionando perfiles de finanzas, \
administración y operaciones en el Perú, especialista en filtros ATS (Workday, Taleo, SuccessFactors \
y los de Bumeran y Computrabajo). Revisas un logro del CV frente a un aviso concreto.

Tu criterio es estricto: un CV que no refleja el lenguaje del aviso no llega a una persona.

Reglas que no puedes romper:
1. No inventes nada. No añadas cifras, porcentajes, montos, herramientas, cargos, empresas ni años \
que no estén en el texto original. Si falta la cifra, NO la pongas: deja el logro sin cifra.
2. Usa las palabras exactas del aviso solo cuando el texto original ya describe esa misma tarea.
3. Empieza con un verbo de acción en pasado y primera persona (Gestioné, Reduje, Elaboré).
4. Una sola línea, máximo 28 palabras, sin adjetivos de relleno (proactivo, dinámico, responsable).
5. Estructura: acción + qué + con qué herramienta (si estaba) + resultado (si estaba).

Devuelve solo JSON: {"propuesta": "...", "pregunta": "..."}.
"pregunta" es lo que le preguntarías a la candidata para poder cuantificar el logro; vacío si ya \
tiene cifra."""

STOP = set("""a al algo ante bajo cada como con contra cual cuando de del desde donde dos el ella ellos en entre
era es esa ese eso esta este esto estos fue ha hacia hasta hay la las le les lo los mas me mi muy no nos o otra
otro para pero por que se sea ser si sin sobre su sus tambien te tiene tu un una uno unos y ya anos ano
empresa experiencia trabajo puesto cargo area funciones requisitos conocimiento conocimientos manejo nivel
minimo minima deseable indispensable buscamos ofrecemos beneficios persona personas equipo capacidad
disponibilidad horario lunes viernes sabado sueldo salario planilla ingreso postula oferta importante
similares afines egresado bachiller titulado estudiante carrera carreras realizar apoyar brindar
mantener asegurar garantizar cumplir contar requiere necesario necesaria nuestro nuestra nuestros""".split())
WEAK_STARTS = ("responsable de", "encargado de", "encargada de", "apoyo en", "apoyo a", "apoye en",
               "ayudante", "participacion en", "participe en", "funciones de", "labores de", "tareas de")
FILLER = ("proactivo", "proactiva", "dinamico", "dinamica", "trabajo en equipo", "orientado a resultados",
          "orientada a resultados", "puntual", "empatico", "empatica", "lider nato",
          "bajo presion", "ganas de aprender", "comprometido", "comprometida")
# Pasado en primera persona: «Gestioné», «Elaboré». Los irregulares sin tilde van en lista corta.
VERB_END = re.compile(r"^(?:[a-záéíóúñ]+(?:é|í|ó|amos|imos|aron|ieron)|reduje|hice|obtuve|mantuve|propuse|conduje|produje|puse|tuve)\b", re.I)
NUMBER = re.compile(r"\d")
PASS, RISK = 80, 60


def _words(text: str) -> list:
    found = (w.strip(".") for w in re.findall(r"[a-z0-9+#.]{3,}", norm(text)))
    return [w for w in found if len(w) > 2 and w not in STOP and not w.isdigit()]


def job_keywords(title: str, description: str, tools=None, limit: int = 18) -> list:
    """Los terminos por los que un ATS filtraria este aviso: herramientas, titulo y lo que mas repite."""
    out, seen = [], set()

    def add(term, kind):
        key = norm(term).strip()
        if key and key not in seen and len(key) > 2:
            seen.add(key)
            out.append({"termino": " ".join(term.split()), "tipo": kind})

    for tool in tools or []:
        add(tool, "herramienta")
    for word in _words(title):
        add(word, "puesto")
    words = _words(description)
    pairs = Counter(f"{a} {b}" for a, b in zip(words, words[1:]))
    for pair, n in pairs.most_common(8):
        if n >= 2:
            add(pair, "frase")
    for word, n in Counter(words).most_common(40):
        if n >= 2 and len(out) < limit:
            add(word, "repetida")
    return out[:limit]


def cv_text(p: CandidateProfile) -> str:
    parts = [p.headline, p.summary, " ".join(p.educacion), " ".join(s for s, _ in p.skills)]
    for e in p.experiencia:
        parts += [e.get("cargo", ""), e.get("empresa", ""), " ".join(e.get("bullets", []))]
    return norm(" ".join(x for x in parts if x))


def _check(name, weight, ok, evidence, fix="", knockout=False, partial=None):
    score = weight if ok else round(weight * partial) if partial is not None else 0
    return {"criterio": name, "peso": weight, "puntos": score,
            "estado": "cumple" if ok else "riesgo" if partial else "falla",
            "evidencia": evidence, "correccion": "" if ok else fix, "excluyente": bool(knockout and not ok)}


def audit(p: CandidateProfile, title: str, description: str = "", tools=None, years_required=None) -> dict:
    """Revision estricta. Devuelve veredicto, puntaje, cada criterio con su evidencia y que corregir."""
    text, bullets = cv_text(p), [b for e in p.experiencia for b in e.get("bullets", []) if b.strip()]
    checks, questions = [], []

    # 1 · el nombre del puesto: es lo primero que busca el filtro y quien recluta
    title_words = _words(title)
    hits = [w for w in title_words if w in text]
    ratio = len(hits) / len(title_words) if title_words else 0
    checks.append(_check("El puesto del aviso aparece en tu CV", 18, ratio >= .99,
                         f"{len(hits)} de {len(title_words)} palabras de «{title}» están en tu CV." if title_words else "El aviso no indica el puesto.",
                         "Si ya hiciste estas funciones, nómbralas con las palabras del aviso en tu titular o en el cargo. "
                         "No cambies un cargo que no tuviste.", partial=ratio if ratio >= .5 else None))

    # 2 · palabras clave del aviso
    keys = job_keywords(title, description, tools)
    present = [k for k in keys if norm(k["termino"]) in text]
    missing = [k for k in keys if norm(k["termino"]) not in text]
    cover = len(present) / len(keys) if keys else 0
    checks.append(_check("Palabras clave del aviso", 24, cover >= .7,
                         f"Tu CV contiene {len(present)} de {len(keys)} términos clave ({round(cover * 100)} %)." if keys else "El aviso no trae descripción: no se puede comparar.",
                         "Un filtro automático descarta por debajo del 70 %. Añade solo los términos que describan algo que de verdad hiciste.",
                         partial=cover if cover >= .4 else None))
    for k in missing[:6]:
        questions.append(f"¿Has trabajado con «{k['termino']}»? Si es así, dilo con esas palabras; si no, déjalo fuera.")

    # 3 · años de experiencia (requisito excluyente)
    months = covered_months(p.experiencia)
    if years_required:
        ok = months >= years_required * 12
        checks.append(_check("Años de experiencia exigidos", 14, ok,
                             f"El aviso pide {years_required:g} año(s); tus fechas suman {months // 12} año(s) y {months % 12} mes(es).",
                             "Es un requisito excluyente y no se corrige redactando: no postules como si lo cumplieras.", knockout=True))

    # 4 · fechas con mes y año: sin mes, el ATS no puede calcular tu antigüedad
    undated = [e.get("cargo") or e.get("empresa") or "una experiencia" for e in p.experiencia
               if not parse_month(e.get("inicio", "")) or not parse_month(e.get("fin", ""))]
    checks.append(_check("Fechas con mes y año", 8, not undated and bool(p.experiencia),
                         "Todas tus experiencias tienen mes y año." if not undated and p.experiencia else f"Sin mes en: {', '.join(undated[:3]) or 'no hay experiencia registrada'}.",
                         "Escribe cada periodo como «Mar. 2023 – Dic. 2024». Con solo el año, el filtro cuenta menos tiempo del que trabajaste."))

    # 5 · logros con cifras
    with_number = [b for b in bullets if NUMBER.search(b)]
    share = len(with_number) / len(bullets) if bullets else 0
    checks.append(_check("Logros con cifras", 14, share >= .5,
                         f"{len(with_number)} de {len(bullets)} logros tienen una cifra." if bullets else "No hay logros registrados.",
                         "Quien recluta decide en segundos, y lo que retiene son números. Al menos la mitad de tus logros debe tener uno real.",
                         partial=share * 2 if share >= .25 else None))
    for b in [b for b in bullets if not NUMBER.search(b)][:4]:
        questions.append(f"«{b[:90]}» — ¿cuánto fue? (cuántos clientes, qué monto, qué porcentaje, en cuánto tiempo)")

    # 6 · verbos de accion
    weak = [b for b in bullets if norm(b).startswith(WEAK_STARTS) or not VERB_END.match(b.strip())]
    share = 1 - len(weak) / len(bullets) if bullets else 0
    checks.append(_check("Logros que empiezan con un verbo de acción", 8, bool(bullets) and share >= .8,
                         f"{len(bullets) - len(weak)} de {len(bullets)} logros empiezan con verbo de acción." if bullets else "No hay logros registrados.",
                         "Cambia «Responsable de…» o «Apoyo en…» por lo que hiciste: «Gestioné», «Reduje», «Elaboré».",
                         partial=share if share >= .5 else None))

    # 7 · datos de contacto
    lacking = [n for n, v in (("correo", p.email), ("teléfono", p.telefono), ("ciudad", p.ubicacion)) if not v]
    checks.append(_check("Datos de contacto completos", 6, not lacking,
                         "Correo, teléfono y ciudad presentes." if not lacking else f"Falta: {', '.join(lacking)}.",
                         "Sin ellos no pueden llamarte, y muchos filtros descartan por ciudad."))

    # 8 · extension de cada experiencia
    crowded = [e.get("cargo") or e.get("empresa") for e in p.experiencia if not 2 <= len(e.get("bullets", [])) <= 6]
    long_ones = [b for b in bullets if len(b) > 220]
    ok = not crowded and not long_ones and bool(p.experiencia)
    checks.append(_check("Extensión legible", 4, ok,
                         "Entre 2 y 6 logros por experiencia, de una o dos líneas." if ok else
                         f"{len(crowded)} experiencia(s) fuera de 2–6 logros; {len(long_ones)} logro(s) de más de dos líneas.",
                         "De 3 a 5 logros por experiencia, una línea o dos cada uno. Lo demás no se lee."))

    # 9 · relleno
    fluff = sorted({f for f in FILLER if f in text})
    checks.append(_check("Sin adjetivos de relleno", 4, not fluff,
                         "No hay adjetivos vacíos." if not fluff else f"Aparecen: {', '.join(fluff[:5])}.",
                         "Quítalos: no suman a ningún filtro y ocupan el lugar de un hecho."))

    total = sum(c["peso"] for c in checks)
    score = round(100 * sum(c["puntos"] for c in checks) / total) if total else 0
    knocked = [c["criterio"] for c in checks if c["excluyente"]]
    verdict = ("No pasa el filtro" if knocked or score < RISK else "En riesgo" if score < PASS else "Pasa el filtro")
    order = sorted((c for c in checks if c["estado"] != "cumple"), key=lambda c: c["puntos"] - c["peso"])
    return {
        "veredicto": verdict, "puntaje": score, "excluyentes": knocked,
        "resumen": ("Hay un requisito excluyente que tu CV no cumple: redactar mejor no lo resuelve." if knocked else
                    "Tu CV refleja el aviso y se lee rápido." if verdict == "Pasa el filtro" else
                    "Tiene base, pero un filtro estricto puede dejarlo fuera. Corrige lo de arriba primero." if verdict == "En riesgo" else
                    "Tal como está, lo más probable es que no llegue a una persona."),
        "criterios": checks,
        "prioridades": [{"criterio": c["criterio"], "correccion": c["correccion"]} for c in order[:3]],
        "palabras_clave": {"presentes": [k["termino"] for k in present], "faltantes": [k["termino"] for k in missing]},
        "preguntas": questions[:8],
    }


def _grounded(proposal: str, source: str, cv: str) -> bool:
    """Una propuesta solo vale si no trae cifras ni herramientas que no estaban."""
    if any(n not in source for n in re.findall(r"\d[\d.,]*", proposal)):
        return False
    known = norm(source + " " + cv)
    # Nombres propios y siglas (Excel, SAP…) salvo la primera palabra, que va en mayúscula por ser inicio.
    names = [m.group() for m in re.finditer(r"\b[A-Z][A-Za-z0-9+#]+\b", proposal) if m.start() > 0]
    return all(norm(t) in known for t in names)


def rewrite(p: CandidateProfile, title: str, description: str, limit: int = 6):
    """Propuestas de redaccion con el modelo configurado; None si no hay ninguno."""
    if settings.llm_provider == "none" or not settings.llm_api_key:
        return None
    import httpx
    cv, out = cv_text(p), []
    bullets = [b for e in p.experiencia for b in e.get("bullets", []) if b.strip()][:limit]
    for bullet in bullets:
        try:
            r = httpx.post(settings.llm_base_url.rstrip("/") + "/chat/completions", timeout=40,
                           headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                           json={"model": settings.llm_model, "temperature": 0.2,
                                 "response_format": {"type": "json_object"},
                                 "messages": [{"role": "system", "content": HEADHUNTER_PROMPT},
                                              {"role": "user", "content": f"AVISO: {title}\n{description[:2500]}\n\nLOGRO ORIGINAL: {bullet}"}]})
            data = json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception:
            continue
        proposal = " ".join(str(data.get("propuesta", "")).split())
        if proposal and proposal != bullet and _grounded(proposal, bullet, cv):
            out.append({"original": bullet, "propuesta": proposal, "pregunta": str(data.get("pregunta", ""))[:200]})
        else:
            out.append({"original": bullet, "propuesta": "", "descartada": bool(proposal),
                        "pregunta": str(data.get("pregunta", ""))[:200]})
    return out


@router.get('/applications/{aid}')
def review(aid: int, redaccion: bool = False, db: Session = Depends(get_db)):
    a, job = application(db, aid)
    row = profile_row(db, a.profile_id)
    version = db.query(CVVersion).filter_by(application_id=aid).order_by(CVVersion.id.desc()).first()
    profile = CandidateProfile.from_dict(version.snapshot["cv"]) if version else profile_from_row(row)
    detail = db.query(ApplicationDetail).filter_by(application_id=aid).first()
    vacancy = ((detail.details if detail else {}) or {}).get("vacante", {})
    result = audit(profile, job.titulo, job.descripcion or "", vacancy.get("herramientas"), vacancy.get("anos_obligatorios"))
    result["revisado"] = "CV adaptado a esta vacante" if version else "Tu perfil, sin adaptar"
    result["redaccion_disponible"] = settings.llm_provider != "none" and bool(settings.llm_api_key)
    if redaccion:
        result["redaccion"] = rewrite(profile, job.titulo, job.descripcion or "")
    return result
