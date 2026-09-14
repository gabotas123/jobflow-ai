import os
import tempfile
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + tempfile.mkdtemp() + '/portals-test.db')
os.environ.setdefault('JOBFLOW_DATA_DIR', tempfile.mkdtemp())
import json
import pytest
from fastapi.testclient import TestClient
from jobflow.main import app
from jobflow.db import SessionLocal
from jobflow import job_extract, job_search
from jobflow import portal_accounts as portals
from jobflow.profile_models import CandidateProfile
from conftest import sign_in


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(portals, 'ensure_worker', lambda: None)
    with TestClient(app) as c:
        yield sign_in(c)


# --------------------------------------------------------------------------- #
#  Extraccion y busqueda (sin red)
# --------------------------------------------------------------------------- #
POSTING_PAGE = '''<script type="application/ld+json">{"@context":"https://schema.org/","@graph":[{"@type":"Organization","name":"Portal"},
{"@type":"JobPosting","title":"Analista de Cobranzas","description":"&lt;p&gt;Bachiller en Economía o Contabilidad.&lt;/p&gt;&lt;p&gt;2 años de experiencia en cobranzas. Excel avanzado y Power BI. Modalidad híbrida. Sueldo S/ 2,800&lt;/p&gt;",
"datePosted":"2026-09-10","validThrough":"2099-01-01","hiringOrganization":{"@type":"Organization","name":"Empresa SAC"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"San Isidro","addressRegion":"Lima"}}}]}</script>'''


def test_jsonld_graph_and_enrichment():
    postings = job_extract.job_postings(POSTING_PAGE)
    assert len(postings) == 1
    job = job_extract.enrich(job_extract.from_posting(postings[0]))
    assert job['titulo'] == 'Analista de Cobranzas' and job['empresa'] == 'Empresa SAC'
    assert job['ubicacion'] == 'San Isidro, Lima' and job['fecha_publicacion'] == '2026-09-10'
    assert job['herramientas'] == ['Excel', 'Power BI']
    assert job['anos_obligatorios'] == 2.0
    assert job['modalidad'] == 'Híbrido' and job['salario_max'] == 2800
    assert 'Economía' in job['formacion']
    assert 'vigente' not in job


def test_extract_endpoint_rejects_internal_addresses(client):
    for url in ('http://127.0.0.1:8000/aviso', 'https://localhost/aviso', 'http://10.0.0.5/x', 'file:///etc/passwd'):
        r = client.post('/api/jobs/extract', json={'url': url})
        assert r.status_code == 422, url


def test_extract_endpoint_uses_structured_data(client, monkeypatch):
    class Page:
        status_code = 200
        text = POSTING_PAGE
    monkeypatch.setattr(job_extract, 'fetch_public', lambda url, **kw: Page())
    r = client.post('/api/jobs/extract', json={'url': 'https://pe.computrabajo.com/ofertas-de-trabajo/oferta-123'})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['plataforma'] == 'computrabajo' and data['empresa'] == 'Empresa SAC'
    assert 'salario_max' not in data['campos_vacios']


def test_listing_parsers():
    ct = '''<article class="box_offer sel" data-id="X"><h2 class="fs18"><a class="js-o-link" href="/ofertas-de-trabajo/oferta-de-analista-X#lc=1">
    Analista de Cobranzas </a></h2><p class="dFlex vm_fx fs16 fc_base mt5"><span class="fwB">4,4</span>
    <a class="fc_base t_ellipsis" href="#" offer-grid-article-company-url>EMPRESA SAC</a></p>
    <p class="fs16 fc_base mt5"><span class="mr10">Lima, Lima</span></p><p class="fs13 fc_aux mt15">Hace 2 días</p></article>'''
    [job] = job_search.parse_computrabajo(ct)
    assert job['titulo'] == 'Analista de Cobranzas' and job['empresa'] == 'EMPRESA SAC' and job['ubicacion'] == 'Lima, Lima'
    assert job['url'] == 'https://pe.computrabajo.com/ofertas-de-trabajo/oferta-de-analista-X' and job['fecha_publicacion']
    li = '''<div class="base-card relative base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:1">
    <a class="base-card__full-link absolute" href="https://pe.linkedin.com/jobs/view/analista-at-aris-1?position=1"></a>
    <h3 class="base-search-card__title"> Analista de cobranzas </h3><h4 class="base-search-card__subtitle"><a>ARIS</a></h4>
    <span class="job-search-card__location">Lima, Perú</span><time class="job-search-card__listdate" datetime="2026-09-03">Hace 1 semana</time></div>'''
    [job] = job_search.parse_linkedin(li)
    assert job == {'titulo': 'Analista de cobranzas', 'empresa': 'ARIS', 'ubicacion': 'Lima, Perú',
                   'fecha_publicacion': '2026-09-03', 'url': 'https://pe.linkedin.com/jobs/view/analista-at-aris-1'}


