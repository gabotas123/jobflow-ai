"""Google OAuth and explicit integrations. No secrets in responses or source code."""
import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import Column, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Base, EmailMonitoreado
from .career import profile_row, prefs, AgendaEvent, daily_summary
from .email_monitor import classify_email
router=APIRouter(prefix='/api/google')
SCOPES={'gmail_read':'https://www.googleapis.com/auth/gmail.readonly','gmail_send':'https://www.googleapis.com/auth/gmail.send','calendar':'https://www.googleapis.com/auth/calendar.events.owned'}
class GoogleConnection(Base):
    __tablename__='google_connections'
    id=Column(Integer,primary_key=True)
    profile_id=Column(Integer,index=True)
    service=Column(String)
    encrypted=Column(Text)
    email=Column(String)
    status=Column(String,default='connected')
    __table_args__=(UniqueConstraint('profile_id','service'),)
class OAuthState(Base):
    __tablename__='google_oauth_states'
    state_hash=Column(String,primary_key=True)
    profile_id=Column(Integer)
    service=Column(String)
    expires=Column(Integer)
class Delivery(Base):
    __tablename__='google_deliveries'
    key=Column(String,primary_key=True)
    status=Column(String)
    detail=Column(JSON,default=dict)
class ImportedMessage(Base):
    __tablename__='google_imported_messages'
    key=Column(String,primary_key=True)
    profile_id=Column(Integer,index=True)
    email_id=Column(Integer)

def configured():
    return all(os.getenv(k) for k in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI','JOBFLOW_TOKEN_KEY'))
def cipher():
    try:return Fernet(os.environ['JOBFLOW_TOKEN_KEY'].encode())
    except (KeyError,ValueError):raise HTTPException(503,'La conexión Google necesita configuración del administrador.')
def connection(db,pid,service):
    c=db.query(GoogleConnection).filter_by(profile_id=pid,service=service).first()
    if not c or c.status!='connected':raise HTTPException(409,'Conecta y autoriza Google para esta función.')
    return c

def connection_status(db,pid):
    profile_row(db,pid)
    out={s:{'connected':False,'configured':configured(),'email':''} for s in SCOPES}
    for c in db.query(GoogleConnection).filter_by(profile_id=pid):out[c.service].update(connected=c.status=='connected',email=c.email)
    return out
@router.get('/{pid}/status')
def status(pid:int,db:Session=Depends(get_db)):
    p=prefs(db,pid)
    result={'services':connection_status(db,pid),'scheduler_configured':os.getenv('JOBFLOW_SCHEDULER','false').lower()=='true',
            'last_sync':p.data.get('gmail_last_sync'), 'scheduler_error':p.data.get('scheduler_error','')}
    db.commit()
    return result
@router.post('/{pid}/{service}/connect')
def connect(pid:int,service:str,db:Session=Depends(get_db)):
    profile_row(db,pid)
    if service not in SCOPES:raise HTTPException(404,'Servicio desconocido')
    if not configured():raise HTTPException(503,'Faltan las credenciales OAuth de JobFlow en el servidor. Consulta la guía de despliegue.')
    cipher()
    redirect=os.environ['GOOGLE_REDIRECT_URI']
    if not redirect.startswith(('https://','http://localhost:')):raise HTTPException(503,'La URL de retorno de Google debe utilizar HTTPS.')
    state=secrets.token_urlsafe(32)
    db.add(OAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(),profile_id=pid,service=service,expires=int(time.time())+600));db.commit()
    query=urlencode({'client_id':os.environ['GOOGLE_CLIENT_ID'],'redirect_uri':redirect,'response_type':'code','scope':SCOPES[service]+' https://www.googleapis.com/auth/userinfo.email','access_type':'offline','prompt':'consent','state':state})
    from fastapi.responses import JSONResponse
    response=JSONResponse({'url':'https://accounts.google.com/o/oauth2/v2/auth?'+query})
    response.set_cookie('jobflow_oauth',state,max_age=600,httponly=True,secure=redirect.startswith('https'),samesite='lax',path='/api/google/callback')
    return response

