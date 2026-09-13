"""Extraccion de avisos laborales desde su enlace publico.

Convierte un anuncio de Bumeran, Computrabajo, LinkedIn u otro portal con datos
estructurados (schema.org JobPosting) en los campos que usa JobFlow para
evaluar la vacante. Solo se leen paginas publicas: nunca se usa la sesion del
candidato. Lo que no aparece en el anuncio queda vacio, nunca se supone.
"""
from __future__ import annotations

import html as html_lib
import ipaddress
import json
import re
import socket
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from .workflow import norm, safe_url

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MAX_BYTES = 4 * 1024 * 1024

TOOLS = [
    "Excel", "Power BI", "Power Query", "Power Pivot", "VBA", "SQL", "Python", "R", "SAP", "Oracle",
    "Dynamics", "Tableau", "Looker", "Qlik", "Google Sheets", "Access", "Outlook", "PowerPoint", "Word",
    "Salesforce", "HubSpot", "CRM", "ERP", "Concar", "Siscont", "Starsoft", "Softland", "Odoo", "Macros",
]


class ExtractionError(ValueError):
    pass


def portal_for(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for key in ("bumeran", "computrabajo", "linkedin", "indeed", "hiringroom", "pandape"):
        if key in host:
            return key
    return "manual"


def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ExtractionError("No se encontró el sitio del enlace. Revisa la dirección.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ExtractionError("Solo se pueden leer anuncios publicados en internet.")


def fetch_public(url: str, *, method: str = "GET", json_body=None, headers=None, timeout: float = 20) -> httpx.Response:
    """Descarga una pagina publica validando cada redireccion (sin redes internas)."""
    current = safe_url(url)
    if not current:
        raise ExtractionError("Pega el enlace completo del aviso.")
    base = {"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9"}
    with httpx.Client(follow_redirects=False, timeout=timeout, headers={**base, **(headers or {})}) as client:
        for _ in range(6):
            parts = urlsplit(current)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise ExtractionError("Usa un enlace HTTP o HTTPS.")
            _public_host(parts.hostname)
            try:
                response = client.request(method, current, json=json_body)
            except httpx.HTTPError:
                raise ExtractionError("El portal no respondió. Inténtalo de nuevo en unos minutos.")
            if response.is_redirect:
                current = urljoin(current, response.headers.get("location", ""))
                method, json_body = "GET", None
                continue
            if len(response.content) > MAX_BYTES:
                raise ExtractionError("La página del aviso es demasiado grande para leerla.")
            return response
    raise ExtractionError("El enlace redirige demasiadas veces.")


# --------------------------------------------------------------------------- #
#  Datos estructurados
# --------------------------------------------------------------------------- #
def html_to_text(value: str) -> str:
    value = html_lib.unescape(html_lib.unescape(value or ""))
    value = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", value)
    value = re.sub(r"(?i)<li[^>]*>", "• ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[ \t\xa0]+", " ", value)
    return re.sub(r"\n\s*\n+", "\n", value).strip()


def job_postings(page_html: str) -> list[dict]:
    """Todos los objetos JobPosting de los bloques JSON-LD (incluye @graph)."""
    found: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = node.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                found.append(node)
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in node:
                    walk(node[key])

    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html, re.S | re.I):
        try:
            walk(json.loads(m.group(1).strip()))
        except ValueError:
            continue
    return found


def _location(posting: dict) -> str:
    loc = posting.get("jobLocation")
    loc = loc[0] if isinstance(loc, list) and loc else loc
    if not isinstance(loc, dict):
        return ""
    addr = loc.get("address")
    if isinstance(addr, str):
        return addr
    if not isinstance(addr, dict):
        return ""
    parts = [addr.get("addressLocality"), addr.get("addressRegion")]
    return ", ".join(dict.fromkeys(str(p).strip() for p in parts if p and str(p).strip()))


def _salary(posting: dict) -> tuple[float | None, float | None]:
    salary = posting.get("baseSalary")
    value = salary.get("value") if isinstance(salary, dict) else None
    if isinstance(value, dict):
        low, high = value.get("minValue"), value.get("maxValue") or value.get("value")
        try:
            return (float(low) if low else None, float(high) if high else None)
        except (TypeError, ValueError):
            return None, None
    return None, None


def from_posting(posting: dict) -> dict:
    org = posting.get("hiringOrganization")
    company = org.get("name", "") if isinstance(org, dict) else (org if isinstance(org, str) else "")
    low, high = _salary(posting)
    published = str(posting.get("datePosted") or "")[:10]
    valid_through = str(posting.get("validThrough") or "")[:10]
    job = {
        "titulo": html_lib.unescape(str(posting.get("title") or "")).strip(),
        "empresa": html_lib.unescape(str(company)).strip(),
        "descripcion": html_to_text(str(posting.get("description") or "")),
        "ubicacion": _location(posting),
        "modalidad": "Remoto" if str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE" else "",
        "fecha_publicacion": published if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published) else None,
        "salario_min": low,
        "salario_max": high,
    }
    try:
        if valid_through and date.fromisoformat(valid_through) < date.today():
            job["vigente"] = False
    except ValueError:
        pass
    return job