def test_search_reports_blocked_portal_without_inventing(monkeypatch):
    def blocked(*a, **k):
        raise job_extract.ExtractionError('El portal bloqueó la búsqueda automática.')
    monkeypatch.setattr(job_search, 'fetch_listing', blocked)
    entry = job_search.search(CandidateProfile(nombre='Ana'), 'indeed', 'analista', 'Lima')
    assert entry['estado'] == 'requiere_navegador' and entry['resultados'] == [] and entry['url']


# --------------------------------------------------------------------------- #
#  Plan de llenado
# --------------------------------------------------------------------------- #
def confirmed_profile():
    p = CandidateProfile(nombre='Ana Pérez', email='ana@example.com', telefono='999888777', ubicacion='Lima',
                         rango_salarial='S/2,500–2,800', disponibilidad='Inmediata', movilidad='Si, movilidad propia',
                         educacion=['Bachiller en Economía'], skills=[('Excel', 'avanzado')], verificado=True)
    p.hechos_confirmados = {k: 'Confirmado' for k in ('email', 'telefono', 'ubicacion', 'disponibilidad', 'movilidad',
                                                       'salario_pretendido', 'formacion', 'herramientas')}
    return p


def test_plan_fills_only_confirmed_facts():
    fields = [
        {'key': '1', 'label': 'Salario pretendido', 'type': 'text', 'required': True, 'filled': False},
        {'key': '2', 'label': '¿Cuentas con movilidad propia?', 'type': 'select', 'options': ['Selecciona', 'Sí', 'No'], 'required': True, 'filled': False},
        {'key': '3', 'label': 'Teléfono', 'type': 'tel', 'required': True, 'filled': True},
        {'key': '4', 'label': '¿Por qué te interesa este puesto?', 'type': 'textarea', 'required': True, 'filled': False},
        {'key': '5', 'label': 'Acepto los términos', 'type': 'checkbox', 'required': True, 'filled': False},
        {'key': '6', 'label': 'DNI', 'type': 'text', 'required': True, 'filled': False},
        {'key': '7', 'label': 'Comentario opcional', 'type': 'text', 'required': False, 'filled': False},
    ]
    plan = {s['key']: s for s in portals.plan_fields(fields, confirmed_profile(), 'Analista', {})}
    assert plan['1'] == {**plan['1'], 'action': 'fill', 'value': '2500'}
    assert plan['2']['action'] == 'select' and plan['2']['value'] == 'Sí'
    assert '3' not in plan
    assert plan['4']['action'] == 'pending'  # generated motivation text always needs your review
    assert plan['5']['action'] == 'pending'  # never accepts terms on your behalf
    assert plan['6']['action'] == 'pending' and 'sensible' in plan['6']['reason']
    assert plan['7']['action'] == 'skip'
    approved = {'¿por que te interesa este puesto?': 'Me interesa por mi experiencia en cobranzas B2B.'}
    plan = {s['key']: s for s in portals.plan_fields(fields, confirmed_profile(), 'Analista', approved)}
    assert plan['4']['action'] == 'fill' and plan['4']['source'] == 'Respuesta aprobada por ti'


def test_profile_list_choices_work_with_autofill():
    """The option lists in «Mi perfil» (web/app.js) must stay usable by the executor."""
    yes_no = ['Selecciona', 'Sí', 'No']
    assert portals.choose_option(yes_no, 'Sí, cuento con movilidad propia') == 'Sí'
    assert portals.choose_option(yes_no, 'Sí, cuento con movilidad propia y licencia de conducir') == 'Sí'
    assert portals.choose_option(yes_no, 'No, me movilizo en transporte público') == 'No'
    assert portals.choose_option(yes_no, 'No cuento con movilidad propia') == 'No'
    fields = [{'key': '1', 'label': 'Salario pretendido', 'type': 'text', 'required': True, 'filled': False},
              {'key': '2', 'label': 'Disponibilidad para incorporarte', 'type': 'select', 'options': ['Inmediata', 'En 1 mes'], 'required': True, 'filled': False}]
    for salary, expected in (('S/2,500 – S/3,000', '2500'), ('Hasta S/1,500', '1500'), ('Más de S/8,000', '8000')):
        p = confirmed_profile()
        p.rango_salarial = salary
        plan = {s['key']: s for s in portals.plan_fields(fields, p, 'Analista', {})}
        assert plan['1']['value'] == expected
        assert plan['2'] == {**plan['2'], 'action': 'select', 'value': 'Inmediata'}


