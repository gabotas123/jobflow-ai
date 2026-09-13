"""Cuentas de portales y postulacion automatica con evidencia.

Conexion: JobFlow abre una ventana real del portal; el candidato inicia sesion
personalmente (JobFlow nunca ve ni guarda su contrasena, y el candidato resuelve
cualquier verificacion). Solo se guarda la sesion del navegador, cifrada.

Postulacion: un unico trabajador procesa la cola de candidaturas que el
candidato autorizo. Completa solo datos confirmados o respuestas aprobadas, se
detiene ante CAPTCHA, pruebas, preguntas sensibles o desconocidas, y marca
"postulada" solo si el portal muestra la confirmacion. Un resultado incierto
queda como intento no confirmado y nunca se reenvia automaticamente.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db
from .models import Base, FormularioResuelto
from .workflow import ApplicationDetail, AuditEvent, norm

router = APIRouter(prefix="/api/portals")

PORTALS = {
    "bumeran": {
        "nombre": "Bumeran", "domain": "bumeran.com.pe",
        "login_url": "https://www.bumeran.com.pe/login",
        "probe_url": "https://www.bumeran.com.pe/postulantes/postulaciones",
        "login_markers": ("/login",),
    },
    "computrabajo": {
        "nombre": "Computrabajo", "domain": "computrabajo.com",
        "login_url": "https://candidato.pe.computrabajo.com/acceso/",
        "probe_url": "https://candidato.pe.computrabajo.com/candidate/",
        "login_markers": ("account/login", "/acceso"),
    },
}
UNSUPPORTED = {
    "linkedin": "LinkedIn prohíbe la automatización y puede suspender la cuenta: JobFlow prepara tus respuestas y tú postulas.",
    "indeed": "Indeed bloquea el acceso automatizado: abre el aviso y postula personalmente.",
}
BLOCKED_STATES = ("incompatible", "pendiente_revision_duplicado", "vencida", "rechazada")
ACTIVE_RUNS = ("en_cola", "ejecutando")
LOGIN_TIMEOUT = 600
DAILY_LIMIT = int(os.getenv("JOBFLOW_APPLY_DAILY_LIMIT", "20"))

APPLY_TEXT = r"^(postularme|postular(me|se)?( ahora| a este empleo| a esta oferta| al empleo)?|aplicar( ahora)?|enviar (mi )?postulaci[oó]n|confirmar postulaci[oó]n|finalizar postulaci[oó]n|enviar (mi )?cv)$"
# Generic buttons only count once the application flow has started (never on the job page).
NEXT_TEXT = r"^(enviar|confirmar|finalizar|continuar|siguiente|guardar y continuar)$"
DONE_BUTTON = r"^(postulado|ya postulaste|ya te postulaste|postulaci[oó]n enviada)$"
CONFIRM_TEXT = re.compile(
    r"(postulaci[oó]n (fue |ha sido )?(enviada|exitosa|realizada|registrada|completada)|te (has )?postulado|"
    r"ya (te )?postulaste|ya est[aá]s postulad|postulaste con [eé]xito|hemos recibido tu (postulaci[oó]n|cv|curr[ií]culum)|"
    r"tu (cv|curr[ií]culum) (fue|ha sido) enviado|(te )?postulaste (correctamente|exitosamente))", re.I)
CAPTCHA_TEXT = re.compile(r"(no soy un robot|verifica que eres (un )?humano|captcha|confirma que eres humano)", re.I)
TEST_TEXT = re.compile(r"(prueba|test|evaluaci[oó]n) (psicom[eé]trica|t[eé]cnica|de conocimientos|de personalidad)|video ?entrevista|graba(r)? (un )?video", re.I)


# --------------------------------------------------------------------------- #
#  Modelos
# --------------------------------------------------------------------------- #
class PortalAccount(Base):
    __tablename__ = "portal_accounts"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, index=True, nullable=False)
    portal = Column(String, nullable=False)
    encrypted = Column(Text, nullable=False)
    status = Column(String, default="connected")
    connected_at = Column(DateTime, default=datetime.utcnow)
    checked_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("profile_id", "portal"),)


class AutoApplyRun(Base):
    __tablename__ = "auto_apply_runs"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, index=True, nullable=False)
    profile_id = Column(Integer, index=True, nullable=False)
    portal = Column(String, nullable=False)
    status = Column(String, default="en_cola")
    detail = Column(JSON, default=dict)
    created = Column(DateTime, default=datetime.utcnow)
    updated = Column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------- #
#  Cifrado y entorno
# --------------------------------------------------------------------------- #
def cipher() -> Fernet:
    key = os.getenv("JOBFLOW_TOKEN_KEY", "")
    if not key:
        path = Path(settings.data_dir) / ".jobflow_key"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(Fernet.generate_key().decode())
            try:
                path.chmod(0o600)
            except OSError:
                pass
        key = path.read_text().strip()
    try:
        return Fernet(key.encode())
    except ValueError:
        raise HTTPException(503, "La clave de cifrado de JobFlow no es válida.")


def browser_status() -> tuple[bool, str]:
    if os.getenv("RENDER") or os.getenv("JOBFLOW_LOCAL_BROWSER", "true").lower() == "false":
        return False, ("Conectar cuentas y postular automáticamente requiere abrir JobFlow en tu computadora "
                       "(Abrir_JobFlow.bat): el servidor web no tiene una ventana donde iniciar sesión.")
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False, "Faltan componentes de JobFlow. Ejecuta Instalar_Todo.bat."
    if not find_browser():
        return False, "Instala Google Chrome o Microsoft Edge: JobFlow usa tu navegador para iniciar sesión y postular."
    return True, ""


def evidence_dir() -> Path:
    path = Path(settings.data_dir) / "evidencias"
    path.mkdir(parents=True, exist_ok=True)
    return path


def portal_for_url(url: str) -> str:
    from .job_extract import portal_for
    return portal_for(url or "")


def account(db, pid, portal):
    return db.query(PortalAccount).filter_by(profile_id=pid, portal=portal).first()


def account_ready(acc) -> bool:
    try:
        return json.loads(cipher().decrypt(acc.encrypted.encode())).get("formato") == "navegador_real"
    except (InvalidToken, ValueError, AttributeError):
        return False


def on_login(url: str, portal: str) -> bool:
    return any(m in (url or "").lower() for m in PORTALS[portal]["login_markers"])


# --------------------------------------------------------------------------- #
#  Navegador real del candidato (Chrome/Edge) con un perfil propio de JobFlow
# --------------------------------------------------------------------------- #
# Los portales bloquean el Chromium de automatizacion y el modo oculto (Cloudflare
# responde "you have been blocked" o 403). Por eso se abre el Chrome/Edge instalado
# como un proceso normal y solo se conecta por DevTools para leer el estado.
BLOCK_TEXT = re.compile(r"(you have been blocked|unable to access|403 forbidden|access denied|attention required|"
                        r"just a moment|checking your browser|acceso denegado)", re.I)
BROWSER_CANDIDATES = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
)


def find_browser() -> str:
    custom = os.getenv("JOBFLOW_BROWSER_PATH", "")
    for candidate in ([custom] if custom else []) + [os.path.expandvars(c) for c in BROWSER_CANDIDATES]:
        if candidate and "%" not in candidate and Path(candidate).is_file():
            return candidate
    for name in ("google-chrome", "chrome", "chromium", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def browser_profile(pid: int) -> Path:
    path = Path(settings.data_dir).resolve() / "navegador" / f"perfil_{pid}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class RealBrowser:
    """Chrome/Edge sin marcas de automatizacion, controlado por DevTools local."""

    def __init__(self, playwright, pid: int, start_url: str = "about:blank"):
        exe = find_browser()
        if not exe:
            raise RuntimeError("No se encontró Google Chrome ni Microsoft Edge. Instala uno de ellos para conectar tus cuentas.")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [exe, f"--user-data-dir={browser_profile(pid)}", f"--remote-debugging-port={port}",
             "--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble",
             "--hide-crash-restore-bubble", "--window-size=1280,900", "--new-window", start_url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.browser, last_error = None, None
        deadline = time.time() + 25
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("Ya hay una ventana de JobFlow abierta con tu perfil de navegador. Ciérrala e inténtalo otra vez.")
            try:
                self.browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=5000)
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
        if not self.browser:
            self.close()
            raise RuntimeError("No se pudo controlar el navegador. " + str(last_error)[:150])
        self.context = self.browser.contexts[0]

    def pages(self):
        return [pg for pg in self.context.pages if not pg.is_closed()]

    def alive(self) -> bool:
        # Chrome may hand the window to a child process, so the DevTools link is the source of truth.
        return self.browser is not None and self.browser.is_connected()

    def close(self):
        if self.browser is not None:
            try:
                self.browser.new_browser_cdp_session().send("Browser.close")
            except Exception:
                pass
        try:
            self.proc.wait(10)
        except Exception:
            self.proc.terminate()


def session_state(context, portal: str, wait_ms: int = 8000) -> str:
    """Abre la zona privada del portal: 'activa', 'sin_sesion' o 'bloqueado'."""
    probe = context.new_page()
    try:
        probe.goto(PORTALS[portal]["probe_url"], wait_until="domcontentloaded", timeout=30000)
        deadline = time.time() + wait_ms / 1000
        while time.time() < deadline:  # the login redirect is done by JavaScript after load
            if on_login(probe.url, portal):
                return "sin_sesion"
            probe.wait_for_timeout(500)
        text = _visible_text(probe)
        if BLOCK_TEXT.search(text):
            return "bloqueado"
        return "activa" if len(text.strip()) > 40 and not on_login(probe.url, portal) else "sin_sesion"
    except Exception:
        return "sin_sesion"
    finally:
        try:
            probe.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  Conexion de cuentas (inicio de sesion personal en la ventana del portal)
# --------------------------------------------------------------------------- #
LOGINS: dict[tuple[int, str], dict] = {}
LOGIN_LOCK = threading.Lock()
LOGIN_ACTIVE = ("abriendo", "esperando", "verificando")


def _set_login(key, status, message=""):
    with LOGIN_LOCK:
        LOGINS[key] = {"status": status, "message": message, "at": time.time()}


def _request_login(key, action):
    with LOGIN_LOCK:
        if key in LOGINS:
            LOGINS[key]["request"] = action


def login_active(pid) -> str:
    return next((portal for (p, portal), s in LOGINS.items() if p == pid and s["status"] in LOGIN_ACTIVE), "")


def save_session(pid, portal, state: dict) -> None:
    db = SessionLocal()
    try:
        acc = account(db, pid, portal) or PortalAccount(profile_id=pid, portal=portal, encrypted="")
        acc.encrypted = cipher().encrypt(json.dumps(state).encode()).decode()
        acc.status, acc.connected_at, acc.checked_at = "connected", datetime.utcnow(), datetime.utcnow()
        db.add(acc)
        db.commit()
    finally:
        db.close()


def login_worker(pid: int, portal: str) -> None:
    key, cfg = (pid, portal), PORTALS[portal]
    waiting = f"Inicia sesión en la ventana de {cfg['nombre']} y luego pulsa «Ya inicié sesión». JobFlow no lee tu contraseña."
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            real = RealBrowser(p, pid, cfg["login_url"])
            try:
                _set_login(key, "esperando", waiting)
                deadline, last_probe = time.time() + LOGIN_TIMEOUT, 0.0
                while time.time() < deadline:
                    time.sleep(2)
                    request = LOGINS.get(key, {}).get("request")
                    if request == "cancel":
                        _set_login(key, "cancelada", "Conexión cancelada.")
                        return
                    pages = real.pages() if real.alive() else []
                    if not pages:
                        _set_login(key, "cancelada", "Se cerró la ventana antes de conectar la cuenta.")
                        return
                    manual = request == "verify"
                    left_login = any(cfg["domain"] in pg.url and not on_login(pg.url, portal) for pg in pages)
                    if not manual and (not left_login or time.time() - last_probe < 20):
                        continue
                    last_probe = time.time()
                    _set_login(key, "verificando", "Comprobando tu sesión…")
                    state = session_state(real.context, portal)
                    if state == "activa":
                        save_session(pid, portal, {"formato": "navegador_real", "perfil": str(browser_profile(pid))})
                        _set_login(key, "conectada", f"Cuenta de {cfg['nombre']} conectada.")
                        return
                    if state == "bloqueado":
                        _set_login(key, "esperando", f"{cfg['nombre']} mostró una página de bloqueo o verificación. "
                                                     "Complétala en la ventana si aparece y vuelve a pulsar «Ya inicié sesión».")
                    elif manual:
                        _set_login(key, "esperando", f"Todavía no hay una sesión iniciada en {cfg['nombre']}. "
                                                     "Termina de ingresar en la ventana y vuelve a pulsar «Ya inicié sesión».")
                    else:
                        _set_login(key, "esperando", waiting)
                _set_login(key, "vencida", "Pasaron 10 minutos sin completar el inicio de sesión.")
            finally:
                real.close()
    except Exception as exc:  # pragma: no cover - depende del escritorio local
        _set_login(key, "error", "No se pudo abrir el navegador. " + str(exc)[:250])


# --------------------------------------------------------------------------- #
#  Plan de llenado (sin navegador: testeable)
# --------------------------------------------------------------------------- #
YES = ("si", "sí", "yes")


def choose_option(options, value):
    v = norm(value)
    if not v:
        return None
    clean = [(o, norm(o)) for o in options if norm(o) and not norm(o).startswith(("selecciona", "elige", "--"))]
    for original, n in clean:
        if n == v:
            return original
    if v in YES or v.startswith(("si ", "si,", "cuento con", "cuenta con", "tengo ")):
        return next((o for o, n in clean if n in YES), None)
    if v == "no" or v.startswith(("no ", "no,", "sin ")):
        return next((o for o, n in clean if n == "no"), None)
    matches = [o for o, n in clean if len(n) > 2 and (n in v or v in n)]
    return matches[0] if len(matches) == 1 else None


def plan_fields(fields, profile, vacancy_title, approved: dict, cv_path: str | None = None):
    """Decide que hacer con cada campo visible. Nunca completa datos desconocidos."""
    from .autofill import generate_answers, map_fields
    pending_fields = [f for f in fields if not f.get("filled")]
    mapping = map_fields([{"id": f["key"], "label": f.get("label", ""), "type": f.get("type", ""),
                           "options": f.get("options", [])} for f in pending_fields])
    answers = generate_answers(mapping, profile, vacancy_title)
    plan = []
    for f, m, a in zip(pending_fields, mapping, answers):
        label, kind, required = f.get("label", ""), f.get("type", "text"), bool(f.get("required"))
        step = {"key": f["key"], "label": label, "type": kind, "required": required}
        if kind == "file":
            plan.append({**step, "action": "file", "value": cv_path} if cv_path else
                        {**step, "action": "pending" if required else "skip", "reason": "Requiere adjuntar un CV aprobado para esta candidatura."})
            continue
        if kind == "checkbox":
            plan.append({**step, "action": "pending" if required else "skip",
                         "reason": "Casilla obligatoria (términos o declaración): revísala personalmente."})
            continue
        if m["bloqueada"]:
            plan.append({**step, "action": "pending" if required else "skip",
                         "reason": "Pregunta sensible o evaluación: requiere tu intervención."})
            continue
        value = approved.get(norm(label), "")
        source = "Respuesta aprobada por ti"
        if not value and a["answer"] and not a["necesita_input"]:
            value, source = a["answer"], a.get("fuente") or "Perfil confirmado"
        if not value:
            plan.append({**step, "action": "pending" if required else "skip",
                         "reason": "No hay un dato confirmado para esta pregunta."})
            continue
        if kind in ("select", "radio"):
            option = choose_option(f.get("options", []), value)
            if option is None:
                plan.append({**step, "action": "pending" if required else "skip", "options": f.get("options", []),
                             "reason": "Ninguna opción coincide con tu dato confirmado."})
                continue
            plan.append({**step, "action": "select", "value": option, "source": source})
            continue
        if kind == "number" or m["canonical"] == "salario_pretendido":
            digits = re.findall(r"\d[\d,.]*", value)
            if not digits:
                plan.append({**step, "action": "pending" if required else "skip", "reason": "Falta un valor numérico confirmado."})
                continue
            value = re.sub(r"[,.](?=\d{3}\b)", "", digits[0])
        plan.append({**step, "action": "fill", "value": value, "source": source})
    return plan


def approved_answers(db, application_id) -> dict:
    out = {}
    forms = (db.query(FormularioResuelto).filter_by(postulacion_id=application_id, aprobado_por_usuario=True)
             .order_by(FormularioResuelto.id.asc()).all())
    for form in forms:
        for a in form.respuestas_generadas or []:
            if str(a.get("answer", "")).strip():
                out[norm(a.get("label", ""))] = str(a["answer"]).strip()
    return out


# --------------------------------------------------------------------------- #
#  Ejecutor sobre una pagina de Playwright
# --------------------------------------------------------------------------- #
FIELDS_JS = r"""
(scopeSelector) => {
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const text = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const scope = document.querySelector(scopeSelector) || document;
  document.querySelectorAll('[data-jobflow-field]').forEach(e => e.removeAttribute('data-jobflow-field'));
  const labelOf = el => {
    if (el.labels && el.labels.length) return [...el.labels].map(text).join(' ');
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const by = el.getAttribute('aria-labelledby');
    if (by) return by.split(/\s+/).map(id => text(document.getElementById(id))).join(' ');
    let node = el;
    for (let i = 0; i < 4 && node; i++) {
      node = node.parentElement;
      const cand = node && node.querySelector('legend, label, h3, h4, p, span');
      if (cand && text(cand) && !cand.contains(el)) return text(cand);
    }
    return el.placeholder || el.name || '';
  };
  const out = []; const groups = {};
  scope.querySelectorAll('input, textarea, select').forEach((el, i) => {
    const tag = el.tagName.toLowerCase();
    const type = tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea' : (el.type || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'search', 'image', 'reset', 'password'].includes(type)) return;
    if (el.closest('header, footer, nav, [role=search]') || el.disabled) return;
    const shown = visible(el) || (['radio', 'checkbox', 'file'].includes(type) && el.parentElement && visible(el.parentElement));
    if (!shown) return;
    el.setAttribute('data-jobflow-field', String(i));
    const required = el.required || el.getAttribute('aria-required') === 'true';
    if (type === 'radio') {
      const name = el.name || ('radio' + i);
      const optionLabel = (el.labels && el.labels.length) ? text(el.labels[0]) : (el.value || '');
      if (!groups[name]) {
        const holder = el.closest('fieldset, [role=radiogroup]') || el.parentElement?.parentElement;
        const legend = holder && holder.querySelector('legend, p, span, label');
        groups[name] = { key: 'radio:' + name, label: legend ? text(legend) : name, type: 'radio', required, options: [], filled: false };
        out.push(groups[name]);
      }
      groups[name].options.push(optionLabel);
      groups[name].required = groups[name].required || required;
      groups[name].filled = groups[name].filled || el.checked;
      return;
    }
    out.push({ key: String(i), label: labelOf(el).slice(0, 300), type, required,
      options: type === 'select' ? [...el.options].map(o => o.text.trim()).filter(Boolean) : [],
      filled: type === 'checkbox' ? el.checked : type === 'file' ? el.files.length > 0 :
              type === 'select' ? (el.selectedIndex > 0 || (el.value && !/selecc|elige/i.test(el.options[el.selectedIndex]?.text || ''))) : !!el.value.trim() });
  });
  return out;
}
"""

ACTION_JS = r"""
([patterns, donePattern, genericOutsideDialog]) => {
  const done = new RegExp(donePattern, 'i');
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-jobflow-action],[data-jobflow-scope]').forEach(e => { e.removeAttribute('data-jobflow-action'); e.removeAttribute('data-jobflow-scope'); });
  const dialog = [...document.querySelectorAll('[role=dialog], dialog[open], .modal.show, [aria-modal=true]')].filter(visible).pop();
  const root = dialog || document;
  const buttons = [...root.querySelectorAll('button, a, input[type=submit], [role=button]')].filter(visible)
    .filter(b => !b.closest('header, footer, nav') && !b.disabled);
  const label = b => (b.innerText || b.value || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  let button = null;
  patterns.forEach((pattern, i) => {
    if (button || (i > 0 && !dialog && !genericOutsideDialog)) return;
    const re = new RegExp(pattern, 'i'); button = buttons.find(b => re.test(label(b)));
  });
  if (!button && buttons.some(b => done.test(label(b)))) return { done: true };
  if (!button) return { found: false, dialog: !!dialog };
  button.setAttribute('data-jobflow-action', '1');
  let scope = button.closest('form, [role=dialog], dialog, [aria-modal=true]');
  if (!scope) { let n = button; for (let i = 0; i < 6 && n; i++) { n = n.parentElement; if (n && n.querySelector('input, textarea, select')) { scope = n; break; } } }
  if (scope) scope.setAttribute('data-jobflow-scope', '1');
  return { found: true, label: label(button), scoped: !!scope, dialog: !!dialog };
}
"""


def _visible_text(page) -> str:
    try:
        return page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception:
        return ""


def _settle(page, ms=2500):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def _blocker(page) -> str:
    if page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='challenges.cloudflare'], .g-recaptcha, .h-captcha").count():
        return "captcha"
    body = _visible_text(page)
    if BLOCK_TEXT.search(body[:600]):
        return "bloqueo_portal"
    if CAPTCHA_TEXT.search(body):
        return "captcha"
    if TEST_TEXT.search(body):
        return "evaluacion"
    return ""


def _confirmation(page) -> str:
    m = CONFIRM_TEXT.search(_visible_text(page))
    return m.group(0) if m else ""


def _perform(page, step):
    target = page.locator(f"[data-jobflow-field='{step['key']}']") if not step["key"].startswith("radio:") else None
    if step["action"] == "fill":
        target.first.fill(str(step["value"]))
    elif step["action"] == "file":
        target.first.set_input_files(step["value"])
    elif step["action"] == "select":
        if step["type"] == "select":
            target.first.select_option(label=step["value"])
        else:
            name = step["key"].split(":", 1)[1]
            page.get_by_label(step["value"], exact=True).and_(page.locator(f"input[name='{name}']")).first.check()


def apply_on_page(page, portal: str, url: str, planner, max_steps: int = 6, trace: dict | None = None) -> dict:
    """Recorre el formulario del portal. `planner(fields)` devuelve el plan de llenado.

    `trace` se comparte con quien llama para saber si hubo clics aunque ocurra un error.
    """
    trace = trace if trace is not None else {}
    trace.setdefault("clicks", [])
    trace.setdefault("filled", [])

    def result(status, reason="", **extra):
        return {"status": status, "reason": reason, "trace": trace, "url": page.url, **extra}

    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    _settle(page, 3000)
    clicked_on = page.url
    for _ in range(max_steps):
        if on_login(page.url, portal):
            return result("bloqueada", "sesion_cerrada", message="El portal pidió iniciar sesión nuevamente.")
        blocker = _blocker(page)
        if blocker:
            return result("bloqueada", blocker, message={
                "captcha": "El portal muestra un CAPTCHA o una verificación: requiere tu intervención.",
                "bloqueo_portal": "El portal bloqueó el acceso desde el navegador. Postula desde el aviso original o inténtalo más tarde.",
            }.get(blocker, "La postulación incluye una prueba o video: complétala personalmente."))
        evidence = _confirmation(page)
        if evidence:
            return result("postulada", "confirmacion_portal", evidence=evidence, previa=not trace["clicks"])
        patterns = [APPLY_TEXT, NEXT_TEXT] if trace["clicks"] else [APPLY_TEXT]
        navigated = bool(trace["clicks"]) and page.url != clicked_on
        action = page.evaluate(ACTION_JS, [patterns, DONE_BUTTON, navigated])
        if action.get("done"):
            return result("postulada", "confirmacion_portal", evidence="El portal indica que la postulación figura como enviada.",
                          previa=not trace["clicks"])
        if not action.get("found"):
            break
        if action["label"] in trace["clicks"] and not re.match(r"^(siguiente|continuar|guardar y continuar)$", action["label"], re.I):
            # Never press a send/apply button twice: the first press may already have applied.
            errors = page.evaluate("() => [...document.querySelectorAll('[role=alert], .error, .invalid-feedback, .field-error')]"
                                   ".map(e => e.innerText.trim()).filter(Boolean).slice(0, 5)")
            return result("intento_no_confirmado", "sin_confirmacion",
                          message="El portal volvió a mostrar el botón sin confirmar la postulación. Revisa el portal antes de reintentar. "
                                  + " · ".join(errors))
        fields = page.evaluate(FIELDS_JS, "[data-jobflow-scope='1']" if action.get("scoped") else "body")
        plan = planner(fields)
        pending = [s for s in plan if s["action"] == "pending"]
        if pending:
            return result("bloqueada", "preguntas", message="Hay preguntas sin un dato confirmado. Respóndelas y vuelve a intentarlo.",
                          questions=pending, fields=fields)
        for step in plan:
            if step["action"] in ("fill", "select", "file"):
                _perform(page, step)
                trace["filled"].append({"label": step["label"], "value": step["value"] if step["action"] != "file" else "CV adjunto",
                                        "source": step.get("source", "")})
        clicked_on = page.url
        page.locator("[data-jobflow-action='1']").first.click()
        trace["clicks"].append(action["label"])
        _settle(page)
    evidence = _confirmation(page)
    if evidence:
        return result("postulada", "confirmacion_portal", evidence=evidence, previa=False)
    if not trace["clicks"]:
        return result("bloqueada", "sin_boton", message="No se encontró el botón para postular. La vacante puede estar cerrada.")
    return result("intento_no_confirmado", "sin_confirmacion",
                  message="No apareció una confirmación del portal. Revisa tus postulaciones en el portal antes de reintentar.")


# --------------------------------------------------------------------------- #
#  Cola y trabajador
# --------------------------------------------------------------------------- #
WAKE = threading.Event()
STOP = threading.Event()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            STOP.clear()
            _worker = threading.Thread(target=worker_loop, name="jobflow-auto-apply", daemon=True)
            _worker.start()
    WAKE.set()


def recover_interrupted():
    """Una ejecucion cortada pudo haber enviado la postulacion: nunca se repite sola."""
    db = SessionLocal()
    try:
        for run in db.query(AutoApplyRun).filter_by(status="ejecutando"):
            run.status = "intento_no_confirmado"
            run.detail = {**(run.detail or {}), "message": "JobFlow se cerró durante la postulación. Revisa el portal."}
            db.add(AuditEvent(application_id=run.application_id, action="intento_no_confirmado",
                              payload={"run_id": run.id, "motivo": "ejecucion_interrumpida"}))
        db.commit()
        return db.query(AutoApplyRun).filter_by(status="en_cola").count()
    finally:
        db.close()


def worker_loop():
    delay = float(os.getenv("JOBFLOW_APPLY_DELAY_SECONDS", "45"))
    while not STOP.is_set():
        db = SessionLocal()
        try:
            # The login window and an application cannot share the browser profile at once.
            queued = db.query(AutoApplyRun).filter_by(status="en_cola").order_by(AutoApplyRun.id).all()
            run_id = next((r.id for r in queued if not login_active(r.profile_id)), None)
        finally:
            db.close()
        if not run_id:
            WAKE.wait(30)
            WAKE.clear()
            continue
        process_run(run_id)
        STOP.wait(delay * random.uniform(0.7, 1.3))


def run_in_browser(pid: int, fn):
    """Abre el Chrome/Edge del candidato con su perfil de JobFlow (sesiones incluidas)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        real = RealBrowser(p, pid)
        try:
            page = real.context.new_page()
            for extra in real.pages():
                if extra != page and extra.url in ("about:blank", "chrome://newtab/", "edge://newtab/"):
                    extra.close()
            return fn(page)
        finally:
            real.close()


