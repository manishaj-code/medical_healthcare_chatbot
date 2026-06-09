"""Extract triage data from chat history for doctor summaries."""
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import DURATION_PATTERN, _parse_condition, _pending_duration_number
from app.services.symptom_service import save_assessment

SYMPTOM_KEYWORDS = ("fever", "cough", "pain", "headache", "nausea", "fatigue", "cold")


def extract_triage_from_history(history: list[dict] | None) -> dict:
    symptoms: list[str] = []
    duration: str | None = None
    conditions: list[str] = []
    breathing_issue = False

    if not history:
        return {"symptoms": symptoms, "duration": duration, "conditions": conditions}

    for h in history:
        if str(h.get("role")) != "user":
            continue
        content = h.get("content", "")
        text = content.lower()

        for s in SYMPTOM_KEYWORDS:
            if s in text and s not in symptoms:
                symptoms.append(s)

        if DURATION_PATTERN.search(text) or re.search(r"\d+\s*days?", text):
            duration = content.strip()
        elif text in {"day", "days", "hour", "hours", "week", "weeks", "month", "months"}:
            num = _pending_duration_number(history[: history.index(h) + 1])
            if num:
                duration = f"{num} {content.strip()}"

        cond = _parse_condition(text)
        if cond and cond not in conditions:
            conditions.append(cond)

        if text in {"yes", "yeah", "yep"}:
            idx = history.index(h)
            for prev in reversed(history[:idx]):
                if str(prev.get("role")) == "assistant" and "do you have any breathing" in prev.get("content", "").lower():
                    breathing_issue = True
                    break

    if breathing_issue and "breathing difficulty" not in symptoms:
        symptoms.append("breathing difficulty")

    return {"symptoms": symptoms, "duration": duration, "conditions": conditions}


async def persist_triage_from_chat(
    db: AsyncSession,
    patient_id: UUID,
    conversation_id: UUID,
    history: list[dict] | None,
) -> None:
    data = extract_triage_from_history(history)
    if not data["symptoms"] and not data["conditions"]:
        return
    await save_assessment(
        db,
        patient_id,
        data["symptoms"] or ["general symptoms"],
        duration=data["duration"],
        conditions=data["conditions"] or None,
        conversation_id=conversation_id,
    )
