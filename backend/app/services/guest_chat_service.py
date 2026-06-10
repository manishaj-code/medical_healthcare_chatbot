import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.emergency_detection import (
    build_emergency_reply,
    detect_emergency,
    detect_mental_health_crisis,
)
from app.multi_agent.offline_fallback import offline_education_reply, plan_triage_turn
from app.services.chat_ui import (
    build_booking_offer_ui,
    build_duration_picker_ui,
    build_symptom_picker_ui,
)
from app.services.symptom_extraction import looks_like_health_complaint
from app.services.guest_booking_service import (
    clear_abandoned_booking,
    in_guest_booking,
    is_find_doctor_start,
    process_guest_booking,
)
from app.services.guest_report_service import report_upload_prompt
from app.services.guest_session_store import load_guest_session, save_guest_session
from app.services.symptom_extraction import update_session_symptoms
from app.services.symptom_service import assess_symptoms

START_SYMPTOM_TRIAGE_TOKEN = "[start_symptom_triage]"
START_EXPLAIN_REPORT_TOKEN = "[start_explain_report]"

_START_TRIAGE_RE = re.compile(
    r"^(i['']?d like to )?(analyze|assess|check) (my )?symptoms\.?$",
    re.I,
)

_EXPLAIN_REPORT_RE = re.compile(
    r"^(i['']?d like (help )?(understanding|to understand) (a |my )?medical report|explain (my )?(medical )?report)\.?$",
    re.I,
)

ADVANCED_GATED_PATTERNS = [
    re.compile(r"\bupload\b", re.I),
    re.compile(r"\blab\b", re.I),
    re.compile(r"\brefill\b", re.I),
    re.compile(r"\bprescription\b", re.I),
]


def _clear_stale_auth_state(session: dict) -> None:
    if session.get("awaiting") in ("guest_email", "guest_otp") and not session.get("pending_slot"):
        session.pop("awaiting", None)
        session.pop("guest_email", None)
    if session.get("care_goal") == "guest_verify":
        session.pop("care_goal", None)


def _in_active_booking_flow(session: dict) -> bool:
    if session.get("care_goal") != "guest_booking":
        return False
    return session.get("awaiting") in {
        "pick_doctor",
        "pick_slot",
        "confirm_booking",
        "guest_email",
        "guest_otp",
    }


def _is_report_explain_start(text: str) -> bool:
    stripped = text.strip()
    if stripped == START_EXPLAIN_REPORT_TOKEN:
        return True
    return bool(_EXPLAIN_REPORT_RE.match(stripped))


def _requires_signup(text: str, session: dict) -> str | None:
    if in_guest_booking(session) or is_find_doctor_start(text):
        return None
    if session.get("awaiting") == "offer_booking":
        return None
    if session.get("care_goal") in ("symptom_assessment", "guest_report", "guest_report_done"):
        return None
    if _is_report_explain_start(text):
        return None
    if re.search(r"\breport\b", text, re.I):
        return "advanced"
    for pattern in ADVANCED_GATED_PATTERNS:
        if pattern.search(text):
            return "advanced"
    return None


def _is_symptom_triage_start(text: str) -> bool:
    stripped = text.strip()
    if stripped == START_SYMPTOM_TRIAGE_TOKEN:
        return True
    return bool(_START_TRIAGE_RE.match(stripped))


def _affirmative_short(text: str) -> bool:
    return text.strip().lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please"}


def _assistant_offered_assessment(history: list) -> bool:
    for msg in reversed(history[-6:]):
        if msg.get("role") != "assistant":
            continue
        content = (msg.get("content") or "").lower()
        return "assess your symptoms" in content
    return False


def _begin_symptom_triage_reply() -> tuple[str, dict]:
    reply = (
        "Hello! How are you feeling today? "
        "Tell me what's bothering you — for example headache, fever, or dizziness — or tap a symptom below."
    )
    return reply, build_symptom_picker_ui()


def _advanced_feature_reply() -> str:
    return (
        "Prescription refills need a signed-in account. "
        "Use **Sign in** below — or tap **Explain my medical report** / **Check my symptoms** here."
    )


