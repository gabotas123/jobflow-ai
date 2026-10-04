import os
import tempfile
os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.mkdtemp()+'/headhunter-test.db')
import pytest
from fastapi.testclient import TestClient
from jobflow.cv_parser import parse_cv
from jobflow.headhunter import audit, _grounded, rewrite
from jobflow.main import app
from conftest import sign_in

FLOJO = """MARIA QUISPE
Lima, Peru | maria@example.com | 999 111 222

EXPERIENCIA
Asistente de Cobranzas - Corporacion Andina SAC
Ene. 2023 - Dic. 2024
- Responsable de la gestion de cartera de clientes.
- Apoyo en conciliaciones bancarias.

HABILIDADES
Excel avanzado
"""
FUERTE = """MARIA QUISPE
Lima, Peru | maria@example.com | 999 111 222

EXPERIENCIA
Analista de Cobranzas - Corporacion Andina SAC
Ene. 2023 - Dic. 2024
- Gestioné una cartera de 120 clientes corporativos con seguimiento semanal de pagos.
- Reduje la morosidad de 18 % a 11 % en 8 meses con un plan de cobranza por tramos.
- Elaboré 12 reportes mensuales de cobranzas y conciliaciones bancarias en Excel y SAP.

HABILIDADES
Excel avanzado, SAP intermedio, cobranzas, conciliaciones bancarias
"""
AVISO = ("Buscamos Analista de Cobranzas. Funciones: gestión de cartera, seguimiento de cobranzas, "
         "conciliaciones bancarias y reportes de cobranzas. Requisitos: Excel, SAP, cobranzas corporativas.")

def test_un_cv_flojo_no_pasa_y_dice_que_corregir():
    r=audit(parse_cv(FLOJO),'Analista de Cobranzas',AVISO,['Excel','SAP'])
    assert r['veredicto']!='Pasa el filtro' and r['puntaje']<80
    estados={c['criterio']:c['estado'] for c in r['criterios']}
    assert estados['Logros con cifras']=='falla'
    assert estados['Logros que empiezan con un verbo de acción']=='falla'
    assert 'SAP' in r['palabras_clave']['faltantes']
    assert r['prioridades'] and all(p['correccion'] for p in r['prioridades'])
    assert any('SAP' in q for q in r['preguntas'])          # pregunta, no lo añade

def test_un_cv_fuerte_pasa():
    r=audit(parse_cv(FUERTE),'Analista de Cobranzas',AVISO,['Excel','SAP'])
    assert r['veredicto']=='Pasa el filtro' and r['puntaje']>=80, r
    assert r['excluyentes']==[]

def test_los_anos_exigidos_son_excluyentes_aunque_el_cv_sea_bueno():
    r=audit(parse_cv(FUERTE),'Analista de Cobranzas',AVISO,['Excel','SAP'],years_required=5)
    assert r['veredicto']=='No pasa el filtro'
    assert r['excluyentes']==['Años de experiencia exigidos']
    assert 'no lo resuelve' in r['resumen']

def test_una_propuesta_con_datos_nuevos_se_descarta():
    origen='Gestion de cartera de clientes corporativos en Excel.'
    cv='gestion de cartera de clientes corporativos en excel'
    assert _grounded('Gestioné la cartera de clientes corporativos en Excel.',origen,cv)
    assert not _grounded('Gestioné una cartera de 120 clientes corporativos en Excel.',origen,cv)   # cifra inventada
    assert not _grounded('Gestioné la cartera de clientes corporativos en SAP.',origen,cv)          # herramienta inventada

def test_sin_modelo_configurado_no_hay_redaccion():
    assert rewrite(parse_cv(FLOJO),'Analista de Cobranzas',AVISO) is None

def test_la_revision_es_privada_y_usa_la_candidatura():
    with TestClient(app) as c:
        sign_in(c)
        pid=c.post('/api/cv/upload',files={'file':('cv.txt',FLOJO,'text/plain')}).json()['id']
        h=c.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
        c.post(f'/api/career/profiles/{pid}/confirm',json={'profile_hash':h,'accepted':True})
        c.put(f'/api/career/profiles/{pid}/goals',json={'titles':['Analista de cobranzas'],'location':'Lima','modality':'Híbrido'})
        aid=c.post('/api/jobs/import',json={'profile_id':pid,'empresa':'Destino SAC','titulo':'Analista de Cobranzas','descripcion':AVISO,'url':'https://example.com/hh/1'}).json()['id']
        r=c.get(f'/api/headhunter/applications/{aid}')
        assert r.status_code==200
        body=r.json()
        assert body['revisado']=='Tu perfil, sin adaptar' and body['redaccion_disponible'] is False
        assert body['veredicto'] in ('En riesgo','No pasa el filtro')
        with TestClient(app) as otro:
            otro.post('/api/auth/register',json={'username':'intruso-hh','password':'otra-clave-123','nombre':'Intruso'})
            assert otro.get(f'/api/headhunter/applications/{aid}').status_code==404
