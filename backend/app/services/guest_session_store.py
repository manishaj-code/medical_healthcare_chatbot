import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, Patient
from app.models.enums import MessageRole
from app.services.cache import get_redis
from app.services.flow_state import clear_flow, get_flow, set_flow
from app.services.guest_flow import guest_flow_conversation_id
from app.services.guest_resume_service import (
    merge_guest_flow_sessions,
    migration_title,
    prepare_resume_session,
)
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

    guest_session = data.get("session") or {}
    guest_flow_id = guest_flow_conversation_id(session_id)
    guest_flow = await get_flow(guest_flow_id)
    flow_session = merge_guest_flow_sessions(guest_session, guest_flow.get("session") or {})

    conv = Conversation(
        patient_id=patient.id,
        title=title or migration_title(flow_session),
        language="en",
        active_agent=flow_session.get("active_specialist") or "conversation",
    )
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

    symptoms = await resolve_detected_symptoms(
        flow_session,
        [{"role": m.get("role"), "content": m.get("content", "")} for m in data["messages"]],
    )
    if symptoms:
        flow_session["detected_symptoms"] = symptoms
        triage = dict(flow_session.get("triage_collected") or {})
        triage["symptoms"] = symptoms
        flow_session["triage_collected"] = triage

    pending_action = flow_session.get("pending_auth_action")
    if pending_action:
        flow_session = prepare_resume_session(flow_session, pending_action)

    if flow_session:
        await set_flow(conv.id, {"session": flow_session})

    redis = await get_redis()
    await redis.delete(_guest_key(session_id))
    await clear_flow(guest_flow_id)
    return conv
