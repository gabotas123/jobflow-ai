"""Respuestas a preguntas de postulacion deducidas del CV confirmado, siempre con evidencia.

Cubre las preguntas que los portales repiten y que no son un dato suelto del perfil:
  * «¿Tienes experiencia en X?» / «¿Manejas X?»  -> «Sí» + la función real del CV que lo prueba.
  * «¿Cuántos años de experiencia tienes en X?»  -> meses calculados con las fechas de las
    experiencias que mencionan X (solo si las fechas tienen mes y año).
  * «Nivel de inglés / Excel»                    -> el nivel confirmado.

Nunca responde «No» ni supone: si el CV no muestra evidencia o faltan fechas, devuelve
None con el motivo para que el candidato responda.
"""
from __future__ import annotations

import re
from datetime import date

from .workflow import norm

MONTHS = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7,
          "ago": 8, "aug": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}
PRESENT = ("actualidad", "presente", "actual", "hoy", "la fecha", "present", "current")
# Words that describe the question rather than its topic.
STOP = set("""
tienes tiene tengo cuentas cuenta cuentas posees posee has hayas trabajado realizado tenido gestionado manejado
manejas maneja manejo dominas domina dominio conoces conoce conocimiento conocimientos sabes sabe experiencia
experiencias cuantos cuantas anos ano meses mes tiempo cuanto nivel indica indique detalla describe cuentanos
alguna algun algunos algunas previa previo comprobable minimo minima menos mas similar similares puesto puestos
cargo cargos area areas rubro sector empresa empresas funciones funcion procesos proceso trabajo trabajando
como para sobre desde hasta este esta estos estas otro otra otros otras donde cual cuales que tus sus una uno
unos unas del las los con por sin entre usar uso utilizando utilizado herramienta herramientas analisis
""".split())
GENERIC_YEARS = ("area", "puesto", "similar", "cargo", "rubro", "funciones", "total", "laboral", "profesional")
YEARS_Q = re.compile(r"\b(cuant[oa]s? (anos|meses|tiempo)|anos de experiencia|tiempo de experiencia|anos trabajando)\b")
YESNO_Q = re.compile(r"^(tienes|tiene|cuentas con|cuenta con|posees|posee|has (trabajado|realizado|tenido|gestionado|manejado|usado|utilizado)|"
                     r"manejas|maneja|conoces|dominas|sabes|tienes conocimiento|cuentas con experiencia|has participado)\b")
LEVEL_Q = re.compile(r"\bnivel de ([a-z0-9 .+#]+)")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", norm(text))


def _stem(word: str) -> str:
    return word[:6] if len(word) > 6 else word


def topic_words(question: str, raw: bool = False) -> list[str]:
    """Palabras del tema; conserva siglas cortas escritas en mayúsculas (SAP, SQL, FI)."""
    out = []
    for original in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9+#]+", question):
        word = norm(original)
        if word not in STOP and (len(word) >= 4 or (len(original) >= 2 and original.isupper())):
            out.append(original if raw else word)
    return list(dict.fromkeys(out))


def topic_stems(question: str) -> list[str]:
    return list(dict.fromkeys(_stem(w) for w in topic_words(question)))


def _matches(stem: str, text: str) -> bool:
    return any(_stem(w) == stem or (len(stem) >= 5 and w.startswith(stem)) for w in _words(text))


def parse_month(value: str, today: date | None = None) -> tuple[int, int] | None:
    """«Mar. 2024», «marzo de 2024», «03/2024», «2024-03» o «Actualidad»; None si falta el mes."""
    v = norm(value).strip(" .")
    today = today or date.today()
    if not v:
        return None
    if any(p in v for p in PRESENT):
        return today.year, today.month
    m = re.search(r"\b(19|20)(\d{2})[-/.](\d{1,2})\b", v) or None
    if m:
        return int(m.group(1) + m.group(2)), int(m.group(3))
    m = re.search(r"\b(\d{1,2})[-/.]((?:19|20)\d{2})\b", v)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"\b([a-z]{3})[a-z]*\.?\s*(?:de\s+|del\s+)?((?:19|20)\d{2})\b", v)
    if m and m.group(1) in MONTHS:
        return int(m.group(2)), MONTHS[m.group(1)]
    return None


def experience_months(exp: dict, today: date | None = None) -> int | None:
    start, end = parse_month(exp.get("inicio", ""), today), parse_month(exp.get("fin", ""), today)
    if not start or not end:
        return None
    months = (end[0] * 12 + end[1]) - (start[0] * 12 + start[1]) + 1
    return months if months > 0 else None


def years_label(months: int) -> str:
    years, rest = divmod(months, 12)
    parts = ([f"{years} año" + ("s" if years != 1 else "")] if years else []) + \
            ([f"{rest} mes" + ("es" if rest != 1 else "")] if rest else [])
    return " y ".join(parts) or "menos de 1 mes"


def choose_years_option(options: list[str], months: int) -> str | None:
    """Elige un rango como «1 a 2 años» o «Menos de 1 año» que contenga los meses."""
    years = months / 12
    for option in options:
        n = norm(option)
        nums = [float(x) for x in re.findall(r"\d+(?:[.,]\d+)?", n.replace(",", "."))]
        if not nums or "ano" not in n and "mes" not in n:
            continue
        scale = 1 / 12 if "mes" in n and "ano" not in n else 1
        low, high = (nums[0] * scale, nums[1] * scale) if len(nums) > 1 else (nums[0] * scale, nums[0] * scale)
        if re.search(r"\b(menos|hasta|menor)\b", n) and years < high:
            return option
        if re.search(r"\b(mas|mayor|\+)\b|\+", n) and years >= low:
            return option
        if len(nums) > 1 and low <= years <= high:
            return option
        if len(nums) == 1 and int(years) == int(low) and not re.search(r"menos|mas|\+", n):
            return option
    return None