def process_run(run_id: int):
    from .career import CVVersion, profile_hash
    from .cv_generator import build_docx
    from .models import Postulacion, Vacante
    from .seed import get_profile_row, profile_from_row
    db = SessionLocal()
    try:
        run = db.get(AutoApplyRun, run_id)
        if not run or run.status != "en_cola":
            return
        app = db.get(Postulacion, run.application_id)
        vacancy = db.get(Vacante, app.vacante_id)
        row = get_profile_row(db, run.profile_id)
        acc = account(db, run.profile_id, run.portal)
        run.status, run.updated = "ejecutando", datetime.utcnow()
        db.add(AuditEvent(application_id=app.id, action="auto_postulacion_iniciada", payload={"run_id": run.id, "portal": run.portal}))
        db.commit()
        try:
            state = json.loads(cipher().decrypt(acc.encrypted.encode())) if acc and acc.status == "connected" else None
        except (InvalidToken, ValueError):
            state = None
        if not state or state.get("formato") != "navegador_real":
            return finish(db, run, {"status": "bloqueada", "reason": "sesion_cerrada", "message": "Vuelve a conectar tu cuenta del portal."})
        cv_path = None
        version = next((v for v in db.query(CVVersion).filter_by(application_id=app.id).order_by(CVVersion.id.desc())
                        if v.snapshot.get("approved") and v.snapshot.get("profile_hash") == profile_hash(row)), None)
        if version:
            cv_path = str(evidence_dir() / f"cv_{run.id}.docx")
            Path(cv_path).write_bytes(build_docx(version.snapshot["cv"]).getvalue())
        profile = profile_from_row(row)
        approved = approved_answers(db, app.id)
        planner = lambda fields: plan_fields(fields, profile, vacancy.titulo, approved, cv_path)
        shot = evidence_dir() / f"run_{run.id}.png"

        trace: dict = {}

        def work(page):
            try:
                outcome = apply_on_page(page, run.portal, vacancy.url, planner, trace=trace)
            except Exception as exc:
                outcome = {"status": "error", "reason": "fallo_tecnico", "message": str(exc)[:300], "trace": trace}
            try:
                page.screenshot(path=str(shot))
                outcome["captura"] = shot.name
            except Exception:
                pass
            return outcome

        try:
            outcome = run_in_browser(run.profile_id, work)
        except Exception as exc:
            outcome = {"status": "error", "reason": "navegador", "message": "Falló el navegador: " + str(exc)[:200], "trace": trace}
        outcome["cv_version_id"] = version.id if version else None
        finish(db, run, outcome)
    finally:
        db.close()


