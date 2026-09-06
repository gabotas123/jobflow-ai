"""Pipeline de Autofill (modulo 5 del documento tecnico).

Flujo agnostico de plataforma:
    [Detector de Formulario] -> [Mapeador Semantico] -> [Generador de Respuestas]
    -> [Revision Humana] -> [Ejecutor de Envio]

Toda respuesta generada pasa por aprobacion humana antes de "enviarse".
En el formulario de prueba (plataforma `test`) el flujo funciona end-to-end.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from . import models
from .profile_models import CandidateProfile
from .models import FormularioResuelto


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# Formulario de prueba (estilo Bumeran) para la demo de sustentacion.
TEST_FORM_SCHEMA = [
    {"id": "exp", "label": "¿Cuántos años de experiencia tienes en el área?", "type": "textarea"},
    {"id": "salario", "label": "Pretensión salarial (S/)", "type": "number"},
    {"id": "disp", "label": "Disponibilidad para incorporarte", "type": "text"},
    {"id": "mov", "label": "¿Cuentas con movilidad propia?", "type": "select",
     "options": ["Sí", "No"]},
    {"id": "modal", "label": "Modalidad de trabajo preferida", "type": "select",
     "options": ["Presencial", "Híbrido", "Remoto"]},
    {"id": "idioma", "label": "Nivel de inglés", "type": "select",
     "options": ["Básico", "Intermedio", "Avanzado"]},
    {"id": "herramientas", "label": "Herramientas que manejas", "type": "textarea"},
    {"id": "formacion", "label": "Formación académica", "type": "textarea"},
    {"id": "resumen", "label": "Perfil profesional (resumen)", "type": "textarea"},
    {"id": "motivo", "label": "¿Por qué te interesa este puesto?", "type": "textarea"},
    {"id": "linkedin", "label": "Enlace de tu perfil de LinkedIn", "type": "text"},
]

# Reglas de mapeo semantico: subcadena de la etiqueta -> campo canonico del perfil.
# IMPORTANTE: el orden importa (primera coincidencia gana).
FIELD_RULES = [
    (("linkedin", "link"), "linkedin"),
    (("movilidad", "transporte", "vehiculo"), "movilidad"),
    (("telefono", "celular", "movil"), "telefono"),
    (("correo", "email", "e-mail"), "email"),
    (("ubicacion", "ciudad", "distrito", "residencia"), "ubicacion"),
    (("por que", "motivo", "interesa", "interes"), "motivo_interes"),
    (("anos de experiencia", "años de experiencia", "experiencia"), "experiencia_total"),
    (("salario", "salarial", "sueldo", "remuneracion"), "salario_pretendido"),
    (("disponibilidad", "incorporarte", "inicio"), "disponibilidad"),
    (("modalidad", "presencial", "remoto", "hibrido"), "modalidad"),
    (("idioma", "ingles", "lengua"), "idioma_ingles"),
    (("herramienta", "software", "tecnologias"), "herramientas"),
    (("formacion", "estudios", "educacion", "carrera"), "formacion"),
    (("resumen", "presentacion", "perfil profesional", "objetivo"), "resumen_perfil"),
    (("cargo deseado", "puesto deseado", "posicion deseada", "cargo", "puesto", "posicion"), "cargo_deseado"),
]


def detect_form(form_schema: Optional[List[dict]] = None) -> List[dict]:
    """Detector de formulario. Con `form_schema` devuelve los campos tal cual;
    con una pagina Playwright (DOM) extraeria input/label/select automaticamente."""
    if form_schema is None:
        form_schema = TEST_FORM_SCHEMA
    return [dict(f) for f in form_schema]


def detect_from_dom(page) -> List[dict]:
    """Version real: extrae campos del DOM con Playwright.

    (Requiere `playwright` instalado y una pagina cargada. En el MVP se usa
    el formulario de prueba, pero esta implementacion es la del producto.)
    """
    fields = []
    for el in page.query_selector_all("input, textarea, select"):
        info = el.evaluate(
            """el => ({ id: el.id || '', name: el.name || '',
                        type: el.type || (el.tagName === 'SELECT' ? 'select' : 'text'),
                        placeholder: el.placeholder || '' })"""
        )
        label_el = page.query_selector(f"label[for='{info['id']}']") if info.get("id") else None
        label = label_el.inner_text() if label_el else (
            info.get("placeholder") or info.get("name") or info.get("id"))
        options = []
        if info["type"] == "select":
            options = page.evaluate(
                """(id) => Array.from(document.querySelector('#'+id)?.options || [])
                   .map(o => o.text)""", info["id"])
        fields.append({"id": info["id"] or info["name"], "label": label,
                       "type": info["type"], "options": options})
    return fields


def map_fields(fields: List[dict]) -> List[dict]:
    """Mapeador semantico: etiqueta del campo -> campo canonico del perfil."""
    out = []
    for f in fields:
        label = norm(f.get("label", ""))
        canonical = None
        for keys, canon in FIELD_RULES:
            if any(k in label for k in keys):
                canonical = canon
                break
        out.append({
            "field_id": f.get("id", ""),
            "label": f.get("label", ""),
            "type": f.get("type", ""),
            "opciones": f.get("options", []),
            "canonical": canonical or "no_mapeado",
            "confianza": 1.0 if canonical else 0.2,
            "necesita_revision": not bool(canonical),
        })
    return out


def generate_answers(mapping: List[dict], profile: "CandidateProfile", vacante_titulo: str,
                     seniority: str = "analista_junior") -> List[dict]:
    """Generador de respuestas: banco generico + perfil (solo datos reales)."""
    from .answer_generator import build_answers
    bank = build_answers(profile, vacante_titulo, seniority)
    out = []
    for m in mapping:
        canon = m["canonical"]
        item = bank.get(canon)
        if item and item.get("answer"):
            out.append({"field_id": m["field_id"], "label": m["label"],
                        "canonical": canon, "answer": item["answer"],
                        "fuente": item.get("fuente", ""), "confianza": item.get("confianza", 1.0),
                        "necesita_input": False})
        else:
            out.append({"field_id": m["field_id"], "label": m["label"],
                        "canonical": canon, "answer": "",
                        "fuente": "", "confianza": 0.0,
                        "necesita_input": True,
                        "nota": "Campo sin dato verificable: requiere intervencion del usuario."})
    return out


# --------------------------------------------------------------------------- #
#  Revision humana + ejeccion (simulada para `test`, real via adapters)
# --------------------------------------------------------------------------- #
def create_draft(db: Session, profile_id: int, platform: str, vacante_titulo: str,
                 fields: List[dict], mapping: List[dict], answers: List[dict]) -> FormularioResuelto:
    draft = FormularioResuelto(
        profile_id=profile_id,
        plataforma=platform,
        campos_detectados=fields,
        mapeo_semantico=mapping,
        respuestas_generadas=answers,
        aprobado_por_usuario=False,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def approve(db: Session, form_id: int, edits: Optional[List[dict]] = None) -> Optional[FormularioResuelto]:
    d = db.get(FormularioResuelto, form_id)
    if not d:
        return None
    answers = list(d.respuestas_generadas or [])
    if edits:
        by_field = {e.get("field_id"): e.get("answer", "") for e in edits}
        for a in answers:
            if a.get("field_id") in by_field:
                a["answer"] = by_field[a["field_id"]]
                a["editado_por_usuario"] = True
    d.respuestas_generadas = answers
    d.aprobado_por_usuario = True
    d.fecha_aprobacion = datetime.utcnow()
    db.commit()
    db.refresh(d)
    return d


def submit(db: Session, form_id: int) -> Optional[FormularioResuelto]:
    """Ejecutor de envio. Para el formulario de prueba, marca como enviado y
    crea una Postulacion. Para plataformas reales usaria Playwright (adapters)."""
    d = db.get(FormularioResuelto, form_id)
    if not d:
        return None
    if not d.aprobado_por_usuario:
        return None  # regla de oro: nunca enviar sin aprobacion humana
    d.enviado = True
    db.commit()
    db.refresh(d)
    return d