# --------------------------------------------------------------------------- #
#  Portales
# --------------------------------------------------------------------------- #
BUMERAN_SEARCH = "https://www.bumeran.com.pe/api/avisos/searchV2"


def bumeran_search(query: str, page_size: int = 20) -> list[dict]:
    response = fetch_public(
        f"{BUMERAN_SEARCH}?pageSize={page_size}&page=0&sort=RELEVANTES", method="POST",
        headers={"x-site-id": "BMPE", "Content-Type": "application/json", "Referer": "https://www.bumeran.com.pe/"},
        json_body={"filtros": [], "busquedaExtendida": False, "tipoDetalle": "full", "withHome": False,
                   "internacional": False, "query": query})
    if response.status_code != 200:
        raise ExtractionError("Bumeran no respondió a la búsqueda.")
    try:
        return response.json().get("content") or []
    except ValueError:
        raise ExtractionError("Bumeran devolvió una respuesta inesperada.")


def from_bumeran(aviso: dict) -> dict:
    fecha = str(aviso.get("fechaPublicacion") or "")
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", fecha)
    job = {
        "titulo": (aviso.get("titulo") or "").strip(),
        "empresa": (aviso.get("empresa") or "").strip(),
        "descripcion": re.sub(r"(?<=[\wáéíóú.)])(?=(?:Requisitos|Funciones|Beneficios|Condiciones|Horario|Ofrecemos)\s*:)", "\n",
                              html_to_text(aviso.get("detalle") or "")),
        "ubicacion": (aviso.get("localizacion") or "").strip(),
        "modalidad": (aviso.get("modalidadTrabajo") or "").strip(),
        "fecha_publicacion": f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None,
        "portal_id": str(aviso.get("id") or ""),
        "tiene_preguntas": bool(aviso.get("tienePreguntas")),
        "salario_obligatorio": bool(aviso.get("salarioObligatorio")),
    }
    if aviso.get("id"):
        slug = re.sub(r"[^a-z0-9]+", "-", norm(job["titulo"])).strip("-")
        job["url"] = f"https://www.bumeran.com.pe/empleos/{slug}-{aviso['id']}.html"
    return job


def extract_bumeran(url: str) -> dict:
    m = re.search(r"/empleos/([a-z0-9-]+?)-(\d{6,})\.html", url)
    if not m:
        raise ExtractionError("No reconozco este enlace de Bumeran. Abre el aviso y copia su dirección.")
    slug, aviso_id = m.group(1), m.group(2)
    words = [w for w in slug.split("-") if len(w) > 2][:6]
    # The slug may end with the company name, which the search does not match.
    queries = dict.fromkeys(" ".join(words[:n]) for n in range(len(words), 0, -1))
    for query in list(queries)[:4]:
        for aviso in bumeran_search(query, 50):
            if str(aviso.get("id")) == aviso_id:
                return {**from_bumeran(aviso), "url": url}
    raise ExtractionError("Bumeran no mostró este aviso públicamente. Puede estar cerrado; revisa el enlace.")


