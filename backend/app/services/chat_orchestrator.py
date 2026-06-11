"""Shared chat orchestration for Patient Portal and Landing Page MediAI Assistant."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.emergency_detection import (
    build_emergency_reply,
    detect_emergency,
    detect_mental_health_crisis,
)
from app.models import Conversation, Patient
from app.multi_agent.supervisor import multi_agent_supervisor
from app.services.flow_state import get_flow, set_flow
from app.services.guest_resume_service import get_resume_context
from app.services.guest_aura_flow import attach_nav_menu, process_aura_guest_turn
from app.services.guest_report_service import clear_report_followup, should_leave_report_followup
from app.multi_agent.booking_actions import start_find_doctor_flow
from app.multi_agent.offline_fallback import kickoff_symptom_triage_turn
from app.services.symptom_extraction import looks_like_health_complaint
from app.services.guest_auth_service import in_guest_auth, process_guest_auth_turn
from app.services.guest_flow import guest_flow_conversation_id
from app.services.guest_session_store import load_guest_session, save_guest_session
from app.services.patient_context import load_patient_context
from app.services.symptom_extraction import resolve_detected_symptoms

START_SYMPTOM_TRIAGE_TOKEN = "[start_symptom_triage]"
START_FIND_DOCTOR_TOKEN = "[start_find_doctor]"
START_EXPLAIN_REPORT_TOKEN = "[start_explain_report]"

_QUICK_ACTION_MESSAGES = {
    START_SYMPTOM_TRIAGE_TOKEN: "I'm not feeling well and would like help assessing my symptoms.",
    START_FIND_DOCTOR_TOKEN: "I'd like to find a specialist doctor and book an appointment.",
}

GUEST_PATIENT_CTX: dict[str, Any] = {
    "patient_id": None,
    "name": None,
    "age": None,
    "gender": None,
    "blood_group": None,
    "conditions": [],
    "medications": [],
    "allergies": [],
    "active_appointments": [],
    "recent_visits": [],
    "memory_facts": [],
}


@dataclass
class GuestConversationAdapter:
    """Minimal conversation object for multi-agent supervisor (guest mode)."""

    id: UUID
    active_agent: str = "conversation"
    emergency_flag: bool = False


def _compact_history(messages: list[dict]) -> list[dict]:
    return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages[-40:]]


def _upload_kind_from_session(session: dict) -> str | None:
    awaiting = session.get("awaiting")
    if awaiting == "symptom_image":
        return "symptom"
    if awaiting == "report_upload":
        return "report"
    return None


def _awaiting_input_from_session(session: dict) -> str | None:
    awaiting = session.get("awaiting")
    if awaiting == "guest_email":
        return "email"
    if awaiting == "guest_otp":
        return "otp"
    if awaiting in ("report_upload", "symptom_image"):
        return "upload"
    return None


def _reset_triage_on_start(session: dict, text: str) -> None:
    """Clear stale triage state when guest explicitly starts symptom check."""
    if text.strip() == START_SYMPTOM_TRIAGE_TOKEN or text.strip().lower() in {
        "check my symptoms",
        "i'd like to assess my symptoms",
        "i'd like to check my symptoms",
        "analyze my symptoms",
    }:
        session["care_goal"] = "symptom_assessment"
        session["triage_collected"] = {}
        session.pop("awaiting", None)
        session.pop("triage_assessed", None)
        session.pop("booking_declined", None)
        session.pop("assessment_shown", None)
        session.pop("severity_asked", None)


def _prepare_find_doctor_start(session: dict, text: str) -> None:
    if text.strip() == START_FIND_DOCTOR_TOKEN:
        session["care_goal"] = "find_doctor"
        session["active_specialist"] = "scheduling_agent"
        session.pop("awaiting", None)


async def process_patient_message(
    db: AsyncSession,
    conversation: Conversation,
    patient: Patient,
    message: str,
    history: list[dict],
    report_id: str | None = None,
) -> tuple[str, str, bool, dict | None, list[str]]:
    """Authenticated patient chat — used by Patient Portal."""
    from app.services.appointment_card_service import complete_guest_resume_booking

    flow = await get_flow(conversation.id)
    session = flow.get("session") or {}
    resuming = bool(session.get("resume_after_auth"))

    if resuming and session.get("pending_slot"):
        completed = await complete_guest_resume_booking(
            db, patient, conversation.id, session
        )
        if completed:
            await set_flow(conversation.id, {"session": session})
            return (
                completed["reply"],
                completed["agent"],
                False,
                completed.get("ui"),
                list(session.get("detected_symptoms") or []),
            )

    reply, agent, emergency, ui = await multi_agent_supervisor.process(
        db,
        conversation,
        patient,
        message,
        history=history,
        report_id=report_id,
    )

    flow = await get_flow(conversation.id)
    session = flow.get("session") or {}
    if resuming:
        session.pop("resume_after_auth", None)
        session.pop("pending_auth_action", None)
        session.pop("guest_resume_action", None)
        await set_flow(conversation.id, {"session": session})

    detected = await resolve_detected_symptoms(
        session,
        history + [{"role": "user", "content": message}],
    )
    return reply, agent, emergency, ui, detected


async def load_patient_resume_context(conversation_id) -> dict[str, Any]:
    """Resume hints for a migrated guest conversation."""
    flow = await get_flow(conversation_id)
    session = flow.get("session") or {}
    return get_resume_context(session)


async def process_guest_message(
    db: AsyncSession,
    session_id: str,
    text: str,
) -> dict[str, Any]:
    """Landing Page MediAI Assistant — same multi-agent brain, email gate for patient actions."""
    data = await load_guest_session(session_id)
    if not data:
        raise ValueError("Guest session expired. Please start a new consultation.")

    history = list(data.get("messages") or [])
    original_text = text
    text = _QUICK_ACTION_MESSAGES.get(text.strip(), text)

    conv_id = guest_flow_conversation_id(session_id)
    flow = await get_flow(conv_id)
    session = merge_guest_session(data.get("session") or {}, flow.get("session") or {})

    auth_result = await process_guest_auth_turn(db, session_id, original_text, session, history, data)
    if auth_result:
        await set_flow(conv_id, {"session": session})
        return auth_result

    _reset_triage_on_start(session, original_text)
    _prepare_find_doctor_start(session, original_text)

    if original_text.strip() == START_SYMPTOM_TRIAGE_TOKEN:
        kickoff = kickoff_symptom_triage_turn(session)
        session.update(kickoff.get("session_patch") or {})
        history.append({"role": "user", "content": original_text})
        history.append({
            "role": "assistant",
            "content": kickoff["reply"],
            "agent": "symptom_assessment",
            "ui": kickoff.get("ui"),
        })
        data["messages"] = history[-40:]
        data["session"] = session
        await set_flow(conv_id, {"session": session})
        await save_guest_session(session_id, data)
        return attach_nav_menu({
            "reply": kickoff["reply"],
            "emergency": False,
            "agent": "symptom_assessment",
            "ui": kickoff.get("ui"),
            "requires_signup": False,
            "awaiting_input": _awaiting_input_from_session(session),
            "upload_kind": _upload_kind_from_session(session),
        }, session)

    if original_text.strip() == START_FIND_DOCTOR_TOKEN:
        find_doctor = await start_find_doctor_flow(db, session, history)
        session.update(find_doctor.get("session_patch") or {})
        history.append({"role": "user", "content": original_text})
        history.append({
            "role": "assistant",
            "content": find_doctor["reply"],
            "agent": "scheduling_agent",
            "ui": find_doctor.get("ui"),
        })
        data["messages"] = history[-40:]
        data["session"] = session
        await set_flow(conv_id, {"session": session})
        await save_guest_session(session_id, data)
        return attach_nav_menu({
            "reply": find_doctor["reply"],
            "emergency": False,
            "agent": "scheduling_agent",
            "ui": find_doctor.get("ui"),
            "requires_signup": False,
            "awaiting_input": _awaiting_input_from_session(session),
            "upload_kind": _upload_kind_from_session(session),
        }, session)

    if should_leave_report_followup(original_text, session):
        clear_report_followup(session, keep_analysis=True)
    elif original_text.strip() in {
        START_SYMPTOM_TRIAGE_TOKEN,
        START_FIND_DOCTOR_TOKEN,
        START_EXPLAIN_REPORT_TOKEN,
    } or looks_like_health_complaint(original_text):
        clear_report_followup(session, keep_analysis=False)

    if detect_mental_health_crisis(text):
        reply = build_emergency_reply(mental_health_crisis=True)
        history.append({"role": "user", "content": original_text})
        history.append({"role": "assistant", "content": reply, "agent": "emergency", "emergency": True})
        data["messages"] = history[-40:]
        data["session"] = session
        await save_guest_session(session_id, data)
        return {"reply": reply, "emergency": True, "agent": "emergency", "ui": None, "requires_signup": False}

    if detect_emergency(text):
        reply = build_emergency_reply()
        history.append({"role": "user", "content": original_text})
        history.append({"role": "assistant", "content": reply, "agent": "emergency", "emergency": True})
        data["messages"] = history[-40:]
        data["session"] = session
        await save_guest_session(session_id, data)
        return {"reply": reply, "emergency": True, "agent": "emergency", "ui": None, "requires_signup": False}

    aura = process_aura_guest_turn(original_text, text, session)
    if aura:
        if aura.get("session_patch"):
            session.update(aura["session_patch"])
        if not aura.get("delegate"):
            history.append({"role": "user", "content": original_text})
            history.append({
                "role": "assistant",
                "content": aura["reply"],
                "agent": aura.get("agent", "conversation"),
                "ui": aura.get("ui"),
            })
            data["messages"] = history[-40:]
            data["session"] = session
            await set_flow(conv_id, {"session": session})
            await save_guest_session(session_id, data)
            result = attach_nav_menu({
                "reply": aura["reply"],
                "emergency": False,
                "agent": aura.get("agent", "conversation"),
                "ui": aura.get("ui"),
                "requires_signup": False,
                "awaiting_input": aura.get("awaiting_input") or _awaiting_input_from_session(session),
                "upload_kind": _upload_kind_from_session(session),
            }, session)
            return result
        if aura.get("map_to_message"):
            text = aura["map_to_message"]

    await set_flow(conv_id, {"session": session})

    adapter = GuestConversationAdapter(id=conv_id)
    compact_history = _compact_history(history)

    reply, agent, emergency, ui = await multi_agent_supervisor.process(
        db,
        adapter,
        patient=None,
        user_message=text,
        history=compact_history,
        report_id=None,
        is_guest=True,
        guest_session_id=session_id,
        patient_ctx=GUEST_PATIENT_CTX,
    )

    flow = await get_flow(conv_id)
    session = dict(flow.get("session") or session)
    await set_flow(conv_id, {"session": session})

    history.append({"role": "user", "content": original_text})
    history.append({"role": "assistant", "content": reply, "agent": agent, "ui": ui, "emergency": emergency})
    data["messages"] = history[-40:]
    data["session"] = session
    await save_guest_session(session_id, data)

    return attach_nav_menu({
        "reply": reply,
        "emergency": emergency,
        "agent": agent,
        "ui": ui,
        "requires_signup": False,
        "awaiting_input": _awaiting_input_from_session(session),
        "upload_kind": _upload_kind_from_session(session),
    }, session)


def merge_guest_session(redis_session: dict, flow_session: dict) -> dict:
    """Merge Redis guest session with supervisor flow — flow wins on conflicts."""
    return {**dict(redis_session or {}), **dict(flow_session or {})}


async def load_guest_chat_history(session_id: str) -> dict[str, Any]:
    """Return persisted guest messages for UI hydration."""
    data = await load_guest_session(session_id)
    if not data:
        raise ValueError("Guest session expired. Please start a new consultation.")
    messages = data.get("messages") or []
    session = data.get("session") or {}
    return {
        "messages": messages,
        "awaiting_input": _awaiting_input_from_session(session),
    }
