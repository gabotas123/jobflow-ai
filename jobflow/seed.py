"""Inicializacion, seed y helpers de perfiles de candidato."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from . import models
from .db import SessionLocal, init_db
from .email_monitor import seed_mock_emails
from .gap_analysis import analyze, cv_text
from .knowledge import EMAIL, FULL_NAME, LOCATION, TARGET_ROLES_DEFAULT, build_gabriel
from .profile_models import CandidateProfile

DEFAULT_ROLE = {
    "target_role": "Analista de Cobranzas",
    "seniority": "analista_junior",
    "must": ["Excel", "cuentas por cobrar", "cobranzas", "aging", "Power BI", "SQL"],
    "nice": ["SAP", "facturacion", "Python"],
}


def ensure_seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(models.Usuario).count() == 0:
            user = models.Usuario(nombre=FULL_NAME, email=EMAIL, ubicacion=LOCATION)
            db.add(user)
            db.flush()

            db.add(models.PerfilBusqueda(
                usuario_id=user.id,
                puestos_objetivo=TARGET_ROLES_DEFAULT,
                seniority="analista_junior",
                ubicacion=LOCATION,
                remoto=False,
                rango_salarial="S/2300 - S/3200",
            ))

            # Perfil verificado (semilla) como candidato
            profile = build_gabriel()
            row = models.CandidateProfileRow(
                usuario_id=user.id, nombre=profile.nombre, fuente_cv=profile.fuente_cv,
                texto_extraido=cv_text(profile), estructura=profile.to_dict(),
            )
            db.add(row)
            db.flush()

            cv = models.CV(
                usuario_id=user.id,
                archivo_original="Gabriel_Gutierrez_CV_Cobranzas_B2B_Bumeran_2026.pdf",
                texto_extraido=cv_text(profile),
            )
            db.add(cv)
            db.flush()

            # Puesto objetivo activo por defecto
            db.add(models.PuestoObjetivo(
                profile_id=row.id, titulo=DEFAULT_ROLE["target_role"],
                seniority=DEFAULT_ROLE["seniority"], modality="Presencial o hibrido",
                ubicacion=LOCATION, rango_salarial="S/2500 - S/2800",
                must_haves=DEFAULT_ROLE["must"], nice_to_haves=DEFAULT_ROLE["nice"],
                activo=True,
            ))
            # Conexiones de plataformas (para el gestor de vinculaciones)
            for plat, nota in [
                ("bumeran", "Autofill de formularios"),
                ("computrabajo", "Autofill de formularios"),
                ("linkedin", "Copiloto (sin envio automatico)"),
                ("indeed", "Busqueda de vacantes"),
                ("gmail", "Correos de reclutamiento"),
            ]:
                db.add(models.PlataformaConectada(usuario_id=user.id, plataforma=plat,
                                                  conectada=False, nota=nota))

            result = analyze(profile, DEFAULT_ROLE["target_role"], DEFAULT_ROLE["seniority"],
                             DEFAULT_ROLE["must"], DEFAULT_ROLE["nice"])
            db.add(models.GapAnalysis(
                cv_id=cv.id, profile_id=row.id,
                puesto_objetivo=DEFAULT_ROLE["target_role"],
                score_global=result["score_global"],
                score_keywords=result["components"][0]["score"],
                score_experiencia=result["components"][1]["score"],
                score_star=result["components"][2]["score"],
                score_formato_ats=result["components"][3]["score"],
                brechas=result["gaps"],
                sugerencias=result["reescrituras"],
            ))

            seed_mock_emails(db, user.id)
            db.commit()
    finally:
        db.close()


def get_first_user(db: Session) -> Optional[models.Usuario]:
    user = db.query(models.Usuario).first()
    if not user:
        ensure_seed()
        user = db.query(models.Usuario).first()
    return user


# --------------------------------------------------------------------------- #
#  Helpers de perfiles de candidato
# --------------------------------------------------------------------------- #
def list_profile_rows(db: Session) -> List[models.CandidateProfileRow]:
    return (db.query(models.CandidateProfileRow)
            .order_by(models.CandidateProfileRow.creado.asc()).all())


def get_profile_row(db: Session, profile_id: int) -> Optional[models.CandidateProfileRow]:
    return db.get(models.CandidateProfileRow, profile_id)


def profile_from_row(row: models.CandidateProfileRow) -> CandidateProfile:
    return CandidateProfile.from_dict(row.estructura or {})


def default_puesto_values(profile: CandidateProfile) -> dict:
    """Puesto objetivo por defecto para un CV subido (cargo principal + dominio)."""
    from .job_search import build_query
    cargos = [e.get("cargo", "") for e in profile.experiencia if e.get("cargo")]
    titulo = (cargos[0] if cargos else "Analista") or "Analista"
    dom = build_query(profile)
    return {
        "titulo": titulo,
        "seniority": "analista_junior",
        "modality": "Presencial o hibrido",
        "ubicacion": profile.ubicacion or "Lima",
        "rango_salarial": "",
        "must_haves": [d for d in (dom, "Excel", "Power BI", "reportes") if d],
        "nice_to_haves": ["SQL", "SAP"],
    }
