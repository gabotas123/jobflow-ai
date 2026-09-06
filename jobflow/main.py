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
from .cv_generator import build_docx, optimize_profile, render_cv_html, render_latex
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
    yield


app = FastAPI(title="JobFlow AI", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")


def _user(db: Session) -> models.Usuario:
    u = get_first_user(db)
    if not u:
        raise HTTPException(500, "Sin usuario demo")
    return u


def _candidate(db: Session, profile_id: Optional[int] = None):
    """Resuelve el perfiles de candidato (activo o default: el primero)."""
    row = get_profile_row(db, profile_id) if profile_id else None
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
         "fecha": r.creado.isoformat() if r.creado else None}
        for r in rows
    ]


@app.post("/api/cv/upload", status_code=201)
async def api_cv_upload(
    file: UploadFile = File(...),
    nombre_hint: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _user(db)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Formato no soportado: {suffix}. Usa PDF, DOCX o TXT.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        text = extract_text(tmp_path)
    finally:
        os.unlink(tmp_path)

    if not text.strip():
        raise HTTPException(400, "No se pudo extraer texto del archivo (¿CV escaneado o sin texto?).")

    profile = parse_cv(text, filename=file.filename or "", nombre_hint=nombre_hint)
    row = models.CandidateProfileRow(
        usuario_id=user.id, nombre=profile.nombre, fuente_cv=file.filename or "CV subido",
        texto_extraido=text[:200000], estructura=profile.to_dict(),
    )
    db.add(row)
    db.flush()
    # Puesto objetivo por defecto (cargo principal + dominio)
    pv = default_puesto_values(profile)
    db.add(models.PuestoObjetivo(profile_id=row.id, activo=True, **pv))
    db.commit()
    db.refresh(row)
    result = profile.to_dict()
    result["id"] = row.id
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
    optimized, changes = optimize_profile(profile)
    optimized["id"] = row.id
    return {
        "candidato": profile.nombre,
        "profile_id": row.id,
        "total_correcciones": len(changes),
        "correcciones": changes[:20],
        "cv": optimized,
        "cv_html": render_cv_html(optimized),
        "download_url": f"/api/cv/{row.id}/download",
        "latex": render_latex(optimized),
        "latex_url": f"/api/cv/{row.id}/download?format=latex",
    }


@app.get("/api/cv/{profile_id}/download")
def api_cv_download(profile_id: int, format: str = "docx", db: Session = Depends(get_db)):
    row = get_profile_row(db, profile_id)
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    profile = profile_from_row(row)
    optimized, _ = optimize_profile(profile)
    fname = optimized["nombre"].replace(" ", "_").replace(" ", "_")
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
    platforms = ["bumeran", "computrabajo", "indeed", "linkedin"]
    results = search_all(profile, platforms)
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
    if not rows:  # backfill: CVs subidos antes de la funcion de puestos
        profile = profile_from_row(row)
        if profile.verificado:  # perfil semilla: puesto de cobranzas con su rango
            from .seed import DEFAULT_ROLE
            pv = {"titulo": DEFAULT_ROLE["target_role"], "seniority": DEFAULT_ROLE["seniority"],
                  "modality": "Presencial o hibrido", "ubicacion": profile.ubicacion,
                  "rango_salarial": "S/2500 - S/2800",
                  "must_haves": DEFAULT_ROLE["must"], "nice_to_haves": DEFAULT_ROLE["nice"]}
        else:
            pv = default_puesto_values(profile)
        p = models.PuestoObjetivo(profile_id=profile_id, activo=True, **pv)
        db.add(p)
        db.commit()
        db.refresh(p)
        rows = [p]
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
    if not p or p.profile_id != profile_id:
        raise HTTPException(404, "Puesto no encontrado")
    p.titulo, p.seniority, p.modality = req.titulo, req.seniority, req.modality
    p.ubicacion, p.rango_salarial = req.ubicacion, req.rango_salarial
    p.must_haves, p.nice_to_haves = req.must_haves, req.nice_to_haves
    db.commit()
    return {"id": p.id, "titulo": p.titulo, "activo": bool(p.activo)}


@app.post("/api/profiles/{profile_id}/puestos/activo")
def api_puestos_activo(profile_id: int, req: ActivePuestoRequest, db: Session = Depends(get_db)):
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
        {"plataforma": r.plataforma, "conectada": bool(r.conectada), "nota": r.nota,
         "actualizada": r.actualizada.isoformat() if r.actualizada else None}
        for r in rows
    ]


@app.put("/api/platforms/connections")
def api_connection_update(req: PlatformConnectRequest, db: Session = Depends(get_db)):
    user = _user(db)
    r = db.query(models.PlataformaConectada).filter_by(usuario_id=user.id,
                                                      plataforma=req.plataforma).first()
    if not r:
        r = models.PlataformaConectada(usuario_id=user.id, plataforma=req.plataforma, nota="")
        db.add(r)
    r.conectada = req.conectada
    db.commit()
    return {"plataforma": r.plataforma, "conectada": bool(r.conectada)}