def finish(db, run, outcome: dict):
    from .models import Postulacion
    app = db.get(Postulacion, run.application_id)
    trace = outcome.get("trace") or {}
    if outcome.get("status") == "error" and trace.get("clicks"):
        outcome = {**outcome, "status": "intento_no_confirmado",
                   "message": "Ocurrió un fallo después de pulsar en el portal. Revisa si la postulación figura antes de reintentar."}
    acc = account(db, run.profile_id, run.portal)
    if acc and outcome.get("status") == "postulada":
        acc.checked_at = datetime.utcnow()
    if acc and outcome.get("reason") == "sesion_cerrada":
        acc.status = "expired"
    status = outcome.get("status", "error")
    questions = outcome.pop("questions", None)
    outcome.pop("fields", None)
    run.status, run.updated = status, datetime.utcnow()
    run.detail = {**outcome, "questions": questions or []}
    payload = {"run_id": run.id, "portal": run.portal, "motivo": outcome.get("reason"), "mensaje": outcome.get("message", ""),
               "captura": outcome.get("captura"), "respuestas_enviadas": trace.get("filled", [])}
    if status == "postulada":
        app.estado = "postulada"
        app.fecha_envio = app.fecha_envio or datetime.utcnow()
        app.respuestas_formulario = trace.get("filled", [])
        db.add(AuditEvent(application_id=app.id, action="postulada", payload={
            **payload, "tipo_evidencia": "mensaje_portal", "evidencia": outcome.get("evidence", ""),
            "fuente": "Confirmación detectada por JobFlow en el portal" + (" (postulación previa)" if outcome.get("previa") else ""),
            "cv_version_id": outcome.get("cv_version_id")}))
    elif status == "bloqueada":
        app.estado = "bloqueada"
        if questions:
            form = FormularioResuelto(profile_id=run.profile_id, postulacion_id=app.id, plataforma=run.portal,
                                      campos_detectados=questions, mapeo_semantico=[],
                                      respuestas_generadas=[{"field_id": q["key"], "label": q["label"], "answer": "",
                                                             "fuente": "", "necesita_input": True,
                                                             "bloqueada": "sensible" in q.get("reason", ""),
                                                             "nota": q.get("reason", ""), "opciones": q.get("options", [])}
                                                            for q in questions],
                                      aprobado_por_usuario=False)
            db.add(form)
            db.flush()
            payload["form_id"] = form.id
        db.add(AuditEvent(application_id=app.id, action="bloqueada", payload=payload))
    elif status == "intento_no_confirmado":
        app.estado = "intento_no_confirmado"
        db.add(AuditEvent(application_id=app.id, action="intento_no_confirmado", payload=payload))
    else:
        db.add(AuditEvent(application_id=app.id, action="auto_postulacion_error", payload=payload))
    db.commit()
    return run


