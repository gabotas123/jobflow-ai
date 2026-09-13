"""Additive career workspace: explicit goals, immutable CVs, contacts and agenda."""
import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone, date
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Session
from .models import Base, CandidateProfileRow, PuestoObjetivo, Postulacion, Vacante
from .db import get_db
from .seed import profile_from_row
from .workflow import AuditEvent, norm, safe_url
from .cv_generator import render_cv_html, render_latex, build_docx
router = APIRouter(prefix='/api/career')

class Preferences(Base):
    __tablename__ = 'career_preferences'
    profile_id = Column(Integer, ForeignKey('candidate_profiles.id'), primary_key=True)
    data = Column(JSON, default=dict)
class CVVersion(Base):
    __tablename__ = 'career_cv_versions'
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey('postulaciones.id'), index=True)
    snapshot = Column(JSON)
    created = Column(DateTime, default=datetime.utcnow)
class AgendaEvent(Base):
    __tablename__ = 'career_events'
    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    profile_id = Column(Integer, ForeignKey('candidate_profiles.id'), index=True)
    application_id = Column(Integer, ForeignKey('postulaciones.id'), nullable=True)
    fingerprint = Column(String, unique=True)
    data = Column(JSON)
    google_id = Column(String, default='')
    sync_status = Column(String, default='local')
    created = Column(DateTime, default=datetime.utcnow)
class Recruiter(Base):
    __tablename__ = 'career_recruiters'
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey('postulaciones.id'), index=True)
    data = Column(JSON)

def profile_row(db, pid):
    row=db.get(CandidateProfileRow,pid)
    if not row:raise HTTPException(404,'Perfil no encontrado')
    return row

def prefs(db,pid):
    profile_row(db,pid)
    row=db.get(Preferences,pid)
    if not row:
        row=Preferences(profile_id=pid,data={});db.add(row);db.flush()
    return row

def profile_hash(row):
    data=copy.deepcopy(row.estructura or {})
    for k in ('verificado','hechos_confirmados'):data.pop(k,None)
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def is_confirmed(db,row):
    p=db.get(Preferences,row.id)
    return bool(p and p.data.get('confirmed_hash')==profile_hash(row))

def require_ready(db,pid):
    row=profile_row(db,pid)
    if not is_confirmed(db,row):raise HTTPException(409,'Revisa y confirma los datos de tu CV antes de continuar.')
    if not prefs(db,pid).data.get('goals_confirmed'):raise HTTPException(409,'Elige y guarda los puestos a los que deseas postular.')
    return row

def application(db,aid):
    a=db.get(Postulacion,aid)
    if not a:raise HTTPException(404,'Candidatura no encontrada')
    return a,db.get(Vacante,a.vacante_id)

DEFAULT_SETTINGS={'timezone':'America/Lima','digest_time':'21:00','digest_enabled':False,'gmail_sync_enabled':False,'calendar_auto':False,'theme':'light'}
class Confirmation(BaseModel):
    profile_hash:str
    accepted:bool
@router.get('/profiles/{pid}/setup')
def setup(pid:int,db:Session=Depends(get_db)):
    row=profile_row(db,pid);p=prefs(db,pid);data=dict(p.data);db.commit()
    return {'confirmed':is_confirmed(db,row),'profile_hash':profile_hash(row),'goals_confirmed':data.get('goals_confirmed',False),'settings':{k:data.get(k,v) for k,v in DEFAULT_SETTINGS.items()}}
