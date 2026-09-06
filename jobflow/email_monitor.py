"""Monitoreo de correo (modulo 6 del documento tecnico).

En produccion: conexion OAuth2 a Gmail API / Microsoft Graph (nunca contraseñas),
scopes minimos (lectura + borradores), job periodico, clasificacion con LLM y
reutilizacion del pipeline de autofill, siempre con revision humana.

En el MVP: clasificacion deterministica + bandeja simulada (seed) para la demo.
"""
from __future__ import annotations

import unicodedata
from typing import Dict, List

from sqlalchemy.orm import Session

from . import models


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# Remitentes/firmas tipicos de reclutamiento
RECRUITERS = ("hiringroom", "bumeran", "computrabajo", "linkedin", "rrhh", "talento",
              "reclutamiento", "jobs", "empleos")

ACTION_WORDS = ("cuestionario", "formulario", "completar", "finalizar", "assessment",
                "evaluacion", "entrevista", "proceso", "solicitud", "requiere")
FORM_WORDS = ("formulario", "cuestionario", "google form", "link", "enlace", "adjunto")


def classify_email(remitente: str, asunto: str, cuerpo: str = "") -> Dict:
    """Clasifica un correo: requiere accion? tiene formulario? urgencia?"""
    txt = norm(f"{remitente} {asunto} {cuerpo}")
    is_recruiting = any(r in norm(remitente) for r in RECRUITERS)
    action = any(w in txt for w in ("cuestionario", "formulario", "evaluacion",
                                    "assessment", "entrevista", "completar", "solicitud"))
    has_form = any(w in txt for w in FORM_WORDS)
    urgent = any(w in txt for w in ("urgente", "48 horas", "vencimiento", "hoy", "24 hora"))
    clasificacion = "requiere_accion" if (action or (is_recruiting and has_form)) else "informativo"
    return {
        "clasificacion": clasificacion,
        "tiene_formulario": has_form,
        "es_reclutamiento": is_recruiting,
        "urgente": urgent,
        "motivo": (
            "Viene de un reclutador y menciona un formulario/cuestionario a completar."
            if clasificacion == "requiere_accion" else "Correo informativo, sin accion inmediata."
        ),
    }


# Bandeja simulada para la demo (inspirada en el historial real de cuentas de HiringRoom)
MOCK_EMAILS = [
    {
        "remitente": "info@hiringroom.com",
        "asunto": "Cuestionario de la vacante Analista de Cobranzas - YOFC",
        "cuerpo": ("Gracias por postular a nuestra vacante. Para continuar el proceso, "
                   "complete el cuestionario en el siguiente enlace antes del vencimiento. "
                   "Formulario: experiencia, salario, disponibilidad."),
    },
    {
        "remitente": "proempresa@talento.pe",
        "asunto": "Solicitud de datos - Gestor de Cobranzas",
        "cuerpo": "Confirme su movilidad propia y experiencia en cobranzas para avanzar a la entrevista.",
    },
    {
        "remitente": "no-reply@bumeran.com.pe",
        "asunto": "Tu postulacion fue recibida",
        "cuerpo": "Hemos registrado tu postulacion a Analista de Cobranzas. Sigue el estado desde tu panel.",
    },
    {
        "remitente": "noticias@portalempleo.pe",
        "asunto": "5 consejos para mejorar tu CV (boletin)",
        "cuerpo": "Novedades del mercado laboral y consejos de preparacion.",
    },
]


def enviar_correo(db: Session, usuario_id: int, destinatario: str, asunto: str,
                  cuerpo: str, postulacion_id: int = None) -> models.EmailEnviado:
    """Envia un correo real (si hay SMTP configurado) o lo registra como simulado.

    Devuelve el registro `EmailEnviado`: la postulacion queda vinculada al
    correo (conector correo <-> solicitud).
    """
    from .config import settings
    estado = "simulado"
    try:
        if settings.smtp_host and settings.smtp_user:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(cuerpo, "plain", "utf-8")
            msg["Subject"] = asunto
            msg["From"] = settings.smtp_user
            msg["To"] = destinatario
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_pass)
                server.sendmail(settings.smtp_user, [destinatario], msg.as_string())
            estado = "enviado"
        elif not destinatario:
            estado = "error"
    except Exception:
        estado = "error"

    row = models.EmailEnviado(
        usuario_id=usuario_id, postulacion_id=postulacion_id, destinatario=destinatario,
        asunto=asunto, cuerpo=cuerpo, estado=estado,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def seed_mock_emails(db: Session, usuario_id: int) -> List[models.EmailMonitoreado]:
    existing = db.query(models.EmailMonitoreado).count()
    if existing:
        return db.query(models.EmailMonitoreado).all()
    created = []
    for m in MOCK_EMAILS:
        cls = classify_email(m["remitente"], m["asunto"], m["cuerpo"])
        e = models.EmailMonitoreado(
            usuario_id=usuario_id, remitente=m["remitente"], asunto=m["asunto"],
            cuerpo=m["cuerpo"], clasificacion=cls["clasificacion"],
            tiene_formulario=cls["tiene_formulario"], estado="pendiente" if cls["clasificacion"] == "requiere_accion" else "archivado",
        )
        db.add(e)
        created.append(e)
    db.commit()
    for c in created:
        db.refresh(c)
    return created
