"""Post-upload report explanation and optional Report Discussion Appointment flow."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Consultation, Doctor, Report, User
from app.models.enums import AppointmentStatus
from app.multi_agent.booking_actions import format_report_reply
from app.services.chat_ui import build_report_followup_ui

REPORT_DISCUSSION_REASON = "Medical Report Review & Consultation"

REPORT_DISCUSSION_QUESTION = (
    "**Would you like to schedule an appointment with a doctor to discuss your report in detail?**"
)

REPORT_DISCUSSION_QUESTION_MARKER = "discuss your report in detail"

REPORT_DISCUSSION_DECLINE = (
    "**No problem.** Your report has been securely saved to your health records for future reference. "
    "If you have any questions or decide to consult a doctor later, you can book an appointment anytime "
    "from your Patient Portal. Take care and stay healthy!"
)

REPORT_FOLLOWUP_YES = "Yes, schedule an appointment"
REPORT_FOLLOWUP_NO = "No, not right now"

REPORT_DOCTOR_ANOTHER_MESSAGE = "Choose another doctor for report review"

CONSULTATION_MODE_MARKER = "meet your doctor for this report review"

REPORT_DOCTOR_CHOICE_MARKER = "schedule your report review with the same doctor"

_REPORT_FLOW_AWAITING = frozenset({
    "report_followup",
    "report_discussion_mode",
    "report_discussion_doctor",
})

_REPORT_BOOKING_AWAITING = frozenset({
    "pick_doctor",
    "pick_slot",
    "confirm_booking",
})

_SLOT_PICK_RE = re.compile(
    r"(today|tomorrow|\d{4}-\d{2}-\d{2}).*:\s*\d{1,2}:\d{2}\s*(am|pm)",
    re.I,
)

_REPORT_YES_PHRASES = frozenset({
    "yes",
    "yeah",
    "sure",
    "ok",
    "okay",
    "yep",
    "yes please",
    "go ahead",
    REPORT_FOLLOWUP_YES.lower(),
})

_REPORT_NO_PHRASES = frozenset({
    "no",
    "nope",
    "not now",
    "no thanks",
    "no thank you",
    REPORT_FOLLOWUP_NO.lower(),
})


def report_doctor_previous_message(doctor_name: str) -> str:
    return f"Book with {doctor_name} again for report review"


def report_doctor_choice_prompt(doctor_name: str) -> str:
    return (
        f"You previously consulted with **{doctor_name}**. "
        "Would you like to schedule your report review with the same doctor, or choose another doctor?"
    )


def is_slot_booking_message(text: str) -> bool:
    """True when the patient picked a doctor/time from the booking calendar."""
    t = text.strip()
    if not t:
        return False
    if _SLOT_PICK_RE.search(t):
        return True
    return bool(
        re.search(r"\b\d{1,2}:\d{2}\s*(am|pm)\b", t, re.I)
        and ("today" in t.lower() or "tomorrow" in t.lower() or "dr." in t.lower() or "dr " in t.lower())
    )


def is_report_booking_in_progress(session: dict) -> bool:
    return (
        session.get("care_goal") == "report_discussion"
        and session.get("awaiting") in _REPORT_BOOKING_AWAITING
    )


def _assistant_content_has_report_offer(content: str) -> bool:
    lowered = (content or "").lower()
    markers = (
        REPORT_DISCUSSION_QUESTION_MARKER,
        "schedule an appointment with a doctor to discuss your report",
        "discuss your report in detail",
        "educational summary",
    )
    return any(marker in lowered for marker in markers) and (
        "report" in lowered or "schedule an appointment" in lowered
    )


def history_has_report_discussion_offer(history: list[dict]) -> bool:
    """True when chat history includes the post-upload report booking prompt."""
    for msg in reversed(history):
        if msg.get("role") not in ("assistant", "Assistant"):
            continue
        if _assistant_content_has_report_offer(msg.get("content") or ""):
            return True
    return False


def _last_user_message(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg.get("role") in ("user", "User"):
            content = (msg.get("content") or "").strip()
            if content:
                return content
    return ""


def _recent_assistant_messages(history: list[dict], limit: int = 8) -> list[str]:
    messages: list[str] = []
    for msg in reversed(history[-limit:]):
        if msg.get("role") not in ("assistant", "Assistant"):
            continue
        content = (msg.get("content") or "").strip()
        if content:
            messages.append(content)
    return messages


def history_shows_consultation_mode_prompt(history: list[dict]) -> bool:
    return any(
        CONSULTATION_MODE_MARKER in content.lower()
        for content in _recent_assistant_messages(history)
    )


def history_shows_report_doctor_choice_prompt(history: list[dict]) -> bool:
    return any(
        REPORT_DOCTOR_CHOICE_MARKER in content.lower()
        or (
            "same doctor" in content.lower()
            and "report review" in content.lower()
        )
        for content in _recent_assistant_messages(history)
    )


def is_report_consultation_mode_turn(history: list[dict], user_text: str) -> bool:
    if not is_consultation_mode_choice(user_text):
        return False
    return history_shows_consultation_mode_prompt(history)


def is_report_doctor_choice_turn(history: list[dict], user_text: str) -> bool:
    if not is_report_doctor_choice_action(user_text):
        return False
    return history_shows_report_doctor_choice_prompt(history)


def _infer_report_doctor_preference_from_history(history: list[dict]) -> str | None:
    for msg in reversed(history):
        if msg.get("role") not in ("user", "User"):
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if is_report_doctor_previous_choice(content):
            return "previous"
        if is_report_doctor_another_choice(content):
            return "another"
        if is_consultation_mode_choice(content) or is_report_followup_action(content):
            break
    return None


def infer_report_discussion_awaiting(history: list[dict], user_text: str = "") -> str | None:
    """Best-effort report-flow stage from chat when Redis session was lost."""
    last_user = (user_text or _last_user_message(history)).strip()

    if is_report_consultation_mode_turn(history, last_user):
        return "report_discussion_mode"
    if history_shows_consultation_mode_prompt(history) and not last_user:
        return "report_discussion_mode"
    if is_report_doctor_choice_turn(history, last_user):
        return "report_discussion_doctor"
    if history_shows_report_doctor_choice_prompt(history) and last_user and is_report_followup_yes(last_user):
        return "report_discussion_doctor"
    if history_has_report_discussion_offer(history):
        if last_user and is_report_followup_action(last_user):
            return "report_followup"
        if last_user and (
            is_report_doctor_choice_action(last_user)
            or is_consultation_mode_choice(last_user)
        ):
            return None
        if history_has_pending_report_followup(history):
            return "report_followup"
        if last_user and is_report_followup_yes(last_user):
            return "report_discussion_doctor"
    return None


def history_has_pending_report_followup(history: list[dict]) -> bool:
    """True when the patient has not yet answered the report follow-up prompt."""
    if not history_has_report_discussion_offer(history):
        return False
    last_user = _last_user_message(history)
    if last_user and (
        is_slot_booking_message(last_user)
        or is_report_followup_action(last_user)
        or is_report_doctor_choice_action(last_user)
        or is_consultation_mode_choice(last_user)
    ):
        return False
    return True


async def _attach_latest_report_context(
    db: AsyncSession,
    session: dict,
    patient_id: UUID,
) -> None:
    if session.get("last_report_id") and session.get("last_report_analysis"):
        return
    result = await db.execute(
        select(Report)
        .where(Report.patient_id == patient_id)
        .order_by(Report.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        return
    session["last_report_id"] = str(report.id)
    analysis = report.analysis_json or {}
    if analysis.get("summary") or analysis.get("abnormal") is not None:
        session["last_report_analysis"] = analysis


async def rehydrate_report_discussion_session(
    db: AsyncSession,
    session: dict,
    history: list[dict],
    patient_id: UUID | None,
    *,
    user_text: str | None = None,
) -> bool:
    """Restore report-discussion flow when Redis session was lost but chat history shows the offer."""
    last_user = (user_text or _last_user_message(history)).strip()

    if is_report_booking_in_progress(session):
        if patient_id:
            await _attach_latest_report_context(db, session, patient_id)
        return True

    if is_slot_booking_message(last_user):
        session.setdefault("care_goal", "report_discussion")
        session.setdefault("active_specialist", "scheduling_agent")
        if session.get("last_doctor_search") or session.get("selected_doctor"):
            session["awaiting"] = "pick_doctor"
        if patient_id:
            await _attach_latest_report_context(db, session, patient_id)
        return True

    in_report_flow = session.get("awaiting") in _REPORT_FLOW_AWAITING
    has_offer = history_has_report_discussion_offer(history)
    pending_followup = history_has_pending_report_followup(history)
    user_is_followup = bool(last_user and is_report_followup_action(last_user))
    inferred_stage = infer_report_discussion_awaiting(history, last_user)

    if in_report_flow:
        if patient_id:
            await _attach_latest_report_context(db, session, patient_id)
        return True

    if inferred_stage and session.get("awaiting") not in _REPORT_BOOKING_AWAITING:
        session["awaiting"] = inferred_stage
        session["care_goal"] = "report_discussion"
        session["active_specialist"] = "scheduling_agent"
        session.pop("recommended_specialty", None)
        session.pop("triage_assessed", None)
        session.pop("detected_symptoms", None)
        session.pop("triage_collected", None)
        if inferred_stage == "report_discussion_doctor" and patient_id:
            previous = await get_previous_consultant(db, patient_id)
            if previous:
                session["previous_consultant"] = previous
        if patient_id:
            await _attach_latest_report_context(db, session, patient_id)
        pref = _infer_report_doctor_preference_from_history(history)
        if pref:
            session["report_doctor_preference"] = pref
        return True

    if not has_offer:
        return False

    if not pending_followup and not user_is_followup:
        return False

    if is_slot_booking_message(last_user):
        return False

    session["awaiting"] = "report_followup"
    session["care_goal"] = "report_discussion"
    session["active_specialist"] = "report_agent"
    session.pop("recommended_specialty", None)
    session.pop("triage_assessed", None)
    session.pop("detected_symptoms", None)
    session.pop("triage_collected", None)
    if patient_id:
        await _attach_latest_report_context(db, session, patient_id)
    return True


def is_in_report_discussion_flow(session: dict, history: list[dict] | None = None) -> bool:
    if is_report_booking_in_progress(session):
        return True
    if session.get("awaiting") in _REPORT_FLOW_AWAITING:
        return True
    if session.get("care_goal") == "report_discussion":
        return True
    if not history:
        return False
    if infer_report_discussion_awaiting(history):
        return True
    if history_has_pending_report_followup(history):
        return True
    last_user = _last_user_message(history)
    if last_user and is_report_followup_action(last_user) and history_has_report_discussion_offer(history):
        return True
    if last_user and is_report_consultation_mode_turn(history, last_user):
        return True
    if last_user and is_report_doctor_choice_turn(history, last_user):
        return True
    return False


async def get_previous_consultant(db: AsyncSession, patient_id: UUID) -> dict[str, str] | None:
    """Most recent doctor the patient completed a visit with."""
    result = await db.execute(
        select(Appointment, User.name, Doctor.id)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status == AppointmentStatus.completed,
        )
        .order_by(Appointment.completed_at.desc().nullslast(), Appointment.slot_date.desc())
        .limit(1)
    )
    row = result.first()
    if row:
        appt, doctor_name, doctor_id = row
        return {
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name or "your doctor",
            "last_visit_date": str(appt.slot_date),
            "appointment_id": str(appt.id),
        }

    consult_row = await db.execute(
        select(Consultation, User.name, Doctor.id)
        .join(Appointment, Appointment.id == Consultation.appointment_id)
        .join(Doctor, Doctor.id == Consultation.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            Consultation.patient_id == patient_id,
            Consultation.status == "completed",
        )
        .order_by(Consultation.completed_at.desc().nullslast())
        .limit(1)
    )
    consult = consult_row.first()
    if consult:
        consultation, doctor_name, doctor_id = consult
        return {
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name or "your doctor",
            "last_visit_date": "",
            "appointment_id": str(consultation.appointment_id),
        }
    return None


def is_report_followup_action(text: str) -> bool:
    return is_report_followup_yes(text) or is_report_followup_no(text)


def is_report_followup_yes(text: str) -> bool:
    t = text.strip().lower()
    if t in _REPORT_YES_PHRASES:
        return True
    return "yes" in t and ("schedule" in t or "appointment" in t or "book" in t)


def is_report_followup_no(text: str) -> bool:
    t = text.strip().lower()
    if t in _REPORT_NO_PHRASES:
        return True
    return t.startswith("no") and "schedule" not in t and "appointment" not in t


def is_report_doctor_previous_choice(text: str) -> bool:
    t = text.strip().lower()
    return (
        "book with" in t
        and ("again" in t or "report review" in t or "same doctor" in t or "previous doctor" in t)
    ) or t in {"book with my previous doctor", "same doctor", "previous doctor"}


def is_report_doctor_another_choice(text: str) -> bool:
    t = text.strip().lower()
    return (
        "another doctor" in t
        or "choose another" in t
        or "different doctor" in t
        or t == REPORT_DOCTOR_ANOTHER_MESSAGE.lower()
    )


def is_report_doctor_choice_action(text: str) -> bool:
    return is_report_doctor_previous_choice(text) or is_report_doctor_another_choice(text)


def is_consultation_mode_choice(text: str) -> bool:
    return parse_consultation_mode(text) is not None


def parse_consultation_mode(text: str) -> str | None:
    t = text.strip().lower()
    if any(p in t for p in ("video consultation", "video consult", "video call", "video")):
        return "video"
    if any(p in t for p in ("in-person", "in person", "clinic visit", "office visit")):
        return "in_person"
    return None


def compose_report_discussion_reply(analysis: dict) -> str:
    explanation = format_report_reply(analysis, "summarize this report in simple terms")
    return f"{explanation}\n\n{REPORT_DISCUSSION_QUESTION}"


def report_followup_session_patch(report_id: str | UUID, analysis: dict) -> dict[str, Any]:
    return {
        "awaiting": "report_followup",
        "care_goal": "report_discussion",
        "last_report_id": str(report_id),
        "last_report_analysis": analysis,
        "active_specialist": "report_agent",
    }


def build_report_discussion_followup_payload(
    report_id: str | UUID,
    analysis: dict,
) -> tuple[str, dict, dict[str, Any]]:
    reply = compose_report_discussion_reply(analysis)
    ui = build_report_followup_ui()
    session_patch = report_followup_session_patch(report_id, analysis)
    return reply, ui, session_patch


def consultation_mode_prompt() -> str:
    return (
        "How would you like to meet your doctor for this report review?\n\n"
        "Choose **In-Person Consultation** or **Video Consultation** below."
    )


def clear_report_discussion_session(session: dict, *, keep_analysis: bool = True) -> None:
    if session.get("awaiting") in _REPORT_FLOW_AWAITING:
        session.pop("awaiting", None)
    if session.get("care_goal") in ("report_discussion", "guest_report_done", "guest_report"):
        session.pop("care_goal", None)
    session.pop("report_qa_open", None)
    session.pop("appointment_reason", None)
    session.pop("linked_report_id", None)
    session.pop("pending_consultation_mode", None)
    session.pop("previous_consultant", None)
    session.pop("report_doctor_preference", None)
    if not keep_analysis:
        session.pop("last_report_analysis", None)
        session.pop("last_report_id", None)
