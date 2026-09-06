"""Punto de entrada: `python -m jobflow`.

Arranca la API y abre el navegador en la web de JobFlow AI.
Elige automaticamente un puerto libre (8000, 8001, ...) para que NUNCA
falle por "puerto en uso" y muestra la URL correcta.
"""
from __future__ import annotations

import socket
import threading
import webbrowser

import uvicorn

from .config import settings


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
