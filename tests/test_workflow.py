import os
import tempfile
from datetime import date

os.environ['DATABASE_URL'] = 'sqlite:///' + tempfile.mkdtemp() + '/test.db'
from fastapi.testclient import TestClient
from jobflow.main import app
from jobflow.profile_models import CandidateProfile
from jobflow.answer_generator import build_answers
from jobflow.knowledge import build_gabriel
from jobflow.workflow import evaluate
import pytest
from conftest import sign_in


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield sign_in(c)


def test_no_language_or_job_title_invention():
    p=CandidateProfile(nombre='Prueba', languages={'portugues':'avanzado'}, experiencia=[{'empresa':'Empresa','bullets':[]}])
    answers=build_answers(p)
    assert 'idioma_ingles' not in answers
    assert 'Analista' not in answers['experiencia_total']['answer']
    assert answers['experiencia_total']['needs_input']
    p.verificado=True
    assert 'Liberty' not in build_answers(p)['experiencia_total']['answer']


def test_seed_has_no_unverified_numbers():
    p=build_gabriel()
    assert not p.verificado
    assert not any('20 %' in b or '300,000' in b or '~15' in b for b in p.all_bullets())
    assert not any('LISA' in e for e in p.educacion)
    assert p.pendientes


def test_scoring_unknowns_and_exclusions():
    p=build_gabriel()
    a=evaluate(p,{'titulo':'Gerente de Finanzas'})
    assert a['requisito_excluyente']
    b=evaluate(p,{'titulo':'Analista de cobranzas'})
    assert b['vigente'] is None
    assert b['cobertura'] < 100
    c=evaluate(p,{'titulo':'Analista', 'anos_obligatorios':3})
    assert c['requisito_excluyente']
    assert evaluate(p,{'titulo':'Astronauta'})['compatibilidad']==0


def test_application_lifecycle_and_duplicate(client):
    profile=client.get('/api/profiles').json()[0]['id']
    data=dict(profile_id=profile,titulo='Analista de Cobranzas',empresa='Empresa Test',
              url='https://example.com/empleos/123?utm_source=mail',ubicacion='Lima',
              herramientas=['Excel'],fecha_publicacion=str(date.today()))
    r=client.post('/api/jobs/import',json=data)
    assert r.status_code==201, r.text
    aid=r.json()['id']
    data['url']='https://example.com/empleos/123?utm_source=another'
    duplicate=client.post('/api/jobs/import',json=data).json()
    assert duplicate['duplicada'] and duplicate['id']==aid
    apps=client.get('/api/applications').json()
    a=next(x for x in apps if x['id']==aid)
    assert a['estado']=='descubierta' and a['fecha'] is None
    assert client.patch(f'/api/applications/{aid}',json={'estado':'postulada'}).status_code==422
    assert client.patch(f'/api/applications/{aid}',json={'estado':'entrevista'}).status_code==409
    r=client.patch(f'/api/applications/{aid}',json={'estado':'postulada','tipo_evidencia':'id_candidatura','evidencia':'TEST-123'})
    assert r.status_code==200
    assert client.patch(f'/api/applications/{aid}',json={'estado':'entrevista','nota':'Confirmación recibida'}).status_code==200
    exported=client.get('/api/tracker/export').json()
    assert next(x for x in exported if x['id']==aid)['auditoria'][-2]['datos']['evidencia']=='TEST-123'


def test_demo_never_creates_application_and_external_send_is_blocked(client):
    before=len(client.get('/api/applications').json())
    schema=[{'id':'q1','label':'Disponibilidad para incorporarte','type':'text'}]
    for platform in ['test','manual','linkedin']:
        r=client.post('/api/form/prepare',json={'platform':platform,'form_schema':schema}).json()
        fid=r['form_id']
        assert client.post(f'/api/form/{fid}/submit').status_code==409
        assert client.post(f'/api/form/{fid}/approve',json={'edits':[{'field_id':'q1','answer':'Inmediata'}]}).status_code==200
        result=client.post(f'/api/form/{fid}/submit')
        if platform=='test':
            assert result.status_code==200 and result.json()['enviado'] is False
            assert client.post(f'/api/form/{fid}/submit').json()['simulado']
        else:
            assert result.status_code==409
    assert len(client.get('/api/applications').json())==before


def test_sensitive_questions_and_unknown_profile(client):
    r=client.post('/api/form/prepare',json={'form_schema':[{'id':'dni','label':'Número de DNI','type':'text'}]}).json()
    assert r['answers'][0]['bloqueada']
    assert client.post(f"/api/form/{r['form_id']}/approve",json={'edits':[{'field_id':'dni','answer':'example'}]}).status_code==409
    assert client.post('/api/jobs/search',json={'profile_id':999999}).status_code==404
    assert client.post('/api/form/prepare',json={'platform':'bumeran'}).status_code==422
    assert client.put('/api/platforms/connections',json={'plataforma':'gmail','conectada':True}).status_code==409