@router.get('/callback')
def callback(request:Request,code:str='',state:str='',error:str='',db:Session=Depends(get_db)):
    cookie=request.cookies.get('jobflow_oauth','')
    if not state or not cookie or not secrets.compare_digest(state,cookie):raise HTTPException(400,'Autorización inválida. Vuelve a conectar Google desde JobFlow.')
    h=hashlib.sha256(state.encode()).hexdigest();s=db.get(OAuthState,h)
    if not s or s.expires<time.time():raise HTTPException(400,'Autorización vencida. Inténtalo de nuevo.')
    pid,service=s.profile_id,s.service
    if db.query(OAuthState).filter_by(state_hash=h).delete()!=1:raise HTTPException(409,'Autorización ya utilizada')
    db.commit()
    if error or not code:raise HTTPException(400,'Google no concedió la autorización.')
    try:
        token=httpx.post('https://oauth2.googleapis.com/token',data={'code':code,'client_id':os.environ['GOOGLE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],'redirect_uri':os.environ['GOOGLE_REDIRECT_URI'],'grant_type':'authorization_code'},timeout=20)
        token.raise_for_status();data=token.json()
        if SCOPES[service] not in data.get('scope','').split():raise HTTPException(403,'No se concedió el permiso solicitado.')
        info=httpx.get('https://www.googleapis.com/oauth2/v2/userinfo',headers={'Authorization':'Bearer '+data['access_token']},timeout=20)
        info.raise_for_status();email=info.json().get('email','')
        if not email:raise HTTPException(403,'No se pudo identificar la cuenta Google')
    except (httpx.HTTPError,KeyError,ValueError):raise HTTPException(502,'No se pudo completar la conexión con Google. Inténtalo nuevamente.')
    c=db.query(GoogleConnection).filter_by(profile_id=pid,service=service).first()
    if not c:c=GoogleConnection(profile_id=pid,service=service);db.add(c)
    data['expires_at']=time.time()+data.get('expires_in',3600)
    c.email=email;c.status='connected';c.encrypted=cipher().encrypt(json.dumps(data).encode()).decode();db.commit()
    response=RedirectResponse('/#connections',status_code=303);response.delete_cookie('jobflow_oauth',path='/api/google/callback');return response

@router.post('/{pid}/{service}/disconnect')
def disconnect(pid:int,service:str,db:Session=Depends(get_db)):
    profile_row(db,pid)
    c=db.query(GoogleConnection).filter_by(profile_id=pid,service=service).first()
    if c:db.delete(c)
    p=prefs(db,pid);flag={'gmail_send':'digest_enabled','gmail_read':'gmail_sync_enabled','calendar':'calendar_auto'}.get(service)
    if flag:p.data={**p.data,flag:False}
    db.commit();return {'disconnected':True,'note':'Permiso local retirado. Puedes revocar el acceso de JobFlow desde tu cuenta Google.'}

def google_request(db,pid,service,method,path,payload=None,params=None):
    c=connection(db,pid,service)
    try:data=json.loads(cipher().decrypt(c.encrypted.encode()))
    except (InvalidToken,ValueError):raise HTTPException(503,'No se pudo abrir la conexión cifrada. Vuelve a conectar la cuenta.')
    if data.get('expires_at',0)<time.time()+60:
        try:
            r=httpx.post('https://oauth2.googleapis.com/token',data={'client_id':os.environ['GOOGLE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],'refresh_token':data.get('refresh_token',''),'grant_type':'refresh_token'},timeout=20)
            r.raise_for_status();data.update(r.json());data['expires_at']=time.time()+data.get('expires_in',3600)
            c.encrypted=cipher().encrypt(json.dumps(data).encode()).decode();db.commit()
        except (httpx.HTTPError,KeyError):
            c.status='reconnect';db.commit();raise HTTPException(409,'La autorización Google venció. Vuelve a conectar.')
    # Paths are generated by this module; external email content is never fetched.
    try:
        r=httpx.request(method,'https://www.googleapis.com/'+path,params=params,json=payload,headers={'Authorization':'Bearer '+data['access_token']},timeout=25)
        r.raise_for_status();return r.json() if r.content else {}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502,{'message':'Google rechazó la operación. Revisa la conexión.','google_status':exc.response.status_code})
    except httpx.HTTPError:raise HTTPException(502,'No se confirmó la respuesta de Google.')

def sync_event(db,e):
    if not e.data.get('confirmed'):raise HTTPException(409,'Confirma la fecha y hora antes de sincronizar.')
    if e.sync_status=='synced':return {'id':e.id,'status':'synced'}
    d=e.data;gid=e.google_id or 'jf'+e.id
    payload={'summary':d['title'],'description':d['source'],'location':d['location'],
             'start':{'dateTime':d['start'],'timeZone':d['timezone']},'end':{'dateTime':d['end'],'timeZone':d['timezone']},
             'reminders':{'useDefault':False,'overrides':[{'method':'popup','minutes':30}]}}
    # Stable Google IDs make an uncertain create retry safe. No attendees/invitations.
    try:
        if e.google_id:result=google_request(db,e.profile_id,'calendar','PATCH','calendar/v3/calendars/primary/events/'+gid,payload,{'sendUpdates':'none'})
        else:
            try:result=google_request(db,e.profile_id,'calendar','POST','calendar/v3/calendars/primary/events',{**payload,'id':gid},{'sendUpdates':'none'})
            except HTTPException as exc:
                if isinstance(exc.detail,dict) and exc.detail.get('google_status')==409:
                    result=google_request(db,e.profile_id,'calendar','PATCH','calendar/v3/calendars/primary/events/'+gid,payload,{'sendUpdates':'none'})
                else:raise
        e.google_id=result['id'];e.sync_status='synced';db.commit()
    except (HTTPException,KeyError):e.sync_status='pendiente';db.commit();raise HTTPException(502,'Evento guardado en JobFlow; la sincronización con Google sigue pendiente.')
    return {'id':e.id,'status':e.sync_status}
@router.post('/events/{eid}/sync')
def event_sync(eid:str,db:Session=Depends(get_db)):
    e=db.get(AgendaEvent,eid)
    if not e:raise HTTPException(404,'Evento no encontrado')
    profile_row(db,e.profile_id)
    return sync_event(db,e)

def plain_parts(payload):
    out=[]
    if payload.get('mimeType')=='text/plain' and payload.get('body',{}).get('data'):
        try:out.append(base64.urlsafe_b64decode(payload['body']['data']+'===').decode(errors='replace'))
        except (ValueError,TypeError):pass
    for p in payload.get('parts',[]):out+=plain_parts(p)
    return out

def sync_gmail(db,pid):
    c=connection(db,pid,'gmail_read')
    listing=google_request(db,pid,'gmail_read','GET','gmail/v1/users/me/messages',params={'q':'newer_than:14d -subject:"JobFlow · Resumen" {entrevista postulación postulacion hiringroom pandape reclutamiento cuestionario}','maxResults':50})
    count=0
    for message in listing.get('messages',[]):
        key=hashlib.sha256(f'{pid}|{c.email}|{message["id"]}'.encode()).hexdigest()
        if db.get(ImportedMessage,key):continue
        data=google_request(db,pid,'gmail_read','GET','gmail/v1/users/me/messages/'+message['id'],params={'format':'full'})
        payload=data.get('payload',{});headers={h['name'].lower():h['value'] for h in payload.get('headers',[])}
        body='\n'.join(plain_parts(payload)) or data.get('snippet','')
        cls=classify_email(headers.get('from',''),headers.get('subject',''),body)
        row=EmailMonitoreado(usuario_id=profile_row(db,pid).usuario_id,remitente=headers.get('from','')[:250],asunto=headers.get('subject','')[:500],cuerpo=body[:40000],clasificacion=cls['clasificacion'],tiene_formulario=cls['tiene_formulario'],estado='pendiente' if cls['clasificacion']=='requiere_accion' else 'archivado')
        db.add(row);db.flush();db.add(ImportedMessage(key=key,profile_id=pid,email_id=row.id))
        try:db.commit();count+=1
        except IntegrityError:db.rollback()
    p=prefs(db,pid);p.data={**p.data,'gmail_last_sync':datetime.now(timezone.utc).isoformat()};db.commit()
    return {'imported':count,'more_available':bool(listing.get('nextPageToken')),'note':'Correos externos sin validar; revisa el contexto antes de actuar.'}
@router.post('/{pid}/gmail/sync')
def gmail_sync(pid:int,db:Session=Depends(get_db)):
    profile_row(db,pid);return sync_gmail(db,pid)

def send_digest(db,pid):
    c=connection(db,pid,'gmail_send');summary=daily_summary(db,pid)
    key=f'digest:{pid}:{summary["date"]}'
    prior=db.get(Delivery,key)
    if prior:return {'status':prior.status,'duplicate':True}
    delivery=Delivery(key=key,status='intento_no_confirmado',detail={});db.add(delivery)
    try:db.commit()
    except IntegrityError:db.rollback();return {'status':'en_proceso','duplicate':True}
    msg=EmailMessage();msg['To']=c.email;msg['Subject']='JobFlow · Resumen '+summary['date']
    counts=summary['counts']
    lines=[f"Postulaciones confirmadas hoy: {counts['confirmed']}",f"Preparadas hoy: {counts['prepared']}",f"Pendientes de revisión: {counts['pending']}",'','Actividad:']
    lines += [f"• {i['company']} — {i['title']}: {i['status']}" for i in summary['activity']]
    lines += ['','Próximos eventos:']+[f"• {e['title']} — {e['start']}" for e in summary['upcoming']]
    msg.set_content('\n'.join(lines));raw=base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        result=google_request(db,pid,'gmail_send','POST','gmail/v1/users/me/messages/send',{'raw':raw})
        if not result.get('id'):raise HTTPException(502,'Envío sin confirmación')
        delivery.status='enviado';delivery.detail={'google_message_id':result['id']};db.commit()
    except HTTPException:
        # Never blindly repeat an uncertain mail send.
        delivery.detail={'error':'Comprueba Enviados en Gmail; no se repetirá automáticamente.'};db.commit();raise
    return {'status':'enviado','recipient':c.email}
@router.post('/{pid}/digest/send')
def digest(pid:int,db:Session=Depends(get_db)):
    profile_row(db,pid);return send_digest(db,pid)

@router.get('/{pid}/mail')
def profile_mail(pid:int,db:Session=Depends(get_db)):
    profile_row(db,pid)
    ids=[r.email_id for r in db.query(ImportedMessage).filter_by(profile_id=pid)]
    return [{'id':r.id,'from':r.remitente,'subject':r.asunto,'body':r.cuerpo,'status':r.estado} for r in db.query(EmailMonitoreado).filter(EmailMonitoreado.id.in_(ids)).order_by(EmailMonitoreado.id.desc())]