def queue_application(db, aid: int, confirm_not_sent: bool = False) -> AutoApplyRun:
    from .career import application, require_ready
    app, vacancy = application(db, aid)
    require_ready(db, app.profile_id)
    portal = portal_for_url(vacancy.url if vacancy else "")
    if portal in UNSUPPORTED:
        raise HTTPException(409, UNSUPPORTED[portal])
    if portal not in PORTALS:
        raise HTTPException(409, "La postulación automática está disponible para avisos de Bumeran y Computrabajo.")
    if app.estado in BLOCKED_STATES:
        raise HTTPException(409, "Esta vacante está marcada como incompatible, duplicada, vencida o rechazada.")
    if db.query(AuditEvent).filter_by(application_id=aid, action="postulada").first():
        raise HTTPException(409, "Esta candidatura ya tiene una postulación confirmada.")
    detail = db.query(ApplicationDetail).filter_by(application_id=aid).first()
    if detail and (detail.details or {}).get("analisis", {}).get("requisito_excluyente"):
        raise HTTPException(409, "La vacante tiene un requisito excluyente. Revísala antes de postular.")
    acc = account(db, app.profile_id, portal)
    if not acc or acc.status != "connected" or not account_ready(acc):
        raise HTTPException(409, f"Conecta tu cuenta de {PORTALS[portal]['nombre']} en Conexiones.")
    runs = db.query(AutoApplyRun).filter_by(application_id=aid).order_by(AutoApplyRun.id.desc()).all()
    if runs and runs[0].status in ACTIVE_RUNS:
        raise HTTPException(409, "Esta candidatura ya está en la cola de postulación.")
    if runs and runs[0].status == "intento_no_confirmado" and not confirm_not_sent:
        raise HTTPException(409, f"El último intento no se confirmó. Revisa en {PORTALS[portal]['nombre']} si figura tu postulación; "
                                 "si no figura, confirma que no se envió para reintentar.")
    since = datetime.utcnow() - timedelta(hours=24)
    used = db.query(AutoApplyRun).filter(AutoApplyRun.profile_id == app.profile_id, AutoApplyRun.created >= since,
                                         AutoApplyRun.status.in_(("en_cola", "ejecutando", "postulada", "intento_no_confirmado"))).count()
    if used >= DAILY_LIMIT:
        raise HTTPException(429, f"Llegaste al límite de {DAILY_LIMIT} postulaciones automáticas en 24 horas.")
    ok, note = browser_status()
    if not ok:
        raise HTTPException(409, note)
    run = AutoApplyRun(application_id=aid, profile_id=app.profile_id, portal=portal, status="en_cola",
                       detail={"confirmado_no_enviado": confirm_not_sent} if confirm_not_sent else {})
    db.add(run)
    db.flush()
    db.add(AuditEvent(application_id=aid, action="auto_postulacion_autorizada", payload={
        "run_id": run.id, "portal": portal, "confirmo_intento_previo_no_enviado": confirm_not_sent}))
    db.commit()
    return run