def test_choose_option_is_conservative():
    assert portals.choose_option(['Sí', 'No'], 'Si, movilidad propia') == 'Sí'
    assert portals.choose_option(['Básico', 'Intermedio', 'Avanzado'], 'Avanzado') == 'Avanzado'
    assert portals.choose_option(['Lima', 'Arequipa'], 'Experiencia en cobranzas') is None


# --------------------------------------------------------------------------- #
#  Cola de postulaciones
# --------------------------------------------------------------------------- #
def ready_profile(client):
    r = client.post('/api/cv/upload', files={'file': ('cv.txt', 'ANA PEREZ\nEducación\nBachiller en Economía', 'text/plain')})
    pid = r.json()['id']
    client.patch(f'/api/profiles/{pid}', json={'nombre': 'Ana Pérez', 'email': 'ana@example.com', 'rango_salarial': 'S/2,500',
                                               'movilidad': 'Si, movilidad propia',
                                               'experiencia': [{'empresa': 'Empresa', 'cargo': 'Asistente', 'bullets': ['Cobranzas B2B.']}]})
    h = client.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
    assert client.post(f'/api/career/profiles/{pid}/confirm', json={'profile_hash': h, 'accepted': True}).status_code == 200
    assert client.put(f'/api/career/profiles/{pid}/goals', json={'titles': ['Analista de cobranzas'], 'location': 'Lima', 'modality': 'Híbrido'}).status_code == 200
    return pid


def import_job(client, pid, url, title='Analista de cobranzas'):
    r = client.post('/api/jobs/import', json={'profile_id': pid, 'empresa': 'Empresa', 'titulo': title,
                                              'descripcion': 'Cobranzas.', 'url': url})
    assert r.status_code == 201, r.text
    return r.json()['id']


def connect(pid, portal='bumeran'):
    db = SessionLocal()
    db.add(portals.PortalAccount(profile_id=pid, portal=portal, encrypted=portals.cipher().encrypt(json.dumps({'formato': 'navegador_real', 'perfil': 'x'}).encode()).decode()))
    db.commit()
    db.close()


def test_queue_rules_and_uncertain_attempts(client, monkeypatch):
    monkeypatch.delenv('RENDER', raising=False)
    pid = ready_profile(client)
    linkedin = import_job(client, pid, 'https://pe.linkedin.com/jobs/view/analista-1')
    r = client.post(f'/api/portals/applications/{linkedin}/apply', json={})
    assert r.status_code == 409 and 'LinkedIn' in r.json()['detail']
    aid = import_job(client, pid, f'https://www.bumeran.com.pe/empleos/analista-de-cobranzas-{pid}000001.html', 'Analista junior de cobranzas')
    r = client.post(f'/api/portals/applications/{aid}/apply', json={})
    assert r.status_code == 409 and 'Conecta tu cuenta' in r.json()['detail']
    status = client.get(f'/api/portals/{pid}').json()
    assert [a['status'] for a in status['accounts']] == ['disconnected', 'disconnected', 'disconnected']
    connect(pid)
    monkeypatch.setenv('RENDER', 'true')
    assert 'computadora' in client.post(f'/api/portals/applications/{aid}/apply', json={}).json()['detail']
    monkeypatch.delenv('RENDER')
    r = client.post(f'/api/portals/applications/{aid}/apply', json={})
    assert r.status_code == 202, r.text
    run_id = r.json()['id']
    assert client.post(f'/api/portals/applications/{aid}/apply', json={}).status_code == 409  # already queued
    db = SessionLocal()
    run = db.get(portals.AutoApplyRun, run_id)
    run.status = 'ejecutando'
    portals.finish(db, run, {'status': 'error', 'reason': 'fallo_tecnico', 'message': 'x', 'trace': {'clicks': ['Postularme'], 'filled': []}})
    db.close()
    runs = client.get(f'/api/portals/applications/{aid}/runs').json()['runs']
    assert runs[0]['status'] == 'intento_no_confirmado'  # a failure after clicking is never "not sent"
    assert client.post(f'/api/portals/applications/{aid}/apply', json={}).status_code == 409
    r = client.post(f'/api/portals/applications/{aid}/apply', json={'confirm_not_sent': True})
    assert r.status_code == 202
    db = SessionLocal()
    run = db.get(portals.AutoApplyRun, r.json()['id'])
    portals.finish(db, run, {'status': 'postulada', 'reason': 'confirmacion_portal', 'evidence': 'Tu postulación fue enviada',
                             'trace': {'clicks': ['Postularme'], 'filled': [{'label': 'Salario', 'value': '2500'}]}})
    db.close()
    apps = {a['id']: a for a in client.get(f'/api/applications?profile_id={pid}').json()}
    assert apps[aid]['estado'] == 'postulada'
    assert any(e['accion'] == 'postulada' and e['datos']['tipo_evidencia'] == 'mensaje_portal' for e in apps[aid]['auditoria'])
    assert client.post(f'/api/portals/applications/{aid}/apply', json={'confirm_not_sent': True}).status_code == 409


