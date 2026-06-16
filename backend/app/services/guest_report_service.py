"""Guest landing chat — medical report upload and explanation (no login required)."""
from __future__ import annotations

from typing import Any

from app.services.flow_state import set_flow
from app.services.guest_flow import guest_flow_conversation_id
from app.services.guest_session_store import load_guest_session, save_guest_session
from app.services.report_discussion_service import (
    build_report_discussion_followup_payload,
    clear_report_discussion_session,
    is_report_followup_action as _is_report_followup_action,
)
from app.services.report_service import (
    SUPPORTED_FORMATS_LABEL,
    analyze_ocr_text,
    extract_report_text,
    validate_report_file,
)


def is_report_followup_action(text: str) -> bool:
    return _is_report_followup_action(text)


def clear_report_followup(session: dict, *, keep_analysis: bool = True) -> None:
    """Exit report button mode so later consultations are not hijacked."""
    clear_report_discussion_session(session, keep_analysis=keep_analysis)


def should_leave_report_followup(text: str, session: dict) -> bool:
    """True when the user is starting a new topic instead of a report action."""
    if session.get("awaiting") != "report_followup":
        return False
    if is_report_followup_action(text):
        return False
    if session.get("report_qa_open"):
        return False
    return True


def report_upload_prompt() -> str:
    return (
        "I can help explain your lab or medical report in plain language.\n\n"
        f"Select your file to upload ({SUPPORTED_FORMATS_LABEL}) — "
        "I'll summarize the key findings for you."
    )


async def process_guest_report_upload(
    session_id: str,
    data: bytes,
    filename: str,
    mime_type: str | None,
) -> dict[str, Any]:
    payload = await load_guest_session(session_id)
    if not payload:
        raise ValueError("Guest session expired. Please start a new consultation.")

    session = payload.get("session") or {}
    history = payload.get("messages") or []

    # Paperclip upload without tapping "Explain my medical report" — start report flow automatically.
    if session.get("care_goal") != "guest_report" or session.get("awaiting") != "report_upload":
        session["care_goal"] = "guest_report"
        session["awaiting"] = "report_upload"

    validate_report_file(filename, mime_type, data)
    ocr = await extract_report_text(data, filename, mime_type)
    if not ocr or not ocr.strip():
        raise ValueError("Could not read text from this file. Try a PDF or clearer image.")

    analysis = await analyze_ocr_text(ocr)
    reply, followup_ui, session_patch = build_report_discussion_followup_payload("guest-upload", analysis)

    history.append({"role": "user", "content": f"Uploaded: {filename}"})
    history.append(
        {
            "role": "assistant",
            "content": reply,
            "agent": "report_agent",
            "ui": followup_ui,
        }
    )

    session.update(session_patch)
    session["care_goal"] = "guest_report_done"
    payload["messages"] = history[-40:]
    payload["session"] = session
    await save_guest_session(session_id, payload)
    await set_flow(guest_flow_conversation_id(session_id), {"session": session})

    return {
        "reply": reply,
        "emergency": False,
        "agent": "report_agent",
        "ui": followup_ui,
        "requires_signup": False,
        "awaiting_input": None,
        "upload_kind": None,
    }
