"""JobFlow AI - API FastAPI + aplicacion web (multi-perfil).

Endpoints principales:
    GET  /                        -> SPA (dashboard, perfiles, analisis, autofill, postulaciones, correo)
    GET  /api/profiles            -> lista de perfiles de candidato
    POST /api/cv/upload           -> subir un CV (PDF/DOCX/TXT) y parsearlo -> nuevo perfil
    GET  /api/profiles/{id}       -> perfil estructurado
    PATCH /api/profiles/{id}      -> corregir datos parseados
    POST /api/analyze             -> gap analysis XYZ (30/30/25/15) del perfil vs puesto
    POST /api/form/prepare        -> pipeline de autofill del perfil activo
    ... y el resto (approve/submit/applications/emails/adapters)
"""
from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import models
from .adapters import ADAPTERS, get_adapter
from .cv_generator import build_docx, optimize_profile, render_cv_html, render_latex, tailored_profile, CV_VARIANTS
from .job_search import PLATFORMS, search_all
from .autofill import (
    TEST_FORM_SCHEMA, approve, create_draft, detect_form, generate_answers,
    map_fields, submit,
)
from .cv_parser import extract_text, parse_cv
from .db import get_db
from .email_monitor import classify_email, enviar_correo
from .gap_analysis import analyze as run_gap_analysis
from .knowledge import build_gabriel
from .config import settings
from .workflow import ApplicationDetail, AuditEvent, evaluate, register, safe_url
from .schemas import JobImportRequest, JobExtractRequest, ApplicationUpdateRequest, EmailImportRequest
from .schemas import (
    ActivePuestoRequest, AnalysisRequest, ApproveRequest, EmailClassifyRequest,
    FormRunRequest, GenerateRequest, PlatformConnectRequest, PostulacionRequest,
    ProfileUpdateRequest, PuestoRequest,
)
from .seed import (
    default_puesto_values, ensure_seed, get_first_user, get_profile_row,
    list_profile_rows, profile_from_row,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_seed()
    from .portal_accounts import browser_status, ensure_worker, recover_interrupted
    if recover_interrupted() and browser_status()[0]:
        ensure_worker()
    import threading
    stop = threading.Event()
    worker = None
    if os.getenv("JOBFLOW_SCHEDULER", "false").lower() == "true":
        from .scheduler import loop
        worker = threading.Thread(target=loop, args=(stop,), daemon=True)
        worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker:
            worker.join(timeout=2)


app = FastAPI(title="JobFlow AI", version="0.6.1", lifespan=lifespan)
from .accounts import current_user, delete_profile, ensure_profile_slots, router as accounts_router
from .career import application as owned_application, router as career_router, require_ready
from .google_integration import router as google_router
from .portal_accounts import router as portals_router
app.include_router(accounts_router)
app.include_router(career_router)
app.include_router(google_router)
app.include_router(portals_router)
# Every /api route needs a JobFlow session; HTTP Basic remains an optional outer guard.
from .security import AccessMiddleware
app.add_middleware(AccessMiddleware)
app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")


def _user(db: Session) -> models.Usuario:
    return current_user(db)


def _form(db: Session, form_id: int) -> models.FormularioResuelto:
    d = db.get(models.FormularioResuelto, form_id)
    if not d or not d.profile_id or not get_profile_row(db, d.profile_id):
        raise HTTPException(404, "Formulario no encontrado")
    return d


def _candidate(db: Session, profile_id: Optional[int] = None):
    """Resuelve el perfiles de candidato (activo o default: el primero)."""
    row = get_profile_row(db, profile_id) if profile_id else None
    if profile_id and not row:
        raise HTTPException(404, "Perfil no encontrado")
    if not row:
        rows = list_profile_rows(db)
        if not rows:
            raise HTTPException(404, "No hay perfiles de candidato. Sube un CV o crea uno.")
        row = rows[0]
    return profile_from_row(row), row


# --------------------------------------------------------------------------- #
#  Web
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


# --------------------------------------------------------------------------- #
#  Perfiles de candidato (multi-CV)
# --------------------------------------------------------------------------- #
@app.get("/api/profiles")
def api_profiles(db: Session = Depends(get_db)):
    user = _user(db)
    rows = list_profile_rows(db)
    return [
        {"id": r.id, "nombre": r.nombre, "fuente_cv": r.fuente_cv,
         "verificado": bool((r.estructura or {}).get("verificado")),
         "postulaciones": db.query(models.Postulacion).filter_by(profile_id=r.id).count(),
         "fecha": r.creado.isoformat() if r.creado else None}
        for r in rows
    ]


@app.post("/api/cv/upload", status_code=201)
async def api_cv_upload(
    file: UploadFile = File(...),
    nombre_hint: str = Form(""),
    profile_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Sin `profile_id` crea el primer perfil; con él reemplaza los datos de ese perfil."""
    user = _user(db)
    target = get_profile_row(db, profile_id) if profile_id else None
    if profile_id and not target:
        raise HTTPException(404, "Perfil no encontrado")
    if not target:
        ensure_profile_slots(db, user)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Formato no soportado: {suffix}. Usa PDF, DOCX o TXT.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            os.unlink(tmp.name)
            raise HTTPException(413, "El CV supera los 10 MB.")
        tmp.write(content)
        tmp_path = tmp.name
    try:
        text = extract_text(tmp_path)
    except Exception:
        raise HTTPException(400, "No se pudo leer el CV. Comprueba que no esté dañado o protegido.")
    finally:
        os.unlink(tmp_path)

    if not text.strip():
        raise HTTPException(400, "No se pudo extraer texto del archivo (¿CV escaneado o sin texto?).")

    profile = parse_cv(text, filename=file.filename or "", nombre_hint=nombre_hint)
    if target:
        # New CV replaces the extracted data; the changed hash forces a new review and confirmation.
        row = target
        profile.nombre = profile.nombre or row.nombre
        row.nombre, row.fuente_cv = profile.nombre, file.filename or "CV subido"
        row.texto_extraido, row.estructura = text[:200000], profile.to_dict()
    else:
        row = models.CandidateProfileRow(
            usuario_id=user.id, nombre=profile.nombre, fuente_cv=file.filename or "CV subido",
            texto_extraido=text[:200000], estructura=profile.to_dict(),
        )
        db.add(row)
        db.flush()
        from .career import Preferences
        db.add(Preferences(profile_id=row.id, data={}))
    # The candidate selects targets only after reviewing extracted facts.
    db.commit()
    db.refresh(row)
    result = profile.to_dict()
    result["id"] = row.id
    result["actualizado"] = bool(target)
    result["texto_extraido"] = text[:1200] + ("…" if len(text) > 1200 else "")
    return result


@app.get("/api/profiles/{profile_id}")
def api_profile_detail(profile_id: int, db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    data = profile_from_row(row).to_dict()
    data["id"] = row.id
    data["fuente_cv"] = row.fuente_cv
    data["texto_extraido"] = (row.texto_extraido or "")[:1200]
    return data


@app.delete("/api/profiles/{profile_id}")
def api_profile_delete(profile_id: int, db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    return delete_profile(db, row)


@app.patch("/api/profiles/{profile_id}")
def api_profile_update(profile_id: int, req: ProfileUpdateRequest, db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    profile = profile_from_row(row)
    for field in ("nombre", "email", "telefono", "ubicacion", "linkedin", "headline",
                  "summary", "seniority", "rango_salarial", "disponibilidad", "movilidad"):
        value = getattr(req, field)
        if value is not None:
            setattr(profile, field, value)
    if req.skills is not None:
        profile.skills = [(s.strip(), "") for s in req.skills if s.strip()]
    for field in ("experiencia", "educacion", "languages", "proyectos", "pendientes"):
        value = getattr(req, field, None)
        if value is not None:
            setattr(profile, field, value)
    if req.skill_levels is not None:
        profile.skills = [(s[0], s[1]) for s in req.skill_levels]
    profile.verificado = False
    profile.hechos_confirmados = {}  # Edits invalidate previous field confirmations.
    row.nombre = profile.nombre
    row.estructura = profile.to_dict()
    db.commit()
    db.refresh(row)
    return profile.to_dict()


# --------------------------------------------------------------------------- #
#  Generacion de CV corregido
# --------------------------------------------------------------------------- #
@app.post("/api/cv/generate")
def api_cv_generate(req: GenerateRequest, db: Session = Depends(get_db)):
    profile, row = _candidate(db, req.profile_id)
    if req.variant not in CV_VARIANTS:
        raise HTTPException(422, "Versión de CV desconocida")
    optimized, changes = tailored_profile(profile, req.variant)
    optimized["id"] = row.id
    return {
        "candidato": profile.nombre,
        "profile_id": row.id,
        "total_correcciones": len(changes),
        "correcciones": changes[:20],
        "cv": optimized,
        "cv_html": render_cv_html(optimized),
        "download_url": f"/api/cv/{row.id}/download?variant={req.variant}",
        "latex": render_latex(optimized),
        "latex_url": f"/api/cv/{row.id}/download?format=latex&variant={req.variant}",
    }


@app.get("/api/cv/{profile_id}/download")
def api_cv_download(profile_id: int, format: str = "docx", variant: str = "maestro", db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    profile = profile_from_row(row)
    if variant not in CV_VARIANTS or format not in ("docx", "latex"):
        raise HTTPException(422, "Formato o versión de CV desconocidos")
    optimized, _ = tailored_profile(profile, variant)
    import re, unicodedata
    ascii_name = unicodedata.normalize("NFKD", optimized["nombre"]).encode("ascii", "ignore").decode()
    fname = (re.sub(r"[^A-Za-z0-9_-]", "_", ascii_name)[:80] or "Candidato") + "_" + variant
    if format == "latex":
        tex = render_latex(optimized)
        return StreamingResponse(
            iter([tex.encode("utf-8")]),
            media_type="application/x-tex",
            headers={"Content-Disposition": f'attachment; filename="{fname}_CV_Optimizado.tex"'},
        )
    bio = build_docx(optimized)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}_CV_Optimizado.docx"'},
    )


# --------------------------------------------------------------------------- #
#  Busqueda de empleo (Bumeran, Computrabajo, LinkedIn, Indeed)
# --------------------------------------------------------------------------- #
@app.post("/api/jobs/search")
def api_jobs_search(req: GenerateRequest, db: Session = Depends(get_db)):
    profile, row = _candidate(db, req.profile_id)
    require_ready(db, row.id)
    platforms = ["bumeran", "computrabajo", "indeed", "linkedin"]
    choices = _puestos(db, row.id)
    active = next((p for p in choices if p.id == req.target_id), None) if req.target_id else next((p for p in choices if p.activo), None)
    if not active:
        raise HTTPException(409, "Selecciona un puesto objetivo guardado.")
    results = search_all(profile, platforms, location=active.ubicacion if active else profile.ubicacion,
                         query=active.titulo if active else None)
    return {
        "candidato": profile.nombre,
        "profile_id": row.id,
        "query": results[0]["query"] if results else "",
        "plataformas": results,
    }


# --------------------------------------------------------------------------- #
#  Puestos objetivo (CRUD + activo)
# --------------------------------------------------------------------------- #
def _puestos(db: Session, profile_id: int):
    return (db.query(models.PuestoObjetivo).filter_by(profile_id=profile_id)
            .order_by(models.PuestoObjetivo.activo.desc(), models.PuestoObjetivo.id.asc()).all())


@app.get("/api/profiles/{profile_id}/puestos")
def api_puestos_list(profile_id: int, db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    rows = _puestos(db, profile_id)
    return [
        {"id": p.id, "titulo": p.titulo, "seniority": p.seniority, "modality": p.modality,
         "ubicacion": p.ubicacion, "rango_salarial": p.rango_salarial,
         "must_haves": p.must_haves, "nice_to_haves": p.nice_to_haves, "activo": bool(p.activo)}
        for p in rows
    ]


@app.post("/api/profiles/{profile_id}/puestos", status_code=201)
def api_puestos_create(profile_id: int, req: PuestoRequest, db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    puesto = models.PuestoObjetivo(profile_id=profile_id, activo=True, titulo=req.titulo,
                                   seniority=req.seniority, modality=req.modality,
                                   ubicacion=req.ubicacion, rango_salarial=req.rango_salarial,
                                   must_haves=req.must_haves, nice_to_haves=req.nice_to_haves)
    db.add(puesto)
    db.flush()
    # desactivar los demas (solo un puesto activo)
    for p in _puestos(db, profile_id):
        if p.id != puesto.id:
            p.activo = False
    db.commit()
    db.refresh(puesto)
    return {"id": puesto.id, "titulo": puesto.titulo, "activo": True}


@app.put("/api/profiles/{profile_id}/puestos/{puesto_id}")
def api_puestos_edit(profile_id: int, puesto_id: int, req: PuestoRequest, db: Session = Depends(get_db)):
    p = db.get(models.PuestoObjetivo, puesto_id)
    if not p or p.profile_id != profile_id or not get_profile_row(db, profile_id):
        raise HTTPException(404, "Puesto no encontrado")
    p.titulo, p.seniority, p.modality = req.titulo, req.seniority, req.modality
    p.ubicacion, p.rango_salarial = req.ubicacion, req.rango_salarial
    p.must_haves, p.nice_to_haves = req.must_haves, req.nice_to_haves
    db.commit()
    return {"id": p.id, "titulo": p.titulo, "activo": bool(p.activo)}


@app.post("/api/profiles/{profile_id}/puestos/activo")
def api_puestos_activo(profile_id: int, req: ActivePuestoRequest, db: Session = Depends(get_db)):
    if not get_profile_row(db, profile_id):
        raise HTTPException(404, "Perfil no encontrado")
    for p in _puestos(db, profile_id):
        p.activo = (p.id == req.puesto_id)
    db.commit()
    return {"activo": req.puesto_id}


# --------------------------------------------------------------------------- #
#  Conexiones de plataformas (Bumeran, LinkedIn, Indeed, Computrabajo, Gmail)
# --------------------------------------------------------------------------- #
@app.get("/api/platforms/connections")
def api_connections(db: Session = Depends(get_db)):
    user = _user(db)
    rows = db.query(models.PlataformaConectada).filter_by(usuario_id=user.id).all()
    if not rows:
        rows = []
        for plat, nota in [("bumeran", "Autofill de formularios"), ("computrabajo", "Autofill de formularios"),
                           ("linkedin", "Copiloto (sin envio automatico)"), ("indeed", "Busqueda de vacantes"),
                           ("gmail", "Correos de reclutamiento")]:
            r = models.PlataformaConectada(usuario_id=user.id, plataforma=plat, conectada=False, nota=nota)
            db.add(r)
            rows.append(r)
        db.commit()
    return [
        {"plataforma": r.plataforma, "conectada": False, "nota": r.nota,
         "actualizada": r.actualizada.isoformat() if r.actualizada else None}
        for r in rows
    ]


@app.put("/api/platforms/connections")
def api_connection_update(req: PlatformConnectRequest, db: Session = Depends(get_db)):
    raise HTTPException(409, "La conexión de cuentas aún no está implementada. Marcar una casilla no inicia sesión.")


# --------------------------------------------------------------------------- #
#  Postular desde Empleos -> Tracker + correo automatico
# --------------------------------------------------------------------------- #
@app.post("/api/postulaciones", status_code=201)
def api_postular(req: PostulacionRequest, db: Session = Depends(get_db)):
    user = _user(db)
    profile, row = _candidate(db, req.profile_id)
    if not req.titulo.strip() or not req.empresa.strip():
        raise HTTPException(422, "Indica empresa y puesto para guardar la oportunidad.")
    job = req.model_dump()
    try:
        post, duplicate = register(db, user.id, row.id, job, evaluate(profile, job))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"postulacion_id": post.id, "vacante_id": post.vacante_id,
            "estado": post.estado, "duplicada": duplicate, "enviada": False}


# --------------------------------------------------------------------------- #
#  Analisis XYZ
# --------------------------------------------------------------------------- #
@app.post("/api/analyze")
def api_analyze(req: AnalysisRequest, db: Session = Depends(get_db)):
    user = _user(db)
    profile, row = _candidate(db, req.profile_id)
    # Usar el puesto objetivo activo del perfil (la fuente de verdad)
    puesto = next((p for p in _puestos(db, row.id) if p.activo), None)
    if req.usar_puesto and puesto:
        target, seniority = puesto.titulo, puesto.seniority
        must, nice = list(puesto.must_haves or []), list(puesto.nice_to_haves or [])
    else:
        target, seniority = req.target_role, req.seniority
        must, nice = req.must_haves, req.nice_to_haves
    result = run_gap_analysis(profile, target, seniority, must, nice, req.jd_text)
    db.add(models.GapAnalysis(
        cv_id=None, profile_id=row.id,
        puesto_objetivo=target,
        score_global=result["score_global"],
        score_keywords=result["components"][0]["score"],
        score_experiencia=result["components"][1]["score"],
        score_star=result["components"][2]["score"],
        score_formato_ats=result["components"][3]["score"],
        brechas=result["gaps"],
        sugerencias=result["reescrituras"],
    ))
    db.commit()
    return result


@app.get("/api/overview")
def api_overview(profile_id: Optional[int] = None, db: Session = Depends(get_db)):
    user = _user(db)
    _, row = _candidate(db, profile_id)
    last = (db.query(models.GapAnalysis)
            .filter_by(profile_id=row.id)
            .order_by(models.GapAnalysis.creado.desc()).first())
    records = db.query(models.Postulacion).filter_by(profile_id=row.id).all()
    apps = sum(bool(db.query(AuditEvent).filter_by(application_id=p.id, action="postulada").first()) for p in records)
    pendientes = (db.query(models.EmailMonitoreado)
                  .filter_by(usuario_id=user.id, estado="pendiente").count())
    adapters = [get_adapter(p, build_gabriel()).status() for p in ADAPTERS]
    puesto = next((p for p in _puestos(db, row.id) if p.activo), None)
    return {
        "candidato": row.nombre,
        "profile_id": row.id,
        "score_global": last.score_global if last else None,
        "puesto_objetivo": {"titulo": puesto.titulo, "seniority": puesto.seniority,
                            "rango_salarial": puesto.rango_salarial} if puesto else None,
        "puesto_analizado": last.puesto_objetivo if last else None,
        "postulaciones": apps,
        "oportunidades": len(records),
        "correos_pendientes": pendientes,
        "adapters": adapters,
    }


@app.get("/api/adapters")
def api_adapters():
    return [get_adapter(p, build_gabriel()).status() for p in ADAPTERS]


# --------------------------------------------------------------------------- #
#  Pipeline de autofill
# --------------------------------------------------------------------------- #
@app.get("/api/form/test-schema")
def api_test_schema():
    return TEST_FORM_SCHEMA


@app.post("/api/form/prepare")
def api_form_prepare(req: FormRunRequest, db: Session = Depends(get_db)):
    user = _user(db)
    profile, row = _candidate(db, req.profile_id)
    if req.platform != "test" and not req.form_schema:
        raise HTTPException(422, "Pega las preguntas reales; el formulario de ejemplo no representa al portal.")
    fields = detect_form(req.form_schema)
    mapping = map_fields(fields)
    answers = generate_answers(mapping, profile, req.vacante_titulo)
    draft = create_draft(db, row.id, req.platform, req.vacante_titulo, fields, mapping, answers)
    return {
        "form_id": draft.id,
        "plataforma": draft.plataforma,
        "vacante": req.vacante_titulo,
        "candidato": profile.nombre,
        "fields": fields,
        "mapping": mapping,
        "answers": answers,
        "regla_humana": "Borrador para revisión. No se envía al portal.",
    }


@app.get("/api/form/{form_id}")
def api_form_get(form_id: int, db: Session = Depends(get_db)):
    d = _form(db, form_id)
    return {
        "form_id": d.id, "plataforma": d.plataforma,
        "campos": d.campos_detectados, "mapeo": d.mapeo_semantico,
        "respuestas": d.respuestas_generadas,
        "aprobado": d.aprobado_por_usuario, "enviado": d.enviado,
    }


@app.post("/api/form/{form_id}/approve")
def api_form_approve(form_id: int, req: ApproveRequest, db: Session = Depends(get_db)):
    _form(db, form_id)
    try:
        d = approve(db, form_id, req.edits)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not d:
        raise HTTPException(404, "Formulario no encontrado")
    return {"aprobado": True, "form_id": d.id, "respuestas": d.respuestas_generadas}


@app.post("/api/form/{form_id}/submit")
def api_form_submit(form_id: int, db: Session = Depends(get_db)):
    _form(db, form_id)
    try:
        d = submit(db, form_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not d:
        raise HTTPException(409, "Revisa y aprueba el formulario primero.")
    return {"enviado": False, "simulado": True, "estado": "demostracion_completada",
            "form_id": d.id, "mensaje": "Prueba completada. No se envió ninguna postulación a una empresa."}


# --------------------------------------------------------------------------- #
#  Correo / postulaciones
# --------------------------------------------------------------------------- #
@app.get("/api/emails")
def api_emails(db: Session = Depends(get_db)):
    user = _user(db)
    rows = (db.query(models.EmailMonitoreado).filter_by(usuario_id=user.id)
            .order_by(models.EmailMonitoreado.fecha.desc()).all())
    out = []
    for e in rows:
        fr = db.query(models.FormularioResuelto).filter_by(email_id=e.id).order_by(
            models.FormularioResuelto.id.desc()).first()
        out.append({
            "id": e.id, "remitente": e.remitente, "asunto": e.asunto,
            "clasificacion": e.clasificacion, "tiene_formulario": e.tiene_formulario,
            "estado": e.estado,
            "form_id": fr.id if fr else None,
            "form_enviado": bool(fr and fr.enviado),
        })
    return out


@app.post("/api/emails/{email_id}/resolver", status_code=201)
def api_email_resolver(email_id: int, db: Session = Depends(get_db)):
    """Conecta el correo con la solicitud: crea el formulario (pipeline de autofill)
    vinculado a ese correo, para aprobar y enviar desde la pestana Autofill."""
    raise HTTPException(409, "Pega las preguntas del enlace en Preparar respuestas. No se ha abierto ni enviado el formulario del correo.")


@app.post("/api/emails/classify")
def api_emails_classify(req: EmailClassifyRequest):
    return classify_email(req.remitente, req.asunto, req.cuerpo)


@app.get("/api/applications")
def api_applications(profile_id: Optional[int] = None, db: Session = Depends(get_db)):
    user = _user(db)
    q = db.query(models.Postulacion).filter_by(usuario_id=user.id)
    if profile_id:
        q = q.filter_by(profile_id=profile_id)
    rows = q.order_by(models.Postulacion.creado.desc()).all()
    out = []
    for p in rows:
        vacante = db.get(models.Vacante, p.vacante_id) if p.vacante_id else None
        correo = (db.query(models.EmailEnviado).filter_by(postulacion_id=p.id)
                  .order_by(models.EmailEnviado.id.desc()).first())
        detail = db.query(ApplicationDetail).filter_by(application_id=p.id).first()
        events = db.query(AuditEvent).filter_by(application_id=p.id).order_by(AuditEvent.id).all()
        confirmed = any(e.action == "postulada" for e in events)
        shown_status = p.estado
        if p.estado in ("enviado", "enviada_desde_busqueda", "postulada") and not confirmed:
            shown_status = "intento_no_confirmado"
        out.append({
            "detalle": detail.details if detail else {},
            "auditoria": [{"accion": e.action, "datos": e.payload, "fecha": e.created.isoformat()} for e in events],
            "id": p.id, "estado": shown_status,
            "fecha": p.fecha_envio.isoformat() if p.fecha_envio else None,
            "n_respuestas": len(p.respuestas_formulario or []),
            "vacante": {
                "titulo": vacante.titulo if vacante else "",
                "empresa": vacante.empresa if vacante else "",
                "plataforma": vacante.plataforma if vacante else "",
                "url": vacante.url if vacante else "",
            } if vacante else None,
            "correo": {"estado": correo.estado, "destinatario": correo.destinatario,
                       "asunto": correo.asunto} if correo else None,
        })
    return out


@app.get("/healthz")
def health():
    return {"status": "ok", "version": "0.6.1"}


@app.post("/api/jobs/extract")
def extract_job_posting(req: JobExtractRequest):
    from .job_extract import ExtractionError, extract_job
    try:
        return extract_job(req.url)
    except (ExtractionError, ValueError) as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/jobs/import", status_code=201)
def import_job(req: JobImportRequest, db: Session = Depends(get_db)):
    profile, row = _candidate(db, req.profile_id)
    job = req.model_dump(exclude={"profile_id"})
    job["titulo"], job["empresa"] = job["titulo"].strip(), job["empresa"].strip()
    if not job["titulo"] or not job["empresa"]:
        raise HTTPException(422, "Empresa y puesto son obligatorios.")
    analysis = evaluate(profile, job)
    try:
        app, duplicate = register(db, _user(db).id, row.id, job, analysis)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"id": app.id, "estado": app.estado, "duplicada": duplicate, "analisis": analysis}


@app.patch("/api/applications/{application_id}")
def update_application(application_id: int, req: ApplicationUpdateRequest, db: Session = Depends(get_db)):
    app, _ = owned_application(db, application_id)
    if req.estado == "duplicado_descartado":
        if app.estado != "pendiente_revision_duplicado" or not req.nota.strip():
            raise HTTPException(422, "Indica por qué los anuncios corresponden a vacantes diferentes.")
        detail = db.query(ApplicationDetail).filter_by(application_id=app.id).first()
        excluded = (detail.details or {}).get("analisis", {}).get("requisito_excluyente") if detail else False
        app.estado = "incompatible" if excluded else "descubierta"
        db.add(AuditEvent(application_id=app.id, action="duplicado_descartado", payload={"nota": req.nota}))
        db.commit()
        return {"id": app.id, "estado": app.estado}
    allowed = {"descubierta", "preparada", "intento_no_confirmado", "postulada", "en_revision",
               "cv_leido", "contactado", "entrevista", "evaluacion", "rechazada", "oferta", "vencida"}
    if req.estado not in allowed:
        raise HTTPException(422, "Estado no permitido")
    if app.estado in ("incompatible", "pendiente_revision_duplicado") and req.estado not in ("rechazada", "vencida"):
        raise HTTPException(409, "Esta vacante está bloqueada por requisitos o posible duplicado. Revisa el aviso original.")
    confirmed = db.query(AuditEvent).filter_by(application_id=app.id, action="postulada").first()
    if req.estado in ("en_revision", "cv_leido", "contactado", "entrevista", "evaluacion", "oferta") and not confirmed:
        raise HTTPException(409, "Registra primero la evidencia de la postulación.")
    if req.estado == "postulada":
        if req.cv_version_id is not None:
            from .career import CVVersion
            version = db.get(CVVersion, req.cv_version_id)
            if not version or version.application_id != app.id or not version.snapshot.get("approved"):
                raise HTTPException(409, "Selecciona una versión aprobada de esta candidatura.")
        if req.tipo_evidencia not in ("mensaje_portal", "correo_confirmacion", "id_candidatura") or not req.evidencia.strip():
            raise HTTPException(422, "Indica el mensaje del portal, correo de confirmación o ID de candidatura.")
        if not app.fecha_envio:
            app.fecha_envio = datetime.utcnow()
    app.estado = req.estado
    db.add(AuditEvent(application_id=app.id, action=req.estado, payload={
        "fuente": "Registro manual del candidato; no verificación automática del portal",
        "tipo_evidencia": req.tipo_evidencia, "evidencia": req.evidencia.strip(), "nota": req.nota, "cv_version_id": req.cv_version_id}))
    db.commit()
    return {"id": app.id, "estado": app.estado}


@app.get("/api/tracker/export")
def export_tracker(profile_id: Optional[int] = None, db: Session = Depends(get_db)):
    import json
    content = json.dumps(api_applications(profile_id, db), ensure_ascii=False, indent=2).encode()
    return StreamingResponse(iter([content]), media_type="application/json",
                             headers={"Content-Disposition": 'attachment; filename="jobflow-seguimiento.json"'})


@app.post("/api/emails/import", status_code=201)
def import_email(req: EmailImportRequest, db: Session = Depends(get_db)):
    user = _user(db)
    previous = db.query(models.EmailMonitoreado).filter_by(
        usuario_id=user.id, remitente=req.remitente, asunto=req.asunto, cuerpo=req.cuerpo).first()
    if previous:
        return {"id": previous.id, "duplicado": True}
    result = classify_email(req.remitente, req.asunto, req.cuerpo)
    email = models.EmailMonitoreado(usuario_id=user.id, remitente=req.remitente, asunto=req.asunto,
                                   cuerpo=req.cuerpo, clasificacion=result["clasificacion"],
                                   tiene_formulario=result["tiene_formulario"], estado="importado_manualmente")
    db.add(email)
    db.commit()
    return {"id": email.id, "duplicado": False, "clasificacion": result,
            "nota": "Texto importado; identidad del remitente y enlaces no verificados."}


@app.post("/api/applications/{application_id}/prepare")
def prepare_application(application_id: int, req: FormRunRequest, db: Session = Depends(get_db)):
    app, _ = owned_application(db, application_id)
    if app.estado in ("incompatible", "pendiente_revision_duplicado", "vencida", "rechazada"):
        raise HTTPException(409, "Esta oportunidad requiere revisión antes de preparar respuestas.")
    if db.query(AuditEvent).filter_by(application_id=app.id, action="postulada").first():
        raise HTTPException(409, "Ya registraste una postulación; usa Respuestas para cuestionarios posteriores.")
    if not req.form_schema:
        raise HTTPException(422, "Pega las preguntas reales del portal, una por línea.")
    profile, row = _candidate(db, app.profile_id)
    if req.profile_id and req.profile_id != row.id:
        raise HTTPException(409, "La oportunidad pertenece a otro perfil.")
    vacancy = db.get(models.Vacante, app.vacante_id)
    detail = db.query(ApplicationDetail).filter_by(application_id=app.id).first()
    variant = (detail.details or {}).get("analisis", {}).get("cv_seleccionado", "maestro") if detail else "maestro"
    fields = detect_form(req.form_schema)
    mapping = map_fields(fields)
    answers = generate_answers(mapping, profile, vacancy.titulo if vacancy else "")
    draft = create_draft(db, row.id, "manual", vacancy.titulo if vacancy else "", fields, mapping, answers)
    draft.postulacion_id = app.id
    app.estado = "preparada"
    app.respuestas_formulario = answers
    cv, _ = tailored_profile(profile, variant)
    from .career import CVVersion, profile_hash
    approved_versions = db.query(CVVersion).filter_by(application_id=app.id).order_by(CVVersion.id.desc()).all()
    selected = next((v for v in approved_versions if v.snapshot.get("approved")
                     and v.snapshot.get("profile_hash") == profile_hash(row)), None)
    if selected:
        cv = selected.snapshot["cv"]
    db.add(AuditEvent(application_id=app.id, action="preparada", payload={
        "form_id": draft.id, "cv_variante": variant, "perfil_snapshot": profile.to_dict(),
        "cv_version_id": selected.id if selected else None,
        "cv_latex": render_latex(cv), "respuestas_borrador": answers}))
    db.commit()
    return {"form_id": draft.id, "plataforma": "manual", "vacante": vacancy.titulo if vacancy else "",
            "candidato": profile.nombre, "answers": answers,
            "regla_humana": "Borrador vinculado al seguimiento. Revisa antes de copiar al portal."}
