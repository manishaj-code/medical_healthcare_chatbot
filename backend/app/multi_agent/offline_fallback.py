"""Offline fallbacks when LLM calls fail (quota, network, etc.). Structural triage only — no disease scripts."""
from __future__ import annotations

import re
from typing import Any

from app.services.chat_ui import (
    build_duration_picker_ui,
    build_more_symptoms_ui,
    build_no_more_symptoms_ui,
    build_severity_picker_ui,
    build_symptom_starter_ui,
)
from app.healthcare_policy import (
    build_greeting_reply,
    build_thanks_reply,
    is_active_care_flow,
    is_thanks_message,
    patient_first_name,
)
from app.services.symptom_extraction import (
    extract_symptoms_offline,
    is_non_symptom_message,
    looks_like_health_complaint,
)

# ── Duration extraction (offline fallback when LLM unavailable) ─────────────
_DURATION_RE = re.compile(
    r"""
    (?:
        \d+[-–]\d+\s*(?:days?|weeks?|hours?)          # "2-3 days", "1-2 weeks"
        | \d+\s*(?:days?|weeks?|hours?|months?)        # "3 days", "2 weeks"
        | (?:a\s+)?few\s+days                          # "few days"
        | (?:about|almost|nearly|around|over)\s+(?:a\s+)?\w+  # "about a week"
        | (?:a\s+)?couple\s+of\s+(?:days?|weeks?)      # "couple of days"
        | several\s+(?:days?|weeks?|months?)           # "several days"
        | since\s+(?:yesterday|last\s+night|this\s+morning|\S+)
        | from\s+yesterday
        | \byesterday\b
        | last\s+night
        | this\s+morning
        | just\s+started
        | for\s+a\s+while
        | (?:a|one)\s+week
    )
    """,
    re.I | re.VERBOSE,
)

_START_TRIAGE_RE = re.compile(
    r"^(i['']?d like to )?(analyze|assess|check) (my )?symptoms\.?$|^\[start_symptom_triage\]$",
    re.I,
)

_SYMPTOM_KICKOFF_RE = re.compile(
    r"^(check symptoms|check my symptoms|\[start_symptom_triage\]|"
    r"i(?:'m| am) not feeling well.*(?:assess|check|help with).*(?:symptoms|symptom))",
    re.I,
)


def is_symptom_triage_kickoff(text: str) -> bool:
    """True when the patient tapped Check symptoms or equivalent — no concrete complaint yet."""
    tl = text.strip().lower()
    if tl in {
        "[start_symptom_triage]",
        "check symptoms",
        "check my symptoms",
        "i'm not feeling well and would like help assessing my symptoms.",
    }:
        return True
    return bool(_SYMPTOM_KICKOFF_RE.match(tl))


def kickoff_symptom_triage_turn(session: dict) -> dict[str, Any]:
    """Structured first turn: ask what they're suffering from and start triage state."""
    pname = patient_first_name(session.get("_patient_first_name"))
    collected: dict[str, Any] = {"questions_asked": ["symptoms"]}
    return {
        "reply": (
            f"I'm sorry you're not feeling well, {pname}. "
            "What symptoms are you experiencing right now? "
            "Describe what's bothering you — for example fever, headache, cough, or stomach pain — "
            "and I'll ask a few short follow-up questions to understand how you're doing."
        ),
        "ui": build_symptom_starter_ui(),
        "session_patch": {
            "triage_collected": collected,
            "care_goal": "symptom_assessment",
            "active_specialist": "triage_agent",
            "awaiting": "free_text_symptoms",
        },
    }

_BUTTON_DURATIONS = {
    "less than 1 day": "less than 1 day",
    "1-3 days": "1-3 days",
    "1–3 days": "1-3 days",
    "4-7 days": "4-7 days",
    "4–7 days": "4-7 days",
    "over 1 week": "over 1 week",
    "not sure": "not sure",
}


def extract_duration(text: str) -> str | None:
    """Extract duration from free text or quick-action button labels."""
    tl = text.strip().lower()
    if tl in _BUTTON_DURATIONS:
        return _BUTTON_DURATIONS[tl]
    match = _DURATION_RE.search(text)
    return match.group(0).strip() if match else None