def run_data(run: AutoApplyRun) -> dict:
    d = run.detail or {}
    return {"id": run.id, "application_id": run.application_id, "portal": run.portal, "status": run.status,
            "created": run.created.isoformat(), "updated": run.updated.isoformat() if run.updated else None,
            "message": d.get("message", ""), "reason": d.get("reason", ""), "evidence": d.get("evidence", ""),
            "questions": d.get("questions", []), "filled": (d.get("trace") or {}).get("filled", []),
            "screenshot": f"/api/portals/runs/{run.id}/captura" if d.get("captura") else None}


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #
class ApplyRequest(BaseModel):
    confirm_not_sent: bool = False


class BatchRequest(BaseModel):
    application_ids: list[int] = Field(min_length=1, max_length=30)


@router.get("/{pid}")
def portals_status(pid: int, db: Session = Depends(get_db)):
    from .career import profile_row
    profile_row(db, pid)
    ok, note = browser_status()
    accounts = []
    for key, cfg in PORTALS.items():
        acc = account(db, pid, key)
        login = LOGINS.get((pid, key))
        status = acc.status if acc else "disconnected"
        if acc and status == "connected" and not account_ready(acc):
            status = "expired"  # sessions saved by 0.6.0 used the blocked automation browser
        accounts.append({"portal": key, "nombre": cfg["nombre"], "status": status,
                         "connected_at": acc.connected_at.isoformat() if acc else None,
                         "login": {"status": login["status"], "message": login["message"]} if login else None})
    queue = db.query(AutoApplyRun).filter(AutoApplyRun.profile_id == pid, AutoApplyRun.status.in_(ACTIVE_RUNS)).count()
    return {"browser_available": ok, "browser_note": note, "accounts": accounts, "unsupported": UNSUPPORTED,
            "queue": queue, "daily_limit": DAILY_LIMIT}


