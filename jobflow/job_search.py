"""Busqueda de empleo en Bumeran, Computrabajo, LinkedIn e Indeed.

Estrategia honesta y robusta:
  1) Se construye la URL de busqueda directa por plataforma (siempre utilizable).
  2) Intento de captura con Playwright (navegador real Chromium + User-Agent).
  3) Si la plataforma bloquea (403 / captcha / authwall), se reporta el estado y
     se devuelve el enlace directo: la busqueda real se hace en el navegador del
     usuario, donde tiene su sesion (LinkedIn especialmente: el bot no automatiza
     su busqueda por ToS).

Extraccion de resultados: JSON-LD (JobPosting) cuando existe + regex por
plataforma. Ningun resultado se inventa: si no se puede confirmar, no se lista.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

PLATFORMS = {
    "bumeran": {"nombre": "Bumeran", "modo": "autofill"},
    "computrabajo": {"nombre": "Computrabajo", "modo": "autofill"},
    "linkedin": {"nombre": "LinkedIn", "modo": "copiloto"},
    "indeed": {"nombre": "Indeed", "modo": "busqueda"},
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def slugify(s: str) -> str:
    return "-".join(_norm(s).split())[:60]


def search_url(platform: str, query: str, location: str = "") -> str:
    loc = location or "Lima"
    q = urllib.parse.quote(query)
    if platform == "bumeran":
        return f"https://www.bumeran.com.pe/empleos-{slugify(query)}-{slugify(loc)}.html"
    if platform == "computrabajo":
        return f"https://www.computrabajo.com.pe/trabajo-de-{slugify(query)}"
    if platform == "linkedin":
        return f"https://pe.linkedin.com/jobs/search?keywords={q}&location={urllib.parse.quote(loc)}"
    if platform == "indeed":
        return f"https://pe.indeed.com/jobs?q={q}&l={urllib.parse.quote(loc)}"
    return ""


def fetch_http(url: str, timeout: int = 10) -> Optional[str]:
    """Intento simple (urllib + UA). None si falla."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_playwright(url: str, timeout: int = 20) -> Optional[dict]:
    """Captura con Playwright (chromium headless): html + tarjetas extraidas del DOM.

    Devuelve None si playwright no esta instalado o falla. Las tarjetas se
    extraen con JS en el navegador (post-render), por lo que funciona en
    sitios SPA (Bumeran, Indeed) y en SSR.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, locale="es-PE")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            extracted = page.evaluate(
                """() => {
                    const out = [];
                    const seen = new Set();
                    const isJob = (href) => /(empleos-[^"]*\\d|trabajo-[^"]*\\d|\\/viewjob|\\/rc\\/clk|\\/jobs\\/view\\/)/i.test(href);
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    for (const a of anchors) {
                        const href = a.href || '';
                        if (!isJob(href)) continue;
                        const t = (a.textContent || '').trim();
                        if (t.length >= 8 && t.length <= 140 && !seen.has(t)) {
                            seen.add(t);
                            const card = a.closest('article, li, div[data-testid], .job, .card');
                            const txt = card ? (card.textContent || '') : '';
                            const companyMatch = txt.replace(t, '').match(/[A-ZÁÉÍÓÚÑ][^\\n|]{3,40}/);
                            out.push({title: t, link: href,
                                      company: companyMatch ? companyMatch[0].trim() : ''});
                        }
                    }
                    return out.slice(0, 20);
                }"""
            )
            html = page.content()
            browser.close()
            return {"html": html, "extracted": extracted or []}
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Parseo de resultados
# --------------------------------------------------------------------------- #
def _ld_jobs(html: str) -> List[dict]:
    """Busca bloques application/ld+json del tipo JobPosting."""
    jobs: List[dict] = []
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict) or it.get("@type") not in ("JobPosting", "JobPosting".lower()):
                continue
            title = (it.get("title") or "").strip()
            company = ""
            org = it.get("hiringOrganization")
            if isinstance(org, dict):
                company = (org.get("name") or "").strip()
            location = it.get("jobLocation")
            if isinstance(location, list):
                location = location[0] if location else None
            loc_txt = ""
            if isinstance(location, dict):
                addr = location.get("address", {})
                if isinstance(addr, dict):
                    loc_txt = " ".join(str(a) for a in [addr.get("addressLocality"),
                                                        addr.get("addressRegion")] if a)
            url = (it.get("url") or "").strip()
            if title:
                jobs.append({"title": title, "company": company, "location": loc_txt, "link": url})
    return jobs


def _regex_jobs(html: str, platform: str) -> List[dict]:
    """Heuristicas por plataforma cuando no hay JSON-LD."""
    jobs: List[dict] = []
    if platform == "computrabajo":
        for m in re.finditer(
                r'href="(/trabajo-[^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>.*?'
                r'(?:<span class="[^"]*company[^"]*"[^>]*>(.*?)</span>)?', html, re.S):
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            company = re.sub(r"<[^>]+>", "", m.group(3) or "").strip() if m.group(3) else ""
            if title:
                jobs.append({"title": title, "company": company, "location": "", "link": m.group(1)})
    if platform == "indeed":
        for m in re.finditer(r'href="(/viewjob\?[^"]+)"[^>]*>(?:<[^>]+>)*([^<]{3,90})<', html, re.S):
            title = m.group(2).strip()
            if title:
                jobs.append({"title": title, "company": "", "location": "", "link": m.group(1)})
    return jobs


def parse_results(html: str, platform: str, base_url: str) -> List[dict]:
    jobs = _ld_jobs(html) or _regex_jobs(html, platform)
    out, seen = [], set()
    for j in jobs:
        key = _norm(j["title"] + "|" + j.get("company", ""))
        if key in seen:
            continue
        seen.add(key)
        link = j.get("link", "")
        if link.startswith("/"):
            link = base_url.rstrip("/") + link
        out.append({"titulo": j.get("title"), "empresa": j.get("company") or "—",
                    "ubicacion": j.get("location") or "—", "link": link})
    return out[:15]


# --------------------------------------------------------------------------- #
#  Busqueda principal
# --------------------------------------------------------------------------- #
def build_query(profile) -> str:
    """Construye la consulta de busqueda a partir del cargo principal del perfil.

    Ej.: 'Analista de Créditos BM' -> 'analista de creditos'.
    Evita contaminar la busqueda con nombres de herramientas.
    """
    cargos = [e.get("cargo", "") for e in profile.experiencia if e.get("cargo")]
    if not cargos:
        return "finanzas"
    cargo = cargos[0]
    low = _norm(cargo)
    low = re.sub(r"\b(practicante|pro|junior|sr|senior|semi|confidencial|bm|latam|norte)\b", "", low)
    low = re.sub(r"\s+", " ", low).strip(" -")
    words = low.split()
    # descartar siglas/abreviaturas cortas y quedar con el rol principal
    clean = [w for w in words if len(w) > 2]
    query = " ".join(clean[:5])
    return query or "finanzas"


def quick_match(profile, result: dict) -> int:
    """Affinidad rapida %: tokens del perfil (skills + headline + cargo) vs resultado."""
    profile_tokens = set()
    for kw in [s for s, _ in profile.skills] + [_norm(profile.headline or "")] + \
              [_norm(e.get("cargo", "")) for e in profile.experiencia[:2]]:
        profile_tokens.update(t for t in _norm(kw).split() if len(t) > 3)
    text = _norm(f"{result['titulo']} {result['empresa']} {result['ubicacion']}")
    hits = sum(1 for t in profile_tokens if t in text)
    if not profile_tokens:
        return 0
    return min(95, 40 + int(hits / len(profile_tokens) * 60))


def search(profile, platform: str, query: str, location: str = "") -> Dict:
    url = search_url(platform, query, location)
    entry = {
        "plataforma": platform, "nombre": PLATFORMS.get(platform, {}).get("nombre", platform),
        "modo": PLATFORMS.get(platform, {}).get("modo", ""), "query": query,
        "url": url, "estado": "sin_datos", "resultados": [], "nota": "",
    }
    html = fetch_http(url)
    extracted: List[dict] = []
    if html and ("Security Check" in html or len(re.sub(r"<[^>]+>", "", html).strip()) < 60):
        html = None  # contenido anti-bot: intentar navegador
    pw = fetch_playwright(url)
    if pw:
        html = pw.get("html") or html
        extracted = pw.get("extracted") or []
    if not html:
        entry["estado"] = "protegida"
        entry["nota"] = ("El sitio bloqueo la captura automatizada. Abre el enlace de busqueda "
                         "en tu navegador (con tu sesion) para ver las vacantes reales.")
        return entry
    if "Security Check" in html or len(re.sub(r"<[^>]+>", "", html).strip()) < 60:
        entry["estado"] = "protegida"
        entry["nota"] = "Verificacion anti-bot detectada. Usa el enlace de busqueda en tu navegador."
        return entry

    results = parse_results(html, platform, url)
    for x in extracted:  # tarjetas del DOM (post render JS)
        if not x.get("title"):
            continue
        results.append({"titulo": x["title"], "empresa": x.get("company") or "—",
                        "ubicacion": "—", "link": x.get("link", "")})
    seen: set = set()
    deduped = []
    for r in results:
        k = _norm(r["titulo"] + "|" + r.get("empresa", ""))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    results = deduped[:15]
    if not results:
        entry["estado"] = "requiere_navegador"
        entry["nota"] = "No se extrajeron tarjetas de esta pagina. Abre el enlace en tu navegador."
        return entry
    for r in results:
        r["match"] = quick_match(profile, r)
    results.sort(key=lambda r: r["match"], reverse=True)
    entry["estado"] = "ok"
    entry["resultados"] = results
    return entry


def search_all(profile, platforms: List[str], location: str = "") -> List[Dict]:
    query = build_query(profile)
    return [search(profile, p, query, location) for p in platforms]
