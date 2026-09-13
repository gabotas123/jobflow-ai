"""Auditable assisted applications. No endpoint pretends to submit to an ATS."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from .models import Base, Postulacion, Vacante


class ApplicationDetail(Base):
    __tablename__ = "application_details"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("postulaciones.id"), unique=True, nullable=False)
    profile_id = Column(Integer, ForeignKey("candidate_profiles.id"), nullable=False)
    fingerprint = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("profile_id", "fingerprint"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("postulaciones.id"), nullable=False)
    action = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    created = Column(DateTime, default=datetime.utcnow)


def norm(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(value or ""))
                            if unicodedata.category(c) != "Mn").lower().split())


def safe_url(value):
    if not value:
        return ""
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Usa un enlace HTTP o HTTPS sin credenciales.")
    # Only stored/rendered; never fetched from this endpoint.
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")
             and k.lower() not in ("trk", "trackingid", "ref", "source")]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), ""))


def fingerprint(job):
    url = safe_url(job.get("url", ""))
    if url:
        return hashlib.sha256(url.encode()).hexdigest()
    key = "|".join(norm(job.get(k)) for k in ("empresa", "titulo", "ubicacion"))
    return hashlib.sha256(key.encode()).hexdigest()


DOMAINS = {
    "cobranzas": ("cobran", "cuentas por cobrar", "aging", "recaud", "recuperacion"),
    "gestion": ("costos", "presupuest", "control de gestion", "planeamiento", "eac"),
    "datos": ("reporting", "datos", "power bi", "business intelligence", "reportes"),
    "finanzas": ("finanzas", "financiero", "tesoreria", "conciliacion"),
    "operaciones": ("operacion", "incidencia", "operativo"),
}


def select_cv(title):
    t = norm(title)
    for domain, label in (("cobranzas", "cobranzas"), ("gestion", "gestion"), ("datos", "datos")):
        if any(word in t for word in DOMAINS[domain]):
            return label
    return "maestro"


def evaluate(profile, job):
    """Conservative evidence score, not a probability of recruitment success.

    Unprovided criteria get zero and are separately reported as unknown. No
    generic experience is treated as verified experience in a specific role.
    """
    title = norm(job.get("titulo"))
    experience = norm(" ".join(" ".join(e.get("bullets", [])) + " " + e.get("cargo", "")
                                for e in profile.experiencia))
    desc = norm(job.get("descripcion"))
    blocks, gaps, unknown, parts = [], [], [], []
    def add(name, weight, score, reason, known=True):
        parts.append(dict(criterio=name, peso=weight, puntos=score, motivo=reason, conocido=known))
        if not known:
            unknown.append(name)
    if re.search(r"\b(gerente|jefe|jefatura|director|senior|sr|practicante)\b", title):
        blocks.append("Nivel fuera del alcance asistente/junior/analista autorizado")
    if any(x in title for x in ("teleoperador", "asesor de ventas", "asesor call center", "asesor de cobranzas")):
        blocks.append("Funciones comerciales o teleoperación fuera del perfil autorizado")
    if job.get("vigente") is False:
        blocks.append("Vacante vencida")
    wanted = {d for d, words in DOMAINS.items() if any(w in title for w in words)}
    available = {d for d, words in DOMAINS.items() if any(w in experience for w in words)}
    ratio = len(wanted & available) / len(wanted) if wanted else 0
    add("Coincidencia funcional", 30, round(30 * ratio),
        "Funciones del título contrastadas con experiencia declarada", bool(wanted))
    years = job.get("anos_obligatorios")
    if years is None:
        match = re.search(r"(?:minim[oa](?: de)?|al menos|indispensable(?:s)?[: ]*|obligatori[oa](?:s)?[: ]*)\s*(\d+)\s*anos", desc)
        if match:
            years = float(match.group(1))
    relevant = job.get("meses_relevantes_confirmados")
    if years is not None and years >= 3:
        blocks.append("Exige tres o más años obligatorios de experiencia específica")
    if years is not None and relevant is not None and relevant < years * 12:
        blocks.append("Experiencia específica confirmada inferior a la obligatoria")
    known = years is not None and (years == 0 or relevant is not None)
    add("Experiencia requerida", 20, 20 if known and (years == 0 or relevant >= years * 12) else 0,
        "Meses específicos confirmados por el candidato" if known else "Falta requisito o experiencia específica confirmada", known)
    tools = job.get("herramientas", [])
    skills = {norm(s) for s, _ in profile.skills}
    missing = [s for s in tools if not any(norm(s) == sk or norm(s) in sk for sk in skills)]
    gaps.extend("Herramienta por verificar: " + s for s in missing)
    add("Herramientas", 15, round(15 * (len(tools)-len(missing))/len(tools)) if tools else 0,
        "Comparación con herramientas declaradas; el nivel debe revisarse", bool(tools))
    education = norm(job.get("formacion"))
    edu_ok = bool(education) and any(education in norm(e) for e in profile.educacion)
    add("Formación", 10, 10 if edu_ok else 0, "Coincidencia textual con formación declarada", bool(education))
    junior = bool(re.search(r"\b(asistente|junior|analista)\b", title))
    add("Seniority", 10, 10 if junior and not blocks else 0, "Nivel indicado en el título", junior or bool(blocks))
    location = norm(job.get("ubicacion"))
    modality = norm(job.get("modalidad"))
    loc_ok = bool(location and (location in norm(profile.ubicacion) or "lima" in location and "lima" in norm(profile.ubicacion)))
    add("Ubicación y modalidad", 5, 5 if loc_ok else 0,
        "Ubicación compatible; revisar modalidad" if loc_ok else "Ubicación/modalidad por confirmar", bool(location))
    salary = job.get("salario_max")
    minimum = job.get("salario_min_aceptado")
    add("Salario", 5, 5 if salary is not None and minimum is not None and salary >= minimum else 0,
        "Comparación con mínimo aceptado declarado", salary is not None and minimum is not None)
    published = job.get("fecha_publicacion")
    try:
        age = (date.today() - date.fromisoformat(str(published))).days
    except (ValueError, TypeError):
        age = None
    add("Fecha de publicación", 5, 5 if age is not None and 0 <= age <= 7 else 0,
        "Últimos siete días" if age is not None and 0 <= age <= 7 else "Fecha antigua o sin verificar", age is not None and age >= 0)
    score = sum(p["puntos"] for p in parts)
    return {"compatibilidad": score, "cobertura": sum(p["peso"] for p in parts if p["conocido"]),
            "nivel_recomendado": "incompatible" if blocks else "alta prioridad" if score >= 80 else "razonable" if score >= 65 else "revisar" if score >= 50 else "baja evidencia o encaje",
            "requisito_excluyente": bool(blocks), "motivos_exclusion": blocks,
            "brechas": gaps, "datos_pendientes": unknown,
            "componentes": parts, "cv_seleccionado": select_cv(title),
            "vigente": job.get("vigente"), "requiere_intervencion": True,
            "accion_recomendada": "descartar" if blocks else "revisar y preparar"}


def register(db, user_id, profile_id, job, analysis=None):
    job = dict(job)
    job["url"] = safe_url(job.get("url", ""))
    key = fingerprint(job)
    detail = db.query(ApplicationDetail).filter_by(profile_id=profile_id, fingerprint=key).first()
    if detail:
        return db.get(Postulacion, detail.application_id), True
    # Include records made by previous versions in exact-URL deduplication.
    if job["url"]:
        legacy = (db.query(Postulacion, Vacante).join(Vacante, Postulacion.vacante_id == Vacante.id)
                  .filter(Postulacion.profile_id == profile_id).all())
        for old, vacancy in legacy:
            try:
                same = safe_url(vacancy.url) == job["url"]
            except ValueError:
                same = False
            if same:
                return old, True
    # Cross-portal equality is a possible duplicate requiring review, never
    # automatic merging of distinct announcements with the same title.
    for old in db.query(ApplicationDetail).filter_by(profile_id=profile_id).all():
        previous = (old.details or {}).get("vacante", {})
        if all(norm(previous.get(k)) == norm(job.get(k)) for k in ("empresa", "titulo", "ubicacion")):
            job["posible_duplicado_de"] = old.application_id
            break
    vacancy = Vacante(usuario_id=user_id, plataforma=job.get("plataforma", "manual"),
                      url=job["url"], titulo=job["titulo"], empresa=job["empresa"],
                      descripcion=job.get("descripcion", ""))
    db.add(vacancy)
    db.flush()
    status = "incompatible" if (analysis or {}).get("requisito_excluyente") else "descubierta"
    if job.get("posible_duplicado_de"):
        status = "pendiente_revision_duplicado"
    app = Postulacion(usuario_id=user_id, profile_id=profile_id, vacante_id=vacancy.id,
                      estado=status, fecha_envio=None)
    db.add(app)
    db.flush()
    db.add(ApplicationDetail(application_id=app.id, profile_id=profile_id, fingerprint=key,
                             details={"vacante": job, "analisis": analysis or {}}))
    db.add(AuditEvent(application_id=app.id, action="registrada", payload={"estado": status}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        detail = db.query(ApplicationDetail).filter_by(profile_id=profile_id, fingerprint=key).one()
        return db.get(Postulacion, detail.application_id), True
    return app, False