def extract_meta(page_html: str) -> dict:
    """Ultimo recurso: titulo y descripcion de la pagina, sin inventar empresa."""
    def meta(name):
        m = re.search(rf'<meta[^>]+(?:property|name)="{name}"[^>]+content="([^"]*)"', page_html, re.I)
        return html_lib.unescape(m.group(1)).strip() if m else ""
    title = meta("og:title") or html_lib.unescape((re.search(r"<title>(.*?)</title>", page_html, re.S | re.I) or [None, ""])[1]).strip()
    return {"titulo": title[:250], "empresa": "", "descripcion": meta("og:description") or meta("description"),
            "ubicacion": "", "modalidad": "", "fecha_publicacion": None}


# --------------------------------------------------------------------------- #
#  Enriquecimiento desde la descripcion
# --------------------------------------------------------------------------- #
def enrich(job: dict) -> dict:
    text = job.get("descripcion") or ""
    low = norm(text)
    detected = []
    tools = [t for t in TOOLS if re.search(rf"(?<![a-z]){re.escape(norm(t))}(?![a-z])", low)]
    if tools and not job.get("herramientas"):
        job["herramientas"] = tools
        detected.append("herramientas")
    if job.get("anos_obligatorios") is None:
        m = re.search(r"(\d{1,2})\s*(?:a|-|o)?\s*(?:\d{1,2})?\s*anos?\s+(?:de\s+experiencia|en\s+(?:el|la|puestos?|areas?|cargos?|funciones)|como)", low) \
            or re.search(r"experiencia[^.\n]{0,40}?(\d{1,2})\s*anos?", low)
        if m:
            job["anos_obligatorios"] = float(m.group(1))
            detected.append("anos_obligatorios")
    if not job.get("formacion"):
        m = re.search(r"(?:bachiller|titulad[oa]|egresad[oa]|licenciad[oa]|tecnic[oa]|estudiante)[^.\n]{0,120}", text, re.I)
        if m:
            job["formacion"] = m.group(0).strip(" :.-")[:250]
            detected.append("formacion")
    if not job.get("modalidad"):
        for word, label in (("hibrid", "Híbrido"), ("remot", "Remoto"), ("teletrabajo", "Remoto"), ("presencial", "Presencial")):
            if word in low:
                job["modalidad"] = label
                detected.append("modalidad")
                break
    if job.get("salario_max") is None:
        amounts = [float(a.replace(",", "")) for a in re.findall(r"s/\.?\s*(\d{1,3}(?:,\d{3})+|\d{3,6})", low)]
        amounts = [a for a in amounts if 500 <= a <= 50000]
        if amounts:
            job["salario_max"] = max(amounts)
            detected.append("salario_max")
    if re.search(r"(aviso|oferta|convocatoria|proceso)\s+(finalizad|cerrad|vencid)", low):
        job["vigente"] = False
    job["detectados_en_descripcion"] = detected
    return job


def extract_job(url: str) -> dict:
    url = safe_url(url)
    portal = portal_for(url)
    if portal == "bumeran":
        job = extract_bumeran(url)
    else:
        response = fetch_public(url)
        if response.status_code in (404, 410):
            raise ExtractionError("El aviso ya no existe en el portal.")
        if response.status_code != 200:
            raise ExtractionError("El portal bloqueó la lectura automática. Copia la descripción manualmente.")
        page = response.text
        postings = job_postings(page)
        job = from_posting(postings[0]) if postings else extract_meta(page)
        if not postings and portal in ("computrabajo", "linkedin"):
            raise ExtractionError("No se encontró el aviso en esta página. Puede haber sido retirado.")
    job.update(url=url, plataforma=portal)
    job = enrich(job)
    if not job.get("titulo"):
        raise ExtractionError("No se pudo identificar el puesto en esta página.")
    job["fuente"] = f"Leído del anuncio público el {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    job["campos_vacios"] = [k for k in ("empresa", "ubicacion", "modalidad", "fecha_publicacion", "salario_max", "herramientas")
                            if not job.get(k)]
    return job
