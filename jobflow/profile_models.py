"""Modelo de candidato (generic, no hardcodeado).

Un `CandidateProfile` es la representacion estructurada del CV de CUALQUIER
persona. Puede venir de:
  - la base de conocimiento verificada (perfil semilla, verificado=True), o
  - el parseo de un CV subido (PDF/DOCX/TXT) por `cv_parser.py`.

Todo el motor (gap analysis, respuestas, autofill) se alimenta de aqui.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class CandidateProfile:
    nombre: str = ""
    email: str = ""
    telefono: str = ""
    ubicacion: str = ""
    linkedin: str = ""
    headline: str = ""
    positioning: str = ""
    summary: str = ""
    seniority: str = "no_definido"       # asistente | analista_junior | analista
    rango_salarial: str = ""
    disponibilidad: str = ""
    movilidad: str = ""
    # cada entrada: {empresa, cargo, inicio, fin, bullets:[...]}
    experiencia: List[dict] = field(default_factory=list)
    skills: List[tuple] = field(default_factory=list)      # (nombre, nivel)
    languages: Dict[str, str] = field(default_factory=dict)  # nombre -> nivel
    educacion: List[str] = field(default_factory=list)
    proyectos: List[str] = field(default_factory=list)
    verificado: bool = False             # True: perfil canónico con respuestas acordadas
    fuente_cv: str = ""                  # archivo o "manual"
    notas: str = ""

    # ------------------------------------------------------------------ #
    def all_bullets(self) -> List[str]:
        return [b for e in self.experiencia if isinstance(e, dict) for b in e.get("bullets", [])]

    def first_company(self) -> str:
        for e in self.experiencia:
            if isinstance(e, dict) and e.get("empresa"):
                return e["empresa"]
        return ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["skills"] = [[k, v] for k, v in self.skills]
        return d

    @staticmethod
    def from_dict(d: dict) -> "CandidateProfile":
        d = dict(d or {})
        d.setdefault("experiencia", [])
        d.setdefault("skills", [])
        d["experiencia"] = [e for e in d.get("experiencia", []) if isinstance(e, dict)]
        d["skills"] = [(str(k), str(v)) for k, v in d.get("skills", [])]
        return CandidateProfile(**{k: v for k, v in d.items() if k in CandidateProfile.__dataclass_fields__})
