from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, get_settings, setup_logging
from app.middleware import AuditMiddleware, RateLimitMiddleware, RequestIDMiddleware
from app.routes.router import api_router
from app.services.cache import close_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield
    await close_redis()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuditMiddleware)
    from app.routes.health import router as health_router

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
