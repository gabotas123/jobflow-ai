import os
import re
import tempfile
os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.mkdtemp()+'/landing-test.db')
from fastapi.testclient import TestClient
from jobflow.main import app
from conftest import sign_in

PORTADA='Postula a más empleos'
APP='id="auth-screen"'

def test_sin_sesion_la_raiz_es_la_portada():
    with TestClient(app) as c:
        r=c.get('/')
        assert r.status_code==200
        assert PORTADA in r.text and APP not in r.text

def test_con_sesion_la_raiz_es_la_aplicacion():
    with TestClient(app) as c:
        sign_in(c)
        assert APP in c.get('/').text
        # la portada sigue disponible para enseñarla con la sesión abierta
        assert PORTADA in c.get('/inicio').text

def test_app_abre_siempre_la_aplicacion():
    with TestClient(app) as c:
        assert APP in c.get('/app').text

def test_los_enlaces_internos_de_la_portada_tienen_destino():
    with TestClient(app) as c:
        html=c.get('/inicio').text
    anclas=set(re.findall(r'href="#([\w-]+)"',html))
    ids=set(re.findall(r'\bid="([\w-]+)"',html))
    assert anclas and anclas<=ids, anclas-ids
    # cada pestaña controla un panel que existe
    controles=set(re.findall(r'aria-controls="([\w-]+)"',html))
    assert controles and controles<=ids, controles-ids
