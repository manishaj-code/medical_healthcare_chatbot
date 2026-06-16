"""Button-driven MediAI Assistant flows for the landing-page guest chat."""
from __future__ import annotations

from typing import Any

from app.multi_agent.booking_actions import format_report_reply
from app.services.chat_ui import build_specialty_picker_ui
from app.services.guest_report_service import clear_report_followup

# Internal tokens — mapped to friendly labels on the frontend.
START_SYMPTOM_TRIAGE = "[start_symptom_triage]"
START_FIND_DOCTOR = "[start_find_doctor]"
START_EXPLAIN_REPORT = "[start_explain_report]"
TYPE_OWN_SYMPTOMS = "[aura_type_symptoms]"
MAIN_MENU = "[aura_main_menu]"
FIND_BY_SYMPTOMS = "[aura_find_by_symptoms]"
FIND_BY_SPECIALTY = "[aura_find_by_specialty]"
FIND_NEAR_ME = "[aura_find_near_me]"
VIEW_ALL_DOCTORS = "[aura_view_all_doctors]"
SPECIALTY_MORE = "[aura_specialty_more]"
UPLOAD_REPORT = "[aura_upload_report]"
UPLOAD_PRESCRIPTION = "[aura_upload_prescription]"
UPLOAD_LAB = "[aura_upload_lab]"
UPLOAD_IMAGE = "[aura_upload_image]"
UPLOAD_SYMPTOM_IMAGE = "[aura_upload_symptom_image]"

_AURA_TOKENS = frozenset({
    START_SYMPTOM_TRIAGE,
    START_FIND_DOCTOR,
    START_EXPLAIN_REPORT,
    TYPE_OWN_SYMPTOMS,
    MAIN_MENU,
    FIND_BY_SYMPTOMS,
    FIND_BY_SPECIALTY,
    FIND_NEAR_ME,
    VIEW_ALL_DOCTORS,
    SPECIALTY_MORE,
    UPLOAD_REPORT,
    UPLOAD_PRESCRIPTION,
    UPLOAD_LAB,
    UPLOAD_IMAGE,
    UPLOAD_SYMPTOM_IMAGE,
})

_TOKEN_LABELS: dict[str, str] = {
    START_SYMPTOM_TRIAGE: "🩺 Check My Symptoms",
    START_FIND_DOCTOR: "👨‍⚕️ Find a Specialist Doctor",
    START_EXPLAIN_REPORT: "📄 Explain My Medical Report",
    TYPE_OWN_SYMPTOMS: "📝 Type My Own Symptoms",
    MAIN_MENU: "🏠 Main Menu",
    FIND_BY_SYMPTOMS: "By Symptoms",
    FIND_BY_SPECIALTY: "By Specialty",
    FIND_NEAR_ME: "Near Me",
    VIEW_ALL_DOCTORS: "View All Doctors",
    SPECIALTY_MORE: "More…",
    UPLOAD_REPORT: "📄 Upload Report",
    UPLOAD_PRESCRIPTION: "💊 Upload Prescription",
    UPLOAD_LAB: "🧪 Upload Lab Report",
    UPLOAD_IMAGE: "🖼️ Upload Image",
    UPLOAD_SYMPTOM_IMAGE: "📷 Upload Symptom Photo",
}


def aura_display_label(text: str) -> str:
    return _TOKEN_LABELS.get(text.strip(), text.strip())


def _reply(
    reply: str,
    *,
    agent: str = "conversation",
    ui: dict | None = None,
    session_patch: dict | None = None,
    awaiting_input: str | None = None,
    delegate: bool = False,
    map_to_message: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "reply": reply,
        "emergency": False,
        "agent": agent,
        "ui": ui,
        "requires_signup": False,
        "awaiting_input": awaiting_input,
        "delegate": delegate,
    }
    if session_patch:
        result["session_patch"] = session_patch
    if map_to_message:
        result["map_to_message"] = map_to_message
    return result


