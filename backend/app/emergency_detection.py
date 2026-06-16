"""Rule-based emergency detection — LLM output must not set emergency without these checks."""
from __future__ import annotations

import re

from app.models.enums import RiskLevel
from app.services.symptom_extraction import extract_symptoms_offline
from app.services.symptom_service import _SYMPTOM_RULES, assess_symptoms

EMERGENCY_PATTERNS = [
    r"chest pain",
    r"heart attack",
    r"cardiac arrest",
    r"can'?t breathe",
    r"cannot breathe",
    r"difficulty breathing",
    r"trouble breathing",
    r"shortness of breath",
    r"breathing problem",
    r"breathing issue",
    r"breathing difficulty",
    r"hard to breathe",
    r"hard time breathing",
    r"labou?red breathing",
    r"gasping for air",
    r"not breathing",
    r"choking",
    r"stroke",
    r"face droop",
    r"slurred speech",
    r"unconscious",
    r"passed out",
    r"unresponsive",
    r"severe bleeding",
    r"heavy bleeding",
    r"bleeding heavily",
    r"seizure",
    r"convulsion",
    r"severe.{0,40}pain",
    r"pain.{0,40}(left |right )?arm",
    r"(left |right )?arm.{0,40}pain",
    r"radiat.{0,20}arm",
    r"crushing pain",
    r"allergic reaction",
    r"anaphylaxis",
    r"throat swelling",
    r"tongue swelling",
    r"overdose",
    r"poison",
    r"sudden weakness",
    r"one.?sided numbness",
    r"vision loss",
    r"sudden blindness",
    r"high fever.{0,30}stiff neck",
    r"stiff neck.{0,30}fever",
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

_SEVERITY_RE = re.compile(
    r"\b(severe|extreme|intense|unbearable|worst|sudden|acute|critical|"
    r"life.?threatening|excruciating|agonizing|very bad|getting worse|worsening)\b",
    re.I,
)

_URGENCY_RE = re.compile(
    r"\b(immediate|immediately|urgent|urgently|right away|asap|emergency|"
    r"need help now|can'?t wait|cannot wait|help me now)\b",
    re.I,
)

_DISTRESS_RE = re.compile(
    r"\b(collapsed|fainting|passed out|unresponsive|bleeding heavily|"
    r"blood everywhere|can'?t move|cannot move|paralyz)\b",
    re.I,
)

_BREATHING_CONCERN_RE = re.compile(
    r"\b(breath|breathing|breathe|breathed|shortness of breath|short of breath|"
    r"can'?t breathe|cannot breathe|hard to breathe|difficulty breathing|"
    r"trouble breathing|breathing problem|breathing issue|breathing difficulty|"
    r"gasping|wheez|suffocat|choking|not breathing|air hunger)\b",
    re.I,
)

_PAIN_OR_DISTRESS_RE = re.compile(
    r"\b(pain|ache|hurt|hurting|cramp|discomfort|pressure|tightness)\b",
    re.I,
)

_BODY_SYSTEM_RE = re.compile(
    r"\b(chest|stomach|abdominal|belly|heart|head|dizzy|faint|bleed|numb|weakness|"
    r"vomit|cramp|gut|lung)\b",
    re.I,
)

_SPECIALTY_FROM_TEXT = (
    (r"\b(chest|heart|palpitation|cardiac)\b", "Cardiologist"),
    (r"\b(stomach|abdominal|belly|gut|vomit|nausea)\b", "Gastroenterologist"),
    (r"\b(breath|breathe|breathing|lung|wheez|asthma)\b", "Pulmonologist"),
    (
        r"\b(head|vision|numb|tingling|stroke|seizure|paralysis|confusion|"
        r"dizzy|vertigo|weakness)\b",
        "Neurologist",
    ),
    (r"\b(bleed|blood|hemorrhage)\b", "General Physician"),
    (r"\b(allerg|swelling|anaphyl)\b", "General Physician"),
    (r"\b(pregnan|pelvic|vaginal)\b", "Gynaecologist"),
    (r"\b(child|infant|baby|toddler)\b", "Pediatrician"),
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


def _has_breathing_concern(text: str) -> bool:
    return bool(_BREATHING_CONCERN_RE.search(text))


def _has_concerning_combo(text: str, symptoms: list[str]) -> bool:
    """Breathing plus another symptom or pain — skip routine triage."""
    if not _has_breathing_concern(text):
        return False
    blob = f"{' '.join(symptoms)} {text}".lower()
    if len(symptoms) >= 2:
        return True
    if _PAIN_OR_DISTRESS_RE.search(blob) and _BODY_SYSTEM_RE.search(blob):
        return True
    return bool(_BODY_SYSTEM_RE.search(blob) and _PAIN_OR_DISTRESS_RE.search(blob))


def _has_severity_signal(text: str) -> bool:
    return bool(_SEVERITY_RE.search(text))


def _has_urgency_signal(text: str) -> bool:
    return bool(_URGENCY_RE.search(text) or _DISTRESS_RE.search(text))


def _extract_urgent_symptoms(text: str) -> list[str]:
    """Pull symptom labels from free text — no fixed emergency phrase list."""
    symptoms = extract_symptoms_offline(text)
    if symptoms:
        return symptoms

    lowered = text.lower()
    for pattern in EMERGENCY_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            label = match.group(0).strip()
            return [label[:1].upper() + label[1:]]

    if _has_severity_signal(lowered) or _has_urgency_signal(lowered):
        complaint = re.sub(
            r"^(i have|i'?ve had|i am having|i'?m having|i feel|feeling|experiencing)\s+",
            "",
            text.strip(),
            flags=re.I,
        ).strip(" .")
        if complaint and len(complaint.split()) <= 12:
            return [complaint[:1].upper() + complaint[1:]]

    return []


def _risk_from_message_text(text: str) -> RiskLevel:
    """Scan full patient message against symptom routing rules (highest risk wins)."""
    order = {
        RiskLevel.low: 0,
        RiskLevel.medium: 1,
        RiskLevel.high: 2,
        RiskLevel.emergency: 3,
    }
    tl = text.lower()
    risk = RiskLevel.low
    for keywords, _sp, rl, _rec in _SYMPTOM_RULES:
        if any(kw in tl for kw in keywords) and order[rl] > order[risk]:
            risk = rl
    return risk


def _resolve_urgent_specialty(text: str, assessed_specialty: str) -> str:
    for pattern, specialty in _SPECIALTY_FROM_TEXT:
        if re.search(pattern, text, re.I):
            return specialty
    if assessed_specialty and assessed_specialty != "Emergency":
        return assessed_specialty
    return "General Physician"


def detect_urgent_consult(text: str) -> dict | None:
    """
    Dynamic urgent tele-consult detection for any serious emergency.
    Uses symptom extraction + risk assessment — not hardcoded phrase combos.
    """
    tl = text.strip().lower()
    if not tl or detect_mental_health_crisis(tl):
        return None

    symptoms = _extract_urgent_symptoms(text)
    assessment = assess_symptoms(symptoms or ["unspecified symptoms"], None, None)
    message_risk = _risk_from_message_text(text)
    assessed_risk = assessment["risk_level"]
    highest_risk = (
        RiskLevel.emergency
        if RiskLevel.emergency in (message_risk, assessed_risk)
        else RiskLevel.high
        if RiskLevel.high in (message_risk, assessed_risk)
        else assessed_risk
    )

    is_rule_emergency = detect_emergency(tl)
    has_breathing = _has_breathing_concern(tl)
    has_severity = _has_severity_signal(tl)
    has_urgency = _has_urgency_signal(tl)
    concerning_combo = _has_concerning_combo(text, symptoms)
    symptom_count = len(symptoms)

    should_trigger = False
    if is_rule_emergency:
        should_trigger = True
    elif concerning_combo or (has_breathing and symptom_count >= 2):
        should_trigger = True
    elif highest_risk == RiskLevel.emergency:
        should_trigger = True
    elif highest_risk == RiskLevel.high and (has_severity or has_urgency or symptom_count >= 2):
        should_trigger = True
    elif has_urgency and symptom_count >= 1:
        should_trigger = True
    elif has_severity and symptom_count >= 2:
        should_trigger = True
    elif has_severity and has_urgency and symptom_count >= 1:
        should_trigger = True

    # Mild routine complaints without urgency stay in normal triage.
    if not should_trigger:
        return None
    if (
        is_routine_symptom_message(text)
        and not is_rule_emergency
        and not has_breathing
        and not concerning_combo
        and not has_severity
        and not has_urgency
        and highest_risk not in (RiskLevel.emergency, RiskLevel.high)
    ):
        return None

    risk_level = "emergency" if (
        is_rule_emergency or highest_risk == RiskLevel.emergency or (has_breathing and concerning_combo)
    ) else "high"

    specialty = _resolve_urgent_specialty(text, assessment["recommended_specialty"])
    display_symptoms = symptoms or _extract_urgent_symptoms(text) or ["Urgent symptoms"]

    return {
        "specialty": specialty,
        "risk_level": risk_level,
        "symptoms": display_symptoms,
        "er_advisory": risk_level == "emergency" or is_rule_emergency or has_breathing,
    }


def build_urgent_consult_opener(
    specialty: str,
    *,
    er_advisory: bool = True,
    symptoms: list[str] | None = None,
) -> str:
    er_line = (
        "If you have severe breathing difficulty, chest pain, or feel unsafe, "
        "**call emergency services (911) or go to the ER now** — do not wait.\n\n"
        if er_advisory
        else ""
    )
    context = ""
    if symptoms:
        shown = ", ".join(symptoms[:4])
        if len(symptoms) > 4:
            shown += ", …"
        context = f"Based on what you've shared ({shown}), "
    return (
        f"{er_line}"
        f"{context}this sounds urgent. Available **{specialty}** doctors are being notified for "
        "**immediate video approval**. You'll join as soon as a doctor approves your request."
    )
