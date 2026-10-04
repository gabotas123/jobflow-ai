"""CV de plantilla a dos columnas: el texto del PDF sale por columnas, no por orden de lectura.

Formato de cada empleo: «Cargo | Empresa», un parrafo y la fecha al final. Los datos son ficticios.
"""
from jobflow.cv_parser import parse_cv

CV = """EXPERIENCIA LABORAL
Especialista en Traducción y Comunicación
Internacional | Andes Trading Exportación
Traducción y revisión de documentación de exportación, y comunicación en inglés con proveedores
internacionales.
feb. 2022 - mar. 2026
Estudiante de Derecho de la Universidad Ficticia, con experiencia en retail, logística y comercio exterior.
He desarrollado experiencia en coordinación con proveedores y atención al cliente.
Lucía Andrea Tanaka Ríos
ESTUDIANTE DE DERECHO (6TO CICLO | DÉCIMO SUPERIOR)
INGLÉS AVANZADO
Bilingual Customer Service Representative |
Contact Center Lima
Atención y resolución de consultas de clientes en inglés.
oct. 2022 - mar. 2023
Supervisor de Logística y Puntos de Venta |
Panda Rojo S.A.C.
Responsable de la coordinación de inventario en tiendas, utilizando Excel y Trello. Supervisé al equipo
de ventas. También gestioné el reclutamiento de personal para mi área.
may. 2022 - ago. 2022
FORMACIÓN ACADÉMICA
Universidad Ficticia
Derecho | en curso
6to ciclo | Décimo Superior
Diploma de Bachillerato - Colegio Peruano Japonés Ficticio
HABILIDADES
Microsoft Excel, nivel intermedio
Redacción y revisión documental
Coordinación con proveedores y equipos
Celular: 999 000 111
Correo: lucia@example.com
Ubicación: La Molina
Consultor de Ventas y Logística | Tienda Sol S.A.C.
Gestión de ventas mediante canales digitales y coordinación de entregas.
ago. 2021 - mar. 2022
"""


def perfil():
    return parse_cv(CV, filename="CV - Lucia Tanaka Rios 2026.pdf")


def test_el_nombre_sale_del_cv_y_no_del_primer_cargo():
    assert perfil().nombre == "Lucía Andrea Tanaka Ríos"


def test_los_empleos_se_reconocen_aunque_esten_repartidos_por_el_documento():
    exp = perfil().experiencia
    assert [(e["cargo"], e["empresa"]) for e in exp] == [
        ("Especialista en Traducción y Comunicación Internacional", "Andes Trading Exportación"),
        ("Bilingual Customer Service Representative", "Contact Center Lima"),
        ("Supervisor de Logística y Puntos de Venta", "Panda Rojo S.A.C."),
        ("Consultor de Ventas y Logística", "Tienda Sol S.A.C."),      # estaba dentro de «Habilidades»
    ]
    assert (exp[0]["inicio"], exp[0]["fin"]) == ("feb. 2022", "mar. 2026")
    assert len(exp[2]["bullets"]) == 3 and exp[2]["bullets"][1] == "Supervisé al equipo de ventas."


def test_los_empleos_van_del_mas_reciente_al_mas_antiguo():
    fines = [e["fin"] for e in perfil().experiencia]
    assert fines == ["mar. 2026", "mar. 2023", "ago. 2022", "mar. 2022"]


def test_el_resumen_no_se_pierde_ni_se_mezcla_con_un_empleo():
    p = perfil()
    assert p.summary.startswith("Estudiante de Derecho de la Universidad Ficticia")
    assert all("Estudiante de Derecho" not in b for e in p.experiencia for b in e["bullets"])


def test_las_habilidades_no_absorben_empleos_ni_contacto():
    habilidades = dict(perfil().skills)
    assert habilidades["Microsoft Excel"] == "intermedio"
    assert "Redacción Y Revisión Documental" in habilidades and "Trello" in habilidades
    assert not any("Consultor" in h or "Tienda Sol" in h or "Nivel" == h for h in habilidades)
    assert perfil().ubicacion == "La Molina" and perfil().email == "lucia@example.com"


def test_un_cv_sin_este_formato_se_lee_como_antes():
    p = parse_cv("ANA PEREZ\n\nEXPERIENCIA\nAsistente de Cobranzas - Andina SAC\nEne. 2023 - Dic. 2024\n- Gestión de cartera.\n")
    assert p.experiencia[0]["cargo"] == "Asistente de Cobranzas" and p.experiencia[0]["empresa"] == "Andina SAC"


def test_estudiar_en_un_colegio_japones_no_es_hablar_japones():
    """Un idioma solo se registra si el CV lo declara con su nivel."""
    assert perfil().languages == {"ingles": "Avanzado"}
