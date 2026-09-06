"""Punto de entrada: `python -m jobflow`.

Arranca la API y abre el navegador en la web de JobFlow AI.
"""
from __future__ import annotations

import threading
import webbrowser

import uvicorn

from .config import settings


def _open_browser() -> None:
    try:
        webbrowser.open(f"http://127.0.0.1:{settings.port}/")
    except Exception:  # pragma: no cover
        pass


def main() -> None:
    print(f"JobFlow AI -> http://127.0.0.1:{settings.port}/  (cierra esta ventana para detener)")
    threading.Timer(2.5, _open_browser).start()
    uvicorn.run("jobflow.main:app", host="127.0.0.1", port=settings.port, reload=False)


if __name__ == "__main__":
    main()
