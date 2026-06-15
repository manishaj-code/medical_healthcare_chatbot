"""Guest → Patient Portal context migration and post-auth resume."""
from __future__ import annotations

from typing import Any

# Operational keys from the multi-agent flow — must survive OTP migration.
FLOW_STATE_KEYS = (
    "pending_slot",
    "awaiting",
    "active_specialist",
    "care_goal",
    "selected_doctor",
    "last_doctor_search",
    "recommended_specialty",
    "manage_appointment_id",
    "refill_medication",
    "triage_collected",
    "detected_symptoms",
    "triage_assessed",
    "assessment_shown",
    "booking_declined",
    "last_appointment_id",
    "pending_auth_action",
    "resume_after_auth",
    "guest_resume_action",
    "pending_urgent_consult",
    "pending_urgent_message",
    "urgent_consult_request_id",
    "skip_triage",
)

ACTION_TITLES = {
    "book": "Appointment booking",
    "cancel": "Appointment cancellation",
    "reschedule": "Appointment rescheduling",
    "refill": "Prescription refill",
    "urgent_consult": "Urgent video consultation",
}


def merge_guest_flow_sessions(guest_data_session: dict, flow_session: dict) -> dict:
    """Merge Redis guest payload session with supervisor flow session."""
    merged = dict(flow_session or {})
    for key, value in (guest_data_session or {}).items():
        if value is not None:
            merged[key] = value
    for key in FLOW_STATE_KEYS:
        if flow_session.get(key) is not None and guest_data_session.get(key) is None:
            merged[key] = flow_session[key]
    return merged


def prepare_resume_session(session: dict, action: str) -> dict:
    """Normalize session so Patient Portal can continue the pending guest action."""
    session = dict(session)
    session["resume_after_auth"] = True
    session["guest_resume_action"] = action
    session.pop("guest_email", None)

    care_goals = {
        "book": "appointment",
        "cancel": "manage_appointment",
        "reschedule": "manage_appointment",
        "refill": "refill",
        "urgent_consult": "urgent_consult",
    }
    session.setdefault("care_goal", care_goals.get(action, "appointment"))

    if action == "book" and session.get("pending_slot"):
        session["awaiting"] = "confirm_booking"
        session["active_specialist"] = "scheduling_agent"
    elif action == "cancel" and session.get("manage_appointment_id"):
        session["awaiting"] = "confirm_cancel"
        session["active_specialist"] = "scheduling_agent"
    elif action == "reschedule" and session.get("pending_slot"):
        session["awaiting"] = "confirm_reschedule"
        session["active_specialist"] = "scheduling_agent"
    elif action == "refill":
        session.setdefault("awaiting", "confirm_refill")
        session["active_specialist"] = "refill_agent"
        session["care_goal"] = "refill"
    elif action == "urgent_consult":
        session["awaiting"] = "urgent_consult"
        session["active_specialist"] = "scheduling_agent"
        session["care_goal"] = "urgent_consult"
        session["skip_triage"] = True

    return session


def build_resume_prompt(session: dict) -> str | None:
    """User message that continues the interrupted guest flow in Patient Portal."""
    action = session.get("pending_auth_action") or session.get("guest_resume_action")
    pending = session.get("pending_slot") or {}

    if action == "book" and pending:
        doctor = pending.get("doctor_name", "the doctor")
        when = pending.get("label", "the selected time")
        return f"Yes, please confirm and book my appointment with {doctor} on {when}."
    if action == "cancel":
        return "Yes, please cancel my appointment."
    if action == "reschedule" and pending:
        when = pending.get("label", "the new time")
        return f"Yes, please reschedule my appointment to {when}."
    if action == "refill":
        med = session.get("refill_medication")
        if med:
            return f"Yes, please submit my refill request for {med}."
        return "Yes, please submit my prescription refill request."
    if action == "urgent_consult":
        return "Please start my urgent video consultation and notify available doctors now."
    if session.get("awaiting") == "confirm_booking" and pending:
        return "Yes, please confirm my appointment."
    if session.get("awaiting") == "confirm_refill":
        return "Yes, please confirm my refill request."
    return None


def migration_title(session: dict, default: str = "Health Consultation") -> str:
    action = session.get("pending_auth_action") or session.get("guest_resume_action")
    return ACTION_TITLES.get(action, default)


def get_resume_context(session: dict) -> dict[str, Any]:
    """Serializable resume hints for the Patient Portal client."""
    prompt = build_resume_prompt(session)
    action = session.get("pending_auth_action") or session.get("guest_resume_action")
    return {
        "resume_prompt": prompt,
        "pending_auth_action": action,
        "resume_after_auth": bool(session.get("resume_after_auth")),
        "awaiting": session.get("awaiting"),
    }