@router.post('/profiles/{pid}/confirm')
def confirm(pid:int,req:Confirmation,db:Session=Depends(get_db)):
    row=profile_row(db,pid)
    if not req.accepted or req.profile_hash!=profile_hash(row):raise HTTPException(409,'Los datos cambiaron o falta tu confirmación. Revisa el perfil actualizado.')
    if not row.nombre.strip():raise HTTPException(422,'Completa tu nombre antes de confirmar.')
    p=prefs(db,pid);p.data={**p.data,'confirmed_hash':profile_hash(row),'confirmed_at':datetime.now(timezone.utc).isoformat()}
    data=dict(row.estructura);data['verificado']=True
    from .answer_generator import build_answers
    bank=build_answers(profile_from_row(row))
    data['hechos_confirmados']={k:'Confirmado por el candidato; no verificación documental externa' for k,v in bank.items() if v['answer'] and k not in ('motivo_interes','cargo_deseado','salario_pretendido')}
    if data.get('rango_salarial'):
        data['hechos_confirmados']['salario_pretendido']='Pretensión declarada y confirmada por el candidato'
    row.estructura=data;db.commit();return {'confirmed':True}

class Goals(BaseModel):
    titles:list[str]=Field(min_length=1,max_length=8)
    location:str=Field(min_length=2,max_length=200)
    modality:str=Field(min_length=2,max_length=100)
    salary:str=Field(default='',max_length=100)
    seniority:Literal['asistente','analista_junior','analista']='analista_junior'
    restrictions:str=Field(default='',max_length=2000)
    @field_validator('titles')
    @classmethod
    def titles_valid(cls,values):
        values=list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if not values or any(len(v)<2 or len(v)>200 for v in values):raise ValueError('Indica puestos válidos, uno por línea')
        return values
@router.put('/profiles/{pid}/goals')
def goals(pid:int,req:Goals,db:Session=Depends(get_db)):
    row=profile_row(db,pid)
    if not is_confirmed(db,row):raise HTTPException(409,'Confirma primero los datos de tu CV.')
    db.query(PuestoObjetivo).filter_by(profile_id=pid).delete()
    for i,title in enumerate(req.titles):
        db.add(PuestoObjetivo(profile_id=pid,titulo=title,ubicacion=req.location,modality=req.modality,rango_salarial=req.salary,seniority=req.seniority,activo=i==0,must_haves=[],nice_to_haves=[]))
    p=prefs(db,pid);p.data={**p.data,'goals_confirmed':True,'goals':req.model_dump()};db.commit();return req.model_dump()
@router.get('/profiles/{pid}/goals')
def get_goals(pid:int,db:Session=Depends(get_db)):
    p=prefs(db,pid);data=p.data.get('goals',{});db.commit();return data

@router.post('/applications/{aid}/cv')
def adapt_cv(aid:int,db:Session=Depends(get_db)):
    a,job=application(db,aid);row=require_ready(db,a.profile_id)
    if a.estado in ('incompatible','pendiente_revision_duplicado','vencida','rechazada'):raise HTTPException(409,'Revisa la candidatura antes de adaptar su CV.')
    if db.query(AuditEvent).filter_by(application_id=aid,action='postulada').first():raise HTTPException(409,'Esta candidatura ya fue enviada. Sus versiones se conservan en el historial.')
    source=profile_from_row(row).to_dict();result=copy.deepcopy(source)
    tokens=set(re.findall(r'[a-z]{4,}',norm(job.titulo+' '+(job.descripcion or ''))))-{'para','como','esta','tiene','empresa','experiencia','puesto','trabajo'}
    score=lambda s:len(tokens.intersection(re.findall(r'[a-z]{4,}',norm(s))))
    changes=[]
    for exp in result['experiencia']:
        before=list(exp.get('bullets',[]));after=sorted(before,key=lambda b:-score(b));exp['bullets']=after
        if before!=after:changes.append({'campo':exp.get('empresa','Experiencia'),'antes':'\n'.join(before),'despues':'\n'.join(after),'motivo':'Funciones existentes ordenadas según los requisitos de esta vacante.'})
    result['skills']=sorted(result['skills'],key=lambda s:-score(s[0]))
    if result['skills']!=source['skills']:changes.append({'campo':'Herramientas','antes':', '.join(s[0] for s in source['skills']),'despues':', '.join(s[0] for s in result['skills']),'motivo':'Prioridad según las herramientas del anuncio.'})
    matching=[b for e in result['experiencia'] for b in e.get('bullets',[]) if score(b)]
    if matching:
        summary='Experiencia relevante: '+' '.join(sorted(matching,key=lambda b:-score(b))[:2])
        changes.append({'campo':'Resumen','antes':source.get('summary',''),'despues':summary,'motivo':'Resumen extractivo: solo funciones del perfil confirmado.'});result['summary']=summary
    snapshot={'empresa':job.empresa,'puesto':job.titulo,'source':source,'cv':result,'changes':changes,'profile_hash':profile_hash(row),'job_description':job.descripcion,'approved':False}
    v=CVVersion(application_id=aid,snapshot=snapshot);db.add(v);db.flush()
    db.add(AuditEvent(application_id=aid,action='cv_adaptado',payload={'version_id':v.id,'empresa':job.empresa,'puesto':job.titulo}));db.commit();return version_data(v)

