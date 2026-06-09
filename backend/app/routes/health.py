from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.database import engine
from app.schemas.common import Meta, ResponseEnvelope
from app.services.cache import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
async def ready():
    db_ok = redis_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    redis_ok = await ping_redis()
    status = "ready" if db_ok and redis_ok else "degraded"
    code = 200 if db_ok and redis_ok else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=code,
        content={"status": status, "database": db_ok, "redis": redis_ok},
    )
