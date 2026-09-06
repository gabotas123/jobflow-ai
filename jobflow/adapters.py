"""Adaptadores delgados por plataforma (modulo 5.3 del documento tecnico).

Un motor comun (autofill.py) + adaptadores que resuelven lo especifico de cada
plataforma: sesion, navegacion al formulario y extraccion del DOM. El mapeo
semantico y la generacion de respuestas se reutilizan al 100%.

NOTA (ToS): LinkedIn NO se automatiza (prohibido). Solo actua como copiloto:
genera respuestas listas para pegar. Bumeran/Computrabajo solo sobre la sesion
del propio usuario, con throttle y confirmacion humana.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .knowledge import ANSWER_TEMPLATES
from .profile_models import CandidateProfile


class PlatformAdapter:
    platform: str = ""
    description: str = ""
    tos_note: str = ""

    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def navigate_to_form(self, page, url: str) -> None:
        """Navega hasta el formulario de postulacion (Playwright)."""
        page.goto(url, wait_until="domcontentloaded")

    def submit_real(self, page) -> None:
        raise NotImplementedError("Envio real no implementado en el MVP.")

    def status(self) -> Dict:
        return {
            "plataforma": self.platform,
            "descripcion": self.description,
            "modo": "autofill" if self.platform in ("bumeran", "computrabajo", "test") else "copiloto",
            "tos_note": self.tos_note,
        }


class BumeranAdapter(PlatformAdapter):
    platform = "bumeran"
    description = "Postulacion rapida de Bumeran (sobre la sesion del usuario)."
    tos_note = "Solo sesion propia, una postulacion a la vez, confirmacion humana antes de enviar."


class ComputrabajoAdapter(PlatformAdapter):
    platform = "computrabajo"
    description = "Formulario de Computrabajo (sobre la sesion del usuario)."
    tos_note = "Solo sesion propia, throttle (1 postulacion a la vez), confirmacion humana."


class LinkedinAdapter(PlatformAdapter):
    platform = "linkedin"
    description = "Easy Apply de LinkedIn."
    tos_note = ("AUTOMATIZACION PROHIBIDA por ToS / riesgo de baneo: solo copiloto "
                "(genera respuestas listas para pegar). Nunca se envia automaticamente.")

    def copilot_answers(self, mapping: List[dict], vacante_titulo: str) -> List[dict]:
        from .autofill import generate_answers
        answers = generate_answers(mapping, self.profile, vacante_titulo)
        return answers


class TestFormAdapter(PlatformAdapter):
    platform = "test"
    description = "Formulario de prueba simulado (para la demo de sustentacion)."
    tos_note = "No usa sesiones reales; valida el pipeline completo de forma segura."


ADAPTERS: Dict[str, PlatformAdapter.__class__] = {
    "bumeran": BumeranAdapter,
    "computrabajo": ComputrabajoAdapter,
    "linkedin": LinkedinAdapter,
    "test": TestFormAdapter,
}


def get_adapter(platform: str, profile: CandidateProfile) -> PlatformAdapter:
    cls = ADAPTERS.get(platform, TestFormAdapter)
    return cls(profile)