def version_data(v):
    s=v.snapshot
    return {'id':v.id,'application_id':v.application_id,'created':v.created.isoformat(),'empresa':s['empresa'],'puesto':s['puesto'],'changes':s['changes'],'approved':s.get('approved',False),'original_html':render_cv_html(s['source']),'cv_html':render_cv_html(s['cv'])}
@router.get('/applications/{aid}/cvs')
def versions(aid:int,db:Session=Depends(get_db)):
    application(db,aid)
    return [version_data(v) for v in db.query(CVVersion).filter_by(application_id=aid).order_by(CVVersion.id.desc())]
@router.post('/cv/{vid}/approve')
def approve_cv(vid:int,db:Session=Depends(get_db)):
    v=db.get(CVVersion,vid)
    if not v:raise HTTPException(404,'Versión no encontrada')
    a,_=application(db,v.application_id);row=require_ready(db,a.profile_id)
    if v.snapshot['profile_hash']!=profile_hash(row):raise HTTPException(409,'Tu perfil cambió. Genera una nueva adaptación.')
    if not v.snapshot.get('approved'):
        v.snapshot={**v.snapshot,'approved':True,'approved_at':datetime.now(timezone.utc).isoformat()}
        db.add(AuditEvent(application_id=a.id,action='cv_aprobado',payload={'version_id':vid}));db.commit()
    return {'approved':True,'id':vid}
