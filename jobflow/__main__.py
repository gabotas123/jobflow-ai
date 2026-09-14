"""Punto de entrada: `python -m jobflow`.

Arranca la API y abre el navegador en la web de JobFlow AI.
Elige automaticamente un puerto libre (8000, 8001, ...) para que NUNCA
falle por "puerto en uso" y muestra la URL correcta.
"""
from __future__ import annotations

import os
import socket
import subprocess
import threading
import webbrowser

import uvicorn

from .config import settings


def _stop_previous_instances() -> int:
    """Cierra otras ventanas de JobFlow abiertas: con varias a la vez, cada una tomaba
    postulaciones de la misma cola con su propia versión del código."""
    if os.name != "nt":
        return 0
    me, parent = os.getpid(), os.getppid()
    query = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match '-m jobflow' } | ForEach-Object { $_.ProcessId }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    others = [int(x) for x in out.split() if x.isdigit() and int(x) not in (me, parent)]
    for pid in others:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    return len(others)


def _find_free_port(start: int = 8000, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:  # pragma: no cover
        pass


def main() -> None:
    closed = _stop_previous_instances()
    if closed:
        print(f"  Se cerraron {closed} procesos de JobFlow abiertos antes: queda solo esta versión.")
    port = _find_free_port() or settings.port
    url = f"http://127.0.0.1:{port}/"
    print("=" * 60)
    print("  JobFlow AI")
    print(f"  Abriendo tu navegador en:  {url}")
    print("  (cierra esta ventana para detener la app)")
    print("=" * 60)
    threading.Timer(3.0, _open_browser, args=(url,)).start()
    uvicorn.run("jobflow.main:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
