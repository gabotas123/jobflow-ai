"""Referencia de sueldos para un puesto, con datos publicos y su fuente a la vista.

Dos fuentes, ninguna inventada:
  1. La pagina de salarios de Computrabajo Peru para el puesto: sueldo medio, rango, numero de
     datos y promedio por empresa, de los ultimos 12 meses (segun el propio portal).
  2. Los avisos vigentes que publican su sueldo: lo que se ofrece hoy, con enlace al aviso.

Si una fuente no responde o no tiene el puesto, se dice; nunca se rellena con una estimacion propia.
"""
from __future__ import annotations

import html as html_lib
import re
import statistics
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .career import prefs, profile_row
from .db import get_db
from .job_extract import ExtractionError, fetch_public
from .job_search import fetch_listing, slugify

router = APIRouter(prefix='/api/salaries')

SOURCE = "https://pe.computrabajo.com/salarios/"
TTL = 6 * 3600                      # los promedios cambian poco: no hace falta pedirlos en cada visita
_CACHE: dict = {}
MONEY = re.compile(r"S/\.?\s*([\d.]+)(?:,\d+)?")
ROW = 'class="dFlex w100 mt30 bClick"'


def money(text: str):
    """«S/. 1.815» o «S/. 2.500,00» -> 1815 / 2500. None si no hay cifra."""
    m = MONEY.search(text or "")
    if not m:
        return None
    digits = m.group(1).replace(".", "")
    return int(digits) if digits.isdigit() else None


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _count(fragment: str):
    m = re.search(r'<span class="fc_aux">\s*([\d.]+)\s*salario', fragment)
    return int(m.group(1).replace(".", "")) if m else None


def _range(fragment: str):
    m = re.search(r'class="dFlex tj_fx fs12 fc_aux mt5">\s*<p>(.*?)</p>\s*<p>(.*?)</p>', fragment, re.S)
    return (money(m.group(1)), money(m.group(2))) if m else (None, None)


def _rows(block: str) -> list:
    out = []
    for row in block.split(ROW)[1:]:
        name = re.search(r'<a class="fc_base"[^>]*>(.*?)</a>', row, re.S)
        average = re.search(r'<p class="fwB fs18">(.*?)</p>', row, re.S)
        if not name or not average or money(average.group(1)) is None:
            continue
        low, high = _range(row)
        out.append({"nombre": _text(name.group(1)), "media": money(average.group(1)),
                    "datos": _count(row), "minimo": low, "maximo": high})
    return out


def _related(block: str) -> list:
    """Los puestos parecidos usan otro marcado que las empresas."""
    out = []
    for row in block.split("bClick h_min_72")[1:]:
        name = re.search(r'<a href="[^"]*/salarios/[^"]*"[^>]*>(.*?)</a>', row, re.S)
        average = re.search(r'<p class="fw_b fs18">(.*?)</p>', row, re.S)
        if not name or not average or money(average.group(1)) is None:
            continue
        count = re.search(r">\s*([\d.]+)\s*salarios?\s*</span>", row)
        limits = [money(x) for x in re.findall(r"<p>\s*(S/[^<]+)</p>", row)]
        out.append({"nombre": _text(name.group(1)), "media": money(average.group(1)),
                    "datos": int(count.group(1).replace(".", "")) if count else None,
                    "minimo": limits[-2] if len(limits) >= 2 else None,
                    "maximo": limits[-1] if len(limits) >= 2 else None})
    return out


def parse_salary_page(page: str) -> dict:
    """Lee la pagina de salarios de un puesto. Devuelve {} si no trae un sueldo medio."""
    head = re.search(r'<p class="fwB fs33">(.*?)</p>', page, re.S)
    if not head or money(head.group(1)) is None:
        return {}
    related_at, companies_at = page.find("Salarios relacionados"), page.find("Empresas populares")
    top = page[head.start(): min(x for x in (related_at, companies_at, len(page)) if x > 0)]
    low, high = _range(top)
    related = page[related_at: companies_at if companies_at > related_at else len(page)] if related_at > 0 else ""
    companies = page[companies_at:] if companies_at > 0 else ""
    return {"media": money(head.group(1)), "datos": _count(top), "minimo": low, "maximo": high,
            "empresas": _rows(companies)[:12], "relacionados": _related(related)[:8]}