def extract_symptoms(text: str, prior: list[str] | None = None, session: dict | None = None) -> list[str]:
    from_message = extract_symptoms_offline(text, None)
    if from_message:
        return from_message
    if prior:
        return list(prior)
    if session and session.get("detected_symptoms"):
        return list(session["detected_symptoms"])
    return []


def _starts_new_triage(text: str) -> bool:
    tl = text.strip().lower()
    if _START_TRIAGE_RE.match(tl):
        return True
    if is_non_symptom_message(text):
        return False
    return looks_like_health_complaint(text)


def _is_affirmative_more_symptoms(text: str) -> bool:
    tl = text.strip().lower()
    if "yes, i have more" in tl:
        return True
    return tl in {"yes", "yeah", "yep", "sure"}


def _format_list_more_symptoms_prompt(pname: str) -> str:
    if pname != "there":
        return (
            f"What other symptoms are you experiencing, {pname}? "
            "Please type them below — for example fever, headache, or cough."
        )
    return (
        "What other symptoms are you experiencing? "
        "Please type them below — for example fever, headache, or cough."
    )


def _format_more_symptoms_nudge() -> str:
    return (
        "Please type the other symptoms you're having (e.g. fever, cough, headache), "
        "or tap **No, that's all** if you've shared everything."
    )


def _parse_severity(text: str, collected: dict, awaiting: str | None = None) -> str | None:
    """Parse severity from button labels or free text — avoid mistaking duration digits for pain scores."""
    t = text.strip().lower()
    if t in {"mild", "moderate", "severe", "very severe", "not sure"}:
        return text.strip()
    if awaiting != "pick_severity":
        return None
    if re.search(r"\b([1-9]|10)\s*/\s*10\b", t) or re.search(r"\b([1-9]|10)\s+out of\s+10\b", t):
        return text.strip()
    if re.search(r"\b(pain|severity|scale)\b", t) and re.search(r"\b([1-9]|10)\b", t):
        return text.strip()
    if any(w in t for w in ("mild", "moderate", "severe", "unbearable", "intense", "worse", "better", "same")):
        return text.strip()
    if any(phrase in t for phrase in ("not too bad", "manageable", "terrible")):
        return text.strip()
    return None


def _merge_collected_from_text(text: str, collected: dict, session: dict) -> None:
    """Apply free-text answers to triage slots without re-asking."""
    notes = list(collected.get("notes") or [])
    if text.strip() and not _START_TRIAGE_RE.match(text.strip().lower()):
        if not notes or notes[-1] != text.strip():
            notes.append(text.strip())
    collected["notes"] = notes[-8:]

    combined = " ".join(notes)
    if not collected.get("duration"):
        duration = extract_duration(text) or extract_duration(combined)
        if duration:
            collected["duration"] = duration

    severity = _parse_severity(text, collected, session.get("awaiting"))
    if severity:
        collected["severity"] = severity

    symptoms = session.get("detected_symptoms") or extract_symptoms(
        combined, collected.get("symptoms"), session=session
    )
    if symptoms:
        collected["symptoms"] = symptoms


def _infer_pending_slot_from_history(history: list[dict] | None) -> str | None:
    if not history:
        return None
    for msg in reversed(history[-6:]):
        if msg.get("role") not in ("assistant", "Assistant"):
            continue
        content = (msg.get("content") or "").lower()
        if any(
            phrase in content
            for phrase in (
                "type them below",
                "type freely below",
                "please type the other symptoms",
            )
        ):
            return "list_more_symptoms"
        if any(
            phrase in content
            for phrase in (
                "other symptom",
                "any other",
                "anything else",
                "additional symptom",
                "noticed any other",
            )
        ):
            return "more_symptoms"
        if "how long" in content or "how many days" in content:
            return "duration"
        if "severe" in content or "severity" in content:
            return "severity"
        break
    return None