# --------------------------------------------------------------------------- #
#  Postular desde Empleos -> Tracker + correo automatico
# --------------------------------------------------------------------------- #
@app.post("/api/postulaciones", status_code=201)
def api_postular(req: PostulacionRequest, db: Session = Depends(get_db)):
    user = _user(db)
    # vincular (o crear) la vacante
    vacante = None
    if req.url:
        vacante = db.query(models.Vacante).filter_by(url=req.url.strip()).first()
    if not vacante:
        vacante = models.Vacante(usuario_id=user.id, plataforma=req.plataforma, url=req.url,
                                 titulo=req.titulo, empresa=req.empresa)
        db.add(vacante)
        db.flush()
    post = models.Postulacion(
        usuario_id=user.id, profile_id=req.profile_id, vacante_id=vacante.id,
        estado=req.estado, fecha_envio=datetime.utcnow(), respuestas_formulario=[],
    )
    db.add(post)
    db.flush()

    # correo automatico (simulado si no hay SMTP) - conector correo <-> solicitud
    correo = enviar_correo(
        db, user.id, destinatario=user.email,
        asunto=f"Postulacion registrada: {req.titulo} - {req.empresa}",
        cuerpo=(f"Registraste una postulacion desde JobFlow AI.\n"
                f"Puesto: {req.titulo}\nEmpresa: {req.empresa}\n"
                f"Plataforma: {req.plataforma}\nEnlace: {req.url}"),
        postulacion_id=post.id,
    )
    db.commit()
    db.refresh(post)
    return {"postulacion_id": post.id, "vacante_id": vacante.id, "estado": post.estado,
            "correo": {"estado": correo.estado, "destinatario": correo.destinatario}}


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
    apps = db.query(models.Postulacion).filter_by(profile_id=row.id).count()
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
        "regla_humana": "La postulacion solo se registra tras tu aprobacion.",
    }


@app.get("/api/form/{form_id}")
def api_form_get(form_id: int, db: Session = Depends(get_db)):
    d = db.get(models.FormularioResuelto, form_id)
    if not d:
        raise HTTPException(404, "Formulario no encontrado")
    return {
        "form_id": d.id, "plataforma": d.plataforma,
        "campos": d.campos_detectados, "mapeo": d.mapeo_semantico,
        "respuestas": d.respuestas_generadas,
        "aprobado": d.aprobado_por_usuario, "enviado": d.enviado,
    }


@app.post("/api/form/{form_id}/approve")
def api_form_approve(form_id: int, req: ApproveRequest, db: Session = Depends(get_db)):
    d = approve(db, form_id, req.edits)
    if not d:
        raise HTTPException(404, "Formulario no encontrado")
    return {"aprobado": True, "form_id": d.id, "respuestas": d.respuestas_generadas}


@app.post("/api/form/{form_id}/submit")
def api_form_submit(form_id: int, db: Session = Depends(get_db)):
    user = _user(db)
    d = submit(db, form_id)
    if not d:
        raise HTTPException(400, "Formulario no aprobado por el usuario (regla human-in-the-loop).")
    postulacion = models.Postulacion(
        usuario_id=user.id, profile_id=d.profile_id,
        estado="enviado", fecha_envio=datetime.utcnow(),
        respuestas_formulario=d.respuestas_generadas,
    )
    db.add(postulacion)
    db.flush()
    # Conector correo <-> solicitud: si el formulario vino de un correo, marcarlo resuelto
    if d.email_id:
        email = db.get(models.EmailMonitoreado, d.email_id)
        if email:
            email.estado = "resuelto"
        postulacion.respuestas_formulario = d.respuestas_generadas
    # notificacion automatica del proceso (simulada si no hay SMTP)
    correo = enviar_correo(
        db, user.id, destinatario=user.email,
        asunto="Formulario de postulacion completado (JobFlow AI)",
        cuerpo=f"Se registro la postulacion #{postulacion.id} con las respuestas aprobadas.",
        postulacion_id=postulacion.id,
    )
    db.commit()
    db.refresh(postulacion)
    return {"enviado": True, "postulacion_id": postulacion.id,
            "correo": {"estado": correo.estado, "destinatario": correo.destinatario},
            "regla": "Registrada solo porque tenia aprobacion humana."}


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
    user = _user(db)
    email = db.get(models.EmailMonitoreado, email_id)
    if not email:
        raise HTTPException(404, "Correo no encontrado")
    profile, row = _candidate(db, None)
    vacante_titulo = email.asunto.split(" - ")[-1].strip()[:60] or "Solicitud de empleo"
    fields = detect_form(None)
    mapping = map_fields(fields)
    answers = generate_answers(mapping, profile, vacante_titulo)
    draft = create_draft(db, row.id, "email", vacante_titulo, fields, mapping, answers)
    draft.email_id = email.id
    db.commit()
    db.refresh(draft)
    return {
        "form_id": draft.id, "plataforma": draft.plataforma, "vacante": vacante_titulo,
        "candidato": profile.nombre, "fields": fields, "mapping": mapping,
        "answers": answers,
        "regla_humana": "La postulacion solo se registra tras tu aprobacion.",
    }


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
        out.append({
            "id": p.id, "estado": p.estado,
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
