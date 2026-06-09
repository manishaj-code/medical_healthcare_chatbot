"""HTTP middleware: request ID, rate limiting, audit logging, security headers."""

import hashlib
import time
import uuid
from contextvars import ContextVar

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from app.database import AsyncSessionLocal, get_settings
from app.models.system import AuditLog
from app.services.cache import get_redis

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

settings = get_settings()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_ctx.set(rid)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        if request.url.path.startswith("/api/v1/auth/login"):
            limit = settings.rate_limit_auth_per_minute
            key = f"rl:auth:{request.client.host if request.client else 'unknown'}"
        elif "/chat/" in request.url.path:
            limit = settings.rate_limit_chat_per_minute
            key = f"rl:chat:{request.client.host if request.client else 'unknown'}"
        else:
            return await call_next(request)

        try:
            r = await get_redis()
            now = int(time.time())
            window = now // 60
            rk = f"{key}:{window}"
            count = await r.incr(rk)
            if count == 1:
                await r.expire(rk, 60)
            if count > limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        except HTTPException:
            raise
        except Exception:
            pass
        return await call_next(request)


class AuditMiddleware(BaseHTTPMiddleware):
    MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        response = await call_next(request)
        if request.method in self.MUTATING and request.url.path.startswith("/api/"):
            actor_id = getattr(request.state, "user_id", None)
            ip = request.client.host if request.client else "unknown"
            ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
            async with AsyncSessionLocal() as db:
                db.add(
                    AuditLog(
                        actor_id=actor_id,
                        action=f"{request.method} {request.url.path}",
                        request_id=request_id_ctx.get(),
                        ip_hash=ip_hash,
                        status_code=response.status_code,
                    )
                )
                await db.commit()
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        response = await call_next(request)
        if get_settings().secure_headers_enabled:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response