def test_blocked_questions_become_reviewable_answers(client, monkeypatch):
    monkeypatch.delenv('RENDER', raising=False)
    pid = ready_profile(client)
    connect(pid, 'computrabajo')
    aid = import_job(client, pid, f'https://pe.computrabajo.com/ofertas-de-trabajo/oferta-{pid}-ABC')
    batch = client.post(f'/api/portals/{pid}/apply-batch', json={'application_ids': [aid, 999999]}).json()['results']
    assert batch[0]['queued'] and not batch[1]['queued']
    db = SessionLocal()
    run = db.get(portals.AutoApplyRun, batch[0]['run']['id'])
    question = {'key': '4', 'label': '¿Tienes experiencia con SAP FI?', 'type': 'radio', 'options': ['Sí', 'No'],
                'required': True, 'action': 'pending', 'reason': 'No hay un dato confirmado para esta pregunta.'}
    portals.finish(db, run, {'status': 'bloqueada', 'reason': 'preguntas', 'questions': [question], 'trace': {'clicks': [], 'filled': []}})
    db.close()
    app_data = next(a for a in client.get(f'/api/applications?profile_id={pid}').json() if a['id'] == aid)
    assert app_data['estado'] == 'bloqueada'
    form_id = next(e['datos']['form_id'] for e in app_data['auditoria'] if e['accion'] == 'bloqueada')
    r = client.post(f'/api/form/{form_id}/approve', json={'edits': [{'field_id': '4', 'answer': 'No'}]})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    assert portals.approved_answers(db, aid) == {'¿tienes experiencia con sap fi?': 'No'}
    db.close()


# --------------------------------------------------------------------------- #
#  Ejecutor con navegador real contra un portal simulado
# --------------------------------------------------------------------------- #
JOB_PAGE = '''<!doctype html><html><head><meta charset="utf-8"></head><body><header><input type="search" placeholder="Buscar empleos"></header>
<main><h1>Analista de cobranzas</h1>
<section class="apply"><label for="sal">Salario pretendido</label><input id="sal" name="salarioPretendido" required>
<button id="go">Postularme</button></section>
<aside><form><label for="nl">Correo para novedades</label><input id="nl" type="email"><button type="button">Enviar</button></form></aside></main>
<div role="dialog" id="dlg" style="display:none"><label for="mov">¿Cuentas con movilidad propia?</label>
<select id="mov" required><option>Selecciona</option><option>Sí</option><option>No</option></select>
EXTRA<button id="send">Enviar postulación</button></div>
<p id="ok" style="display:none">¡Tu postulación fue enviada!</p>
<script>
window.sent = 0;
go.onclick = () => { if (!sal.value) return; window.salary = sal.value; dlg.style.display = 'block'; };
send.onclick = () => { if (mov.selectedIndex < 1) return; if (window.MUTE) { dlg.style.display='none'; return; }
  window.sent++; dlg.style.display = 'none'; ok.style.display = 'block'; };
</script></body></html>'''


@pytest.fixture
def portal_page():
    sync_api = pytest.importorskip('playwright.sync_api')
    try:
        manager = sync_api.sync_playwright().start()
        browser = manager.chromium.launch()
    except Exception as exc:
        pytest.skip(f'Chromium no disponible: {exc}')
    pages = {}

    def open_with(body, path='/empleos/analista-1.html', host='www.bumeran.com.pe'):
        context = browser.new_context()
        context.route(f'https://{host}/**', lambda route: route.fulfill(
            status=200, content_type='text/html; charset=utf-8', body=pages.get(route.request.url.split(host)[1].split('?')[0], '<p>Inicia sesión</p>')))
        pages[path] = body
        return context.new_page()
    yield open_with
    browser.close()
    manager.stop()


def planner():
    profile = confirmed_profile()
    return lambda fields: portals.plan_fields(fields, profile, 'Analista de cobranzas', {})


