"""Parser de CV ADAPTATIVO (PDF / DOCX / TXT) -> `CandidateProfile`.

Adaptivo = sin plantilla fija. Detecta el formato de cada CV mediante
heuristicas robustas:
  - encabezados de seccion por PATRON ANCLADO (no substring suelta -> evita que
    lineas de texto como '...objetivos comerciales.' cambien de seccion);
  - empresas por PALABRA COMPLETA (word-boundary) -> evita falsos positivos
    ('cia' dentro de 'gerencia');
  - bullets por marcador/verbo, cargos por palabra de rol;
  - formato comun 'Empresa - Cargo - Fechas' en una sola linea;
  - fechas 'Mes AAAA - Actualidad', 'AAAA - AAAA';
  - ligaduras (fi, fl), glitches de extraccion ('A vanzado' -> 'Avanzado');
  - telefonos con parentesis y/o +, excluyendo DNI; linkedin sin https;
  - 'Logros' en seccion aparte fusionados a la experiencia anterior.

Lo que no detecta lo omite (la UI lo marca para confirmar; nunca se inventa).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from .profile_models import CandidateProfile

# --------------------------------------------------------------------------- #
#  Normalizacion (incluye conversion de ligaduras tipo 'fi' -> 'fi')
# --------------------------------------------------------------------------- #
_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
              "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}


def _fold(text: str) -> str:
    for lig, repl in _LIGATURES.items():
        text = text.replace(lig, repl)
    return text


def norm(t: str) -> str:
    t = _fold(unicodedata.normalize("NFD", t))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# --------------------------------------------------------------------------- #
#  Contacto (variantes de formato)
# --------------------------------------------------------------------------- #
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\(?\+?\d{1,4}\)?[\s.\-()]*\d{3}[\s.\-()]*\d{3,4}(?:[\s.\-()]*\d{2,4})?")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/[^\s|)\]\n]+", re.I)
DNI_RE = re.compile(r"\bDNI\s*[:#]?\s*\d{6,10}\b", re.I)

_MONTHS = "(?:ene|feb|mar|abr|may|jun|jul|ago|set|sep|oct|nov|dic|enero|febrero|marzo|abril|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
# Los grupos 1 y 2 conservan el mes («Ene. 2023»): sin el, no se puede calcular la antiguedad.
DATES_RE = re.compile(
    rf"((?:{_MONTHS})\.?\s+(?:19|20)\d{{2}})\s*[-–]\s*"
    rf"(?:((?:{_MONTHS})\.?\s+(?:19|20)\d{{2}})|(actualidad|presente|actual|hoy))",
    re.I,
)
YEARS_RE = re.compile(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})")

# --------------------------------------------------------------------------- #
#  Encabezados de seccion: patrones ANCLADOS (regex al inicio/fin de linea)
# --------------------------------------------------------------------------- #
HEADER_PATTERNS = {
    "resumen": r"^(resumen|perfil|perfil\s+profesional|resumen\s+profesional|objetivo\s+laboral|presentacion|profile|summary)",
    "experiencia": r"^(experiencia|experiencia\s+laboral|experiencia\s+profesional|empleo|work\s+experience|experience)",
    "logros": r"^(logros|logros\s+destacados|achievements|accomplishments)",
    "educacion": r"^(educacion|formacion|formacion\s+academica|formacion\s+profesional|estudios|historial\s+academico|education|academic)",
    "habilidades": r"^(habilidades|skills|herramientas|competencias|informatica|conocimientos\s+(?:de\s+)?(?:informatica|tecnologicos)?|conocimientos\s+de\s+software)",
    "idiomas": r"^(idiomas|lenguajes|lenguas|languages)",
    "proyectos": r"^(proyectos|projects|portafolio)",
    "cursos": r"^(cursos|certificaciones|courses|certifications|diplomados)",
}

KNOWN_SKILLS = [
    "excel", "power bi", "power query", "vba", "macros", "python", "sql", "sap",
    "stata", "dax", "r studio", "tableau", "looker", "spss", "crm", "salesforce",
    "erp", "power pivot", "google sheets", "access", "office", "notion", "trello",
    "jira", "sesame", "quickbooks", "modelado financiero", "forecasting",
]
LANG_NAMES = {
    "ingles": "ingles", "english": "ingles", "espanol": "espanol",
    "spanish": "espanol", "portugues": "portugues", "japones": "japones",
    "frances": "frances", "aleman": "aleman", "italiano": "italiano",
    "chino": "chino", "mandarin": "chino",
}
LEVEL_WORDS = ("basico", "intermedio", "intermedio alto", "avanzado", "nativo",
               "fluido", "a1", "a2", "b1", "b2", "c1", "c2", "usuario", "aplicado")
ACTION_VERBS = [
    "analiz", "desarroll", "gestion", "implement", "coordina", "lider", "optimiz",
    "automatiz", "elabor", "realic", "llev", "organiz", "control", "evalu", "disen",
    "redact", "prepar", "revis", "segu", "monitore", "capacit", "negoci", "presupuest",
    "identific", "contribu", "particip", "apoyo", "consolid", "valid", "supervis",
    "planificacion", "proyeccion", "mitigar", "fortalec", "manej", "uso",
]
ROLE_WORDS = ("practicante", "asistente", "analista", "auxiliar", "coordinador",
              "ingeniero", "ejecutivo", "contador", "especialista", "profesional",
              "jefe", "supervisor", "gerente", "administrador", "consultor", "tesorero")
COMPANY_WORDS = ("sac", "s.a", "s.a.c", "corp", "banco", "grupo", "universidad",
                 "portales", "limited", "ltd", "inc", "corporativo", "holding",
                 "empresa", "institute", "association", "c&a", "yichang", "pymes")


# --------------------------------------------------------------------------- #
#  Extraccion de texto
# --------------------------------------------------------------------------- #
def extract_text(path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    if suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    raise ValueError(f"Formato no soportado: {suffix}")


def _clean(text: str) -> str:
    """Limpiezas comunes: ligaduras y glitches de extraccion del PDF."""
    text = _fold(text)
    text = re.sub(r"\bF\s*eb\.", "Feb.", text)
    text = re.sub(r"\b([A-Za-z])\s+(vanzado|ntermedio|ntermedia|asico|gresado|inanciero|onomista|ivel|rocedimiento)\b",
                  r"\1\2", text, flags=re.I)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return text


def _find(text: str, pattern: re.Pattern) -> str:
    m = pattern.search(text)
    return m.group(0).strip() if m else ""


# --------------------------------------------------------------------------- #
#  Secciones (patrones anclados; ignora texto corrido)
# --------------------------------------------------------------------------- #
def _header_of(line: str) -> Optional[str]:
    s = line.strip()
    if not s or len(s) > 40:
        return None
    if s.endswith((".", ",", ";", ":")):
        return None                      # lineas de texto corrido
    low = norm(s)
    for sec, pat in HEADER_PATTERNS.items():
        if re.match(pat, low) and len(low.split()) <= 6:
            return sec
    return None


def _split_sections(text: str) -> dict:
    result: dict = {}
    current = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        found = _header_of(s)
        if found:
            current = found
            result.setdefault(current, [])
        elif current:
            result[current].append(s)
    return {k: "\n".join(v) for k, v in result.items()}


# --------------------------------------------------------------------------- #
#  Experiencia
# --------------------------------------------------------------------------- #
def _new_entry() -> dict:
    return {"empresa": "", "cargo": "", "inicio": "", "fin": "", "bullets": []}


def _is_marker_bullet(line: str) -> bool:
    return bool(re.match(r"^\s*[•·\-*▪\d.)]\s", line)) or bool(re.match(r"^\s*[-•·*▪]\s*\S", line))


def _date_only(line: str) -> bool:
    """La linea es solo un periodo («Ene. 2023 - Dic. 2024»), sin empresa ni cargo."""
    rest = DATES_RE.sub(" ", line)
    rest = YEARS_RE.sub(" ", rest)
    return rest != line and len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", rest)) < 4


def _has_dates(text: str) -> bool:
    return bool(DATES_RE.search(text) or YEARS_RE.search(text))


def _is_company_or_date(line: str, low: str) -> bool:
    if DATES_RE.search(line) or YEARS_RE.search(line):
        return True
    if re.search(r"\s&\s", line) or "y cía" in low or "y cia" in low:
        return True
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in COMPANY_WORDS)


def _is_role(line: str, low: str) -> bool:
    words = low.split()
    return bool(words) and words[0].strip(";:,.-") in ROLE_WORDS and len(words) <= 14


def _is_bullet(line: str, low: str) -> bool:
    if _is_marker_bullet(line):
        return True
    return len(line) > 45 or any(v in low for v in ACTION_VERBS)


def _apply_dates(entry: dict) -> None:
    text = entry.get("empresa", "")
    m = DATES_RE.search(text)
    if m:
        entry["inicio"] = " ".join(m.group(1).split())
        entry["fin"] = " ".join(m.group(2).split()) if m.group(2) else "Actualidad"
        text = text[:m.start()] + " " + text[m.end():]
    else:
        m2 = YEARS_RE.search(text)
        if m2:
            entry["inicio"], entry["fin"] = m2.group(1), m2.group(2)
            text = text[:m2.start()] + " " + text[m2.end():]
    # separar 'Empresa - Cargo' cuando vienen en la misma linea
    parts = [p.strip() for p in re.split(r"\s+-\s+", text) if p.strip()]
    if len(parts) >= 2 and norm(parts[-1]).split()[0] in ROLE_WORDS:
        entry["cargo"] = parts[-1]
        text = " - ".join(parts[:-1]) if len(parts) > 2 else parts[0]
    elif len(parts) >= 2 and not entry["cargo"] and norm(parts[0]).split()[0] in ROLE_WORDS:
        # orden inverso, igual de comun: «Asistente de Cobranzas - Corporacion Andina SAC»
        entry["cargo"] = parts[0]
        text = " - ".join(parts[1:])
    # limpiar residuos ' - ' iniciales
    entry["empresa"] = re.sub(r"^[\s\-]+|[\s\-]+$", "", text)
    # «Cargo - Empresa» en una sola linea, cuando el CV no trae linea de empresa aparte
    if not entry["empresa"] and " - " in entry["cargo"]:
        pieces = [p.strip() for p in re.split(r"\s+-\s+", entry["cargo"]) if p.strip()]
        if len(pieces) >= 2 and norm(pieces[0]).split()[0] in ROLE_WORDS:
            entry["cargo"], entry["empresa"] = pieces[0], " - ".join(pieces[1:])


def _pipe_blocks(text: str):
    """CV de plantilla: «Cargo | Empresa», un parrafo y la fecha al final de cada bloque.

    En estos PDF el texto sale por columnas y los empleos quedan repartidos por todo el documento
    (incluso dentro de «Habilidades»), asi que se buscan por su forma y no por la seccion.
    Devuelve (experiencias, texto sin esos bloques) o None si el CV no usa este formato.
    """
    raw = [l.strip() for l in text.splitlines()]
    lines, i = [], 0
    while i < len(raw):                      # la cabecera partida en dos lineas se une
        if raw[i].endswith("|") and i + 1 < len(raw) and raw[i + 1]:
            lines.append(raw[i] + " " + raw[i + 1]); i += 2
        else:
            lines.append(raw[i]); i += 1

    def candidate(line: str) -> bool:
        return (" | " in line and not line.isupper() and not re.search(r"\([^)]*\|[^)]*\)", line)
                and not EMAIL_RE.search(line) and not _date_only(line))

    marks = {n for n, l in enumerate(lines) if candidate(l)}
    found = []
    for n in sorted(marks):
        for j in range(n + 1, min(n + 9, len(lines))):
            if j in marks or _header_of(lines[j]):
                break
            if _date_only(lines[j]):
                found.append((n, j)); break
    if len(found) < 2:
        return None

    used, entries, closed = set(), [], {-1}
    for start, end in found:
        header = lines[start]
        # el cargo puede venir partido: «Especialista en Traduccion y Comunicacion» / «Internacional | G&L»
        prev = lines[start - 1] if start else ""
        before = lines[start - 2] if start > 1 else ""
        if (prev and "|" not in prev and not _date_only(prev) and not _header_of(prev)
                and prev[-1] not in ".,;:" and len(prev.split()) <= 8
                and (start - 2 in closed or _header_of(before) or not before)):
            header = prev + " " + header
            used.add(start - 1)
        cargo, empresa = (x.strip() for x in header.split(" | ", 1))
        body = " ".join(l for l in lines[start + 1:end] if l)
        entry = _new_entry()
        entry["cargo"], entry["empresa"] = cargo, empresa + " " + lines[end]
        entry["bullets"] = [b.strip() for b in re.split(r"(?<=[.!?])\s+", body) if b.strip()]
        _apply_dates(entry)
        entry["cargo"] = cargo                 # _apply_dates no debe reinterpretar la cabecera
        entries.append(entry)
        used.update(range(start, end + 1))
        closed.add(end)
    rest = "\n".join(l for n, l in enumerate(lines) if n not in used)
    return entries, rest


def _parse_experience(sec_text: str) -> List[dict]:
    entries: List[dict] = []
    cur: Optional[dict] = None
    for raw in sec_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = norm(line)
        if _is_marker_bullet(line):
            if cur is None:
                cur = _new_entry(); entries.append(cur)
            cur["bullets"].append(re.sub(r"^[•·\-*▪\d.)\s]+", "", line).strip())
        elif _is_company_or_date(line, low):
            # Una linea que solo trae el periodo pertenece al empleo que se esta leyendo:
            # abrir una entrada nueva desplazaria cargo, fechas y logros al siguiente empleo.
            if _date_only(line) and cur is not None and not _has_dates(cur["empresa"]):
                cur["empresa"] = (cur["empresa"] + " " + line).strip()
            else:
                cur = _new_entry(); cur["empresa"] = line; entries.append(cur)
        elif _is_role(line, low):
            # Solo completa el bloque en curso si aun se esta armando su encabezado;
            # si ya tiene cargo o ya recogio logros, este cargo abre el siguiente empleo.
            if cur is not None and not cur["cargo"] and not cur["bullets"]:
                cur["cargo"] = line
            else:
                cur = _new_entry(); cur["cargo"] = line; entries.append(cur)
        elif _is_bullet(line, low):
            if cur is None:
                cur = _new_entry(); entries.append(cur)
            cur["bullets"].append(line)
        else:
            if cur is not None and not cur["cargo"]:
                cur["cargo"] = line
            elif cur is not None:
                cur["bullets"].append(line)
            else:
                cur = _new_entry(); cur["empresa"] = line; entries.append(cur)
    for e in entries:
        _apply_dates(e)
        e["bullets"] = [b for b in e["bullets"] if b]
    return [e for e in entries if e["empresa"] or e["cargo"] or e["bullets"]]


def _merge_logros(experiencia: List[dict], logros_text: str) -> None:
    """Fusiona una seccion 'Logros' en la experiencia (bullets/empresas extra)."""
    for raw in logros_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = norm(line)
        if _is_company_or_date(line, low):
            e = _new_entry(); e["empresa"] = line; experiencia.append(e)
        elif _is_role(line, low):
            if experiencia:
                experiencia[-1]["cargo"] = line
        elif _is_bullet(line, low) or _is_marker_bullet(line):
            if not experiencia:
                experiencia.append(_new_entry())
            experiencia[-1]["bullets"].append(re.sub(r"^[•·\-*▪\d.)\s]+", "", line).strip())
    for e in experiencia:
        _apply_dates(e)


# --------------------------------------------------------------------------- #
#  Habilidades / idiomas ('Skill - Nivel X' o listas)
# --------------------------------------------------------------------------- #
def _parse_named_lines(section_text: str, plain: bool = False) -> dict:
    out: dict = {}
    for raw in section_text.splitlines():
        line = raw.strip().strip("-•·*").strip()
        if not line or len(line) < 3:
            continue
        m = re.match(r"^(.{2,45}?)\s*[-:]\s*(?:Nivel\s*)?([A-Za-zÁÉÍÓÚÑáéíóúñ\-]+)\s*$", line)
        if m:
            name, level = m.group(1).strip(), m.group(2).strip().lower()
            # nivel embebido en el nombre: "Inglés avanzado - ICPNA"
            if not any(w in level for w in LEVEL_WORDS):
                mk = re.search(r"(basico|intermedio|intermedio alto|avanzado|nativo|fluido)", norm(name))
                if mk:
                    level = mk.group(1)
                    name = re.sub(r"\s*[-–]?\s*(basico|intermedio|intermedio\s+alto|avanzado|nativo|fluido)\s*$",
                                  "", name, flags=re.I).strip()
            out[norm(name)] = (name, level if any(w in level for w in LEVEL_WORDS) else "")
            continue
        parts = [p.strip() for p in re.split(r"[,\|/]", line) if len(p.strip()) > 2]
        if len(parts) > 1:
            last = None
            for p in parts:
                pk = norm(p)
                only_level = re.fullmatch(r"(?:nivel\s+)?(basico|intermedio|avanzado|nativo|fluido)", pk)
                if only_level and last:           # «Microsoft Excel, nivel intermedio»
                    out[last] = (out[last][0], only_level.group(1))
                    continue
                last = pk
                mkl = re.search(r"(basico|intermedio|avanzado|nativo|fluido)\s*$", pk)
                if mkl:
                    lvl = mkl.group(1)
                    p = re.sub(r"\s+[\wáéíóúñ\-]+$", "", p).strip()
                    out[norm(p)] = (p, lvl)
                else:
                    out[pk] = (p, "")
                last = norm(p) if mkl else pk
        elif plain and len(line.split()) <= 7 and not re.search(r"[:@\d|()]", line) and not line.isupper():
            out[norm(line)] = (line, "")        # una habilidad por linea, sin nivel
    return out


def parse_skills(sections: dict, text_low: str) -> List[tuple]:
    # Solo en «Habilidades» vale una habilidad por linea; en «Cursos» esas lineas son titulos partidos.
    items = _parse_named_lines(sections.get("habilidades", ""), plain=True)
    items.update(_parse_named_lines(sections.get("cursos", "")))
    for s in KNOWN_SKILLS:
        pat = re.escape(s)
        if s in text_low or re.search(rf"\b{pat}\b", text_low):
            if not any(k == s.replace(" ", "") for k in items if norm(k).replace(" ", "") == s.replace(" ", "")):
                if not any(s.replace(" ", "") in norm(k).replace(" ", "") for k in items):
                    items[s.replace(" ", "")] = (s, "")
    result, seen = [], set()
    for key, (name, level) in items.items():
        low_key = norm(key)
        norm_name = norm(name)
        if norm_name in seen or norm_name.startswith(("curso ", "diplomatura", "diplomado")):
            continue
        seen.add(norm_name)
        if not level:
            m = re.search(re.escape(norm_name) + r"[^\n]{0,30}(basico|intermedio|avanzado|nativo|usuario|aplicado|fluido)", text_low)
            if m:
                level = m.group(1)
        result.append((name.title() if name else key, level))
    return result


def parse_languages(sections: dict, text_low: str) -> dict:
    idiomas = sections.get("idiomas", "")
    items = _parse_named_lines(idiomas)
    out: dict = {}
    for key, (name, level) in items.items():
        for lname, canon in LANG_NAMES.items():
            if norm(lname) in key:
                out[canon] = level or ""
                break
    if not out:
        # Sin seccion de idiomas solo cuenta el idioma que viene con su nivel («Inglés avanzado»).
        # La palabra suelta no basta: «Colegio Peruano Japonés» no significa que hable japonés.
        listed = norm(idiomas)
        for lname, canon in LANG_NAMES.items():
            m = re.search(rf"\b{re.escape(norm(lname))}\b[^\n]{{0,30}}?\b(basico|intermedio|avanzado|nativo)\b", text_low)
            if m:
                out[canon] = m.group(1).capitalize()
            elif re.search(rf"\b{re.escape(norm(lname))}\b", listed):
                out.setdefault(canon, "")      # nombrado en la seccion «Idiomas», sin nivel: no se supone ninguno
    return out


# --------------------------------------------------------------------------- #
#  Parser principal
# --------------------------------------------------------------------------- #
_HEADER_LOW_WORDS = ("experiencia", "educacion", "habilidades", "idiomas", "proyectos",
                     "resumen", "perfil", "logros", "cursos", "universidad", "banco",
                     "contacto", "formacion")


def parse_cv(text: str, filename: str = "", nombre_hint: str = "") -> CandidateProfile:
    text = _clean(text or "")
    full_low = norm(text)                     # las herramientas se buscan en todo el CV, empleos incluidos
    blocks = _pipe_blocks(text)
    if blocks:
        text = blocks[1]                      # el resto del CV se lee sin los empleos ya reconocidos
    sections = _split_sections(text)
    text_low = norm(text)

    # --- contacto (excluyendo DNI; preferir + / parentesis) ---
    contact_clean = re.sub(DNI_RE, "", text)
    email = _find(contact_clean, EMAIL_RE)
    phones = PHONE_RE.findall(contact_clean)
    phone = next((p for p in phones if "+" in p or "(" in p), phones[0] if phones else "")
    linkedin = _find(contact_clean, LINKEDIN_RE)

    # --- nombre ---
    name = nombre_hint or ""
    if not name:
        candidates = []
        for line in text.splitlines():
            s = line.strip()
            if 4 <= len(s) <= 60 and re.fullmatch(r"[A-Za-zÁÉÍÓÚÑáéíóúñ .'\-]+", s):
                if not any(v in norm(s) for v in _HEADER_LOW_WORDS):
                    candidates.append(s)
        # a) la linea que mas coincide con el nombre del archivo («CV - Kimi Yi Kudaka 2026.pdf»)
        tokens = {t for t in re.findall(r"[a-z]{2,}", norm(filename.rsplit(".", 1)[0]))
                  if t not in ("cv", "curriculum", "vitae", "resume", "hoja", "vida", "copia", "final", "pdf", "docx")}
        scored = [(len(tokens & set(norm(c).split())), c) for c in candidates]
        best = max(scored, default=(0, ""))
        if best[0] >= 2:
            name = best[1]
        else:
            # b) una linea que parezca nombre: de 2 a 5 palabras, todas con mayuscula, y que no sea un cargo
            proper = [c for c in candidates if 2 <= len(c.split()) <= 5
                      and all(w[0].isupper() or norm(w) in ("de", "del", "la", "los") for w in c.split())
                      and norm(c).split()[0] not in ROLE_WORDS]
            name = (proper or candidates or [""])[0]

    # --- headline (saltar la linea del nombre y headers de seccion) ---
    headline = ""
    for line in text.splitlines():
        s = line.strip()
        if not s or len(s) < 6 or norm(s) == norm(name):
            continue
        low_s = norm(s)
        if any(v in low_s for v in ("experiencia", "educacion", "habilidades", "idiomas",
                                    "proyectos", "resumen", "perfil", "contacto", "logros")):
            continue
        # La linea de contacto suele llevar «|»: no es un titular profesional.
        if EMAIL_RE.search(s) or PHONE_RE.search(s) or re.search(r"(https?://|linkedin\.com|www\.)", low_s):
            continue
        if s.isupper() or "|" in s:
            headline = s
            break

    # --- experiencia + logros fusionados ---
    exp_sec = sections.get("experiencia", "")
    # A missing experience section must not turn projects into employment.
    experiencia = _parse_experience(exp_sec)
    orphan_summary = ""
    if blocks:
        # Lo que queda en «Experiencia» tras sacar los bloques es el parrafo de presentacion.
        orphan_summary = " ".join(l.strip() for l in exp_sec.splitlines()
                                  if len(l.strip()) > 50 or l.strip().endswith("."))
        # En dos columnas los empleos salen en el orden de la pagina; se ordenan del mas reciente al mas antiguo.
        from .cv_answers import parse_month
        experiencia = sorted(blocks[0], key=lambda e: (parse_month(e["fin"]) or (0, 0), parse_month(e["inicio"]) or (0, 0)),
                             reverse=True)
    # Standalone achievements require attribution to an employer by the candidate.

    # --- habilidades / idiomas / educacion / proyectos ---
    skills = parse_skills(sections, full_low)
    languages = parse_languages(sections, text_low)
    educacion = [l.strip() for l in sections.get("educacion", "").splitlines() if len(l.strip()) > 4]
    proyectos = [l.strip() for l in sections.get("proyectos", "").splitlines() if len(l.strip()) > 4]
    summary = " ".join(sections.get("resumen", "").split()) or " ".join(orphan_summary.split())

    # --- ubicacion (sin contar la linea del nombre) ---
    location = ""
    loc_text = text.replace(name, "")
    loc_low = norm(loc_text)
    for c in ["san isidro", "miraflores", "surco", "magdalena", "san miguel", "barranco",
              "santiago de surco", "la molina", "san borja", "monterrico", "cercado de lima",
              "los olivos", "san juan de lurigancho", "ate", "comas", "chorrillos", "jesus maria",
              "pueblo libre", "lince", "breña", "rimac", "independencia", "villa el salvador",
              "trujillo", "arequipa", "chiclayo", "piura", "cusco", "huancayo", "tacna", "iquitos",
              "callao", "lima"]:
        if c in loc_low:
            location = c.title()
            break

    # --- headline alternativo a partir de los cargos ---
    if not headline:
        cargos = [e.get("cargo") for e in experiencia if e.get("cargo")]
        headline = " | ".join(cargos[:3]) if cargos else ""

    return CandidateProfile(
        nombre=name or "Sin identificar",
        email=email, telefono=phone, ubicacion=location, linkedin=linkedin,
        headline=headline, summary=summary,
        experiencia=experiencia,
        skills=skills, languages=languages,
        educacion=educacion, proyectos=proyectos,
        verificado=False, fuente_cv=filename or "CV subido",
        pendientes=["Revisar cargos, fechas y habilidades extraídos del CV"] +
                   (["Atribuir logros a la experiencia correcta: " + sections["logros"][:2000]] if sections.get("logros") else []),
    )
