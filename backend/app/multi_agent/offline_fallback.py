"""Offline fallbacks when LLM calls fail (quota, network, etc.). Structural triage only — no disease scripts."""
from __future__ import annotations

import re
from typing import Any

from app.services.chat_ui import (
    build_duration_picker_ui,
    build_severity_picker_ui,
    build_symptom_picker_ui,
    build_yes_no_ui,
)

_DURATION_PATTERNS = (
    re.compile(r"(?:last|past|for)\s+\d+\s*(?:days|day|weeks|week|hours|hour)", re.I),
    re.compile(r"\d+\s*(?:days|day|weeks|week|hours|hour|months|month)", re.I),
    re.compile(r"from\s+\d+\s*(?:days|day|weeks|week|hours|hour)", re.I),
    re.compile(r"few\s+days|couple\s+of\s+days", re.I),
    re.compile(r"since\s+yesterday|since\s+last\s+week", re.I),
)

SYMPTOM_HINTS = (
    "fever", "cough", "headache", "migraine", "pain", "nausea", "dizziness", "fatigue",
    "cold", "sore throat", "vomiting", "rash", "swelling", "breathing", "chest",
    "chills", "body ache", "weakness",
)

_HAVE_SYMPTOM_RE = re.compile(
    r"(?:i have|i'?ve had|i am having|feeling|suffering from|experiencing)\s+(?:a\s+)?([a-z][\w\s-]{0,48})",
    re.I,
)

_NON_SYMPTOM_RE = re.compile(
    r"^(less than 1 day|1-3 days|4-7 days|over 1 week|yes|no|no other symptoms|\[start_symptom_triage\])",
    re.I,
)

_START_TRIAGE_RE = re.compile(
    r"^(i['']?d like to )?(analyze|assess|check) (my )?symptoms\.?$|^\[start_symptom_triage\]$",
    re.I,
)


def extract_duration(text: str) -> str | None:
    for pattern in _DURATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def _normalize_symptom_label(phrase: str) -> str:
    p = phrase.strip().rstrip(".").lower()
    if re.search(r"\bmigrain\w*\b", p):
        return "migraine"
    return p


def extract_symptoms(text: str, prior: list[str] | None = None) -> list[str]:
    blob = " ".join([*(prior or []), text]).lower()
    found: list[str] = []
    for hint in SYMPTOM_HINTS:
        if hint in blob:
            found.append(hint)
    if re.search(r"\bmigrain\w*\b", blob):
        found.append("migraine")
    if found:
        return list(dict.fromkeys(found))

    for segment in re.split(r"[.!?;\n]+", text):
        seg = segment.strip()
        if not seg or _NON_SYMPTOM_RE.match(seg) or _START_TRIAGE_RE.match(seg):
            continue
        if re.search(r"\b(mild|moderate|severe|getting worse)\b", seg, re.I):
            continue
        match = _HAVE_SYMPTOM_RE.search(seg)
        if match:
            label = _normalize_symptom_label(match.group(1))
            if label:
                return [label]
        words = seg.split()
        if 1 <= len(words) <= 5 and not extract_duration(seg):
            return [_normalize_symptom_label(seg)]

    return list(prior or [])


def plan_triage_turn(text: str, session: dict) -> dict[str, Any]:
    """Decide the next triage action without LLM — collect info, then assess."""
    tl = text.strip().lower()
    collected: dict[str, Any] = dict(session.get("triage_collected") or {})
    notes: list[str] = list(collected.get("notes") or [])

    if _START_TRIAGE_RE.match(tl) and not notes and not session.get("triage_assessed"):
        pname = session.get("_patient_first_name", "there")
        return {
            "reply": (
                f"Hello! How are you feeling today, {pname}? "
                "Tell me what's bothering you, or tap a symptom below."
            ),
            "ui": build_symptom_picker_ui(),
            "session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"},
        }

    if text.strip() and not _START_TRIAGE_RE.match(tl):
        notes.append(text.strip())
    collected["notes"] = notes[-6:]

    duration = collected.get("duration") or extract_duration(" ".join(notes))
    duration_phrases = {
        "less than 1 day": "less than 1 day",
        "1-3 days": "1-3 days",
        "4-7 days": "4-7 days",
        "over 1 week": "over 1 week",
    }
    if not duration:
        for phrase, value in duration_phrases.items():
            if phrase in tl:
                duration = value
                break
    if duration:
        collected["duration"] = duration

    if tl == "no other symptoms":
        collected["ready_to_assess"] = True
        symptoms = collected.get("symptoms") or extract_symptoms(" ".join(notes))
        if symptoms and collected.get("duration"):
            return {
                "tool": "assess_symptoms",
                "tool_args": {
                    "symptoms": symptoms,
                    "duration": collected["duration"],
                    "collected": collected,
                    "summary": " ".join(notes),
                },
                "session_patch": {"triage_collected": collected},
            }

    pname = session.get("_patient_first_name", "there")

    if "more symptoms" in tl:
        return {
            "reply": f"What other symptoms are you experiencing, {pname}? Tap below:",
            "ui": build_symptom_picker_ui(),
            "session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"},
        }

    symptoms = extract_symptoms(" ".join(notes), collected.get("symptoms"))
    collected["symptoms"] = symptoms

    if not symptoms:
        return {
            "reply": f"I'm here to help, {pname}. What symptoms are you experiencing? Tap one below:",
            "ui": build_symptom_picker_ui(),
            "session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"},
        }

    if not collected.get("duration"):
        symptom_label = ", ".join(symptoms[:3])
        return {
            "reply": (
                f"I understand you're dealing with {symptom_label}. "
                "How long have you had these symptoms? Choose an option:"
            ),
            "ui": build_duration_picker_ui(),
            "session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"},
        }

    if not collected.get("severity_asked"):
        collected["severity_asked"] = True
        return {
            "reply": (
                f"Thanks — {collected['duration']} is helpful. "
                "How severe are your symptoms? Tap the closest option:"
            ),
            "ui": build_severity_picker_ui(),
            "session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"},
        }

    severity = _parse_severity(text, collected)
    if severity:
        collected["severity"] = severity

    if collected.get("ready_to_assess") or collected.get("severity") or len(notes) >= 3:
        return {
            "tool": "assess_symptoms",
            "tool_args": {
                "symptoms": symptoms,
                "duration": collected["duration"],
                "collected": collected,
                "summary": " ".join(notes),
            },
            "session_patch": {"triage_collected": collected},
        }

    collected["ready_to_assess"] = True
    return {
        "reply": (
            "Any other symptoms — such as difficulty breathing, chest pain, or a very high fever?"
        ),
        "ui": build_yes_no_ui(
            yes_label="Yes, more symptoms",
            yes_message="Yes, I have more symptoms",
            no_label="No other symptoms",
            no_message="No other symptoms",
        ),
        "session_patch": {"triage_collected": collected, "care_goal": "symptom_assessment"},
    }


def _parse_severity(text: str, collected: dict) -> str | None:
    t = text.strip().lower()
    if re.search(r"\b([1-9]|10)\b", t):
        return t
    if any(w in t for w in ("mild", "moderate", "severe", "worse", "better", "same")):
        return t
    if any(w in t for w in ("no", "none", "not really", "just fever", "only")):
        return "unspecified"
    return None


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
