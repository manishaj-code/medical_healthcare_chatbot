import redis.asyncio as redis

from app.database import get_settings

settings = get_settings()
_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def ping_redis() -> bool:
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
