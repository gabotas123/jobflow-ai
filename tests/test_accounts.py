import os
import tempfile
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + tempfile.mkdtemp() + '/accounts-test.db')
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from jobflow import accounts
from jobflow.db import SessionLocal
from jobflow.main import app
from jobflow.models import CandidateProfileRow, Usuario


def new_account(client, name='persona'):
    username = f'{name}-{uuid.uuid4().hex[:8]}'
    r = client.post('/api/auth/register', json={'username': username, 'password': 'una-clave-segura', 'nombre': name.title()})
    assert r.status_code == 201, r.text
    return username


def upload(client, text='MARIA TORRES\nEducación\nBachiller en Contabilidad\nHabilidades\nExcel'):
    r = client.post('/api/cv/upload', files={'file': ('cv.txt', text, 'text/plain')})
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_api_requires_session():
    with TestClient(app) as c:
        assert c.get('/api/profiles').status_code == 401
        assert c.get('/api/auth/me').status_code == 401
        assert c.get('/healthz').status_code == 200
        assert c.get('/').status_code == 200


def test_register_login_logout_and_hashed_password():
    with TestClient(app) as c:
        username = new_account(c)
        assert c.get('/api/auth/me').json()['username'] == username
        db = SessionLocal()
        stored = db.query(Usuario).filter_by(username=username).first().password_hash
        db.close()
        assert stored.startswith('scrypt$') and 'una-clave-segura' not in stored
        assert c.post('/api/auth/logout').status_code == 200
        assert c.get('/api/profiles').status_code == 401
        assert c.post('/api/auth/login', json={'username': username, 'password': 'otra-clave'}).status_code == 401
        r = c.post('/api/auth/login', json={'username': username.upper(), 'password': 'una-clave-segura'})
        assert r.status_code == 200 and c.get('/api/profiles').status_code == 200
        assert c.post('/api/auth/register', json={'username': username, 'password': 'una-clave-segura'}).status_code == 409


def test_registration_validation_and_lockout(monkeypatch):
    with TestClient(app) as c:
        assert c.post('/api/auth/register', json={'username': 'ab', 'password': 'una-clave-segura'}).status_code == 422
        assert c.post('/api/auth/register', json={'username': 'con espacio', 'password': 'una-clave-segura'}).status_code == 422
        assert c.post('/api/auth/register', json={'username': 'corta', 'password': '1234567'}).status_code == 422
        username = new_account(c, 'bloqueo')
        for _ in range(accounts.MAX_FAILURES):
            assert c.post('/api/auth/login', json={'username': username, 'password': 'incorrecta'}).status_code == 401
        assert c.post('/api/auth/login', json={'username': username, 'password': 'una-clave-segura'}).status_code == 429


def test_accounts_are_isolated():
    with TestClient(app) as a, TestClient(app) as b:
        new_account(a, 'ana')
        new_account(b, 'beto')
        pid = upload(a)
        assert [p['id'] for p in a.get('/api/profiles').json()] == [pid]
        assert b.get('/api/profiles').json() == []
        aid = a.post('/api/jobs/import', json={'profile_id': pid, 'empresa': 'Empresa', 'titulo': 'Analista',
                                               'url': f'https://example.com/aislado/{pid}'}).json()['id']
        for path in (f'/api/profiles/{pid}', f'/api/career/profiles/{pid}/setup', f'/api/career/profiles/{pid}/summary',
                     f'/api/portals/{pid}', f'/api/cv/{pid}/download', f'/api/portals/applications/{aid}/runs',
                     f'/api/career/applications/{aid}/cvs'):
            assert b.get(path).status_code == 404, path
        assert b.get(f'/api/applications?profile_id={pid}').json() == []
        assert b.patch(f'/api/profiles/{pid}', json={'nombre': 'Intruso'}).status_code == 404
        assert b.patch(f'/api/applications/{aid}', json={'estado': 'vencida'}).status_code == 404
        assert b.post('/api/jobs/import', json={'profile_id': pid, 'empresa': 'Otra empresa', 'titulo': 'Analista',
                                              'url': f'https://example.com/intruso/{pid}'}).status_code == 404
        assert b.post(f'/api/portals/{pid}/bumeran/disconnect').status_code == 404
        assert a.get(f'/api/profiles/{pid}').json()['nombre'] != 'Intruso'


def test_new_cv_updates_active_profile_instead_of_duplicating():
    with TestClient(app) as a, TestClient(app) as b:
        new_account(a, 'recarga')
        pid = upload(a)
        h = a.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
        assert a.post(f'/api/career/profiles/{pid}/confirm', json={'profile_hash': h, 'accepted': True}).status_code == 200
        r = a.post('/api/cv/upload', data={'profile_id': str(pid)},
                   files={'file': ('cv-2026.txt', 'MARIA TORRES\nEducación\nMaestría en Finanzas\nHabilidades\nPower BI', 'text/plain')})
        assert r.status_code == 201, r.text
        assert r.json()['id'] == pid and r.json()['actualizado']
        assert [p['id'] for p in a.get('/api/profiles').json()] == [pid]
        detail = a.get(f'/api/profiles/{pid}').json()
        assert detail['fuente_cv'] == 'cv-2026.txt' and 'Power BI' in detail['texto_extraido']
        assert not a.get(f'/api/career/profiles/{pid}/setup').json()['confirmed']
        new_account(b, 'ajena')
        foreign = b.post('/api/cv/upload', data={'profile_id': str(pid)}, files={'file': ('x.txt', 'OTRA PERSONA\nExcel', 'text/plain')})
        assert foreign.status_code == 404
        assert a.get(f'/api/profiles/{pid}').json()['fuente_cv'] == 'cv-2026.txt'


