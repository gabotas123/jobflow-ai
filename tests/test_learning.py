import os
import tempfile
os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.mkdtemp()+'/learning-test.db')
from fastapi.testclient import TestClient
from jobflow.learning import courses, plan
from jobflow.main import app

def test_una_herramienta_que_falta_trae_donde_aprenderla():
    p=plan({'brechas':['Herramienta por verificar: Power BI','Herramienta por verificar: SAP','Herramienta por verificar: power bi']})
    assert [h['habilidad'] for h in p['habilidades']]==['Power BI','SAP']      # sin repetir
    bi=p['habilidades'][0]['cursos']
    assert bi[0]['plataforma']=='Microsoft Learn'                              # oficial y gratis primero
    assert all(c['url'].startswith('https://') and 'Power%20BI' in c['url'] or 'Power+BI' in c['url'] for c in bi)
    assert 'Microsoft Learn' not in [c['plataforma'] for c in p['habilidades'][1]['cursos']]
    assert 'confírmalo' in p['aviso']

def test_los_anos_de_experiencia_no_se_venden_como_curso():
    p=plan({'motivos_exclusion':['Exige tres o más años obligatorios de experiencia específica'],'brechas':[]})
    assert p['habilidades']==[] and p['aviso']==''
    assert len(p['no_se_cierra_con_cursos'])==1
    assert 'No se resuelve con un curso' in p['no_se_cierra_con_cursos'][0]['nota']

def test_la_formacion_distinta_tampoco():
    p=plan({'componentes':[{'criterio':'Formación','conocido':True,'puntos':0}]})
    assert 'no reemplaza una carrera' in p['no_se_cierra_con_cursos'][0]['nota']

def test_sin_brechas_no_hay_plan():
    assert plan({})=={'habilidades':[],'no_se_cierra_con_cursos':[],'aviso':''}
    assert courses('')==[]

def test_una_direccion_inexistente_muestra_una_pagina_con_salida():
    with TestClient(app) as c:
        r=c.get('/no-existe')
        assert r.status_code==404 and 'Esta página no existe' in r.text and 'href="/app"' in r.text
        assert c.get('/api/no-existe').headers['content-type'].startswith('application/json')
