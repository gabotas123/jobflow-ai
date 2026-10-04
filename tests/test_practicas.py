"""Quien busca prácticas se evalúa por lo que estudia, y solo ve las prácticas a las que puede postular."""
from jobflow.cv_parser import parse_cv
from jobflow.workflow import LEVELS, evaluate, level_fits

ESTUDIANTE = parse_cv("""LUCIA TANAKA
Lima | lucia@example.com | 999 000 111

EXPERIENCIA
Asistente de Ventas - Tienda Sol SAC
Ene. 2023 - Dic. 2024
- Atención de pedidos y coordinación de entregas.

EDUCACION
Derecho - Universidad Ficticia, 6to ciclo

HABILIDADES
Excel intermedio
""")
PRE, PRO = LEVELS["practicante_preprofesional"][0], LEVELS["practicante_profesional"][0]


def funcional(analisis):
    return next(c for c in analisis["componentes"] if c["criterio"] == "Coincidencia funcional")


def test_las_practicas_preprofesionales_y_profesionales_no_se_mezclan():
    assert level_fits(PRE, {PRE}) and level_fits(PRE, {PRE, PRO})      # «Practicante» a secas vale para ambas
    assert not level_fits(PRE, {PRO})                                   # estudiante: no las de egresados
    assert not level_fits(PRO, {PRE})                                   # egresado: no las de estudiantes
    assert level_fits(PRO, {PRO + 1})                                   # un egresado sí puede mirar «asistente»
    assert level_fits(LEVELS["analista"][0], {LEVELS["analista_junior"][0]})   # el resto, nivel contiguo como antes


def test_una_estudiante_no_ve_practicas_profesionales():
    aviso = {"titulo": "Practicante Profesional Legal", "descripcion": "", "ubicacion": "Lima"}
    r = evaluate(ESTUDIANTE, aviso, "practicante_preprofesional")
    assert r["requisito_excluyente"] and "Practicante profesional" in r["motivos_exclusion"][0]
    ok = evaluate(ESTUDIANTE, {**aviso, "titulo": "Practicante Pre Profesional de Derecho"}, "practicante_preprofesional")
    assert not ok["requisito_excluyente"]


def test_en_practicas_la_carrera_cuenta_como_encaje():
    aviso = {"titulo": "Practicante Pre Profesional de Derecho", "descripcion": "", "ubicacion": "Lima"}
    c = funcional(evaluate(ESTUDIANTE, aviso, "practicante_preprofesional"))
    assert c["puntos"] == 30 and "carrera" in c["motivo"]


def test_fuera_de_practicas_solo_cuenta_lo_trabajado():
    aviso = {"titulo": "Analista Legal", "descripcion": "", "ubicacion": "Lima"}
    c = funcional(evaluate(ESTUDIANTE, aviso, "analista"))
    assert c["puntos"] == 0 and "experiencia declarada" in c["motivo"]
