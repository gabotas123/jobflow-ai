"""Cuentas de JobFlow: usuario y contraseña propios de la app, con sesiones independientes.

No confundir con las cuentas de los portales (portal_accounts.py): de esos portales
JobFlow nunca pide ni guarda contraseñas. Aquí solo se guarda un hash scrypt de la
contraseña con la que cada persona entra a JobFlow.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, inspect, or_, text
from sqlalchemy.orm import Session

from .db import SessionLocal, engine, get_db
from .models import Base, CandidateProfileRow, EmailMonitoreado, Postulacion, Usuario, Vacante

router = APIRouter()
COOKIE = "jobflow_session"
SESSION_DAYS = 30
MAX_FAILURES, LOCK_SECONDS = 5, 300
MAX_PROFILES = int(os.getenv("JOBFLOW_MAX_PROFILES", "3"))
# Usuario de la petición en curso. None solo fuera de una petición (hilos de fondo).
CURRENT_USER: ContextVar[int | None] = ContextVar("jobflow_user", default=None)
_failures: dict[str, tuple[int, float]] = {}
_failures_lock = threading.Lock()


class AppSession(Base):
    __tablename__ = "app_sessions"
    token_hash = Column(String, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True)
    created = Column(DateTime, default=datetime.utcnow)
    expires = Column(DateTime)


def migrate() -> None:
    """Añade las columnas de acceso a bases creadas antes de las cuentas."""
    cols = {c["name"] for c in inspect(engine).get_columns("usuarios")}
    with engine.begin() as conn:
        if "username" not in cols:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN username VARCHAR"))
        if "password_hash" not in cols:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN password_hash VARCHAR DEFAULT ''"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_usuarios_username ON usuarios (username)"))


# --------------------------------------------------------------------------- #
#  Contraseñas y sesiones
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                   dklen=len(base64.b64decode(digest)))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(12))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_user_id(token: str) -> int | None:
    if not token:
        return None
    db = SessionLocal()
    try:
        s = db.get(AppSession, _token_hash(token))
        if not s or s.expires < datetime.utcnow():
            return None
        return s.usuario_id
    finally:
        db.close()


def auth_response(request: Request) -> JSONResponse | None:
    """401 si la ruta de la API requiere sesión y no hay una válida."""
    path = request.url.path
    if not path.startswith("/api/") or path.startswith(("/api/auth/", "/api/google/callback")):
        return None
    uid = session_user_id(request.cookies.get(COOKIE, ""))
    if not uid:
        return JSONResponse({"detail": "Inicia sesión para continuar."}, status_code=401)
    request.state.user_id = uid
    return None


def current_user(db: Session) -> Usuario:
    uid = CURRENT_USER.get()
    user = db.get(Usuario, uid) if uid else None
    if not user:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return user


def can_access(row: CandidateProfileRow | None) -> bool:
    """Un perfil solo es visible para la cuenta dueña (sin restricción en hilos de fondo)."""
    if row is None:
        return False
    uid = CURRENT_USER.get()
    return uid is None or row.usuario_id == uid


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


def _start_session(request: Request, db: Session, user: Usuario, status_code: int = 200) -> JSONResponse:
    db.query(AppSession).filter(AppSession.expires < datetime.utcnow()).delete()
    token = secrets.token_urlsafe(32)
    db.add(AppSession(token_hash=_token_hash(token), usuario_id=user.id,
                      expires=datetime.utcnow() + timedelta(days=SESSION_DAYS)))
    db.commit()
    response = JSONResponse(user_data(user), status_code=status_code)
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=_secure(request), path="/")
    return response


def user_data(user: Usuario) -> dict:
    return {"id": user.id, "username": user.username, "nombre": user.nombre or user.username,
            "max_profiles": MAX_PROFILES}


# --------------------------------------------------------------------------- #
#  Perfiles por cuenta: límite y borrado
# --------------------------------------------------------------------------- #
def ensure_profile_slots(db: Session, user: Usuario, adding: int = 1) -> None:
    count = db.query(CandidateProfileRow).filter_by(usuario_id=user.id).count()
    if count + adding > MAX_PROFILES:
        extra = " o marca menos perfiles" if adding > 1 else ""
        raise HTTPException(409, f"Puedes tener hasta {MAX_PROFILES} perfiles y ya tienes {count}. "
                                 f"Borra alguno para crear otro{extra}.")


def delete_profile(db: Session, row: CandidateProfileRow) -> dict:
    """Borra el perfil y todo lo que depende de él: candidaturas, CV, agenda, conexiones y evidencias."""
    from . import portal_accounts as portals
    from .career import AgendaEvent, CVVersion, Preferences, Recruiter
    from .config import settings
    from .google_integration import Delivery, GoogleConnection, ImportedMessage, OAuthState
    from .models import EmailEnviado, FormularioResuelto, GapAnalysis, PuestoObjetivo
    from .workflow import ApplicationDetail, AuditEvent

    pid = row.id
    busy = db.query(portals.AutoApplyRun).filter(portals.AutoApplyRun.profile_id == pid,
                                                 portals.AutoApplyRun.status.in_(portals.ACTIVE_RUNS)).first()
    if portals.login_active(pid) or busy:
        raise HTTPException(409, "Este perfil tiene una ventana de inicio de sesión o una postulación en curso. "
                                 "Espera a que termine para borrarlo.")

    def gone(model, *criteria):
        return db.query(model).filter(*criteria).delete(synchronize_session=False)

    apps = db.query(Postulacion).filter_by(profile_id=pid).all()
    aids = [a.id for a in apps]
    vacancy_ids = {a.vacante_id for a in apps if a.vacante_id}
    shots = [(r.detail or {}).get("captura") for r in db.query(portals.AutoApplyRun).filter_by(profile_id=pid)]
    if aids:
        for model in (AuditEvent, ApplicationDetail, CVVersion, Recruiter, AgendaEvent, portals.AutoApplyRun):
            gone(model, model.application_id.in_(aids))
        gone(EmailEnviado, EmailEnviado.postulacion_id.in_(aids))
        gone(FormularioResuelto, FormularioResuelto.postulacion_id.in_(aids))
    email_ids = [m.email_id for m in db.query(ImportedMessage).filter_by(profile_id=pid)]
    if email_ids:
        gone(EmailMonitoreado, EmailMonitoreado.id.in_(email_ids))
    for model in (ImportedMessage, GoogleConnection, OAuthState, AgendaEvent, FormularioResuelto, GapAnalysis,
                  PuestoObjetivo, ApplicationDetail, portals.AutoApplyRun, portals.PortalAccount, Preferences):
        gone(model, model.profile_id == pid)
    gone(Delivery, Delivery.key.like(f"digest:{pid}:%"))
    gone(Postulacion, Postulacion.profile_id == pid)
    if vacancy_ids:
        still_used = {v for (v,) in db.query(Postulacion.vacante_id).filter(Postulacion.vacante_id.in_(vacancy_ids))}
        if vacancy_ids - still_used:
            gone(Vacante, Vacante.id.in_(vacancy_ids - still_used))
    db.delete(row)
    db.commit()

    # SQLite may reuse the id of the last row, so nothing keyed by this id may survive.
    for name in filter(None, shots):
        (portals.evidence_dir() / name).unlink(missing_ok=True)
    shutil.rmtree(Path(settings.data_dir).resolve() / "navegador" / f"perfil_{pid}", ignore_errors=True)
    with portals.LOGIN_LOCK:
        for key in [k for k in portals.LOGINS if k[0] == pid]:
            portals.LOGINS.pop(key, None)
    return {"deleted": True, "id": pid, "postulaciones": len(aids)}


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,40}$")


class Credentials(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, v):
        return v.strip().lower()


class Registration(Credentials):
    nombre: str = Field(default="", max_length=120)

    @field_validator("username")
    @classmethod
    def valid_username(cls, v):
        if not USERNAME_RE.match(v):
            raise ValueError("El usuario debe tener de 3 a 40 caracteres: letras, números, punto o guiones, sin espacios.")
        return v

    @field_validator("password")
    @classmethod
    def valid_password(cls, v):
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v


@router.post("/api/auth/register", status_code=201)
def register(req: Registration, request: Request, db: Session = Depends(get_db)):
    if db.query(Usuario).filter_by(username=req.username).first():
        raise HTTPException(409, "Ese usuario ya existe. Elige otro o inicia sesión.")
    user = Usuario(nombre=req.nombre.strip() or req.username, username=req.username,
                   password_hash=hash_password(req.password), email=None)
    db.add(user)
    db.flush()
    return _start_session(request, db, user, status_code=201)


@router.post("/api/auth/login")
def login(req: Credentials, request: Request, db: Session = Depends(get_db)):
    now = time.monotonic()
    with _failures_lock:
        count, until = _failures.get(req.username, (0, 0.0))
    if until > now:
        raise HTTPException(429, f"Demasiados intentos. Espera {int(until - now) // 60 + 1} min y vuelve a intentarlo.")
    user = db.query(Usuario).filter_by(username=req.username).first() if req.username else None
    ok = verify_password(req.password, user.password_hash if user and user.password_hash else _DUMMY_HASH)
    if not (user and user.password_hash and ok):
        with _failures_lock:
            count += 1
            _failures[req.username] = (0, now + LOCK_SECONDS) if count >= MAX_FAILURES else (count, 0.0)
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    with _failures_lock:
        _failures.pop(req.username, None)
    return _start_session(request, db, user)


@router.post("/api/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    if token:
        db.query(AppSession).filter_by(token_hash=_token_hash(token)).delete()
        db.commit()
    response = JSONResponse({"logged_out": True})
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/api/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    uid = session_user_id(request.cookies.get(COOKIE, ""))
    user = db.get(Usuario, uid) if uid else None
    if not user:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return user_data(user)


def unclaimed_rows(db: Session) -> list[CandidateProfileRow]:
    """Perfiles creados antes de las cuentas (dueño sin contraseña o sin dueño)."""
    legacy = [u.id for u in db.query(Usuario).filter(or_(Usuario.password_hash.is_(None), Usuario.password_hash == ""))]
    return (db.query(CandidateProfileRow)
            .filter(or_(CandidateProfileRow.usuario_id.is_(None), CandidateProfileRow.usuario_id.in_(legacy)))
            .order_by(CandidateProfileRow.creado.asc()).all())


@router.get("/api/account/unclaimed")
def unclaimed(db: Session = Depends(get_db)):
    current_user(db)
    return [{"id": r.id, "nombre": r.nombre, "fuente_cv": r.fuente_cv,
             "fecha": r.creado.isoformat() if r.creado else None} for r in unclaimed_rows(db)]


class ClaimRequest(BaseModel):
    profile_ids: list[int] = Field(min_length=1, max_length=50)


@router.post("/api/account/claim")
def claim(req: ClaimRequest, db: Session = Depends(get_db)):
    user = current_user(db)
    from .google_integration import ImportedMessage
    rows = [r for r in unclaimed_rows(db) if r.id in set(req.profile_ids)]
    if rows:
        ensure_profile_slots(db, user, len(rows))
    for row in rows:
        row.usuario_id = user.id
        apps = db.query(Postulacion).filter_by(profile_id=row.id).all()
        for app in apps:
            app.usuario_id = user.id
        vacancy_ids = [a.vacante_id for a in apps if a.vacante_id]
        if vacancy_ids:
            db.query(Vacante).filter(Vacante.id.in_(vacancy_ids)).update({"usuario_id": user.id}, synchronize_session=False)
        email_ids = [m.email_id for m in db.query(ImportedMessage).filter_by(profile_id=row.id)]
        if email_ids:
            db.query(EmailMonitoreado).filter(EmailMonitoreado.id.in_(email_ids)).update({"usuario_id": user.id}, synchronize_session=False)
    db.commit()
    return {"claimed": len(rows), "profile_ids": [r.id for r in rows]}
