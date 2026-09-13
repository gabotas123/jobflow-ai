"""Single-owner deployment guard; Codespaces also keeps its forwarded port private."""
import base64
import hmac
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class AccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        password = os.getenv("JOBFLOW_ACCESS_PASSWORD", "")
        external = os.getenv("JOBFLOW_REQUIRE_AUTH", "false").lower() == "true"
        if request.url.path == "/healthz":
            return await call_next(request)
        if external and not password:
            return Response("Configura JOBFLOW_ACCESS_PASSWORD antes de abrir la aplicación.", status_code=503)
        if password:
            try:
                scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
                user, supplied = base64.b64decode(encoded, validate=True).decode().split(":", 1)
                valid = scheme.lower() == "basic" and hmac.compare_digest(user.encode(), b"jobflow") and hmac.compare_digest(supplied.encode(), password.encode())
            except (ValueError, UnicodeError):
                valid = False
            if not valid:
                return Response("Acceso privado", status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="JobFlow", charset="UTF-8"'})
        # Cross-site writes are never authorized by a previously cached Basic login.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlsplit
                if urlsplit(origin).netloc != request.headers.get("host"):
                    return Response("Origen no autorizado", status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response