def test_executor_completes_application_with_confirmation(portal_page):
    page = portal_page(JOB_PAGE.replace('EXTRA', ''))
    out = portals.apply_on_page(page, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())
    assert out['status'] == 'postulada', out
    assert page.evaluate('window.sent') == 1 and page.evaluate('window.salary') == '2500'
    assert [f['label'] for f in out['trace']['filled']] == ['Salario pretendido', '¿Cuentas con movilidad propia?']
    assert out['trace']['clicks'] == ['Postularme', 'Enviar postulación']


def test_executor_stops_on_unknown_question_before_sending(portal_page):
    extra = '<label for="q">¿Cuántos clientes gestionabas?</label><input id="q" required>'
    page = portal_page(JOB_PAGE.replace('EXTRA', extra))
    out = portals.apply_on_page(page, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())
    assert out['status'] == 'bloqueada' and out['reason'] == 'preguntas'
    assert [q['label'] for q in out['questions']] == ['¿Cuántos clientes gestionabas?']
    assert page.evaluate('window.sent') == 0


def test_executor_blocks_captcha_login_and_missing_confirmation(portal_page):
    captcha = portal_page('<p>Verifica que eres humano</p><button>Postularme</button>')
    assert portals.apply_on_page(captcha, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())['reason'] == 'captcha'
    login = portal_page('<p>Login</p>', path='/login')
    login.route('https://www.bumeran.com.pe/empleos/**', lambda r: r.fulfill(status=302, headers={'Location': 'https://www.bumeran.com.pe/login'}))
    out = portals.apply_on_page(login, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())
    assert out['reason'] == 'sesion_cerrada'
    silent = portal_page(JOB_PAGE.replace('EXTRA', '').replace('window.sent = 0;', 'window.sent = 0; window.MUTE = true;'))
    out = portals.apply_on_page(silent, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())
    assert out['status'] == 'intento_no_confirmado'
    closed = portal_page('<h1>Aviso finalizado</h1>')
    assert portals.apply_on_page(closed, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())['reason'] == 'sin_boton'
    blocked = portal_page('<h1>Sorry, you have been blocked</h1><p>You are unable to access bumeran.com.pe</p><button>Postularme</button>')
    assert portals.apply_on_page(blocked, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html', planner())['reason'] == 'bloqueo_portal'


def test_session_detection_distinguishes_login_block_and_active(portal_page):
    probe = '/postulantes/postulaciones'
    to_login = portal_page('<p>Cargando</p><script>setTimeout(() => location.href = "/login?returnTo=/postulantes", 1200)</script>', path=probe)
    assert portals.session_state(to_login.context, 'bumeran', wait_ms=4000) == 'sin_sesion'
    blocked = portal_page('<h1>Sorry, you have been blocked</h1><p>You are unable to access bumeran.com.pe</p>', path=probe)
    assert portals.session_state(blocked.context, 'bumeran', wait_ms=1500) == 'bloqueado'
    active = portal_page('<h1>Mis postulaciones</h1><p>Analista de cobranzas · Empresa SAC · Postulado el 10/09</p>', path=probe)
    assert portals.session_state(active.context, 'bumeran', wait_ms=1500) == 'activa'


def test_find_browser_prefers_configured_path(monkeypatch, tmp_path):
    exe = tmp_path / 'chrome.exe'
    exe.write_text('')
    monkeypatch.setenv('JOBFLOW_BROWSER_PATH', str(exe))
    assert portals.find_browser() == str(exe)
    monkeypatch.setenv('JOBFLOW_BROWSER_PATH', str(tmp_path / 'missing.exe'))
    assert portals.find_browser() != str(tmp_path / 'missing.exe')


def test_legacy_sessions_require_reconnecting(client, monkeypatch):
    monkeypatch.delenv('RENDER', raising=False)
    pid = ready_profile(client)
    db = SessionLocal()
    db.add(portals.PortalAccount(profile_id=pid, portal='computrabajo',
                                 encrypted=portals.cipher().encrypt(json.dumps({'cookies': []}).encode()).decode()))
    db.commit()
    db.close()
    status = {a['portal']: a['status'] for a in client.get(f'/api/portals/{pid}').json()['accounts']}
    assert status['computrabajo'] == 'expired'
    aid = import_job(client, pid, f'https://pe.computrabajo.com/ofertas-de-trabajo/oferta-legacy-{pid}', 'Asistente de cobranzas')
    assert 'Conecta tu cuenta' in client.post(f'/api/portals/applications/{aid}/apply', json={}).json()['detail']
    assert client.post(f'/api/portals/{pid}/computrabajo/verify').status_code == 409


def test_worker_applies_end_to_end_with_evidence(client, monkeypatch):
    sync_api = pytest.importorskip('playwright.sync_api')
    monkeypatch.delenv('RENDER', raising=False)
    pid = ready_profile(client)
    connect(pid)
    aid = import_job(client, pid, f'https://www.bumeran.com.pe/empleos/analista-{pid}-777.html', 'Analista de créditos y cobranzas')
    run_id = client.post(f'/api/portals/applications/{aid}/apply', json={}).json()['id']
    body = JOB_PAGE.replace('EXTRA', '')

    def fake_browser(profile_id, fn):
        assert profile_id == pid  # the candidate's own browser profile opens the portal
        try:
            with sync_api.sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context()
                context.route('https://www.bumeran.com.pe/**', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=body))
                outcome = fn(context.new_page())
                outcome['storage_state'] = context.storage_state()
                browser.close()
                return outcome
        except Exception as exc:
            if 'Executable' in str(exc):
                pytest.skip('Chromium no disponible')
            raise
    monkeypatch.setattr(portals, 'run_in_browser', fake_browser)
    portals.process_run(run_id)
    run = client.get(f'/api/portals/applications/{aid}/runs').json()['runs'][0]
    assert run['status'] == 'postulada', run
    assert run['screenshot'] and client.get(run['screenshot']).status_code == 200
    assert {f['label'] for f in run['filled']} == {'Salario pretendido', '¿Cuentas con movilidad propia?'}
    app_data = next(a for a in client.get(f'/api/applications?profile_id={pid}').json() if a['id'] == aid)
    assert app_data['estado'] == 'postulada'
    assert [e['accion'] for e in app_data['auditoria']][-3:] == ['auto_postulacion_autorizada', 'auto_postulacion_iniciada', 'postulada']


