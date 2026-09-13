import os
import tempfile
os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.mkdtemp()+'/career-test.db')
import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jobflow.main import app
from jobflow.db import SessionLocal
from jobflow.career import CVVersion, AgendaEvent
from jobflow import google_integration as google

@pytest.fixture
def client():
    with TestClient(app) as c:yield c

def candidate(client):
    r=client.post('/api/cv/upload',files={'file':('cv.txt','ANA PEREZ\nEducación\nBachiller en Economía\nHabilidades\nExcel','text/plain')})
    assert r.status_code==201
    pid=r.json()['id']
    data={'nombre':'Ana Pérez','email':'ana@example.com','educacion':['Bachiller en Economía'],
          'experiencia':[{'empresa':'Empresa real','cargo':'Asistente','inicio':'2024-01','fin':'2024-12','bullets':['Atención al cliente.','Análisis de cartera y reportes de cobranzas.']}],
          'skill_levels':[['Excel','avanzado'],['SAP','básico']], 'summary':'Perfil de finanzas'}
    assert client.patch(f'/api/profiles/{pid}',json=data).status_code==200
    return pid

def ready(client,pid):
    h=client.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
    assert client.post(f'/api/career/profiles/{pid}/confirm',json={'profile_hash':h,'accepted':True}).status_code==200
    r=client.put(f'/api/career/profiles/{pid}/goals',json={'titles':['Analista de cobranzas','Analista de costos'],'location':'Lima','modality':'Híbrido'})
    assert r.status_code==200,r.text

def job(client,pid):
    return client.post('/api/jobs/import',json={'profile_id':pid,'empresa':'Empresa destino','titulo':'Analista de cobranzas','descripcion':'Análisis de cartera con Excel.','url':'https://example.com/job/'+str(pid)}).json()['id']

def test_onboarding_and_target_search(client,monkeypatch):
    pid=candidate(client)
    assert client.get(f'/api/profiles/{pid}/puestos').json()==[]
    assert client.post('/api/jobs/search',json={'profile_id':pid}).status_code==409
    assert client.put(f'/api/career/profiles/{pid}/goals',json={'titles':['Analista'],'location':'Lima','modality':'Remoto'}).status_code==409
    ready(client,pid)
    targets=client.get(f'/api/profiles/{pid}/puestos').json()
    calls=[]
    monkeypatch.setattr('jobflow.main.search_all',lambda p,platforms,location,query: calls.append(query) or [])
    assert client.post('/api/jobs/search',json={'profile_id':pid,'target_id':targets[1]['id']}).status_code==200
    assert calls==['Analista de costos']
    client.patch(f'/api/profiles/{pid}',json={'nombre':'Ana Actualizada'})
    assert not client.get(f'/api/career/profiles/{pid}/setup').json()['confirmed']
    assert client.post('/api/jobs/search',json={'profile_id':pid}).status_code==409

def test_confirmation_rejects_stale_hash(client):
    pid=candidate(client);h=client.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
    client.patch(f'/api/profiles/{pid}',json={'summary':'Resumen corregido'})
    assert client.post(f'/api/career/profiles/{pid}/confirm',json={'profile_hash':h,'accepted':True}).status_code==409

def test_cv_source_preserved_and_version_immutable(client):
    pid=candidate(client);ready(client,pid);aid=job(client,pid)
    before=client.get(f'/api/profiles/{pid}').json()
    r=client.post(f'/api/career/applications/{aid}/cv');assert r.status_code==200,r.text
    vid=r.json()['id']
    assert client.get(f'/api/profiles/{pid}').json()==before
    with SessionLocal() as db:
        s=db.get(CVVersion,vid).snapshot
        assert s['cv']['experiencia'][0]['cargo']=='Asistente'
        assert set(s['cv']['experiencia'][0]['bullets'])==set(s['source']['experiencia'][0]['bullets'])
        assert s['cv']['skills']==s['source']['skills']
    tex=client.get(f'/api/career/cv/{vid}/download').content
    client.patch(f'/api/profiles/{pid}',json={'nombre':'Nombre nuevo'})
    ready(client,pid)
    assert client.post(f'/api/career/cv/{vid}/approve').status_code==409
    assert client.get(f'/api/career/cv/{vid}/download').content==tex

def event_data(pid,aid=None):
    start=datetime.now(timezone.utc)+timedelta(days=1)
    return {'profile_id':pid,'application_id':aid,'title':'Entrevista','start':start.isoformat(),'end':(start+timedelta(hours=1)).isoformat(),'source':'Correo del reclutador','confirmed':True}

def test_event_dedup_scope_timezone_and_export(client):
    pid=candidate(client);other=candidate(client);aid=job(client,other)
    data=event_data(pid,aid)
    assert client.post('/api/career/events',json=data).status_code==409
    data['application_id']=None
    first=client.post('/api/career/events',json=data);assert first.status_code==201,first.text
    eid=first.json()['id']
    assert client.post('/api/career/events',json=data).json()['duplicate']
    assert 'BEGIN:VEVENT' in client.get(f'/api/career/events/{eid}/ics').text
    data['end']=data['start'];assert client.post('/api/career/events',json=data).status_code==422
    data=event_data(pid);data['start']='2026-09-15T10:00:00'
    assert client.post('/api/career/events',json=data).status_code==422

def test_google_not_configured_and_no_fake_connection(client,monkeypatch):
    monkeypatch.delenv('GOOGLE_CLIENT_ID',raising=False);pid=candidate(client)
    assert not client.get(f'/api/google/{pid}/status').json()['services']['calendar']['connected']
    assert client.post(f'/api/google/{pid}/calendar/connect').status_code==503
    assert client.put(f'/api/career/profiles/{pid}/settings',json={'digest_enabled':True}).status_code==409
    assert client.get('/api/google/callback?state=bad&code=bad').status_code==400