def process_aura_guest_turn(
    original_text: str,
    text: str,
    session: dict,
) -> dict[str, Any] | None:
    """
    Handle structured MediAI button flows before the multi-agent supervisor.
    Returns a response dict, or None to continue with normal processing.
    """
    raw = original_text.strip()
    tl = text.strip().lower()

    if raw in (MAIN_MENU, "[aura_nav_menu]"):
        return _reply(
            "I'm here to help. Tell me how you're feeling, ask a health question, "
            "or say you'd like to book an appointment or upload a report.",
            session_patch={
                "care_goal": None,
                "awaiting": None,
                "active_specialist": None,
                "triage_collected": {},
                "last_report_analysis": None,
                "report_qa_open": None,
            },
        )

    if raw in (START_SYMPTOM_TRIAGE, START_FIND_DOCTOR, FIND_BY_SYMPTOMS):
        return None

    if raw == UPLOAD_SYMPTOM_IMAGE:
        return _reply(
            "Select a clear photo of the affected area. I'll analyze visible signs and continue your symptom assessment.",
            agent="triage_agent",
            session_patch={
                "care_goal": "symptom_assessment",
                "active_specialist": "triage_agent",
                "awaiting": "symptom_image",
            },
            awaiting_input="upload",
        )

    if raw == TYPE_OWN_SYMPTOMS:
        return None

    if raw == FIND_BY_SPECIALTY:
        return _reply(
            "Pick a specialty below, or type one in the chat (e.g. Pulmonologist).",
            agent="scheduling_agent",
            ui=build_specialty_picker_ui(),
            session_patch={
                "care_goal": "find_doctor",
                "active_specialist": "scheduling_agent",
                "awaiting": "pick_specialty",
            },
        )

    if raw in (FIND_NEAR_ME, VIEW_ALL_DOCTORS):
        label = "doctors near you" if raw == FIND_NEAR_ME else "all available doctors"
        return _reply(
            f"Let me find {label} for you.",
            agent="scheduling_agent",
            session_patch={
                "care_goal": "appointment",
                "active_specialist": "scheduling_agent",
                "awaiting": "pick_doctor",
            },
            delegate=True,
            map_to_message="Show available doctors",
        )

    if raw == START_EXPLAIN_REPORT:
        return _reply(
            "Select your medical report, prescription, or lab file to upload. "
            "I'll analyze it and explain the results in simple language.",
            agent="report_agent",
            session_patch={
                "care_goal": "guest_report",
                "active_specialist": "report_agent",
                "awaiting": "report_upload",
            },
            awaiting_input="upload",
        )

    if raw in (UPLOAD_REPORT, UPLOAD_PRESCRIPTION, UPLOAD_LAB, UPLOAD_IMAGE):
        labels = {
            UPLOAD_REPORT: "medical report",
            UPLOAD_PRESCRIPTION: "prescription",
            UPLOAD_LAB: "lab report",
            UPLOAD_IMAGE: "medical image",
        }
        return _reply(
            f"Select your {labels[raw]} file to upload. "
            "I'll analyze it and explain the results in simple language.",
            agent="report_agent",
            session_patch={
                "care_goal": "guest_report",
                "awaiting": "report_upload",
            },
            awaiting_input="upload",
        )

    analysis = session.get("last_report_analysis")
    if session.get("awaiting") == "report_followup":
        if raw in _AURA_TOKENS:
            clear_report_followup(session, keep_analysis=False)
            return None

        from app.services.report_discussion_service import (
            REPORT_DISCUSSION_DECLINE,
            is_report_followup_no,
            is_report_followup_yes,
        )

        if is_report_followup_no(text):
            clear_report_followup(session, keep_analysis=True)
            return _reply(
                REPORT_DISCUSSION_DECLINE,
                agent="report_agent",
                session_patch={
                    "awaiting": None,
                    "care_goal": None,
                    "active_specialist": None,
                    "report_qa_open": None,
                },
            )

        if is_report_followup_yes(text):
            return _reply(
                text,
                agent="scheduling_agent",
                delegate=True,
                map_to_message=text,
            )

        if session.get("report_qa_open") and analysis:
            reply = format_report_reply(analysis, text)
            return _reply(
                reply,
                agent="report_agent",
                session_patch={
                    "report_qa_open": True,
                    "awaiting": "report_followup",
                    "care_goal": "guest_report_done",
                },
            )

        clear_report_followup(session, keep_analysis=True)
        return None

    return None


def attach_nav_menu(response: dict[str, Any], session: dict) -> dict[str, Any]:
    """Guest chat uses free-text conversation — no persistent nav menu overlay."""
    return response
