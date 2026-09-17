import os
import tempfile
os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.mkdtemp()+'/feed-test.db')
import pytest
from fastapi.testclient import TestClient
from jobflow.main import app
from conftest import sign_in

@pytest.fixture
def client():
    with TestClient(app) as c:yield sign_in(c)

def candidate(client):
    r=client.post('/api/cv/upload',files={'file':('cv.txt','LUIS RAMOS\nEducación\nBachiller en Contabilidad\nHabilidades\nExcel','text/plain')})
    assert r.status_code==201
    pid=r.json()['id']
    data={'nombre':'Luis Ramos','email':'luis@example.com','educacion':['Bachiller en Contabilidad'],
          'experiencia':[{'empresa':'Estudio contable','cargo':'Asistente de cobranzas','inicio':'2023-01','fin':'2024-12',
                          'bullets':['Gestión de cartera de cobranzas.','Conciliaciones y reportes en Excel.']}],
          'skill_levels':[['Excel','avanzado']],'summary':'Cobranzas y control de cartera','ubicacion':'Lima'}
    assert client.patch(f'/api/profiles/{pid}',json=data).status_code==200
    return pid

def ready(client,pid):
    h=client.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
    assert client.post(f'/api/career/profiles/{pid}/confirm',json={'profile_hash':h,'accepted':True}).status_code==200
    assert client.put(f'/api/career/profiles/{pid}/goals',
                      json={'titles':['Analista de cobranzas'],'location':'Lima','modality':'Híbrido'}).status_code==200

def listing(platform,count=2,start=1):
    return {'plataforma':platform,'nombre':platform.capitalize(),'modo':'postulacion_automatica','query':'x',
            'url':'https://example.com/busqueda','estado':'ok','nota':'','resultados':[
                {'titulo':'Analista de cobranzas','empresa':f'Empresa {platform} {n}','ubicacion':'Lima',
                 'modalidad':'Híbrido','fecha_publicacion':'2026-09-15','plataforma':platform,
                 'url':f'https://{platform}.example.com/aviso/{n}','link':f'https://{platform}.example.com/aviso/{n}',
                 'descripcion':'Gestión de cartera con Excel.','match':70+n,
                 'analisis':{'compatibilidad':70+n,'nivel_recomendado':'razonable','brechas':['SAP no declarado'],
                             'datos_pendientes':['Salario'],'componentes':[{'criterio':'Coincidencia funcional','conocido':True,'puntos':30},
                                                                           {'criterio':'Salario','conocido':False,'puntos':0}]}}
                for n in range(start,start+count)]}

@pytest.fixture
def fake_search(monkeypatch):
    calls=[]
    def fake(profile,platform,query,location='',level=None):
        calls.append((platform,query,location,level))
        return listing(platform)
    monkeypatch.setattr('jobflow.feed.search',fake)
    return calls

def test_feed_needs_confirmed_goals(client):
    pid=candidate(client)
    assert client.post(f'/api/feed/{pid}/actualizar').status_code==409

def test_refresh_saves_scored_jobs_once(client,fake_search):
    pid=candidate(client);ready(client,pid)
    r=client.post(f'/api/feed/{pid}/actualizar')
    assert r.status_code==200,r.text
    assert r.json()['nuevos']==6          # 1 puesto x 3 portales x 2 avisos
    assert {c[0] for c in fake_search}=={'bumeran','computrabajo','linkedin'}
    assert all(c[2]=='Lima' for c in fake_search)
    assert client.post(f'/api/feed/{pid}/actualizar').json()['nuevos']==0   # nada se duplica

def test_listing_shows_score_gaps_and_counts(client,fake_search):
    pid=candidate(client);ready(client,pid)
    client.post(f'/api/feed/{pid}/actualizar')
    body=client.get(f'/api/feed/{pid}').json()
    assert body['counts']['total']==6 and body['counts']['nuevos']==6 and body['counts']['hoy']==6
    first=body['items'][0]
    assert first['score']==72 and first['cumple']=='1 de 2'
    assert first['brechas']==['SAP no declarado'] and first['pendientes']==['Salario']
    assert body['items']==sorted(body['items'],key=lambda j:-j['score'])
    assert body['puestos']==['Analista de cobranzas']

def test_dismissed_jobs_leave_the_feed(client,fake_search):
    pid=candidate(client);ready(client,pid)
    client.post(f'/api/feed/{pid}/actualizar')
    ids=[j['id'] for j in client.get(f'/api/feed/{pid}').json()['items'][:2]]
    assert client.post(f'/api/feed/{pid}/descartar',json={'ids':ids}).json()['descartados']==2
    assert client.get(f'/api/feed/{pid}').json()['counts']['total']==4
    assert client.get(f'/api/feed/{pid}',params={'estado':'todos'}).json()['counts']['total']==6

def test_saving_creates_the_application(client,fake_search):
    pid=candidate(client);ready(client,pid)
    client.post(f'/api/feed/{pid}/actualizar')
    job=client.get(f'/api/feed/{pid}').json()['items'][0]
    saved=client.post(f'/api/feed/{pid}/guardar',json={'ids':[job['id']]}).json()['guardados'][0]
    aid=saved['application_id']
    assert saved['ya_existia'] is False
    detail=client.get('/api/applications',params={'profile_id':pid}).json()
    assert any(a['id']==aid for a in detail)
    again=client.get(f'/api/feed/{pid}').json()['items']
    assert next(j for j in again if j['id']==job['id'])['estado']=='guardado'
    # Una vacante ya postulada no reaparece como novedad.
    assert client.post(f'/api/feed/{pid}/actualizar').json()['nuevos']==0

def test_referrals_only_offer_search_links(client,fake_search):
    pid=candidate(client);ready(client,pid)
    client.post(f'/api/feed/{pid}/actualizar')
    ref=client.get(f'/api/feed/{pid}').json()['items'][0]['referidos']
    assert ref['empresa'].startswith('Empresa')
    assert all(l['url'].startswith('https://') for l in ref['enlaces'])
    assert 'Luis' in ref['mensaje'] and ref['empresa'] in ref['mensaje']

def test_feed_is_private_to_its_account(client,fake_search):
    pid=candidate(client);ready(client,pid)
    client.post(f'/api/feed/{pid}/actualizar')
    with TestClient(app) as other:
        other.post('/api/auth/register',json={'username':'intruso-feed','password':'otra-clave-123','nombre':'Intruso'})
        assert other.get(f'/api/feed/{pid}').status_code==404
        assert other.post(f'/api/feed/{pid}/actualizar').status_code==404