@router.post("/{pid}/{portal}/connect")
def connect_portal(pid: int, portal: str, db: Session = Depends(get_db)):
    from .career import profile_row
    profile_row(db, pid)
    if portal not in PORTALS:
        raise HTTPException(404, UNSUPPORTED.get(portal, "Portal no disponible"))
    ok, note = browser_status()
    if not ok:
        raise HTTPException(409, note)
    open_portal = login_active(pid)
    if open_portal == portal:
        return {"status": LOGINS[(pid, portal)]["status"], "message": "La ventana de inicio de sesión ya está abierta."}
    if open_portal:
        raise HTTPException(409, f"Termina primero la conexión de {PORTALS[open_portal]['nombre']} (o cancélala).")
    if db.query(AutoApplyRun).filter_by(profile_id=pid, status="ejecutando").first():
        raise HTTPException(409, "Hay una postulación en curso con tu navegador. Espera a que termine.")
    _set_login((pid, portal), "abriendo", f"Abriendo {PORTALS[portal]['nombre']} en tu navegador…")
    threading.Thread(target=login_worker, args=(pid, portal), daemon=True, name=f"jobflow-login-{portal}").start()
    return {"status": "abriendo", "message": f"Se abrirá {PORTALS[portal]['nombre']} en tu navegador. Inicia sesión allí y pulsa «Ya inicié sesión»."}


