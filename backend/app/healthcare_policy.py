"""Scope, safety, and messaging policy for the healthcare assistant."""

import re

OFF_TOPIC_REPLY = (
    "I am a healthcare assistant and can only help with medical and healthcare-related "
    "questions. Please ask a healthcare-related query."
)

_ANONYMOUS_PATIENT_NAMES = frozenset({"guest", "anonymous", "visitor", "patient"})


def _is_anonymous_name(name: str | None) -> bool:
    raw = (name or "").strip()
    if not raw:
        return True
    return raw.split()[0].lower() in _ANONYMOUS_PATIENT_NAMES


PLAIN_LANGUAGE_RULES = """
LANGUAGE — keep replies easy to read:
- Use short, simple sentences and common everyday words
- Write so someone who is not fluent in English can follow
- Avoid medical jargon; if you must use a term, explain it in plain words
- Use the patient's first name from context when available — never call them "Patient" or "Guest"
- If no real name is known, skip the name (do not use "there" as a name)
"""


def patient_first_name(name: str | None, *, default: str = "there") -> str:
    """First name for conversational replies — never 'Guest', 'Patient', or other placeholders."""
    raw = (name or "").strip()
    if not raw:
        return default
    first = raw.split()[0]
    if first.lower() in _ANONYMOUS_PATIENT_NAMES:
        return default
    return first


def patient_display_name(name: str | None, *, anonymous_label: str = "You") -> str:
    """Full display name for booking confirmations — anonymous users get a neutral label."""
    raw = (name or "").strip()
    if not raw:
        return anonymous_label
    if raw.split()[0].lower() in _ANONYMOUS_PATIENT_NAMES:
        return anonymous_label
    return raw


def patient_ctx_for_llm(patient_ctx: dict) -> dict:
    """Patient context for LLM prompts — omit placeholder guest names."""
    ctx = dict(patient_ctx)
    if _is_anonymous_name(ctx.get("name")):
        ctx.pop("name", None)
    return ctx


def build_booking_offer_intro(
    pname: str,
    specialty: str,
    *,
    basis: str = "assessment",
) -> str:
    """Friendly doctor-booking opener — uses real first name, never 'Patient'."""
    first = patient_first_name(pname)
    reason = "what you shared" if basis == "symptoms" else "your check-in"
    if first != "there":
        return f"Of course, {first}! Based on {reason}, I recommend a **{specialty}**."
    return f"Based on {reason}, I recommend a **{specialty}**."


def build_specialty_picker_intro(pname: str) -> str:
    first = patient_first_name(pname)
    tail = (
        "Which type of doctor would you like to see? "
        "Pick one below, or type a specialty in the chat."
    )
    if first != "there":
        return f"Of course, {first}! {tail}"
    return tail


def build_assessment_reply(
    pname: str,
    recommendation: str,
    specialty: str,
    risk: str,
) -> str:
    """Post-triage reply in plain language — no awkward 'Thanks, there.'"""
    first = patient_first_name(pname)
    rec = (recommendation or "").strip()
    opener = f"Thanks, {first}. " if first != "there" else ""
    if risk in ("high", "emergency"):
        closing = (
            f"\n\nThis may need quick care. Please see a **{specialty}** soon. "
            "I can help you find a doctor when you are ready."
        )
    else:
        closing = (
            f"\n\nIf you still feel unwell, a **{specialty}** can help. "
            "I can share more tips or help you book a visit."
        )
    return f"{opener}{rec}{closing}"


HEALTH_QA_PROMPT = """You are MedAssist AI — a safe, production-grade healthcare assistant.

SCOPE: Answer ONLY healthcare, medical, wellness, and clinic-service questions.
Use the patient context and conversation history for personalized, context-aware replies.
""" + PLAIN_LANGUAGE_RULES + """

STRICT SAFETY RULES:
- Never diagnose a specific condition for this patient
- Never prescribe medications or recommend dosages
- Never invent lab results, doctors, appointments, or clinic policies
- Provide general medical education in clear, empathetic language
- If information is insufficient, ask ONE clarifying follow-up question
- Never address the patient as "Guest" or "Patient" — use their first name from context, or omit the name
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
    r"^(hi|hello|hey|good\s+(morning|afternoon|evening))[!.?\s]*$",
    re.I,
)

_THANKS_RE = re.compile(r"\b(thank(?:s|you)?|thx|ty)\b", re.I)

_ACTIVE_CARE_AWAITING = frozenset({
    "pick_symptom",
    "pick_duration",
    "pick_severity",
    "more_symptoms",
    "free_text_symptoms",
    "symptom_image",
    "post_assessment",
    "offer_booking",
    "pick_doctor",
    "pick_slot",
    "confirm_booking",
    "confirm_reschedule",
    "confirm_refill",
    "pick_refill_med",
    "report_followup",
    "find_doctor_menu",
    "pick_specialty",
    "guest_email",
    "guest_otp",
})

_ACTIVE_CARE_GOALS = frozenset({
    "symptom_assessment",
    "book_after_triage",
    "appointment",
    "find_doctor",
    "guest_report",
    "guest_report_done",
    "refill",
    "manage_appointment",
    "video_consultation",
})


def is_greeting_only(text: str) -> bool:
    """True only for hi/hello — not yes/no/ok (those are triage flow answers)."""
    return bool(_GREETING_ONLY.match(text.strip()))


def is_thanks_message(text: str) -> bool:
    """Polite closure: thanks, thank you, ok thank you, om thank you!!, etc."""
    t = text.strip().lower()
    if not t:
        return False
    if t in {
        "thanks",
        "thank you",
        "thankyou",
        "thx",
        "ty",
        "ok thanks",
        "ok thank you",
        "okay thanks",
        "okay thank you",
        "got it thanks",
        "thanks!",
        "thank you!",
    }:
        return True
    return bool(_THANKS_RE.search(t))


def build_thanks_reply(patient_name: str = "there") -> str:
    first = patient_first_name(patient_name)
    if first != "there":
        return (
            f"You're welcome, {first}! I'm glad I could help. "
            "Take care, and message me anytime if you need health guidance or want to book an appointment."
        )
    return (
        "You're welcome! I'm glad I could help. "
        "Take care, and message me anytime if you need health guidance or want to book an appointment."
    )


def is_active_care_flow(session: dict) -> bool:
    """Patient is mid-consultation — short replies must continue the flow, not reset."""
    if not session:
        return False
    awaiting = session.get("awaiting")
    if awaiting in _ACTIVE_CARE_AWAITING:
        return True
    if session.get("care_goal") in _ACTIVE_CARE_GOALS:
        return True
    if session.get("active_specialist") == "triage_agent" and not session.get("triage_assessed"):
        return True
    if session.get("detected_symptoms") and not session.get("triage_assessed"):
        return True
    if session.get("report_qa_open"):
        return True
    return False


def should_reset_to_greeting(text: str, session: dict) -> bool:
    """Only reset to welcome when the patient sends a bare greeting outside an active flow."""
    return is_greeting_only(text) and not is_active_care_flow(session)


def build_greeting_reply(patient_name: str = "there") -> str:
    first = patient_first_name(patient_name)
    hello = f"Hello {first}!" if first != "there" else "Hello!"
    return (
        f"{hello} I'm your AI Healthcare Assistant. "
        "I can help you understand symptoms, answer health questions, book appointments, "
        "and review medical reports. How can I help you today?"
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