# --------------------------------------------------------------------------- #
#  Respuestas deducidas del CV (v0.7)
# --------------------------------------------------------------------------- #
from datetime import date as _date
from jobflow.cv_answers import answer_question, parse_month, experience_months, choose_years_option


def cv_profile(dated=True):
    p = confirmed_profile()
    p.experiencia = [
        {'empresa': 'Liberty Seguros Perú / Liberty Specialty Markets', 'cargo': 'Practicante de Finanzas - Cobranzas',
         'inicio': 'Jun. 2025' if dated else '2025', 'fin': 'Jun. 2026' if dated else '2026',
         'bullets': ['Analicé aging, saldos y pagos para priorizar cuentas vencidas de cobranzas B2B.']},
        {'empresa': 'Los Portales', 'cargo': 'Practicante de Costos', 'inicio': 'Ene. 2025', 'fin': 'Mar. 2025',
         'bullets': ['Monitoreé costos y presupuestos EAC con reportes en Excel.']},
    ]
    p.languages = {'ingles': 'Avanzado'}
    return p


def test_dates_and_years_are_computed_only_with_months():
    today = _date(2026, 9, 13)
    assert parse_month('Mar. 2024') == (2024, 3) and parse_month('marzo de 2024') == (2024, 3)
    assert parse_month('03/2024') == (2024, 3) and parse_month('Actualidad', today) == (2026, 9)
    assert parse_month('2024') is None
    assert experience_months({'inicio': 'Jun. 2025', 'fin': 'Jun. 2026'}) == 13
    assert choose_years_option(['Menos de 1 año', '1 a 2 años', 'Más de 2 años'], 13) == '1 a 2 años'
    q = '¿Cuántos años de experiencia tienes en cobranzas?'
    assert answer_question(q, 'number', [], cv_profile())['value'] == '1'
    assert '1 año y 1 mes' in answer_question(q, 'textarea', [], cv_profile())['value']
    assert 'Completa el mes' in answer_question(q, 'number', [], cv_profile(dated=False))['reason']
    assert 'reason' in answer_question('¿Cuántos años de experiencia tienes en empresas de consumo masivo o retail?', 'textarea', [], cv_profile())


def test_yes_no_answers_cite_evidence_and_never_say_no():
    p = cv_profile()
    text = answer_question('¿Tienes experiencia en procesos contables y cobranzas?', 'textarea', [], p)['value']
    assert text.startswith('Sí, en cobranzas.') and 'Liberty Seguros Perú' in text
    # A yes/no choice cannot explain a partial match, so it waits for the candidate.
    assert 'reason' in answer_question('¿Tienes experiencia en procesos contables y cobranzas?', 'radio', ['Sí', 'No'], p)
    assert answer_question('¿Manejas Excel?', 'select', ['Selecciona', 'Sí', 'No'], p)['value'] == 'Sí'
    assert 'reason' in answer_question('¿Tienes experiencia en SAP FI?', 'radio', ['Sí', 'No'], p)
    assert answer_question('Nivel de inglés', 'select', ['Básico', 'Avanzado'], p)['value'] == 'Avanzado'