@router.post("/{pid}/{portal}/verify")
def verify_portal(pid: int, portal: str):
    if login_active(pid) != portal:
        raise HTTPException(409, "No hay una ventana de inicio de sesión abierta para este portal. Pulsa Conectar.")
    _request_login((pid, portal), "verify")
    return {"status": "verificando", "message": "Comprobando tu sesión…"}


@router.post("/{pid}/{portal}/cancel")
def cancel_portal(pid: int, portal: str):
    if login_active(pid) == portal:
        _request_login((pid, portal), "cancel")
    return {"status": "cancelada", "message": "Cerrando la ventana de inicio de sesión."}


@router.post("/{pid}/{portal}/disconnect")
def disconnect_portal(pid: int, portal: str, db: Session = Depends(get_db)):
    if login_active(pid) or db.query(AutoApplyRun).filter_by(profile_id=pid, status="ejecutando").first():
        raise HTTPException(409, "Espera a que termine la ventana abierta o la postulación en curso.")
    acc = account(db, pid, portal)
    if acc:
        db.delete(acc)
        db.commit()
    LOGINS.pop((pid, portal), None)
    note = "Cuenta desconectada de JobFlow."
    if not db.query(PortalAccount).filter_by(profile_id=pid).count():
        # No connected portal remains: delete the browser profile and its cookies.
        shutil.rmtree(Path(settings.data_dir).resolve() / "navegador" / f"perfil_{pid}", ignore_errors=True)
        note += " Se borró la sesión guardada en el navegador de JobFlow."
    else:
        note += " Para cerrar la sesión por completo, sal de tu cuenta desde la web del portal."
    return {"disconnected": True, "note": note}


