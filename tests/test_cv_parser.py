"""El formato mas comun de CV peruano: cargo, linea de periodo, logros."""
from jobflow.cv_parser import parse_cv

CV = """MARIA FERNANDA QUISPE ROJAS
Lima, Peru | maria@example.com | 999 111 222

RESUMEN
Bachiller en Contabilidad con experiencia en cobranzas y conciliaciones bancarias.

EXPERIENCIA
Asistente de Cobranzas - Corporacion Andina SAC
Ene. 2023 - Dic. 2024
- Gestion de cartera de clientes corporativos y seguimiento de pagos.
- Conciliaciones bancarias y reportes mensuales en Excel.
- Coordinacion con el area comercial para regularizar deudas vencidas.

Practicante de Contabilidad - Estudio Contable Lima
Mar. 2022 - Dic. 2022
- Registro de comprobantes y apoyo en declaraciones mensuales.

EDUCACION
Bachiller en Contabilidad - Universidad de Lima, 2022

HABILIDADES
Excel avanzado, SAP basico, conciliaciones, cobranzas, analisis de cartera
"""


def test_periodo_propio_no_desplaza_los_empleos():
    """La linea de fechas pertenece al empleo que la precede, no abre uno nuevo."""
    p = parse_cv(CV)
    assert len(p.experiencia) == 2, p.experiencia
    primero, segundo = p.experiencia
    assert primero["cargo"] == "Asistente de Cobranzas"
    assert primero["empresa"] == "Corporacion Andina SAC"
    assert (primero["inicio"], primero["fin"]) == ("2023", "2024")
    assert len(primero["bullets"]) == 3
    assert segundo["cargo"] == "Practicante de Contabilidad"
    assert segundo["empresa"] == "Estudio Contable Lima"
    assert (segundo["inicio"], segundo["fin"]) == ("2022", "2022")
    assert len(segundo["bullets"]) == 1


def test_la_linea_de_contacto_no_es_el_titular():
    p = parse_cv(CV)
    assert "@" not in p.headline and "999" not in p.headline
    assert p.headline == "Asistente de Cobranzas | Practicante de Contabilidad"


def test_lima_se_reconoce_como_ubicacion():
    assert parse_cv(CV).ubicacion == "Lima"
    assert parse_cv(CV.replace("Lima, Peru", "Arequipa, Peru")).ubicacion == "Arequipa"


def test_orden_empresa_cargo_sigue_funcionando():
    """El orden inverso, con la empresa primero, no debe romperse."""
    p = parse_cv("""JUAN PEREZ

EXPERIENCIA
Corporacion Andina SAC - Analista de Costos
Ene. 2023 - Actualidad
- Control de costos de produccion y reportes de margen.
""")
    assert p.experiencia[0]["cargo"] == "Analista de Costos"
    assert p.experiencia[0]["empresa"] == "Corporacion Andina SAC"
    assert p.experiencia[0]["fin"] == "Actualidad"


def test_las_habilidades_conservan_su_nivel():
    niveles = dict(parse_cv(CV).skills)
    assert niveles.get("Excel") == "avanzado"
    assert niveles.get("Sap") == "basico"