def test_answer_bank_reuses_approved_answers_but_not_company_specific_ones(client):
    from jobflow.models import FormularioResuelto
    pid = ready_profile(client)
    first = import_job(client, pid, f'https://example.com/banco/{pid}/1', 'Analista de créditos')
    db = SessionLocal()
    db.add(FormularioResuelto(profile_id=pid, postulacion_id=first, plataforma='bumeran', aprobado_por_usuario=True,
                              respuestas_generadas=[{'label': '¿Cuál es tu expectativa salarial?', 'answer': 'S/ 3,000'},
                                                    {'label': '¿Por qué quieres trabajar en esta empresa?', 'answer': 'Por Koplast'}]))
    db.commit()
    bank = portals.answer_bank(db, pid)
    db.close()
    assert bank == {'¿cual es tu expectativa salarial?': 'S/ 3,000'}


def test_linkedin_needs_explicit_risk_acceptance_and_normalized_url(client, monkeypatch):
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.setattr(portals, 'login_worker', lambda pid, portal: None)
    pid = ready_profile(client)
    r = client.post(f'/api/portals/{pid}/linkedin/connect')
    assert r.status_code == 409 and 'prohíben' in r.json()['detail']
    assert client.post(f'/api/portals/{pid}/linkedin/connect', json={'acepto_riesgo': True}).status_code == 200
    portals.LOGINS.pop((pid, 'linkedin'), None)
    assert portals.apply_url('linkedin', 'https://pe.linkedin.com/jobs/view/analista-de-cobranzas-at-aris-4454836420') == \
        'https://www.linkedin.com/jobs/view/4454836420/'


BUMERAN_REAL = """<!doctype html><html><head><meta charset="utf-8"><style>
.overlay{position:fixed;inset:0;background:#0006;z-index:50;display:none}.modal{background:#fff;margin:40px auto;width:700px;padding:20px}
</style></head><body><header><input placeholder="Buscar empleo por puesto o palabra clave"></header>
<main><h1>Analista de Créditos y Cobranzas</h1><aside id="side">STATE</aside></main>
<div class="overlay" id="ov"><div class="modal"><h2>Responde las preguntas</h2><p>Es importante para la empresa que brindes más información.</p>
<div class="q"><p>¿Cual es tu expectativa salarial? <span>*</span></p><div><textarea placeholder="Ingresa tu respuesta"></textarea><span>0 / 2000</span></div></div>
<div class="q"><p>¿Cuántos años de experiencia tienes en empresas de consumo masivo o retail?<span>*</span></p><div><textarea placeholder="Ingresa tu respuesta"></textarea><span>0 / 2000</span></div></div>
<div class="q"><p>¿Tienes experiencia en procesos contables y cobranzas?<span>*</span></p><div><textarea placeholder="Ingresa tu respuesta"></textarea><span>0 / 2000</span></div></div>
<button id="resp" disabled>Responder</button></div></div>
<script>
window.applications = 0; window.answers = null;
const areas = [...document.querySelectorAll('textarea')];
areas.forEach(a => a.addEventListener('input', () => { resp.disabled = areas.some(x => !x.value.trim()); }));
function openQuestions() { ov.style.display = 'block'; }
function wire() {
  const go = document.getElementById('go');
  if (go) go.onclick = () => { window.applications++; side.innerHTML = '<p>Postulado el 13/09/2026</p><button id="card">Preguntas sin responder<br><small>Responde las preguntas para aumentar tus chances</small></button>'; wire(); openQuestions(); };
  const card = document.getElementById('card'); if (card) card.onclick = openQuestions;
}
resp.onclick = () => { window.answers = areas.map(a => a.value); ov.style.display = 'none'; side.innerHTML = '<p>Postulado el 13/09/2026</p>'; };
wire();
</script></body></html>"""


def test_bumeran_registers_application_then_answers_questions_from_cv(portal_page):
    page = portal_page(BUMERAN_REAL.replace('STATE', '<button id="go">Postularme</button>'))
    profile = cv_profile()
    out = portals.apply_on_page(page, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html',
                                lambda fields: portals.plan_fields(fields, profile, 'Analista', {}))
    assert out['status'] == 'postulada' and out['reason'] == 'preguntas_pendientes', out
    assert page.evaluate('window.applications') == 1 and page.evaluate('window.answers') is None
    assert [q['label'] for q in out['questions']] == ['¿Cuántos años de experiencia tienes en empresas de consumo masivo o retail?']
    proposed = {s['label']: s['value'] for s in out['planned']}
    assert proposed['¿Cual es tu expectativa salarial?'] == 'S/2,500–2,800'
    assert proposed['¿Tienes experiencia en procesos contables y cobranzas?'].startswith('Sí, en cobranzas.')


