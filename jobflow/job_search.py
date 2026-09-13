"""Busqueda de empleo en Bumeran, Computrabajo y LinkedIn (paginas publicas).

  * Bumeran: API publica de avisos (incluye descripcion completa y modalidad).
  * Computrabajo: tarjetas del listado publico.
  * LinkedIn: listado publico de empleos (sin sesion; LinkedIn no se automatiza).
  * Indeed bloquea la lectura automatica: solo se entrega el enlace de busqueda.

Cada resultado se evalua con el perfil confirmado. Ningun resultado se inventa:
si un portal no responde, se informa y se ofrece el enlace original.
"""
from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from datetime import date, timedelta
from typing import Dict, List

from .job_extract import ExtractionError, bumeran_search, fetch_public, from_bumeran, html_to_text, job_postings, from_posting
from .workflow import norm

PLATFORMS = {
    "bumeran": {"nombre": "Bumeran", "modo": "postulacion_automatica"},
    "computrabajo": {"nombre": "Computrabajo", "modo": "postulacion_automatica"},
    "linkedin": {"nombre": "LinkedIn", "modo": "copiloto"},
    "indeed": {"nombre": "Indeed", "modo": "enlace"},
}


def slugify(s: str) -> str:
    return "-".join(re.sub(r"[^a-z0-9 ]", " ", norm(s)).split())[:60]


def search_url(platform: str, query: str, location: str = "") -> str:
    loc = (location or "Lima").split(",")[0].strip()
    q = urllib.parse.quote(query)
    if platform == "bumeran":
        return f"https://www.bumeran.com.pe/empleos-busqueda-{slugify(query)}.html"
    if platform == "computrabajo":
        return f"https://pe.computrabajo.com/trabajo-de-{slugify(query)}-en-{slugify(loc)}"
    if platform == "linkedin":
        return f"https://pe.linkedin.com/jobs/search?keywords={q}&location={urllib.parse.quote(loc)}"
    if platform == "indeed":
        return f"https://pe.indeed.com/jobs?q={q}&l={urllib.parse.quote(loc)}"
    return ""


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def relative_date(label: str):
    low = norm(label)
    if re.search(r"hora|minuto|hoy|segundo", low):
        return date.today().isoformat()
    if "ayer" in low:
        return (date.today() - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*(dia|semana|mes)", low)
    if m:
        days = int(m.group(1)) * {"dia": 1, "semana": 7, "mes": 30}[m.group(2)]
        return (date.today() - timedelta(days=days)).isoformat()
    return None


# --------------------------------------------------------------------------- #
#  Lectores por portal
# --------------------------------------------------------------------------- #
def parse_computrabajo(page: str) -> List[dict]:
    out = []
    for card in re.findall(r'<article[^>]*class="[^"]*box_offer[^"]*"[^>]*>(.*?)</article>', page, re.S):
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"#]+)[^"]*"[^>]*>(.*?)</a>', card, re.S)
        if not link:
            continue
        company = re.search(r'<a[^>]+offer-grid-article-company-url[^>]*>(.*?)</a>', card, re.S) \
            or re.search(r'<p class="dFlex[^"]*"[^>]*>(.*?)</p>', card, re.S)
        paragraphs = re.findall(r'<p class="fs16 fc_base mt5"[^>]*>(.*?)</p>', card, re.S)
        when = re.search(r'<p class="fs13 fc_aux[^"]*"[^>]*>(.*?)</p>', card, re.S)
        out.append({
            "titulo": _text(link.group(2)),
            "empresa": re.sub(r"^\d+[,.]\d\s*", "", _text(company.group(1))) if company else "",
            "ubicacion": _text(paragraphs[-1]) if paragraphs else "",
            "fecha_publicacion": relative_date(_text(when.group(1))) if when else None,
            "url": urllib.parse.urljoin("https://pe.computrabajo.com", link.group(1)),
        })
    return out


