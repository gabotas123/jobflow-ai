"""Esquemas de entrada/salida de la API (Pydantic)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    profile_id: Optional[int] = None
    usar_puesto: bool = True                 # usa el puesto objetivo activo del perfil
    target_role: str = "Analista de Cobranzas"
    seniority: str = "analista_junior"
    modality: str = "Presencial o hibrido"
    location: str = "Lima"
    must_haves: List[str] = Field(default_factory=lambda: [
        "Excel", "cuentas por cobrar", "cobranzas", "aging", "Power BI", "SQL",
    ])
    nice_to_haves: List[str] = Field(default_factory=lambda: [
        "SAP", "facturacion", "Python",
    ])
    jd_text: str = ""


class VacanteRequest(BaseModel):
    plataforma: str = "bumeran"          # linkedin | bumeran | computrabajo
    url: str = ""
    titulo: str = "Analista de Cobranzas"
    empresa: str = ""
    descripcion: str = ""
    requisitos: List[str] = Field(default_factory=list)


class FormRunRequest(BaseModel):
    profile_id: Optional[int] = None
    platform: str = "test"               # bumeran | computrabajo | linkedin | test
    vacante_titulo: str = "Analista de Cobranzas"
    vacante_empresa: str = "Empresa Ejemplo SAC"
    url: str = ""
    form_schema: Optional[List[dict]] = None   # para el form de prueba


class GenerateRequest(BaseModel):
    target_id: Optional[int] = None
    profile_id: Optional[int] = None
    variant: str = "maestro"


class PuestoRequest(BaseModel):
    titulo: str = "Analista de Cobranzas"
    seniority: str = "analista_junior"
    modality: str = "Presencial o hibrido"
    ubicacion: str = "Lima"
    rango_salarial: str = ""
    must_haves: List[str] = Field(default_factory=lambda: [
        "Excel", "cuentas por cobrar", "cobranzas", "aging", "Power BI", "SQL",
    ])
    nice_to_haves: List[str] = Field(default_factory=lambda: ["SAP", "facturacion", "Python"])


class ActivePuestoRequest(BaseModel):
    puesto_id: int


class PlatformConnectRequest(BaseModel):
    plataforma: str = "bumeran"
    conectada: bool = True


class PostulacionRequest(BaseModel):
    profile_id: Optional[int] = None
    plataforma: str = "bumeran"
    titulo: str = ""
    empresa: str = ""
    url: str = ""
    estado: str = "enviada_desde_busqueda"


class ProfileUpdateRequest(BaseModel):
    experiencia: Optional[List[dict]] = None
    educacion: Optional[List[str]] = None
    languages: Optional[dict[str, str]] = None
    proyectos: Optional[List[str]] = None
    pendientes: Optional[List[str]] = None
    skill_levels: Optional[List[tuple[str, str]]] = None
    """Campos editables del perfil de candidato (los parseados se corrigen aqui)."""
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    linkedin: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    seniority: Optional[str] = None
    rango_salarial: Optional[str] = None
    disponibilidad: Optional[str] = None
    movilidad: Optional[str] = None
    skills: Optional[List[str]] = None


class ApproveRequest(BaseModel):
    edits: List[dict] = Field(default_factory=list)   # [{field, answer}]


class EmailClassifyRequest(BaseModel):
    remitente: str = "info@hiringroom.com"
    asunto: str = "Cuestionario de la vacante de Analista de Cobranzas"
    cuerpo: str = "Gracias por postular. Complete el siguiente formulario para continuar el proceso."


class JobImportRequest(BaseModel):
    profile_id: Optional[int] = None
    titulo: str = Field(min_length=2, max_length=250)
    empresa: str = Field(min_length=2, max_length=250)
    plataforma: str = Field(default="manual", max_length=40)
    url: str = Field(default="", max_length=2000)
    descripcion: str = Field(default="", max_length=40000)
    ubicacion: str = Field(default="", max_length=250)
    modalidad: str = Field(default="", max_length=100)
    vigente: Optional[bool] = None
    anos_obligatorios: Optional[float] = Field(default=None, ge=0, le=50)
    meses_relevantes_confirmados: Optional[int] = Field(default=None, ge=0, le=600)
    herramientas: List[str] = Field(default_factory=list, max_length=50)
    formacion: str = Field(default="", max_length=250)
    salario_max: Optional[float] = Field(default=None, ge=0)
    salario_min_aceptado: Optional[float] = Field(default=None, ge=0)
    fecha_publicacion: Optional[str] = None


class JobExtractRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class ApplicationUpdateRequest(BaseModel):
    cv_version_id: Optional[int] = None
    estado: str
    evidencia: str = Field(default="", max_length=5000)
    tipo_evidencia: str = ""
    nota: str = Field(default="", max_length=5000)


class EmailImportRequest(BaseModel):
    remitente: str = Field(min_length=3, max_length=250)
    asunto: str = Field(min_length=1, max_length=500)
    cuerpo: str = Field(min_length=1, max_length=40000)