def test_profile_limit_per_account(monkeypatch):
    monkeypatch.setattr(accounts, 'MAX_PROFILES', 3)
    with TestClient(app) as c:
        new_account(c, 'limite')
        assert c.get('/api/auth/me').json()['max_profiles'] == 3
        pids = [upload(c) for _ in range(3)]
        fourth = c.post('/api/cv/upload', files={'file': ('cv.txt', 'OTRA\nExcel', 'text/plain')})
        assert fourth.status_code == 409 and 'Borra' in fourth.json()['detail']
        assert len(c.get('/api/profiles').json()) == 3
        update = c.post('/api/cv/upload', data={'profile_id': str(pids[0])}, files={'file': ('nuevo.txt', 'OTRA\nExcel', 'text/plain')})
        assert update.status_code == 201, 'updating an existing profile is allowed at the limit'
        db = SessionLocal()
        db.add(CandidateProfileRow(usuario_id=None, nombre='Anterior', fuente_cv='a.pdf', estructura={}))
        db.commit()
        legacy = db.query(CandidateProfileRow).filter_by(nombre='Anterior', usuario_id=None).first().id
        db.close()
        assert c.post('/api/account/claim', json={'profile_ids': [legacy]}).status_code == 409
        assert c.delete(f'/api/profiles/{pids[1]}').status_code == 200
        assert c.post('/api/account/claim', json={'profile_ids': [legacy]}).json()['claimed'] == 1
        assert c.delete(f'/api/profiles/{legacy}').status_code == 200
        assert upload(c) not in pids
        assert len(c.get('/api/profiles').json()) == 3


def test_delete_profile_removes_everything_it_owns():
    from jobflow import portal_accounts as portals
    from jobflow.career import AgendaEvent, CVVersion, Preferences
    from jobflow.config import settings
    from jobflow.models import Postulacion, PuestoObjetivo
    from jobflow.workflow import ApplicationDetail, AuditEvent
    with TestClient(app) as a, TestClient(app) as b:
        new_account(a, 'borrar')
        new_account(b, 'vecina')
        pid, keep = upload(a), upload(a)
        other = upload(b)
        aid = a.post('/api/jobs/import', json={'profile_id': pid, 'empresa': 'Empresa', 'titulo': 'Analista',
                                               'url': f'https://example.com/borrar/{pid}'}).json()['id']
        shot = portals.evidence_dir() / f'captura-borrar-{pid}.png'
        shot.write_bytes(b'png')
        browser_dir = Path(settings.data_dir).resolve() / 'navegador' / f'perfil_{pid}'
        browser_dir.mkdir(parents=True, exist_ok=True)
        db = SessionLocal()
        db.add(CVVersion(application_id=aid, snapshot={'approved': False}))
        db.add(AgendaEvent(profile_id=pid, application_id=aid, fingerprint=f'borrar-{pid}', data={}))
        db.add(PuestoObjetivo(profile_id=pid, titulo='Analista'))
        db.add(portals.PortalAccount(profile_id=pid, portal='bumeran', encrypted='x', status='connected'))
        db.add(portals.AutoApplyRun(application_id=aid, profile_id=pid, portal='bumeran', status='postulada', detail={'captura': shot.name}))
        db.commit()
        db.close()
        a.get(f'/api/career/profiles/{pid}/setup')  # creates preferences

        assert b.delete(f'/api/profiles/{pid}').status_code == 404
        r = a.delete(f'/api/profiles/{pid}')
        assert r.status_code == 200 and r.json()['postulaciones'] == 1
        assert [p['id'] for p in a.get('/api/profiles').json()] == [keep]
        assert b.get(f'/api/profiles/{other}').status_code == 200
        db = SessionLocal()
        assert db.get(CandidateProfileRow, pid) is None
        assert not db.query(Postulacion).filter_by(profile_id=pid).count()
        for model in (AuditEvent, ApplicationDetail, CVVersion, portals.AutoApplyRun):
            assert not db.query(model).filter_by(application_id=aid).count(), model
        for model in (AgendaEvent, PuestoObjetivo, portals.PortalAccount, Preferences):
            assert not db.query(model).filter_by(profile_id=pid).count(), model
        db.close()
        assert not shot.exists() and not browser_dir.exists()
        assert a.delete(f'/api/profiles/{pid}').status_code == 404


def test_claim_profiles_created_before_accounts():
    db = SessionLocal()
    legacy = CandidateProfileRow(usuario_id=None, nombre='Perfil anterior', fuente_cv='cv.pdf', estructura={'nombre': 'Perfil anterior'})
    db.add(legacy)
    db.commit()
    pid = legacy.id
    db.close()
    with TestClient(app) as a, TestClient(app) as b:
        new_account(a, 'duena')
        new_account(b, 'otra')
        assert pid in [p['id'] for p in b.get('/api/account/unclaimed').json()]
        assert a.post('/api/account/claim', json={'profile_ids': [pid]}).json()['claimed'] == 1
        assert pid in [p['id'] for p in a.get('/api/profiles').json()]
        assert pid not in [p['id'] for p in b.get('/api/account/unclaimed').json()]
        assert b.post('/api/account/claim', json={'profile_ids': [pid]}).json()['claimed'] == 0
        assert b.get(f'/api/profiles/{pid}').status_code == 404
