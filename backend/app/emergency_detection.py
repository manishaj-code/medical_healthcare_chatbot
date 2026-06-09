"""Rule-based emergency detection — LLM output must not set emergency without these checks."""
from __future__ import annotations

import re

EMERGENCY_PATTERNS = [
    r"chest pain",
    r"heart attack",
    r"can'?t breathe",
    r"cannot breathe",
    r"difficulty breathing",
    r"trouble breathing",
    r"shortness of breath",
    r"stroke",
    r"face droop",
    r"slurred speech",
    r"unconscious",
    r"passed out",
    r"severe bleeding",
    r"heavy bleeding",
    r"seizure",
    r"severe.{0,40}pain",
    r"pain.{0,40}(left |right )?arm",
    r"(left |right )?arm.{0,40}pain",
    r"radiat.{0,20}arm",
    r"crushing pain",
]

MENTAL_HEALTH_CRISIS_PATTERNS = [
    r"suicid",
    r"self.?harm",
    r"kill myself",
    r"end my life",
    r"want to die",
    r"don'?t want to live",
]

ROUTINE_SYMPTOM_HINTS = (
    "headache",
    "migraine",
    "fever",
    "cough",
    "cold",
    "sore throat",
    "nausea",
    "rash",
    "dizziness",
    "refill",
    "prescription",
    "appointment",
    "book",
)


def detect_emergency(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in EMERGENCY_PATTERNS)


def detect_mental_health_crisis(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in MENTAL_HEALTH_CRISIS_PATTERNS)


def is_routine_symptom_message(text: str) -> bool:
    lowered = text.lower().strip()
    if detect_emergency(lowered) or detect_mental_health_crisis(lowered):
        return False
    return any(hint in lowered for hint in ROUTINE_SYMPTOM_HINTS)


def is_confirmed_emergency(text: str) -> bool:
    """True only when the current patient message matches rule-based emergency criteria."""
    if detect_emergency(text) or detect_mental_health_crisis(text):
        return True
    if is_routine_symptom_message(text):
        return False
    return False


def build_emergency_reply(*, mental_health_crisis: bool = False) -> str:
    if mental_health_crisis:
        return (
            "⚠️ If you are in crisis or thinking about harming yourself, please call or text "
            "**988** (Suicide & Crisis Lifeline in the US) or your local emergency number now. "
            "You can also go to the nearest emergency department."
        )
    return (
        "⚠️ This may be a medical emergency. Please call your local emergency number or go to "
        "the nearest emergency department immediately."
    )