def test_bumeran_completes_pending_questions_with_approved_answers(portal_page):
    card = '<p>Postulado el 13/09/2026</p><button id="card">Preguntas sin responder<br><small>Responde las preguntas para aumentar tus chances</small></button>'
    page = portal_page(BUMERAN_REAL.replace('STATE', card))
    profile = cv_profile()
    approved = {'¿cuantos anos de experiencia tienes en empresas de consumo masivo o retail?': 'No tengo experiencia en consumo masivo o retail.'}
    out = portals.apply_on_page(page, 'bumeran', 'https://www.bumeran.com.pe/empleos/analista-1.html',
                                lambda fields: portals.plan_fields(fields, profile, 'Analista', approved))
    assert out['status'] == 'postulada' and not out['questions'], out
    answers = page.evaluate('window.answers')
    assert answers[0] == 'S/2,500–2,800' and answers[1].startswith('No tengo') and answers[2].startswith('Sí, en cobranzas.')
    assert page.evaluate('window.applications') == 0  # never applies again


LINKEDIN_EASY_APPLY = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<main><h1>Analista de cobranzas</h1><button id="easy">Solicitud sencilla</button></main>
<div role="dialog" id="dlg" style="display:none">
 <section id="s1"><label for="mail">Dirección de correo electrónico</label><select id="mail" required><option>Selecciona una opción</option><option selected>ana@example.com</option></select>
  <label for="tel">Número de teléfono móvil</label><input id="tel" required><button id="n1">Siguiente</button></section>
 <section id="s2" style="display:none"><label for="yrs">¿Cuántos años de experiencia tienes en cobranzas?</label><input id="yrs" type="number" required>
  <fieldset><legend>¿Tienes experiencia con Excel?</legend><input type="radio" name="xl" id="xy" value="Yes" required><label for="xy">Sí</label>
  <input type="radio" name="xl" id="xn" value="No"><label for="xn">No</label></fieldset><button id="n2">Revisar</button></section>
 <section id="s3" style="display:none"><p>Revisa tu solicitud</p><button id="send">Enviar solicitud</button></section>
 <section id="ok" style="display:none"><h2>Se envió tu solicitud a ARIS</h2><button>Listo</button></section>
</div>
<script>
window.sent = 0; window.data = null;
easy.onclick = () => { dlg.style.display = 'block'; };
n1.onclick = () => { if (!tel.value) return; s1.style.display = 'none'; s2.style.display = 'block'; };
n2.onclick = () => { if (!yrs.value || !document.querySelector('input[name=xl]:checked')) return; s2.style.display = 'none'; s3.style.display = 'block'; };
send.onclick = () => { window.sent++; window.data = {tel: tel.value, yrs: yrs.value, xl: document.querySelector('input[name=xl]:checked').id}; s3.style.display = 'none'; ok.style.display = 'block'; };
</script></body></html>"""


def test_linkedin_easy_apply_multi_step_with_cv_answers(portal_page):
    page = portal_page(LINKEDIN_EASY_APPLY, path='/jobs/view/4454836420/', host='www.linkedin.com')
    profile = cv_profile()
    out = portals.apply_on_page(page, 'linkedin', 'https://www.linkedin.com/jobs/view/4454836420/',
                                lambda fields: portals.plan_fields(fields, profile, 'Analista de cobranzas', {}))
    assert out['status'] == 'postulada', out
    assert page.evaluate('window.sent') == 1
    assert page.evaluate('window.data') == {'tel': '999888777', 'yrs': '1', 'xl': 'xy'}
    assert out['trace']['clicks'] == ['Solicitud sencilla', 'Siguiente', 'Revisar', 'Enviar solicitud']


def test_linkedin_external_apply_is_reported_clearly(portal_page):
    page = portal_page('<h1>Analista</h1><a href="https://empresa.example/jobs">Solicitar</a>', path='/jobs/view/1234567/', host='www.linkedin.com')
    out = portals.apply_on_page(page, 'linkedin', 'https://www.linkedin.com/jobs/view/1234567/',
                                lambda fields: portals.plan_fields(fields, cv_profile(), 'Analista', {}))
    assert out['reason'] == 'sin_boton' and 'Solicitud sencilla' in out['message']
