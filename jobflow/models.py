"""Modelo de datos completo de JobFlow AI (ver documento tecnico, seccion 4)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True)
    ubicacion = Column(String, default="")
    oauth_tokens = Column(Text, default="")  # tokens OAuth cifrados (validar en MVP)
    creado = Column(DateTime, default=datetime.utcnow)

    perfiles = relationship("PerfilBusqueda", back_populates="usuario")
    cvs = relationship("CV", back_populates="usuario")


class PerfilBusqueda(Base):
    __tablename__ = "perfil_busqueda"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    puestos_objetivo = Column(JSON, default=list)   # ["Analista de Cobranzas", ...]
    seniority = Column(String, default="analista_junior")
    industrias = Column(JSON, default=list)
    ubicacion = Column(String, default="")
    remoto = Column(Boolean, default=False)
    rango_salarial = Column(String, default="S/2300 - S/3200")

    usuario = relationship("Usuario", back_populates="perfiles")


class CV(Base):
    __tablename__ = "cvs"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    archivo_original = Column(String, default="")
    texto_extraido = Column(Text, default="")
    version_optimizada = Column(Text, default="")
    fecha = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="cvs")
    analisis = relationship("GapAnalysis", back_populates="cv")


class CandidateProfileRow(Base):
    """Perfil de candidato (verificado o parseado de un CV subido)."""
    __tablename__ = "candidate_profiles"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    nombre = Column(String, default="")
    fuente_cv = Column(String, default="")
    texto_extraido = Column(Text, default="")
    estructura = Column(JSON, default=dict)
    creado = Column(DateTime, default=datetime.utcnow)


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"
    id = Column(Integer, primary_key=True)
    cv_id = Column(Integer, ForeignKey("cvs.id"), nullable=True)
    profile_id = Column(Integer, ForeignKey("candidate_profiles.id"), nullable=True)
    puesto_objetivo = Column(String, default="")
    score_global = Column(Float, default=0.0)
    score_keywords = Column(Float, default=0.0)
    score_experiencia = Column(Float, default=0.0)
    score_star = Column(Float, default=0.0)
    score_formato_ats = Column(Float, default=0.0)
    brechas = Column(JSON, default=list)
    sugerencias = Column(JSON, default=list)
    creado = Column(DateTime, default=datetime.utcnow)

    cv = relationship("CV", back_populates="analisis")


class Vacante(Base):
    __tablename__ = "vacantes"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    plataforma = Column(String, default="")   # linkedin | bumeran | computrabajo
    url = Column(String, default="")
    titulo = Column(String, default="")
    empresa = Column(String, default="")
    descripcion = Column(Text, default="")
    requisitos_extraidos = Column(JSON, default=list)


class Postulacion(Base):
    __tablename__ = "postulaciones"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    profile_id = Column(Integer, ForeignKey("candidate_profiles.id"), nullable=True)
    vacante_id = Column(Integer, ForeignKey("vacantes.id"), nullable=True)
    estado = Column(String, default="pendiente")  # pendiente|revision_usuario|enviado|en_proceso|rechazado|entrevista
    fecha_envio = Column(DateTime, nullable=True)
    respuestas_formulario = Column(JSON, default=list)
    creado = Column(DateTime, default=datetime.utcnow)


class FormularioResuelto(Base):
    __tablename__ = "formularios_resueltos"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("candidate_profiles.id"), nullable=True)
    postulacion_id = Column(Integer, ForeignKey("postulaciones.id"), nullable=True)
    email_id = Column(Integer, ForeignKey("emails_monitoreados.id"), nullable=True)
    plataforma = Column(String, default="test")
    campos_detectados = Column(JSON, default=list)
    mapeo_semantico = Column(JSON, default=list)
    respuestas_generadas = Column(JSON, default=list)
    aprobado_por_usuario = Column(Boolean, default=False)
    enviado = Column(Boolean, default=False)
    fecha_aprobacion = Column(DateTime, nullable=True)


class PuestoObjetivo(Base):
    __tablename__ = "puestos_objetivos"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("candidate_profiles.id"))
    titulo = Column(String, default="")
    seniority = Column(String, default="analista_junior")
    modality = Column(String, default="")
    ubicacion = Column(String, default="")
    rango_salarial = Column(String, default="")
    must_haves = Column(JSON, default=list)
    nice_to_haves = Column(JSON, default=list)
    activo = Column(Boolean, default=True)


class PlataformaConectada(Base):
    __tablename__ = "plataformas_conectadas"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    plataforma = Column(String, default="")     # bumeran|computrabajo|linkedin|indeed|gmail
    conectada = Column(Boolean, default=False)
    nota = Column(String, default="")
    actualizada = Column(DateTime, default=datetime.utcnow)


class EmailEnviado(Base):
    __tablename__ = "emails_enviados"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    postulacion_id = Column(Integer, ForeignKey("postulaciones.id"), nullable=True)
    destinatario = Column(String, default="")
    asunto = Column(String, default="")
    cuerpo = Column(Text, default="")
    estado = Column(String, default="simulado")   # simulado | enviado | error
    fecha = Column(DateTime, default=datetime.utcnow)


class EmailMonitoreado(Base):
    __tablename__ = "emails_monitoreados"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    remitente = Column(String, default="")
    asunto = Column(String, default="")
    cuerpo = Column(Text, default="")
    clasificacion = Column(String, default="informativo")  # requiere_accion|informativo
    tiene_formulario = Column(Boolean, default=False)
    estado = Column(String, default="pendiente")           # pendiente|resuelto|archivado
    fecha = Column(DateTime, default=datetime.utcnow)
