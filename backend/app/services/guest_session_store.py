import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, Patient
from app.models.enums import MessageRole
from app.services.cache import get_redis
from app.services.flow_state import set_flow
from app.services.symptom_extraction import resolve_detected_symptoms

GUEST_PREFIX = "guest:session:"
GUEST_TTL_SECONDS = 60 * 60 * 24


def _guest_key(session_id: str) -> str:
    return GUEST_PREFIX + session_id


async def create_guest_session() -> str:
    session_id = str(uuid.uuid4())
    redis = await get_redis()
    payload = {"messages": [], "session": {}}
    await redis.setex(_guest_key(session_id), GUEST_TTL_SECONDS, json.dumps(payload))
    return session_id


async def load_guest_session(session_id: str) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(_guest_key(session_id))
    if not raw:
        return None
    return json.loads(raw)


async def save_guest_session(session_id: str, data: dict) -> None:
    redis = await get_redis()
    await redis.setex(_guest_key(session_id), GUEST_TTL_SECONDS, json.dumps(data))


async def migrate_guest_session(
    db: AsyncSession,
    session_id: str,
    patient: Patient,
    *,
    title: str | None = None,
) -> Conversation | None:
    data = await load_guest_session(session_id)
    if not data or not data.get("messages"):
        return None

    conv = Conversation(patient_id=patient.id, title=title or "Health Chat", language="en")
    db.add(conv)
    await db.flush()

    base_time = datetime.now(timezone.utc)
    for i, msg in enumerate(data["messages"]):
        role = MessageRole.user if msg.get("role") == "user" else MessageRole.assistant
        db.add(
            Message(
                conversation_id=conv.id,
                role=role,
                content=msg.get("content", ""),
                agent_name=msg.get("agent"),
                tool_calls_json={"ui": msg["ui"]} if msg.get("ui") else None,
                created_at=base_time + timedelta(microseconds=i),
            )
        )
    await db.flush()

    guest_session = data.get("session") or {}
    symptoms = await resolve_detected_symptoms(
        guest_session,
        [{"role": m.get("role"), "content": m.get("content", "")} for m in data["messages"]],
    )
    if symptoms:
        await set_flow(
            conv.id,
            {
                "session": {
                    "detected_symptoms": symptoms,
                    "triage_collected": {"symptoms": symptoms},
                }
            },
        )

    redis = await get_redis()
    await redis.delete(_guest_key(session_id))
    return conv
