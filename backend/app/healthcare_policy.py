"""Scope, safety, and messaging policy for the healthcare assistant."""

import re

OFF_TOPIC_REPLY = (
    "I am a healthcare assistant and can only help with medical and healthcare-related "
    "questions. Please ask a healthcare-related query."
)

HEALTH_QA_PROMPT = """You are MedAssist AI — a safe, production-grade healthcare assistant.

SCOPE: Answer ONLY healthcare, medical, wellness, and clinic-service questions.
Use the patient context and conversation history for personalized, context-aware replies.

STRICT SAFETY RULES:
- Never diagnose a specific condition for this patient
- Never prescribe medications or recommend dosages
- Never invent lab results, doctors, appointments, or clinic policies
- Provide general medical education in clear, empathetic language
- If information is insufficient, ask ONE clarifying follow-up question
- If uncertain, state your limitation and recommend consulting a licensed clinician
- For emergencies, tell the patient to seek immediate emergency care

You may help with: symptoms (general info), diseases, treatments (general), medications (education only),
preventive care, diagnostics, specialist types, wellness, and appointment guidance.

Respond in natural language (not JSON). Be concise but helpful."""

# Offline fallback — obvious non-healthcare topics
_OFF_TOPIC_PATTERNS = (
    r"\bweather\b", r"\bforecast\b", r"\btemperature in\b",
    r"\bfootball\b", r"\bcricket\b", r"\bsoccer\b", r"\bbasketball\b",
    r"\bmovie\b", r"\bnetflix\b", r"\brecipe\b", r"\bcook\b", r"\brestaurant\b",
    r"\bpython code\b", r"\bjavascript\b", r"\bwrite a program\b", r"\bhomework\b",
    r"\bstock market\b", r"\bbitcoin\b", r"\bcrypto\b",
    r"\bwho won\b", r"\belection\b", r"\bpolitics\b",
    r"\btravel deal\b", r"\bflight ticket\b", r"\bhotel booking\b",
    r"\bjoke\b", r"\btell me a story\b", r"\bpoem\b",
)

_HEALTH_TOPIC_PATTERNS = (
    r"\bdoctor\b", r"\bappointment\b", r"\bhospital\b", r"\bclinic\b",
    r"\bsymptom\b", r"\bfever\b", r"\bpain\b", r"\bheadache\b", r"\bcough\b",
    r"\bmedicine\b", r"\bmedication\b", r"\bprescription\b", r"\btreatment\b",
    r"\bdisease\b", r"\bdiabetes\b", r"\bhypertension\b", r"\bcancer\b",
    r"\bwellness\b", r"\bdiet\b", r"\bnutrition\b", r"\bvaccine\b", r"\bpreventive\b",
    r"\blab\b", r"\btest\b", r"\bdiagnos", r"\bhealth\b", r"\bmedical\b",
    r"\bspecialist\b", r"\brefill\b", r"\breschedule\b", r"\bcancel\b",
)

_GREETING_ONLY = re.compile(
    r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|thanks|thank\s+you|ok|okay|yes|no|sure)[!.?\s]*$",
    re.I,
)


def is_short_flow_reply(text: str) -> bool:
    """Allow yes/no, numbers, doctor picks, and short replies during an active booking/triage flow."""
    t = text.strip().lower()
    if len(t) <= 30 and re.match(r"^(yes|no|yeah|nope|ok|okay|sure|confirm|\d{1,2})$", t):
        return True
    if re.search(r"\d{1,2}:\d{2}\s*(am|pm)?", t):
        return True
    if re.match(r"^dr\.?\s+\w+", t):
        return True
    if re.match(r"^(today|tomorrow)\b", t):
        return True
    return False


def looks_like_doctor_pick(text: str) -> bool:
    return bool(re.match(r"^dr\.?\s+\w+", text.strip(), re.I))


def history_has_pending_booking_offer(history: list[dict] | None) -> bool:
    """Recover context when Redis flow state was lost but the assistant just offered booking."""
    if not history:
        return False
    for msg in reversed(history[-6:]):
        if msg.get("role") not in ("assistant", "Assistant"):
            continue
        content = msg.get("content") or ""
        if "would you like me to show available doctors" in content.lower():
            return True
        break
    return False


def is_off_topic_fallback(text: str) -> bool:
    """Offline guard when LLM is unavailable."""
    t = text.strip().lower()
    if _GREETING_ONLY.match(t):
        return False
    if any(re.search(p, t) for p in _HEALTH_TOPIC_PATTERNS):
        return False
    if any(re.search(p, t) for p in _OFF_TOPIC_PATTERNS):
        return True
    return False


def is_healthcare_related_fallback(text: str) -> bool:
    t = text.strip().lower()
    if _GREETING_ONLY.match(t):
        return True
    return any(re.search(p, t) for p in _HEALTH_TOPIC_PATTERNS)


def should_reject_off_topic(
    text: str,
    understanding: dict | None,
    in_active_flow: bool,
    history: list[dict] | None = None,
) -> bool:
    if in_active_flow or is_short_flow_reply(text) or looks_like_doctor_pick(text):
        return False
    if history_has_pending_booking_offer(history) and (
        _yes_like(text) or looks_like_doctor_pick(text)
    ):
        return False
    if understanding:
        if understanding.get("healthcare_related") is False:
            return True
        if understanding.get("intent") == "off_topic":
            return True
        return False
    return is_off_topic_fallback(text)


def _yes_like(text: str) -> bool:
    return text.strip().lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please"}
