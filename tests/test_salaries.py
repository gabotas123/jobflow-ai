import os
import tempfile
os.environ.setdefault('DATABASE_URL','sqlite:///'+tempfile.mkdtemp()+'/salaries-test.db')
from fastapi.testclient import TestClient
from jobflow import salaries
from jobflow.job_search import parse_computrabajo
from jobflow.main import app
from conftest import sign_in

PAGINA='''<h1>Salario de Analista de cobranzas en Perú</h1>
<div class="boxWhite"><p class="fs15 fc_aux">Media salarial</p><p class="fwB fs33">S/. 1.815<span class="fwN fs18"> /mes</span></p>
<span class="fc_aux">286 salarios</span><div class="dFlex tj_fx fs12 fc_aux mt5"> <p>S/. 850</p> <p>S/. 2.700</p> </div></div>
<span>Salarios relacionados</span>
<div class="dTable w_100 pb40 row bClick h_min_72"><a href="https://pe.computrabajo.com/salarios/analista-de-creditos" title="x">Analista de créditos</a>
<p class="fw_b fs18">S/. 1.816<span> /mes</span></p><span class="fc80">1.638 salarios</span><p>S/. 565</p> <p>S/. 3.650</p></div>
<span>Empresas populares</span>
<div class="dFlex w100 mt30 bClick"><a class="fc_base" href="/tawa">Grupo Tawa</a><p class="fwB fs18">S/. 2.318<span> /mes</span></p>
<span class="fc_aux">11 salarios</span><div class="dFlex tj_fx fs12 fc_aux mt5"> <p>S/. 2.000</p> <p>S/. 2.500</p> </div></div>
<div class="dFlex w100 mt30 bClick"><a class="fc_base" href="/seguroc">Seguroc SA</a><p class="fwB fs18">S/. 1.900<span> /mes</span></p>
<span class="fc_aux">47 salarios</span><div class="dFlex tj_fx fs12 fc_aux mt5"> <p>S/. 1.900</p> <p>S/. 1.900</p> </div></div>'''

def test_se_lee_el_promedio_el_rango_y_las_empresas():
    d=salaries.parse_salary_page(PAGINA)
    assert (d['media'],d['datos'],d['minimo'],d['maximo'])==(1815,286,850,2700)
    assert d['empresas']==[{'nombre':'Grupo Tawa','media':2318,'datos':11,'minimo':2000,'maximo':2500},
                           {'nombre':'Seguroc SA','media':1900,'datos':47,'minimo':1900,'maximo':1900}]
    assert d['relacionados'][0]=={'nombre':'Analista de créditos','media':1816,'datos':1638,'minimo':565,'maximo':3650}

def test_una_pagina_sin_sueldo_no_produce_datos():
    assert salaries.parse_salary_page('<html><h1>No encontrado</h1></html>')=={}
    assert salaries.money('S/. 2.500,00 (Mensual)')==2500 and salaries.money('sin cifra') is None

def test_la_tarjeta_del_aviso_trae_su_sueldo_mensual():
    card='<article class="box_offer"><h2><a href="/ofertas/x-1">Analista</a></h2><p class="dFlex">Empresa</p><p class="fs16 fc_base mt5">Lima</p><span>S/. 2.500,00 (Mensual)</span></article>'
    assert parse_computrabajo(card)[0]['sueldo_publicado']==2500
    assert parse_computrabajo(card.replace('<span>S/. 2.500,00 (Mensual)</span>',''))[0]['sueldo_publicado'] is None

def test_la_expectativa_solo_se_compara():
    d={'media':1815,'minimo':850,'maximo':2700}
    assert 'por encima del máximo' in salaries.expectation('S/2300 - S/3200',{**d,'maximo':2500})['nota']
    assert 'en línea' in salaries.expectation('S/1800',d)['nota']
    assert salaries.expectation('Sin indicar',d)=={} and salaries.expectation('S/2000',{})=={}

def test_la_pantalla_usa_el_puesto_objetivo_y_cita_la_fuente(monkeypatch):
    monkeypatch.setattr(salaries,'market',lambda t:{**salaries.parse_salary_page(PAGINA),'url':'https://pe.computrabajo.com/salarios/x'})
    monkeypatch.setattr(salaries,'postings',lambda t,l:[{'titulo':'Analista','empresa':'A','sueldo':2500,'url':'https://x/1','publicado':None},
                                                        {'titulo':'Analista','empresa':'B','sueldo':1700,'url':'https://x/2','publicado':None}])
    with TestClient(app) as c:
        sign_in(c)
        pid=c.post('/api/cv/upload',files={'file':('cv.txt','ANA\nEducación\nBachiller\nHabilidades\nExcel','text/plain')}).json()['id']
        assert c.get(f'/api/salaries/{pid}').status_code==409          # sin puesto no hay consulta
        h=c.get(f'/api/career/profiles/{pid}/setup').json()['profile_hash']
        c.post(f'/api/career/profiles/{pid}/confirm',json={'profile_hash':h,'accepted':True})
        c.put(f'/api/career/profiles/{pid}/goals',json={'titles':['Analista de cobranzas'],'location':'Lima','modality':'Híbrido','salary':'S/2300 - S/3200'})
        r=c.get(f'/api/salaries/{pid}').json()
        assert r['puesto']=='Analista de cobranzas' and r['mercado']['media']==1815
        assert r['avisos_resumen']=={'cantidad':2,'mediana':2100,'minimo':1700,'maximo':2500}
        assert r['expectativa']['valor']==2750 and r['fuente']['nombre']=='Computrabajo Perú'
        assert c.get(f'/api/salaries/{pid}',params={'puesto':'Analista contable'}).json()['puesto']=='Analista contable'
        with TestClient(app) as otro:
            otro.post('/api/auth/register',json={'username':'intruso-sal','password':'otra-clave-123','nombre':'Intruso'})
            assert otro.get(f'/api/salaries/{pid}').status_code==404