def _evidence(profile, stems: list[str]):
    """Experiencias, funciones y habilidades del CV que mencionan cada tema."""
    found: dict[str, list[tuple[dict | None, str]]] = {s: [] for s in stems}
    for exp in profile.experiencia:
        header = f"{exp.get('cargo', '')} {exp.get('empresa', '')}"
        for stem in stems:
            bullets = [b for b in exp.get("bullets", []) if _matches(stem, b)]
            if bullets or _matches(stem, header):
                found[stem].append((exp, next((b for b in bullets if len(b) > 35), bullets[0] if bullets else "")))
    for name, level in profile.skills:
        for stem in stems:
            if _matches(stem, name):
                found[stem].append((None, f"{name}{' (' + level + ')' if level else ''}"))
    for line in list(profile.educacion) + list(profile.languages):
        for stem in stems:
            if _matches(stem, line):
                found[stem].append((None, line))
    return found


def _company(exp: dict) -> str:
    return re.split(r"\s+[-/|]\s+", exp.get("empresa", "") or "Experiencia")[0].strip()


def _role(exp: dict) -> str:
    return re.sub(r"\s+Lima,?\s*Per[uú]\.?$", "", (exp.get("cargo") or "").strip(), flags=re.I)


def answer_question(label: str, field_type: str, options: list[str], profile, today: date | None = None):
    """Devuelve {'value', 'source'} con evidencia del CV, o {'reason'} si no puede responder."""
    q = norm(label).lstrip("¿¡ ").strip()
    label = label.strip().lstrip("¿¡ ")
    strict = field_type in ("select", "radio", "number")  # no room to explain a partial match

    level = LEVEL_Q.search(q)
    if level and not YEARS_Q.search(q):
        topic = level.group(1).strip()
        for name, value in profile.languages.items():
            if norm(name) and norm(name) in topic and value:
                return {"value": str(value).capitalize(), "source": f"Idioma confirmado en tu CV: {name}"}
        for name, value in profile.skills:
            if value and norm(name) and (norm(name) in topic or topic in norm(name)):
                return {"value": value.capitalize(), "source": f"Nivel confirmado en tu CV: {name}"}
        return {"reason": f"Tu CV no indica un nivel para «{topic}»."}

    if YEARS_Q.search(q):
        stems = [s for s in topic_stems(label) if s not in GENERIC_YEARS]
        exps = profile.experiencia if not stems else []
        if stems:
            found = _evidence(profile, stems)
            matched = [s for s in stems if any(e for e, _ in found[s] if e)]
            if not matched or (strict and len(matched) < len(stems)):
                return {"reason": "Tu CV no muestra experiencia laboral en ese tema. Respóndela tú."}
            exps = list({id(e): e for s in matched for e, _ in found[s] if e}.values())
        if not exps:
            return {"reason": "Tu perfil no tiene experiencias registradas."}
        durations = [experience_months(e, today) for e in exps]
        if any(d is None for d in durations):
            return {"reason": "Completa el mes de inicio y fin de tus experiencias en Mi perfil para calcular los años."}
        months = sum(durations)
        companies = ", ".join(dict.fromkeys(_company(e) for e in exps))
        source = f"Calculado con las fechas de tu CV confirmado ({companies})"
        if field_type == "number":
            return {"value": str(months // 12), "source": source + f": {years_label(months)}"}
        if field_type in ("select", "radio"):
            option = choose_years_option(options, months)
            return {"value": option, "source": source} if option else {"reason": "Ninguna opción coincide con tus años calculados."}
        return {"value": f"{years_label(months)} ({companies}).", "source": source}

    if YESNO_Q.search(q) or (field_type in ("select", "radio") and {norm(o) for o in options} >= {"si", "no"}):
        words, shown = topic_words(label), topic_words(label, raw=True)
        stems = [_stem(w) for w in words]
        if not stems:
            return {"reason": "No se identificó el tema de la pregunta."}
        found = _evidence(profile, stems)
        matched = [s for s in dict.fromkeys(stems) if found[s]]
        if not matched or (strict and len(matched) < len(set(stems))):
            return {"reason": "Tu CV no muestra evidencia de eso. Respóndela tú si corresponde."}
        if field_type in ("select", "radio"):
            return {"value": "Sí", "source": "Evidencia en tu CV confirmado"}
        facts = []
        for stem in matched:
            for exp, detail in found[stem]:
                if exp:
                    fact = f"{_company(exp)}: {detail.rstrip('.')}" if detail else f"{_company(exp)}, como {_role(exp)}"
                else:
                    fact = detail
                if len(fact) > 140:
                    fact = fact[:140].rstrip(" ,;") + "…"
                if fact and fact not in facts:
                    facts.append(fact)
        topics = " y ".join(dict.fromkeys(s for w, s in zip(words, shown) if _stem(w) in matched))
        return {"value": f"Sí, en {topics}. " + "; ".join(facts[:2]) + ".", "source": "Evidencia en tu CV confirmado"}
    return None