def conversational_triage_turn(
    text: str,
    session: dict,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Adaptive triage: one question at a time, free-text + optional quick buttons."""
    from app.services.report_discussion_service import is_report_consultation_mode_turn

    if is_report_consultation_mode_turn(history or [], text):
        return {
            "reply": "Please continue with your report review booking using the options above.",
            "session_patch": {"care_goal": "report_discussion"},
        }

    tl = text.strip().lower()
    pname = patient_first_name(session.get("_patient_first_name"))
    asked: list[str] = list((session.get("triage_collected") or {}).get("questions_asked") or [])

    if is_thanks_message(text):
        return {
            "reply": build_thanks_reply(pname),
            "session_patch": {
                "care_goal": None,
                "awaiting": None,
                "active_specialist": None,
                "triage_collected": None,
            },
        }

    if is_non_symptom_message(text) and not is_active_care_flow(session):
        return {
            "reply": build_greeting_reply(pname),
            "session_patch": {
                "care_goal": None,
                "awaiting": None,
                "triage_collected": None,
                "detected_symptoms": None,
            },
        }

    if session.get("assessment_shown") and _starts_new_triage(text):
        session.pop("assessment_shown", None)
        session.pop("triage_assessed", None)
        session.pop("booking_declined", None)
        session.pop("awaiting", None)
        collected: dict[str, Any] = {"questions_asked": []}
        asked = []
    else:
        collected = dict(session.get("triage_collected") or {})
        asked = list(collected.get("questions_asked") or [])

    _merge_collected_from_text(text, collected, session)
    collected["questions_asked"] = asked

    pending_slot = _infer_pending_slot_from_history(history) or session.get("awaiting")
    if tl in {"no", "nope", "none", "nah"} and pending_slot in {
        "more_symptoms",
        "list_more_symptoms",
        "pick_severity",
    }:
        if pending_slot in {"more_symptoms", "list_more_symptoms"}:
            collected["more_symptoms_answered"] = True
            collected["ready_to_assess"] = True
            collected["more_symptoms_asked"] = True
        elif pending_slot == "pick_severity" and not collected.get("severity"):
            collected["severity"] = "none reported"

    if tl in {"skip", "not sure"} and session.get("awaiting") == "pick_duration" and not collected.get("duration"):
        collected["duration"] = "not sure"

    if tl in {"no other symptoms", "not sure about other symptoms", "no", "none"}:
        collected["more_symptoms_answered"] = True
        collected["ready_to_assess"] = True

    if tl == "not sure" and session.get("awaiting") == "pick_severity" and not collected.get("severity"):
        collected["severity"] = "not sure"

    if tl == "skip":
        awaiting = session.get("awaiting")
        if awaiting == "pick_duration" and not collected.get("duration"):
            collected["duration"] = "unspecified"
        elif awaiting == "pick_severity" and not collected.get("severity"):
            collected["severity"] = "unspecified"
        elif awaiting in {"more_symptoms", "list_more_symptoms"}:
            collected["more_symptoms_answered"] = True
            collected["ready_to_assess"] = True

    if session.get("detected_symptoms"):
        collected["symptoms"] = list(session["detected_symptoms"])
    symptoms = collected.get("symptoms") or session.get("detected_symptoms") or []

    awaiting_slot = session.get("awaiting")
    if _is_affirmative_more_symptoms(text) and awaiting_slot in {"more_symptoms", "list_more_symptoms"}:
        if collected.get("more_symptoms_list_prompted"):
            return {
                "reply": _format_more_symptoms_nudge(),
                "ui": build_no_more_symptoms_ui(),
                "session_patch": {
                    "triage_collected": collected,
                    "care_goal": "symptom_assessment",
                    "awaiting": "list_more_symptoms",
                },
            }
        collected["more_symptoms_list_prompted"] = True
        return {
            "reply": _format_list_more_symptoms_prompt(pname),
            "session_patch": {
                "triage_collected": collected,
                "care_goal": "symptom_assessment",
                "awaiting": "list_more_symptoms",
            },
        }

    if not symptoms:
        if is_thanks_message(text):
            return {
                "reply": build_thanks_reply(pname),
                "session_patch": {
                    "care_goal": None,
                    "awaiting": None,
                    "active_specialist": None,
                    "triage_collected": None,
                },
            }
        if is_symptom_triage_kickoff(text) or "symptoms" not in asked:
            kickoff = kickoff_symptom_triage_turn(session)
            kickoff["session_patch"]["triage_collected"] = collected
            if "symptoms" not in asked:
                asked.append("symptoms")
                kickoff["session_patch"]["triage_collected"]["questions_asked"] = asked
            return kickoff
        return kickoff_symptom_triage_turn(session)

    if not collected.get("duration"):
        if "duration" not in asked:
            asked.append("duration")
            collected["questions_asked"] = asked
        symptom_label = ", ".join(symptoms[:3])
        return {
            "reply": (
                f"I understand you're dealing with **{symptom_label}**. "
                "How long have you been experiencing this? "
                "You can answer naturally — e.g. **since yesterday**, **about 3 days**, or **for a week**."
            ),
            "ui": build_duration_picker_ui(),
            "session_patch": {
                "triage_collected": collected,
                "care_goal": "symptom_assessment",
                "awaiting": "pick_duration",
            },
        }

    if not collected.get("severity"):
        if "severity" not in asked:
            asked.append("severity")
            collected["questions_asked"] = asked
        return {
            "reply": (
                "How would you describe the severity of your symptoms? "
                "You can pick an option or type in your own words."
            ),
            "ui": build_severity_picker_ui(),
            "session_patch": {
                "triage_collected": collected,
                "care_goal": "symptom_assessment",
                "awaiting": "pick_severity",
            },
        }

    if not collected.get("more_symptoms_asked"):
        collected["more_symptoms_asked"] = True
        if "more_symptoms" not in asked:
            asked.append("more_symptoms")
            collected["questions_asked"] = asked
        return {
            "reply": "Are you experiencing any other symptoms?",
            "ui": build_more_symptoms_ui(),
            "session_patch": {
                "triage_collected": collected,
                "care_goal": "symptom_assessment",
                "awaiting": "more_symptoms",
            },
        }

    if collected.get("more_symptoms_asked") and not collected.get("ready_to_assess"):
        if session.get("awaiting") in {"more_symptoms", "list_more_symptoms"} and tl not in {
            "no",
            "no other symptoms",
            "not sure about other symptoms",
            "none",
        } and not _is_affirmative_more_symptoms(text):
            collected["ready_to_assess"] = True
        else:
            return {
                "reply": "Any other symptoms, or should I summarize what you've shared so far?",
                "ui": build_more_symptoms_ui(),
                "session_patch": {
                    "triage_collected": collected,
                    "care_goal": "symptom_assessment",
                    "awaiting": "more_symptoms",
                },
            }

    if session.get("assessment_shown"):
        return {"session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"}}

    return {
        "tool": "assess_symptoms",
        "tool_args": {
            "symptoms": symptoms,
            "duration": collected["duration"],
            "collected": collected,
            "summary": " ".join(collected.get("notes") or []),
        },
        "session_patch": {"triage_collected": collected},
    }


def plan_triage_turn(
    text: str,
    session: dict,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Legacy alias — prefer conversational_triage_turn."""
    return conversational_triage_turn(text, session, history)


def offline_education_reply(text: str) -> str | None:
    """Minimal offline health education when LLM is unavailable."""
    t = text.lower()
    if "fever" in t:
        return (
            "A fever is often a sign your body is fighting an infection. Rest, stay hydrated, "
            "and monitor your temperature. Seek care if fever is very high (above 103°F / 39.4°C), "
            "lasts more than 3 days, or is accompanied by severe symptoms like difficulty breathing "
            "or chest pain. Would you like me to assess your symptoms?"
        )
    if any(w in t for w in ("typhoid", "dengue", "malaria", "flu", "covid")):
        return (
            "These conditions can share symptoms like fever and fatigue. Only a clinician can "
            "diagnose through examination and tests. I can help assess your symptoms and connect "
            "you with a doctor if you'd like."
        )
    if any(w in t for w in ("hello", "hi", "hey")):
        return (
            "Hello! I'm your healthcare assistant. I can help assess symptoms, answer health "
            "questions, book appointments, and review reports. What would you like help with today?"
        )
    return None
