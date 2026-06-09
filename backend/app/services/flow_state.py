"""Redis-backed conversation flow state for multi-step agentic flows."""
import json
import logging
from datetime import date, datetime, time
from uuid import UUID

from app.services.cache import get_redis

logger = logging.getLogger(__name__)
TTL = 86400  # 24 hours — care goals and multi-agent session


def _key(conversation_id: UUID) -> str:
    return f"flow:{conversation_id}"


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


async def get_flow(conversation_id: UUID) -> dict:
    try:
        redis = await get_redis()
        raw = await redis.get(_key(conversation_id))
        return json.loads(raw) if raw else {}
    except Exception as exc:
        logger.warning("get_flow failed: %s", exc)
        return {}


async def set_flow(conversation_id: UUID, data: dict) -> None:
    try:
        redis = await get_redis()
        await redis.set(_key(conversation_id), json.dumps(data, default=_json_default), ex=TTL)
    except Exception as exc:
        logger.warning("set_flow failed: %s", exc)


async def clear_flow(conversation_id: UUID) -> None:
    try:
        redis = await get_redis()
        await redis.delete(_key(conversation_id))
    except Exception:
        pass


async def update_flow(conversation_id: UUID, **kwargs) -> dict:
    data = await get_flow(conversation_id)
    data.update(kwargs)
    await set_flow(conversation_id, data)
    return data