async def process_guest_message(session_id: str, text: str, db: AsyncSession) -> dict[str, Any]:
    data = await load_guest_session(session_id)
    if not data:
        raise ValueError("Guest session expired. Please start a new consultation.")

    session = data.get("session") or {}
    history = data.get("messages") or []
    _clear_stale_auth_state(session)
    clear_abandoned_booking(session, text)
    await update_session_symptoms(session, text)

    if detect_mental_health_crisis(text):
        reply = build_emergency_reply(mental_health_crisis=True)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply, "agent": "emergency", "emergency": True})
        data["messages"] = history[-40:]
        await save_guest_session(session_id, data)
        return {"reply": reply, "emergency": True, "agent": "emergency", "ui": None, "requires_signup": False}

    if detect_emergency(text):
        reply = build_emergency_reply()
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply, "agent": "emergency", "emergency": True})
        data["messages"] = history[-40:]
        await save_guest_session(session_id, data)
        return {"reply": reply, "emergency": True, "agent": "emergency", "ui": None, "requires_signup": False}

    if _is_symptom_triage_start(text) and not _in_active_booking_flow(session):
        reply, ui = _begin_symptom_triage_reply()
        session["care_goal"] = "symptom_assessment"
        session["triage_collected"] = {}
        session.pop("awaiting", None)
        session.pop("triage_assessed", None)
        session.pop("booking_declined", None)
        session.pop("assessment_shown", None)
        history.append({"role": "user", "content": text})
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

    if _is_report_explain_start(text) and not _in_active_booking_flow(session):
        reply = report_upload_prompt()
        session["care_goal"] = "guest_report"
        session["awaiting"] = "report_upload"
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply, "agent": "report_agent"})
        data["messages"] = history[-40:]
        data["session"] = session
        await save_guest_session(session_id, data)
        return {
            "reply": reply,
            "emergency": False,
            "agent": "report_agent",
            "ui": None,
            "requires_signup": False,
            "awaiting_input": "upload",
        }

    booking_result = await process_guest_booking(db, session_id, text, session, history, data)
    if booking_result:
        return booking_result

    if (
        _affirmative_short(text)
        and _assistant_offered_assessment(history)
        and session.get("awaiting") != "offer_booking"
    ):
        session.pop("assessment_shown", None)
        session.pop("triage_assessed", None)
        session.pop("booking_declined", None)
        session.pop("awaiting", None)
        symptoms = list(session.get("detected_symptoms") or [])
        user_notes = [
            (m.get("content") or "").strip()
            for m in history
            if m.get("role") == "user" and (m.get("content") or "").strip()
        ]
        session["care_goal"] = "symptom_assessment"
        session["triage_collected"] = {"symptoms": symptoms, "notes": user_notes[-4:]}
        if symptoms:
            symptom_label = ", ".join(symptoms[:3])
            reply = (
                f"I understand you're dealing with {symptom_label}. "
                "How long have you had these symptoms? Choose an option:"
            )
            ui = build_duration_picker_ui()
        else:
            reply, ui = _begin_symptom_triage_reply()
        history.append({"role": "user", "content": text})
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
        reply = _advanced_feature_reply()
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
            "requires_signup": False,
        }

    session["_patient_first_name"] = "there"
    if session.get("care_goal") != "symptom_assessment" and not session.get("triage_collected"):
        session["care_goal"] = "symptom_assessment"

    decision = plan_triage_turn(text, session)

    emergency = False
    if decision.get("tool") == "assess_symptoms":
        args = decision["tool_args"]
        result = assess_symptoms(args["symptoms"], args.get("duration"), None)
        specialty = result["recommended_specialty"]
        reply = (
            f"Based on your symptoms, I recommend consulting a **{specialty}**.\n\n"
            f"{result['recommendation_text']}\n\n"
            "Would you like to book an appointment?"
        )
        session["awaiting"] = "offer_booking"
        session["recommended_specialty"] = specialty
        session["care_goal"] = "symptom_assessment"
        session["triage_assessed"] = True
        session["assessment_shown"] = True
        ui = build_booking_offer_ui()
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
        if looks_like_health_complaint(text) or session.get("detected_symptoms"):
            pname = session.get("_patient_first_name", "there")
            symptoms = session.get("detected_symptoms") or []
            if symptoms:
                symptom_label = ", ".join(symptoms[:3])
                reply = (
                    f"I understand you're dealing with {symptom_label}. "
                    "How long have you had these symptoms? Choose an option:"
                )
                ui = build_duration_picker_ui()
                session.setdefault("triage_collected", {})["symptoms"] = symptoms
                session["care_goal"] = "symptom_assessment"
            else:
                reply, ui = _begin_symptom_triage_reply()
                session["care_goal"] = "symptom_assessment"
                session["triage_collected"] = {}
            agent = "triage_agent"
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