@router.post("/applications/{aid}/apply", status_code=202)
def apply_application(aid: int, req: ApplyRequest, db: Session = Depends(get_db)):
    run = queue_application(db, aid, req.confirm_not_sent)
    ensure_worker()
    return run_data(run)


@router.post("/{pid}/apply-batch", status_code=202)
def apply_batch(pid: int, req: BatchRequest, db: Session = Depends(get_db)):
    from .models import Postulacion
    results = []
    for aid in dict.fromkeys(req.application_ids):
        app = db.get(Postulacion, aid)
        if not app or app.profile_id != pid:
            results.append({"application_id": aid, "queued": False, "error": "La candidatura no pertenece a este perfil."})
            continue
        try:
            results.append({"application_id": aid, "queued": True, "run": run_data(queue_application(db, aid))})
        except HTTPException as exc:
            db.rollback()
            results.append({"application_id": aid, "queued": False, "error": exc.detail})
    if any(r["queued"] for r in results):
        ensure_worker()
    return {"results": results}


@router.get("/applications/{aid}/runs")
def application_runs(aid: int, db: Session = Depends(get_db)):
    from .career import application
    _, vacancy = application(db, aid)
    portal = portal_for_url(vacancy.url if vacancy else "")
    return {"portal": portal, "supported": portal in PORTALS, "note": UNSUPPORTED.get(portal, ""),
            "runs": [run_data(r) for r in db.query(AutoApplyRun).filter_by(application_id=aid).order_by(AutoApplyRun.id.desc())]}


@router.get("/runs/{rid}/captura")
def run_screenshot(rid: int, db: Session = Depends(get_db)):
    run = db.get(AutoApplyRun, rid)
    name = (run.detail or {}).get("captura") if run else None
    path = evidence_dir() / name if name else None
    if not path or not path.exists():
        raise HTTPException(404, "Captura no disponible")
    return FileResponse(str(path), media_type="image/png")