@router.get('/cv/{vid}/download')
def download_cv(vid:int,format:Literal['latex','docx']='latex',db:Session=Depends(get_db)):
    v=db.get(CVVersion,vid)
    if not v:raise HTTPException(404,'Versión no encontrada')
    content=iter([render_latex(v.snapshot['cv']).encode()]) if format=='latex' else build_docx(v.snapshot['cv'])
    ext='tex' if format=='latex' else 'docx'
    return StreamingResponse(content,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="JobFlow_CV_{vid}.{ext}"'})

class ContactInput(BaseModel):
    name:str=Field(min_length=2,max_length=200)
    role:str=Field(default='',max_length=200)
    education:str=Field(default='',max_length=1000)
    experience:str=Field(default='',max_length=2000)
    source_url:str=Field(min_length=8,max_length=2000)
    relationship:Literal['posible_contacto','responsable_identificado']='posible_contacto'
    evidence:str=Field(default='',max_length=2000)
    @field_validator('source_url')
    @classmethod
    def valid_url(cls,v):
        if not v.startswith('https://'):raise ValueError('Usa una fuente pública HTTPS')
        return safe_url(v)
    @model_validator(mode='after')
    def responsibility(self):
        if self.relationship=='responsable_identificado' and not self.evidence.strip():raise ValueError('Indica evidencia de que gestiona esta vacante')
        return self
@router.get('/applications/{aid}/recruiters')
def recruiters(aid:int,db:Session=Depends(get_db)):
    _,j=application(db,aid)
    q=quote(f'"{j.empresa}" (reclutamiento OR "talent acquisition" OR "recursos humanos") site:linkedin.com/in/')
    return {'search_url':'https://www.google.com/search?q='+q,'mode':'busqueda_asistida','contacts':[{'id':c.id,**c.data} for c in db.query(Recruiter).filter_by(application_id=aid)]}
@router.post('/applications/{aid}/recruiters',status_code=201)
def add_recruiter(aid:int,req:ContactInput,db:Session=Depends(get_db)):
    application(db,aid)
    data={**req.model_dump(),'checked_at':datetime.now(timezone.utc).isoformat(),'verification':'Registrado por el usuario; no verificación automática'}
    for old in db.query(Recruiter).filter_by(application_id=aid):
        if old.data['source_url']==data['source_url']:old.data=data;db.commit();return {'id':old.id,**data}
    c=Recruiter(application_id=aid,data=data);db.add(c);db.commit();return {'id':c.id,**data}

class SettingsInput(BaseModel):
    timezone:str='America/Lima'
    digest_time:str=Field(default='21:00',pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    digest_enabled:bool=False
    gmail_sync_enabled:bool=False
    calendar_auto:bool=False
    theme:Literal['light','dark','system']='light'
    @field_validator('timezone')
    @classmethod
    def timezone_valid(cls,v):
        try:ZoneInfo(v)
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('Zona horaria inválida')
        return v
@router.put('/profiles/{pid}/settings')
def save_settings(pid:int,req:SettingsInput,db:Session=Depends(get_db)):
    p=prefs(db,pid)
    from .google_integration import connection_status
    s=connection_status(db,pid)
    for flag,service in [('digest_enabled','gmail_send'),('gmail_sync_enabled','gmail_read'),('calendar_auto','calendar')]:
        if getattr(req,flag) and not s[service]['connected']:raise HTTPException(409,'Conecta y autoriza primero '+service)
    p.data={**p.data,**req.model_dump()};db.commit();return req.model_dump()

class EventInput(BaseModel):
    profile_id:int
    application_id:int|None=None
    title:str=Field(min_length=2,max_length=200)
    start:datetime
    end:datetime
    timezone:str='America/Lima'
    kind:Literal['entrevista','evaluacion','seguimiento']='entrevista'
    confirmed:bool=False
    source:str=Field(min_length=2,max_length=3000)
    location:str=Field(default='',max_length=1000)
    @model_validator(mode='after')
    def dates(self):
        if not self.start.tzinfo or not self.end.tzinfo:raise ValueError('Incluye la zona horaria en las fechas')
        if self.end<=self.start:raise ValueError('El fin debe ser posterior al inicio')
        try:ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('Zona horaria inválida')
        return self
@router.get('/profiles/{pid}/events')
def events(pid:int,db:Session=Depends(get_db)):
    profile_row(db,pid)
    return sorted([{'id':e.id,**e.data,'sync_status':e.sync_status} for e in db.query(AgendaEvent).filter_by(profile_id=pid)],key=lambda e:e['start'])
def event_key(req):
    return hashlib.sha256(f'{req.profile_id}|{req.application_id}|{norm(req.title)}|{req.start.astimezone(timezone.utc).isoformat()}'.encode()).hexdigest()
@router.post('/events',status_code=201)
def create_event(req:EventInput,db:Session=Depends(get_db)):
    profile_row(db,req.profile_id)
    if req.application_id and application(db,req.application_id)[0].profile_id!=req.profile_id:raise HTTPException(409,'La candidatura pertenece a otro perfil')
    key=event_key(req);old=db.query(AgendaEvent).filter_by(fingerprint=key).first()
    if old:return {'id':old.id,'duplicate':True}
    e=AgendaEvent(profile_id=req.profile_id,application_id=req.application_id,fingerprint=key,data=req.model_dump(mode='json'));db.add(e);db.commit()
    if req.confirmed and prefs(db,req.profile_id).data.get('calendar_auto'):
        from .google_integration import sync_event
        sync_event(db,e)
    return {'id':e.id,'sync_status':e.sync_status}
@router.put('/events/{eid}')
def edit_event(eid:str,req:EventInput,db:Session=Depends(get_db)):
    e=db.get(AgendaEvent,eid)
    if not e or e.profile_id!=req.profile_id:raise HTTPException(404,'Evento no encontrado')
    if req.application_id and application(db,req.application_id)[0].profile_id!=req.profile_id:raise HTTPException(409,'Perfil incorrecto')
    key=event_key(req);other=db.query(AgendaEvent).filter_by(fingerprint=key).first()
    if other and other.id!=eid:raise HTTPException(409,'Ya existe ese evento')
    e.data=req.model_dump(mode='json');e.fingerprint=key;e.sync_status='pendiente';db.commit()
    if req.confirmed and prefs(db,req.profile_id).data.get('calendar_auto'):
        from .google_integration import sync_event
        sync_event(db,e)
    return {'id':e.id,'sync_status':e.sync_status}
@router.get('/events/{eid}/ics')
def event_ics(eid:str,db:Session=Depends(get_db)):
    e=db.get(AgendaEvent,eid)
    if not e:raise HTTPException(404,'Evento no encontrado')
    d=e.data
    escape=lambda s:str(s).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    stamp=lambda s:datetime.fromisoformat(s).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//JobFlow//Agenda//ES','BEGIN:VEVENT',f'UID:{e.id}@jobflow','DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),'DTSTART:'+stamp(d['start']),'DTEND:'+stamp(d['end']),'SUMMARY:'+escape(d['title']),'DESCRIPTION:'+escape(d['source']),'LOCATION:'+escape(d['location']),'STATUS:'+('CONFIRMED' if d['confirmed'] else 'TENTATIVE'),'END:VEVENT','END:VCALENDAR']
    folded=[]
    for line in lines:
        part=''
        for char in line:
            if len((part+char).encode())>73:folded.append(part);part=' '
            part+=char
        folded.append(part)
    return Response('\r\n'.join(folded)+'\r\n',media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="JobFlow-evento.ics"'})

def daily_summary(db,pid,day=None):
    p=prefs(db,pid);tz=ZoneInfo(p.data.get('timezone','America/Lima'));day=day or datetime.now(tz).date()
    start=datetime.combine(day,datetime.min.time(),tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None);end=start+timedelta(days=1)
    apps=db.query(Postulacion).filter_by(profile_id=pid).all();ids=[a.id for a in apps]
    audit=db.query(AuditEvent).filter(AuditEvent.application_id.in_(ids),AuditEvent.created>=start,AuditEvent.created<end).all() if ids else []
    items=[]
    for a in apps:
        j=db.get(Vacante,a.vacante_id);items.append({'id':a.id,'title':j.titulo if j else '','company':j.empresa if j else '','status':a.estado})
    upcoming=[e for e in events(pid,db) if datetime.fromisoformat(e['end'])>datetime.now(timezone.utc)]
    pending=[i for i in items if i['status'] in ('preparada','pendiente_revision_duplicado','bloqueada','intento_no_confirmado')]
    counts={'confirmed':len({e.application_id for e in audit if e.action=='postulada'}),'prepared':len({e.application_id for e in audit if e.action=='preparada'}),'pending':len(pending)}
    return {'date':day.isoformat(),'counts':counts,'activity':[i for i in items if i['id'] in {e.application_id for e in audit}],'pending':pending,'upcoming':upcoming[:5]}
@router.get('/profiles/{pid}/summary')
def summary(pid:int,day:date|None=None,db:Session=Depends(get_db)):
    data=daily_summary(db,pid,day);db.commit();return data
