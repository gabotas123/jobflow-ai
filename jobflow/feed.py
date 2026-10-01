"""Feed diario de empleos del Peru: JobFlow busca solo, puntua y guarda lo nuevo.

Es el equivalente peruano al feed de recomendaciones de los agentes de empleo
de EE.UU.: en vez de que el usuario dispare una busqueda, JobFlow recorre cada
dia sus puestos objetivo en Bumeran, Computrabajo y LinkedIn, descarta lo que ya
vio o ya postulo, y deja una lista puntuada lista para postular en masa.

Nada se inventa: cada fila guarda el enlace original del aviso y el analisis con
el que se calculo su compatibilidad.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from .career import prefs, profile_row, require_ready
from .db import get_db
from .job_search import search
from .models import Base, CandidateProfileRow, Postulacion, PuestoObjetivo, Vacante
from .seed import profile_from_row
from .workflow import norm, register, safe_url

router = APIRouter(prefix='/api/feed')

AUTO_PORTALS = ('bumeran', 'computrabajo', 'linkedin')
MAX_TITLES = 3      # puestos objetivo por actualizacion (cada uno son 3 llamadas a portales)
KEEP_DAYS = 21      # el feed olvida los avisos viejos
PER_QUERY = 12      # avisos guardados por puesto y portal


class FeedJob(Base):
    """Un aviso detectado por la busqueda diaria, con su puntaje y su analisis."""
    __tablename__ = 'feed_jobs'
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey('candidate_profiles.id'), index=True)
    plataforma = Column(String, default='')
    url = Column(String, default='')
    titulo = Column(String, default='')
    empresa = Column(String, default='')
    ubicacion = Column(String, default='')
    modalidad = Column(String, default='')
    descripcion = Column(Text, default='')
    fecha_publicacion = Column(String, default='')
    score = Column(Integer, default=0)
    analisis = Column(JSON, default=dict)
    consulta = Column(String, default='')
    estado = Column(String, default='nuevo')   # nuevo | visto | guardado | descartado
    application_id = Column(Integer, nullable=True)
    detectado = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('profile_id', 'url', name='uq_feed_profile_url'),)


def _row(db, job_id: int, pid: int) -> FeedJob:
    row = db.get(FeedJob, job_id)
    if not row or row.profile_id != pid:
        raise HTTPException(404, 'Ese aviso ya no está en tu feed.')
    return row


def _applied_urls(db, pid: int) -> set:
    """URLs que ya tienen candidatura: no vuelven a aparecer como novedad."""
    pairs = (db.query(Vacante.url).join(Postulacion, Postulacion.vacante_id == Vacante.id)
             .filter(Postulacion.profile_id == pid).all())
    out = set()
    for (url,) in pairs:
        try:
            out.add(safe_url(url or ''))
        except ValueError:
            continue
    return out


def _titles(db, pid: int) -> list:
    saved = [p.titulo for p in db.query(PuestoObjetivo).filter_by(profile_id=pid).all() if p.titulo]
    goals = (prefs(db, pid).data or {}).get('goals') or {}
    titles = list(dict.fromkeys(saved + list(goals.get('titles') or [])))
    return titles[:MAX_TITLES]


def refresh(db, pid: int, platforms=AUTO_PORTALS) -> dict:
    """Corre la busqueda de cada puesto objetivo y guarda lo que todavia no estaba."""
    row = require_ready(db, pid)
    profile = profile_from_row(row)
    goals = (prefs(db, pid).data or {}).get('goals') or {}
    location, level = goals.get('location') or profile.ubicacion or 'Lima', goals.get('seniority')
    titles = _titles(db, pid)
    if not titles:
        raise HTTPException(409, 'Elige y guarda los puestos a los que deseas postular.')
    known = {u for (u,) in db.query(FeedJob.url).filter_by(profile_id=pid).all()}
    known |= _applied_urls(db, pid)
    fresh, errors, seen = [], [], set()
    for title in titles:
        for platform in platforms:
            entry = search(profile, platform, title, location, level)
            if entry['estado'] in ('requiere_navegador', 'sin_datos'):
                errors.append(f"{entry['nombre']}: {entry['nota'] or 'no respondió'}")
                continue
            for job in entry['resultados'][:PER_QUERY]:
                url = job.get('url') or job.get('link') or ''
                if not url or url in known or url in seen:
                    continue
                seen.add(url)
                fresh.append(FeedJob(
                    profile_id=pid, plataforma=job.get('plataforma', platform), url=url,
                    titulo=job.get('titulo', ''), empresa=job.get('empresa', ''),
                    ubicacion=job.get('ubicacion', ''), modalidad=job.get('modalidad', ''),
                    descripcion=(job.get('descripcion') or '')[:4000],
                    fecha_publicacion=job.get('fecha_publicacion') or '',
                    score=int(job.get('match') or 0), analisis=job.get('analisis') or {},
                    consulta=title))
    for item in fresh:
        db.add(item)
    old = datetime.utcnow() - timedelta(days=KEEP_DAYS)
    removed = (db.query(FeedJob).filter(FeedJob.profile_id == pid, FeedJob.detectado < old)
               .filter(FeedJob.estado != 'guardado').delete(synchronize_session=False))
    db.commit()
    return {'nuevos': len(fresh), 'consultas': titles, 'portales': list(platforms),
            'caducados': int(removed or 0), 'notas': errors}


def referral(row: FeedJob, profile) -> dict:
    """Como llegar a alguien de la empresa. Solo enlaces de busqueda y un mensaje redactado:
    JobFlow no lee ni guarda datos de terceros."""
    company = (row.empresa or '').strip()
    if not company:
        return {}
    nombre = (getattr(profile, 'nombre', '') or '').split(' ')[0]
    puesto = row.titulo or 'la vacante'
    mensaje = (f"Hola, soy {nombre or 'un candidato'}. Vi que {company} tiene abierta la posición de "
               f"{puesto} y postulé a través de {row.plataforma.capitalize()}. "
               f"Mi experiencia está en {(getattr(profile, 'resumen', '') or 'el área').split('.')[0][:120].strip() or 'el área'}. "
               "¿Podrías orientarme sobre el proceso o comentarme con quién lo revisa? Gracias por tu tiempo.")
    q = quote_plus(company)
    return {
        'empresa': company,
        'mensaje': mensaje,
        'enlaces': [
            {'nombre': f'Personas de {company} en LinkedIn',
             'url': f'https://www.linkedin.com/search/results/people/?keywords={q}'},
            {'nombre': f'Página de {company} en LinkedIn',
             'url': f'https://www.linkedin.com/company/{quote_plus(norm(company).replace(" ", "-"))}/'},
            {'nombre': f'Otros avisos de {company} en Computrabajo',
             'url': f'https://pe.computrabajo.com/empresas/buscar?q={q}'},
        ],
    }


def item(row: FeedJob, profile=None) -> dict:
    analysis = row.analisis or {}
    parts = analysis.get('componentes') or []
    covered = [p for p in parts if p.get('conocido') and p.get('puntos')]
    return {
        'id': row.id, 'plataforma': row.plataforma, 'url': row.url, 'titulo': row.titulo,
        'empresa': row.empresa, 'ubicacion': row.ubicacion, 'modalidad': row.modalidad,
        'descripcion': (row.descripcion or '')[:600], 'fecha_publicacion': row.fecha_publicacion,
        'score': row.score, 'estado': row.estado, 'application_id': row.application_id,
        'detectado': row.detectado.isoformat() if row.detectado else '',
        'consulta': row.consulta,
        'nivel': analysis.get('nivel_recomendado', ''),
        'cumple': f'{len(covered)} de {len(parts)}' if parts else '',
        'brechas': (analysis.get('brechas') or [])[:4],
        'pendientes': (analysis.get('datos_pendientes') or [])[:4],
        'referidos': referral(row, profile) if profile is not None else {},
    }


@router.get('/{pid}')
def listing(pid: int, estado: str = 'activos', min_score: int = 0, db: Session = Depends(get_db)):
    row = profile_row(db, pid)
    profile = profile_from_row(row)
    query = db.query(FeedJob).filter_by(profile_id=pid)
    if estado == 'activos':
        query = query.filter(FeedJob.estado != 'descartado')
    elif estado != 'todos':
        query = query.filter(FeedJob.estado == estado)
    rows = [r for r in query.order_by(FeedJob.score.desc(), FeedJob.detectado.desc()).all() if r.score >= min_score]
    today = datetime.utcnow().date()
    counts = {'total': len(rows),
              'nuevos': sum(1 for r in rows if r.estado == 'nuevo'),
              'hoy': sum(1 for r in rows if r.detectado and r.detectado.date() == today),
              'guardados': sum(1 for r in rows if r.estado == 'guardado')}
    last = db.query(FeedJob).filter_by(profile_id=pid).order_by(FeedJob.detectado.desc()).first()
    return {'items': [item(r, profile) for r in rows[:120]], 'counts': counts,
            'actualizado': last.detectado.isoformat() if last and last.detectado else '',
            'puestos': _titles(db, pid)}


@router.post('/{pid}/actualizar')
def update(pid: int, db: Session = Depends(get_db)):
    return refresh(db, pid)


class Ids(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=120)


@router.post('/{pid}/descartar')
def dismiss(pid: int, req: Ids, db: Session = Depends(get_db)):
    profile_row(db, pid)
    changed = 0
    for jid in req.ids:
        row = _row(db, jid, pid)
        row.estado = 'descartado'
        changed += 1
    db.commit()
    return {'descartados': changed}


@router.post('/{pid}/vistos')
def mark_seen(pid: int, req: Ids, db: Session = Depends(get_db)):
    profile_row(db, pid)
    for jid in req.ids:
        row = _row(db, jid, pid)
        if row.estado == 'nuevo':
            row.estado = 'visto'
    db.commit()
    return {'ok': True}


@router.post('/{pid}/guardar')
def save(pid: int, req: Ids, db: Session = Depends(get_db)):
    """Crea la candidatura de cada aviso elegido para poder adaptar el CV y postular."""
    row = require_ready(db, pid)
    saved = []
    for jid in req.ids:
        job = _row(db, jid, pid)
        payload = {'plataforma': job.plataforma, 'url': job.url, 'titulo': job.titulo,
                   'empresa': job.empresa, 'ubicacion': job.ubicacion, 'modalidad': job.modalidad,
                   'descripcion': job.descripcion, 'fecha_publicacion': job.fecha_publicacion or None}
        application, existed = register(db, row.usuario_id, pid, payload, job.analisis or {})
        job.estado, job.application_id = 'guardado', application.id
        saved.append({'feed_id': job.id, 'application_id': application.id, 'ya_existia': existed})
    db.commit()
    return {'guardados': saved}
