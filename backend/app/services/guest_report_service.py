"""Guest landing chat — medical report upload and explanation (no login required)."""
from __future__ import annotations

from typing import Any

from app.multi_agent.booking_actions import format_report_reply
from app.services.guest_session_store import load_guest_session, save_guest_session
from app.services.report_service import (
    SUPPORTED_FORMATS_LABEL,
    analyze_ocr_text,
    extract_report_text,
    validate_report_file,
)


def report_upload_prompt() -> str:
    return (
        "I can help explain your lab or medical report in plain language.\n\n"
        f"Tap the **paperclip** below to upload your file ({SUPPORTED_FORMATS_LABEL}), "
        "or upload anytime using the paperclip — I'll summarize the key findings for you."
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
    reply = format_report_reply(analysis, "summarize this report in simple terms")

    history.append({"role": "user", "content": f"Uploaded: {filename}"})
    history.append(
        {
            "role": "assistant",
            "content": reply,
            "agent": "report_agent",
        }
    )

    session["awaiting"] = None
    session["care_goal"] = "guest_report_done"
    session["last_report_analysis"] = analysis
    payload["messages"] = history[-40:]
    payload["session"] = session
    await save_guest_session(session_id, payload)

    return {
        "reply": reply,
        "emergency": False,
        "agent": "report_agent",
        "ui": None,
        "requires_signup": False,
        "awaiting_input": None,
    }