def test_recruiter_responsibility_requires_evidence(client):
    pid=candidate(client);aid=job(client,pid)
    data={'name':'Contacto público','source_url':'https://example.com/contact','relationship':'responsable_identificado'}
    assert client.post(f'/api/career/applications/{aid}/recruiters',json=data).status_code==422
    data['relationship']='posible_contacto'
    assert client.post(f'/api/career/applications/{aid}/recruiters',json=data).status_code==201
    assert 'busqueda_asistida'==client.get(f'/api/career/applications/{aid}/recruiters').json()['mode']

def test_calendar_uncertain_create_retry_reuses_id(client,monkeypatch):
    pid=candidate(client);eid=client.post('/api/career/events',json=event_data(pid)).json()['id'];calls=[]
    def fake(db,pid,service,method,path,payload=None,params=None):
        calls.append((method,payload))
        if len(calls)==1:raise HTTPException(502,'timeout')
        if method=='POST':raise HTTPException(502,{'google_status':409})
        return {'id':'jf'+eid}
    monkeypatch.setattr(google,'google_request',fake)
    assert client.post(f'/api/google/events/{eid}/sync').status_code==502
    assert client.post(f'/api/google/events/{eid}/sync').status_code==200
    assert calls[0][1]['id']==calls[1][1]['id']=='jf'+eid
    assert calls[2][0]=='PATCH'
    assert 'attendees' not in calls[0][1]

def test_digest_uncertain_send_not_repeated(client,monkeypatch):
    pid=candidate(client)
    with SessionLocal() as db:
        db.add(google.GoogleConnection(profile_id=pid,service='gmail_send',encrypted='test',email='self@example.com',status='connected'));db.commit()
    calls=[]
    def fake(*args,**kwargs):calls.append(1);raise HTTPException(502,'timeout')
    monkeypatch.setattr(google,'google_request',fake)
    assert client.post(f'/api/google/{pid}/digest/send').status_code==502
    second=client.post(f'/api/google/{pid}/digest/send')
    assert second.json()['duplicate'] and second.json()['status']=='intento_no_confirmado'
    assert len(calls)==1

def test_summary_counts_evidence_not_opened_jobs(client):
    pid=candidate(client);ready(client,pid);aid=job(client,pid)
    assert client.get(f'/api/career/profiles/{pid}/summary').json()['counts']['confirmed']==0
    client.patch(f'/api/applications/{aid}',json={'estado':'postulada','tipo_evidencia':'id_candidatura','evidencia':'DEMO-TEST'})
    assert client.get(f'/api/career/profiles/{pid}/summary').json()['counts']['confirmed']==1

def test_confirmation_does_not_verify_inferred_salary(client):
    pid=candidate(client);ready(client,pid)
    data=client.get(f'/api/profiles/{pid}').json()
    assert 'salario_pretendido' not in data['hechos_confirmados']

def test_approved_cv_bound_to_preparation_and_evidence(client):
    pid=candidate(client);ready(client,pid);aid=job(client,pid)
    vid=client.post(f'/api/career/applications/{aid}/cv').json()['id']
    assert client.post(f'/api/career/cv/{vid}/approve').status_code==200
    assert client.post(f'/api/applications/{aid}/prepare',json={'profile_id':pid,'form_schema':[{'id':'a','label':'Disponibilidad'}]}).status_code==200
    a=next(a for a in client.get('/api/applications').json() if a['id']==aid)
    assert a['auditoria'][-1]['datos']['cv_version_id']==vid
    assert client.patch(f'/api/applications/{aid}',json={'estado':'postulada','tipo_evidencia':'id_candidatura','evidencia':'TEST-CV','cv_version_id':vid}).status_code==200
    assert client.post(f'/api/career/applications/{aid}/cv').status_code==409

def test_google_oauth_state_and_encrypted_token(client,monkeypatch):
    from cryptography.fernet import Fernet
    from urllib.parse import urlparse,parse_qs
    import httpx
    pid=candidate(client)
    for k,v in {'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret','GOOGLE_REDIRECT_URI':'http://localhost:8000/api/google/callback','JOBFLOW_TOKEN_KEY':Fernet.generate_key().decode()}.items():monkeypatch.setenv(k,v)
    start=client.post(f'/api/google/{pid}/calendar/connect');assert start.status_code==200
    state=parse_qs(urlparse(start.json()['url']).query)['state'][0]
    def token(*args,**kwargs):return httpx.Response(200,json={'access_token':'sensitive-test-token','refresh_token':'sensitive-refresh','scope':google.SCOPES['calendar'],'expires_in':3600},request=httpx.Request('POST',args[0]))
    def identity(*args,**kwargs):return httpx.Response(200,json={'email':'ana@example.com'},request=httpx.Request('GET',args[0]))
    monkeypatch.setattr(google.httpx,'post',token);monkeypatch.setattr(google.httpx,'get',identity)
    assert client.get('/api/google/callback',params={'state':state,'code':'test-code'},follow_redirects=False).status_code==303
    assert client.get(f'/api/google/{pid}/status').json()['services']['calendar']['connected']
    with SessionLocal() as db:
        row=db.query(google.GoogleConnection).filter_by(profile_id=pid,service='calendar').one()
        assert 'sensitive-test-token' not in row.encrypted
        assert 'sensitive-test-token' in google.cipher().decrypt(row.encrypted.encode()).decode()
    assert client.get('/api/google/callback',params={'state':state,'code':'test-code'}).status_code==400
