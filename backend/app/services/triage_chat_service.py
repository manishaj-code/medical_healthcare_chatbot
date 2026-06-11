"""Extract triage data from chat history and flow state for doctor summaries."""
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import DURATION_PATTERN, _parse_condition, _pending_duration_number
from app.models import Conversation, Message, SymptomAssessment
from app.services.flow_state import get_flow
from app.services.symptom_extraction import resolve_detected_symptoms
from app.services.symptom_service import save_assessment


def extract_triage_from_history(history: list[dict] | None) -> dict:
    """Parse duration and chronic conditions from user messages only — never infer symptoms."""
    duration: str | None = None
    conditions: list[str] = []

    if not history:
        return {"symptoms": [], "duration": duration, "conditions": conditions}

    for h in history:
        if str(h.get("role")) != "user":
            continue
        content = h.get("content", "")
        text = content.lower()

        if DURATION_PATTERN.search(text) or re.search(r"\d+\s*days?", text):
            duration = content.strip()
        elif text in {"day", "days", "hour", "hours", "week", "weeks", "month", "months"}:
            num = _pending_duration_number(history[: history.index(h) + 1])
            if num:
                duration = f"{num} {content.strip()}"

        cond = _parse_condition(text)
        if cond and cond not in conditions:
            conditions.append(cond)

    return {"symptoms": [], "duration": duration, "conditions": conditions}


def _add_symptom(symptoms: list[str], seen: set[str], raw: str) -> None:
    label = raw.strip()
    key = label.lower()
    if not label or key in seen:
        return
    if key in {"general symptoms", "general discomfort", "unspecified symptoms"}:
        return
    seen.add(key)
    symptoms.append(label)


async def collect_triage_data(session: dict, history: list[dict] | None) -> dict:
    """Merge triage from flow session (triage_collected, detected_symptoms) and chat history."""
    hist_data = extract_triage_from_history(history)
    triage = session.get("triage_collected") or {}

    symptoms: list[str] = []
    seen: set[str] = set()

    for raw in triage.get("symptoms") or []:
        _add_symptom(symptoms, seen, str(raw))
    for raw in session.get("detected_symptoms") or []:
        _add_symptom(symptoms, seen, str(raw))
    for raw in await resolve_detected_symptoms(session, history or []):
        _add_symptom(symptoms, seen, raw)

    duration = triage.get("duration") or hist_data["duration"]
    if isinstance(duration, str):
        duration = duration.strip() or None

    conditions = list(hist_data["conditions"])
    for raw in triage.get("conditions") or []:
        cond = str(raw).strip()
        if cond and cond not in conditions:
            conditions.append(cond)

    return {
        "symptoms": symptoms,
        "duration": duration,
        "conditions": conditions,
    }


async def _history_for_conversation(db: AsyncSession, conversation_id: UUID) -> list[dict]:
    msg_rows = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    return [
        {
            "role": m.role.value if hasattr(m.role, "value") else str(m.role),
            "content": m.content,
        }
        for m in msg_rows.scalars().all()
    ]


async def persist_triage_for_patient(
    db: AsyncSession,
    patient_id: UUID,
    conversation_id: UUID | None = None,
) -> SymptomAssessment | None:
    """Save SymptomAssessment from latest (or given) chat + flow state before doctor summary."""
    conv_id = conversation_id
    if not conv_id:
        row = await db.execute(
            select(Conversation)
            .where(Conversation.patient_id == patient_id)
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        conv = row.scalar_one_or_none()
        if not conv:
            return None
        conv_id = conv.id

    history = await _history_for_conversation(db, conv_id)
    flow = await get_flow(conv_id)
    session = flow.get("session") or {}
    data = await collect_triage_data(session, history)

    if not data["symptoms"]:
        return None

    return await save_assessment(
        db,
        patient_id,
        data["symptoms"],
        duration=data["duration"],
        conditions=data["conditions"] or None,
        conversation_id=conv_id,
    )


async def persist_triage_from_chat(
    db: AsyncSession,
    patient_id: UUID,
    conversation_id: UUID,
    history: list[dict] | None,
) -> None:
    flow = await get_flow(conversation_id)
    session = flow.get("session") or {}
    data = await collect_triage_data(session, history)
    if not data["symptoms"]:
        return
    await save_assessment(
        db,
        patient_id,
        data["symptoms"],
        duration=data["duration"],
        conditions=data["conditions"] or None,
        conversation_id=conversation_id,
    )
