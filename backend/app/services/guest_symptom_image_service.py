"""Guest Aura — symptom photo upload and triage integration."""
from __future__ import annotations

from typing import Any

from app.services.chat_ui import build_duration_picker_ui
from app.services.guest_flow import guest_flow_conversation_id
from app.services.guest_session_store import load_guest_session, save_guest_session
from app.services.flow_state import get_flow, set_flow
from app.services.symptom_image_service import analyze_symptom_image, format_symptom_image_reply


async def process_guest_symptom_image(
    session_id: str,
    data: bytes,
    filename: str,
    mime_type: str | None,
) -> dict[str, Any]:
    payload = await load_guest_session(session_id)
    if not payload:
        raise ValueError("Guest session expired. Please start a new consultation.")

    session = dict(payload.get("session") or {})
    history = list(payload.get("messages") or [])

    analysis = await analyze_symptom_image(data, filename, mime_type)
    reply = format_symptom_image_reply(analysis)

    symptoms = analysis.get("possible_symptoms") or []
    if symptoms:
        session["detected_symptoms"] = symptoms
        triage = dict(session.get("triage_collected") or {})
        triage["symptoms"] = symptoms
        triage.setdefault("notes", []).append(f"Symptom photo: {filename}")
        session["triage_collected"] = triage
    session["care_goal"] = "symptom_assessment"
    session["active_specialist"] = "triage_agent"
    session["last_symptom_image_analysis"] = analysis

    ui = None
    if not (session.get("triage_collected") or {}).get("duration"):
        session["awaiting"] = "pick_duration"
        ui = build_duration_picker_ui()
        reply += "\n\n**How long have you been experiencing this?**"

    history.append({"role": "user", "content": f"Uploaded symptom photo: {filename}"})
    history.append({"role": "assistant", "content": reply, "agent": "triage_agent", "ui": ui})

    payload["messages"] = history[-40:]
    payload["session"] = session
    await save_guest_session(session_id, payload)

    conv_id = guest_flow_conversation_id(session_id)
    flow = await get_flow(conv_id)
    merged = dict(flow.get("session") or {})
    merged.update(session)
    await set_flow(conv_id, {"session": merged})

    return {
        "reply": reply,
        "emergency": analysis.get("risk_level") == "emergency",
        "agent": "triage_agent",
        "ui": ui,
        "requires_signup": False,
        "awaiting_input": None,
        "upload_kind": None,
    }