def test_cv_upload_generate_and_exports(client):
    cv='MARIA PEREZ\nEducación\nBachiller en Economía\nExperiencia\nEmpresa Demo\nAsistente de Finanzas\nEnero 2024 - Diciembre 2024\nElaboración de reportes financieros\nHabilidades\nExcel\nIdiomas\nPortugués: Avanzado'
    r=client.post('/api/cv/upload',files={'file':('maria.txt',cv,'text/plain')})
    assert r.status_code==201,r.text
    pid=r.json()['id']
    for variant in ['maestro','cobranzas','gestion','datos']:
        result=client.post('/api/cv/generate',json={'profile_id':pid,'variant':variant})
        assert result.status_code==200,result.text
        assert 'Liberty' not in result.json()['latex']
        assert client.get(result.json()['download_url']).content.startswith(b'PK')
        assert '\\documentclass' in client.get(result.json()['latex_url']).text


def test_import_email_dedup_and_no_fake_resolver(client):
    data={'remitente':'recruiter@example.com','asunto':'Completar cuestionario','cuerpo':'Por favor completar el formulario.'}
    first=client.post('/api/emails/import',json=data)
    assert first.status_code==201
    assert client.post('/api/emails/import',json=data).json()['duplicado']
    assert client.post(f"/api/emails/{first.json()['id']}/resolver").status_code==409


def test_private_deployment_guard(client,monkeypatch):
    monkeypatch.setenv('JOBFLOW_REQUIRE_AUTH','true')
    assert client.get('/api/profiles').status_code==503
    monkeypatch.setenv('JOBFLOW_ACCESS_PASSWORD','test-only-password')
    assert client.get('/api/profiles').status_code==401
    assert client.get('/api/profiles',auth=('jobflow','test-only-password')).status_code==200
    assert client.get('/healthz').status_code==200
    assert client.post('/api/jobs/import',auth=('jobflow','test-only-password'),headers={'origin':'https://evil.example'},json={}).status_code==403


def test_cv_preview_escapes_untrusted_content():
    from jobflow.cv_generator import render_cv_html
    p=CandidateProfile(nombre='<script>alert(1)</script>', languages={'<img src=x onerror=alert(1)>':'alto'})
    html=render_cv_html(p.to_dict())
    assert '<script>' not in html and '<img' not in html
    assert '&lt;script&gt;' in html


def test_required_years_in_description():
    assert evaluate(build_gabriel(), {'titulo':'Analista de Finanzas', 'descripcion':'Mínimo de 5 años de experiencia en el área.'})['requisito_excluyente']


def test_preparation_snapshot_and_cross_portal_review(client):
    profile=client.get('/api/profiles').json()[0]['id']
    data={'profile_id':profile,'titulo':'Analista de Tesorería','empresa':'Empresa Snapshot','url':'https://example.com/jobs/a','ubicacion':'Lima'}
    first=client.post('/api/jobs/import',json=data).json()
    aid=first['id']
    data['url']='https://second.example.com/jobs/b'
    second=client.post('/api/jobs/import',json=data).json()
    assert second['estado']=='pendiente_revision_duplicado'
    assert client.patch(f"/api/applications/{second['id']}",json={'estado':'preparada'}).status_code==409
    assert client.patch(f"/api/applications/{second['id']}",json={'estado':'duplicado_descartado','nota':'IDs de requisición diferentes, revisados en la empresa.'}).status_code==200
    draft=client.post(f'/api/applications/{aid}/prepare',json={'profile_id':profile,'form_schema':[{'id':'q','label':'Disponibilidad','type':'text'}]})
    assert draft.status_code==200,draft.text
    fid=draft.json()['form_id']
    assert client.post(f'/api/form/{fid}/approve',json={'edits':[{'field_id':'q','answer':'Inmediata'}]}).status_code==200
    record=next(x for x in client.get('/api/applications').json() if x['id']==aid)
    assert record['estado']=='preparada' and record['fecha'] is None
    assert record['auditoria'][-1]['accion']=='respuestas_aprobadas'
    assert '\\documentclass' in record['auditoria'][-2]['datos']['cv_latex']


def test_legacy_entries_are_not_resent(client):
    from jobflow.db import SessionLocal
    from jobflow.models import Vacante, Postulacion
    profile=client.get('/api/profiles').json()[0]['id']
    with SessionLocal() as db:
        v=Vacante(titulo='Legacy',empresa='Old Co',url='https://legacy.example.com/job/1?utm_source=old')
        db.add(v);db.flush()
        a=Postulacion(profile_id=profile,vacante_id=v.id,estado='enviado')
        db.add(a);db.commit();aid=a.id
    response=client.post('/api/jobs/import',json={'profile_id':profile,'titulo':'Legacy','empresa':'Old Co','url':'https://legacy.example.com/job/1'}).json()
    assert response['duplicada'] and response['id']==aid


def test_parser_does_not_guess_language_level_or_employment():
    from jobflow.cv_parser import parse_cv, parse_languages
    assert parse_languages({'idiomas':'Inglés'}, 'ingles').get('ingles')==''
    p=parse_cv('MARIA PEREZ\nProyectos\nElaboración de un modelo académico de simulación de riesgo financiero.\nIdiomas\nInglés')
    assert not p.experiencia
