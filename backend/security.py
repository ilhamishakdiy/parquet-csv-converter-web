"""Loopback API guard (PRD 05): Host + Origin validation, exact CORS, Private Network
Access preflight and a per-launch session token. CORS alone is not authentication."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

PROTECTED_PREFIXES = ("/inspect", "/preview", "/jobs", "/browse", "/open")


def token_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def token_valid(request: Request, expected: str) -> bool:
    supplied = token_from(request)
    return bool(supplied) and hmac.compare_digest(supplied.encode(), expected.encode())


class LoopbackGuard(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str, allowed_hosts: set[str], trusted_origins: set[str]):
        super().__init__(app)
        self.token = token
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.trusted_origins = trusted_origins

    def _cors(self, response: Response, origin: str | None) -> Response:
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in self.allowed_hosts:
            # Blocks DNS-rebinding: only 127.0.0.1/localhost on our port are accepted.
            return JSONResponse({"detail": {"code": "invalid_host", "message": "Invalid Host header."}}, status_code=421)

        origin = request.headers.get("origin")
        if origin is not None and origin not in self.trusted_origins:
            return JSONResponse({"detail": {"code": "untrusted_origin", "message": "Origin not allowed."}}, status_code=403)

        if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
            response = Response(status_code=204)
            response.headers["Access-Control-Allow-Methods"] = "GET, POST"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Max-Age"] = "600"
            if request.headers.get("access-control-request-private-network") == "true":
                response.headers["Access-Control-Allow-Private-Network"] = "true"
            return self._cors(response, origin)

        if request.url.path.startswith(PROTECTED_PREFIXES) and not token_valid(request, self.token):
            return self._cors(
                JSONResponse(
                    {
                        "detail": {
                            "code": "invalid_token",
                            "message": "This page is not paired with the running converter. Double-click Start.bat to reopen it.",
                        }
                    },
                    status_code=401,
                ),
                origin,
            )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return self._cors(response, origin)
