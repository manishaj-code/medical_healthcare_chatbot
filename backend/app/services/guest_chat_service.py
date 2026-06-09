import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.emergency_detection import (
    build_emergency_reply,
    detect_emergency,
    detect_mental_health_crisis,
)
from app.models import Conversation, Message, Patient
from app.models.enums import MessageRole
from app.multi_agent.offline_fallback import offline_education_reply, plan_triage_turn
from app.services.chat_ui import build_symptom_picker_ui, build_yes_no_ui
from app.services.symptom_service import assess_symptoms
from app.services.cache import get_redis

GUEST_PREFIX = "guest:session:"
GUEST_TTL_SECONDS = 60 * 60 * 24

START_SYMPTOM_TRIAGE_TOKEN = "[start_symptom_triage]"

_START_TRIAGE_RE = re.compile(
    r"^(i['']?d like to )?(analyze|assess|check) (my )?symptoms\.?$",
    re.I,
)

GATED_PATTERNS = [
    re.compile(r"\bbook\b", re.I),
    re.compile(r"\bappointment\b", re.I),
    re.compile(r"\breschedule\b", re.I),
    re.compile(r"\bcancel\b.*\bappointment", re.I),
    re.compile(r"\bupload\b", re.I),
    re.compile(r"\breport\b", re.I),
    re.compile(r"\blab\b", re.I),
    re.compile(r"\brefill\b", re.I),
    re.compile(r"\bprescription\b", re.I),
    re.compile(r"show doctors", re.I),
    re.compile(r"available (?:doctors|slots)", re.I),
]


def _guest_key(session_id: str) -> str:
    return GUEST_PREFIX + session_id


def _requires_signup(text: str, session: dict) -> str | None:
    tl = text.strip().lower()
    if tl in {"yes", "yeah", "sure", "ok", "okay", "yes please"}:
        if session.get("awaiting") == "offer_booking":
            return "booking"
    for pattern in GATED_PATTERNS:
        if pattern.search(text):
            return "advanced"
    return None


def _is_symptom_triage_start(text: str) -> bool:
    stripped = text.strip()
    if stripped == START_SYMPTOM_TRIAGE_TOKEN:
        return True
    return bool(_START_TRIAGE_RE.match(stripped))


def _begin_symptom_triage_reply() -> tuple[str, dict]:
    reply = (
        "Hello! How are you feeling today? "
        "Tell me what's bothering you — for example headache, fever, or dizziness — or tap a symptom below."
    )
    return reply, build_symptom_picker_ui()


def _signup_reply(reason: str) -> str:
    if reason == "booking":
        return (
            "I'd be happy to help you book an appointment. "
            "Please verify your email to create a free account and continue with booking, "
            "your consultation history, and dashboard access."
        )
    return (
        "This feature requires a free MediAI account. "
        "Verify your email to unlock appointment booking, lab uploads, and your personal health dashboard."
    )


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


async def process_guest_message(session_id: str, text: str) -> dict[str, Any]:
    data = await load_guest_session(session_id)
    if not data:
        raise ValueError("Guest session expired. Please start a new consultation.")

    session = data.get("session") or {}
    history = data.get("messages") or []

    if detect_mental_health_crisis(text):
        reply = build_emergency_reply(mental_health_crisis=True)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply, "agent": "emergency", "emergency": True})
        data["messages"] = history[-40:]
        await save_guest_session(session_id, data)
        return {
            "reply": reply,
            "emergency": True,
            "agent": "emergency",
            "ui": None,
            "requires_signup": False,
        }

    if detect_emergency(text):
        reply = build_emergency_reply()
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply, "agent": "emergency", "emergency": True})
        data["messages"] = history[-40:]
        await save_guest_session(session_id, data)
        return {
            "reply": reply,
            "emergency": True,
            "agent": "emergency",
            "ui": None,
            "requires_signup": False,
        }

    if _is_symptom_triage_start(text) and not session.get("care_goal"):
        reply, ui = _begin_symptom_triage_reply()
        session["care_goal"] = "symptom_assessment"
        session["triage_collected"] = {}
        history.append({"role": "assistant", "content": reply, "agent": "triage_agent", "ui": ui})
        data["messages"] = history[-40:]
        data["session"] = session
        await save_guest_session(session_id, data)
        return {
            "reply": reply,
            "emergency": False,
            "agent": "triage_agent",
            "ui": ui,
            "requires_signup": False,
        }

    gate = _requires_signup(text, session)
    if gate:
        reply = _signup_reply(gate)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply, "agent": "guest_gate"})
        data["messages"] = history[-40:]
        data["session"] = session
        await save_guest_session(session_id, data)
        return {
            "reply": reply,
            "emergency": False,
            "agent": "guest_gate",
            "ui": None,
            "requires_signup": True,
            "signup_reason": gate,
        }

    session["_patient_first_name"] = "there"
    decision = plan_triage_turn(text, session)

    emergency = False
    if decision.get("tool") == "assess_symptoms":
        args = decision["tool_args"]
        result = assess_symptoms(args["symptoms"], args.get("duration"), None)
        specialty = result["recommended_specialty"]
        reply = (
            f"Based on your symptoms, I recommend consulting a **{specialty}**.\n\n"
            f"{result['recommendation_text']}\n\n"
            "Would you like me to show available doctors and help you book?"
        )
        session["awaiting"] = "offer_booking"
        session["recommended_specialty"] = specialty
        ui = build_yes_no_ui(
            yes_label="Yes, show doctors",
            yes_message="Yes",
            no_label="Not now",
            no_message="No",
        )
        agent = "triage_agent"
        emergency = str(result.get("risk_level", "")).lower() == "emergency"
        if decision.get("session_patch"):
            session.update(decision["session_patch"])
    elif decision.get("reply"):
        reply = decision["reply"]
        ui = decision.get("ui")
        agent = "triage_agent"
        if decision.get("session_patch"):
            session.update(decision["session_patch"])
    else:
        edu = offline_education_reply(text)
        if edu:
            reply = edu
        else:
            reply = (
                "I'm here to help with symptom assessment and health questions. "
                "Tell me how you're feeling, or tap a symptom to get started."
            )
        ui = None
        agent = "education_agent"

    if decision.get("session_patch") and decision.get("tool") != "assess_symptoms":
        session.update(decision["session_patch"])

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply, "agent": agent, "ui": ui})
    data["messages"] = history[-40:]
    data["session"] = session
    await save_guest_session(session_id, data)

    return {
        "reply": reply,
        "emergency": emergency,
        "agent": agent,
        "ui": ui,
        "requires_signup": False,
    }


async def migrate_guest_session(
    db: AsyncSession, session_id: str, patient: Patient
) -> Conversation | None:
    data = await load_guest_session(session_id)
    if not data or not data.get("messages"):
        return None

    conv = Conversation(patient_id=patient.id, title="Health Chat", language="en")
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

    redis = await get_redis()
    await redis.delete(_guest_key(session_id))
    return conv