def market(title: str) -> dict:
    """Promedio del mercado para un puesto, con cache en memoria."""
    slug = slugify(title)
    if not slug:
        return {}
    hit = _CACHE.get(slug)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        response = fetch_public(SOURCE + slug)
        data = parse_salary_page(response.text) if response.status_code == 200 else {}
    except (ExtractionError, ValueError):
        data = {}
    if data:
        data["url"] = SOURCE + slug
        _CACHE[slug] = (time.time(), data)
    return data


def postings(title: str, location: str) -> list:
    """Avisos vigentes del puesto que publican sueldo mensual."""
    try:
        jobs = fetch_listing("computrabajo", title, location)
    except ExtractionError:
        return []
    out = [{"titulo": j["titulo"], "empresa": j.get("empresa") or "Empresa no indicada",
            "sueldo": j["sueldo_publicado"], "url": j["url"], "publicado": j.get("fecha_publicacion")}
           for j in jobs if j.get("sueldo_publicado") and 500 <= j["sueldo_publicado"] <= 60000]
    return sorted(out, key=lambda j: -j["sueldo"])[:15]


def expectation(text: str, data: dict) -> dict:
    """Donde cae la expectativa declarada frente al promedio. Solo compara: no aconseja una cifra."""
    numbers = [int(n.replace(".", "").replace(",", "")) for n in re.findall(r"\d[\d.,]{2,}", text or "")]
    numbers = [n for n in numbers if 500 <= n <= 60000]
    if not numbers or not data.get("media"):
        return {}
    mine, average = round(sum(numbers[:2]) / len(numbers[:2])), data["media"]
    diff = round(100 * (mine - average) / average)
    if data.get("maximo") and mine > data["maximo"]:
        note = "Está por encima del máximo registrado para este puesto: pocos avisos la cubrirán."
    elif data.get("minimo") and mine < data["minimo"]:
        note = "Está por debajo del mínimo registrado: podrías estar pidiendo menos de lo que se paga."
    elif abs(diff) <= 10:
        note = "Está en línea con el promedio del mercado."
    else:
        note = f"Está {abs(diff)} % por {'encima' if diff > 0 else 'debajo'} del promedio del mercado."
    return {"declarada": text, "valor": mine, "diferencia_pct": diff, "nota": note}


@router.get('/{pid}')
def salaries(pid: int, puesto: str = "", db: Session = Depends(get_db)):
    row = profile_row(db, pid)
    goals = (prefs(db, pid).data or {}).get("goals") or {}
    titles = [t for t in goals.get("titles") or [] if t]
    title = " ".join((puesto or (titles[0] if titles else "")).split())[:120]
    if not title:
        raise HTTPException(409, "Elige primero los puestos a los que deseas postular.")
    data = market(title)
    live = postings(title, goals.get("location") or "Lima")
    amounts = [j["sueldo"] for j in live]
    return {
        "puesto": title, "puestos": titles,
        "mercado": data,
        "avisos": live,
        "avisos_resumen": {"cantidad": len(amounts), "mediana": round(statistics.median(amounts)),
                           "minimo": min(amounts), "maximo": max(amounts)} if amounts else {},
        "expectativa": expectation(goals.get("salary", ""), data),
        "fuente": {"nombre": "Computrabajo Perú", "url": data.get("url", SOURCE),
                   "nota": "Promedios estimados por Computrabajo con datos de empresas, usuarios y empleados de los "
                           "últimos 12 meses. Los avisos son los vigentes hoy que publican su sueldo."},
    }