def parse_linkedin(page: str) -> List[dict]:
    out = []
    for card in re.split(r'<div class="base-card[^"]*job-search-card', page)[1:]:
        link = re.search(r'class="base-card__full-link[^"]*"[^>]+href="([^"?]+)', card)
        title = re.search(r'base-search-card__title[^>]*>(.*?)</h3>', card, re.S)
        if not link or not title:
            continue
        company = re.search(r'base-search-card__subtitle[^>]*>(.*?)</h4>', card, re.S)
        location = re.search(r'job-search-card__location[^>]*>(.*?)</span>', card, re.S)
        posted = re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})"', card)
        out.append({"titulo": _text(title.group(1)), "empresa": _text(company.group(1)) if company else "",
                    "ubicacion": _text(location.group(1)) if location else "",
                    "fecha_publicacion": posted.group(1) if posted else None,
                    "url": html_lib.unescape(link.group(1))})
    return out


def parse_jsonld(page: str) -> List[dict]:
    return [{**from_posting(p), "url": p.get("url", "")} for p in job_postings(page)]


def fetch_listing(platform: str, query: str, location: str) -> List[dict]:
    if platform == "bumeran":
        loc = norm((location or "Lima").split(",")[0])
        avisos = [from_bumeran(a) for a in bumeran_search(query, 40)]
        local = [a for a in avisos if loc in norm(a["ubicacion"])]
        return local or avisos
    response = fetch_public(search_url(platform, query, location))
    if response.status_code != 200:
        raise ExtractionError("El portal bloqueó la búsqueda automática.")
    if platform == "computrabajo":
        return parse_computrabajo(response.text) or parse_jsonld(response.text)
    if platform == "linkedin":
        return parse_linkedin(response.text)
    raise ExtractionError("Este portal no permite la lectura automática. Abre el enlace de búsqueda.")


# --------------------------------------------------------------------------- #
#  Busqueda principal
# --------------------------------------------------------------------------- #
def build_query(profile) -> str:
    """Consulta a partir del cargo principal del perfil (sin nombres de herramientas)."""
    cargos = [e.get("cargo", "") for e in profile.experiencia if e.get("cargo")]
    if not cargos:
        return "finanzas"
    low = norm(cargos[0])
    low = re.sub(r"\b(practicante|pro|junior|sr|senior|semi|confidencial|bm|latam|norte)\b", "", low)
    words = [w for w in re.sub(r"\s+", " ", low).strip(" -").split() if len(w) > 2]
    return " ".join(words[:5]) or "finanzas"


def search(profile, platform: str, query: str, location: str = "") -> Dict:
    from .workflow import evaluate, safe_url
    entry = {
        "plataforma": platform, "nombre": PLATFORMS.get(platform, {}).get("nombre", platform),
        "modo": PLATFORMS.get(platform, {}).get("modo", ""), "query": query,
        "url": search_url(platform, query, location), "estado": "sin_datos", "resultados": [], "nota": "",
    }
    try:
        jobs = fetch_listing(platform, query, location)
    except ExtractionError as exc:
        entry.update(estado="requiere_navegador", nota=str(exc))
        return entry
    seen, results, excluded = set(), [], 0
    for job in jobs:
        try:
            job["url"] = safe_url(job.get("url", ""))
        except ValueError:
            continue
        key = norm(job.get("titulo", "") + "|" + job.get("empresa", "") + "|" + job.get("ubicacion", ""))
        if not job["url"] or not job.get("titulo") or key in seen:
            continue
        seen.add(key)
        if job.get("descripcion"):
            from .job_extract import enrich
            enrich(job)
        job["plataforma"] = platform
        analysis = evaluate(profile, job)
        if analysis["requisito_excluyente"]:
            excluded += 1
            continue
        results.append({**job, "link": job["url"], "match": analysis["compatibilidad"], "analisis": analysis,
                        "descripcion": (job.get("descripcion") or "")[:600]})
    results.sort(key=lambda r: (r["match"], r.get("fecha_publicacion") or ""), reverse=True)
    entry["resultados"] = results[:15]
    entry["estado"] = "ok" if results else "sin_resultados"
    entry["nota"] = (f"{len(results)} vacantes compatibles" + (f"; {excluded} descartadas por nivel, funciones o requisitos." if excluded else ".")
                     if results else "No hubo vacantes compatibles en esta búsqueda." + (f" Se descartaron {excluded}." if excluded else ""))
    return entry


def search_all(profile, platforms: List[str], location: str = "", query=None) -> List[Dict]:
    from concurrent.futures import ThreadPoolExecutor
    query = query or build_query(profile)
    with ThreadPoolExecutor(max_workers=min(4, len(platforms) or 1)) as pool:
        return list(pool.map(lambda p: search(profile, p, query, location), platforms))
