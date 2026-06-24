"""LLM-powered symptom extraction — no fixed medical symptom catalog."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def _llm_client():
    from app.multi_agent.llm import llm

    return llm

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.I)
_OTP_RE = re.compile(r"^\d{6}$")
_APT_ID_RE = re.compile(r"^APT-[A-Z0-9]+$", re.I)

_INTERNAL_ACTION_TOKEN_RE = re.compile(r"^\[(?:start_[^\]]+|set_reminder:[^\]]+)\]$", re.I)
_GREETING_RE = re.compile(r"^(hi|hello|hey|yo|good\s+(morning|afternoon|evening))[!?.]*$", re.I)
_QUICK_ACTION_RE = re.compile(
    r"^(check my symptoms|find a specialist doctor|explain my medical report|"
    r"i(?:'d| would) like to (book an appointment|understand|help understanding))",
    re.I,
)
_TRIAGE_META_RE = re.compile(
    r"^(less than 1 day|1-3 days|4-7 days|over 1 week|yes|no|no other symptoms|"
    r"mild|moderate|severe|ok|okay|thanks|thank you)$",
    re.I,
)
_REPORT_OR_ACTION_RE = re.compile(
    r"please (analyze|summarize|explain)|health risk assessment|medical report|uploaded report|"
    r"out-of-range|abnormal values|book(?:\s+an)?\s+appointment|schedule(?:\s+an)?\s+appointment|"
    r"find a (doctor|specialist)|want to book|"
    r"show doctors|sign in|log ?in|verification code|upload (your |my )?report|"
    r"reminder|reschedule|cancel.*appointment|"
    r"in[- ]person consultation|video consultation|report review|choose another doctor|"
    r"book with .+ again|self[- ]care|recommend a doctor",
    re.I,
)

_HAVE_COMPLAINT_RE = re.compile(
    r"(?:i have|i'?ve had|i am having|i'?m having|had|feeling|suffering from|experiencing|"
    r"dealing with|bothered by)\s+(?:a\s+|an\s+|some\s+)?(.+)",
    re.I,
)

_AND_HAD_RE = re.compile(r"\band\s+had\s+(.+)", re.I)

_VAGUE_WELLNESS_EXACT = frozenset(
    {
        "i'm not feeling well",
        "i am not feeling well",
        "im not feeling well",
        "not feeling well",
        "i'm not feeling good",
        "i am not feeling good",
        "not feeling good",
        "i don't feel well",
        "i do not feel well",
        "dont feel well",
        "i'm unwell",
        "i am unwell",
        "feeling unwell",
        "i'm not well",
        "i am not well",
    }
)

_VAGUE_WELLNESS_RE = re.compile(
    r"^(?:i(?:'m| am)\s+)?(?:not\s+)(?:feeling\s+)?(?:well|good|fine|okay|ok)"
    r"(?:\s+(?:today|right\s+now|at\s+all))?[!.]*$",
    re.I,
)

_POSITIVE_WELLNESS_RE = re.compile(
    r"^(?:i(?:'m| am)\s+)?(?:feeling\s+)?(?:well|good|fine|okay|ok|great|better)"
    r"(?:\s+(?:today|right\s+now|now))?[!.]*$",
    re.I,
)

_VAGUE_SYMPTOM_LABELS = frozenset(
    {"well", "good", "fine", "okay", "ok", "great", "unwell", "not well", "not feeling well"}
)

_GENERIC_STANDALONE_SYMPTOMS = frozenset(
    {"pain", "ache", "aches", "discomfort", "hurt", "hurting", "soreness", "sore"}
)

_SKIP_EXACT = frozenset(
    {
        "yes",
        "no",
        "ok",
        "okay",
        "thanks",
        "thank you",
        "i'd like to book an appointment with a doctor.",
        "i want to book appointment",
        "book appointment",
        "book an appointment",
        "tell me self-care advice for my symptoms",
        "tell me more",
        "recommend a doctor",
        "check my symptoms",
        "check symptoms",
        "find a specialist doctor",
        "explain my medical report",
        "i'm not feeling well and would like help assessing my symptoms.",
        "i'd like to find a specialist doctor and book an appointment.",
        "[start_find_doctor]",
        "yes, i have more symptoms",
        "no other symptoms",
        "not sure about other symptoms",
        "yes, schedule an appointment",
        "no, not right now",
        "in-person consultation",
        "video consultation",
        "choose another doctor for report review",
    }
)

_SYMPTOM_EXTRACT_PROMPT = """You extract medical symptoms from a patient chat message for a healthcare assistant.

Return ONLY valid JSON:
{{
  "symptoms": ["short normalized symptom labels"]
}}

Rules:
- Extract ONLY symptoms, complaints, or health problems the patient describes about themselves
- Support ANY medical symptom worldwide — do not limit to a preset list
- Use clear clinical labels (e.g. "Stomach ulcer", "Lower back pain", "Fever", "Photophobia")
- Correct obvious typos (e.g. "alcer" → "Ulcer")
- Return an empty array if the message is a greeting, booking request, report upload, yes/no, email, OTP, or not about personal health
- Do not invent symptoms the patient did not mention
- Keep each label under 8 words
- Do not duplicate items already in PRIOR SYMPTOMS
- Do not add generic parent terms when a specific symptom is already listed (e.g. use "Leg pain" only, not also "Pain")

PRIOR SYMPTOMS: {prior}
PATIENT MESSAGE: {message}
"""

_SYMPTOM_HISTORY_PROMPT = """You extract all distinct medical symptoms a patient described across their chat messages.

Return ONLY valid JSON:
{{
  "symptoms": ["short normalized symptom labels"]
}}

Rules:
- Include every personal health complaint mentioned across the messages
- Support ANY medical symptom — no preset list
- Use clear clinical labels; correct obvious typos
- Exclude greetings, booking intents, and non-health messages
- Do not invent symptoms
- Keep each label under 8 words
- Do not add generic parent terms when a specific symptom is already listed (e.g. "Leg pain" only, not also "Pain")

PATIENT MESSAGES:
{messages}
"""


def _title_case_phrase(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in text.split())


def _clean_symptom_phrase(phrase: str) -> str:
    cleaned = phrase.strip().rstrip(".!?,")
    cleaned = re.sub(
        r"\s+(for|since|over|about|around)\s+(?:the\s+)?(?:last\s+)?\d+.*$",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+(and|but|with)\s+.+$", "", cleaned, flags=re.I)
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rsplit(" ", 1)[0]
    return _title_case_phrase(cleaned)


def _normalize_llm_symptoms(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        label = _clean_symptom_phrase(item)
        if label and not is_non_symptom_message(label):
            labels.append(label)
    return labels


def filter_vague_symptom_labels(labels: list[str] | None) -> list[str]:
    """Drop wellness words mistaken for symptoms (e.g. 'Well' from 'not feeling well')."""
    if not labels:
        return []
    return [label for label in labels if label.lower().strip() not in _VAGUE_SYMPTOM_LABELS]


def is_vague_wellness_complaint(text: str) -> bool:
    """True for general unwellness with no named symptom — should prompt for specifics."""
    trimmed = text.strip()
    if not trimmed:
        return False
    tl = trimmed.lower()
    if tl in _VAGUE_WELLNESS_EXACT:
        return True
    return bool(_VAGUE_WELLNESS_RE.match(tl))


def is_positive_wellness_update(text: str) -> bool:
    """True for recovery/wellbeing updates that should not start symptom triage."""
    return bool(_POSITIVE_WELLNESS_RE.match(text.strip()))


def is_non_symptom_message(text: str) -> bool:
    """Filter greetings, booking intents, auth fields, and triage UI replies."""
    from app.healthcare_policy import is_thanks_message

    trimmed = text.strip()
    if not trimmed:
        return True
    lower = trimmed.lower()
    if is_thanks_message(trimmed):
        return True
    if is_positive_wellness_update(trimmed):
        return True
    if lower in _SKIP_EXACT:
        return True
    if _INTERNAL_ACTION_TOKEN_RE.match(trimmed):
        return True
    if _GREETING_RE.match(trimmed):
        return True
    if _QUICK_ACTION_RE.match(trimmed):
        return True
    if _TRIAGE_META_RE.match(trimmed):
        return True
    if _REPORT_OR_ACTION_RE.search(trimmed):
        return True
    if _EMAIL_RE.match(trimmed):
        return True
    if _OTP_RE.match(trimmed):
        return True
    if _APT_ID_RE.match(trimmed):
        return True
    if len(trimmed) > 120:
        return True
    return False


def _collapse_redundant_symptoms(labels: list[str]) -> list[str]:
    """Drop generic labels like 'Pain' when 'Leg Pain' is already present."""
    if len(labels) <= 1:
        return labels

    normalized = [label.lower().strip() for label in labels]
    kept: list[str] = []
    for index, label in enumerate(labels):
        key = normalized[index]
        if key in _GENERIC_STANDALONE_SYMPTOMS and any(
            other_index != index and re.search(rf"\b{re.escape(key)}\b", normalized[other_index])
            for other_index in range(len(labels))
        ):
            continue
        kept.append(label)
    return kept


def merge_symptom_lists(prior: list[str] | None, new_items: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*(prior or []), *new_items]:
        label = _clean_symptom_phrase(item)
        if not label or is_non_symptom_message(label):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(label)
    return _collapse_redundant_symptoms(merged)


def filter_symptom_labels(labels: list[str] | None) -> list[str]:
    """Drop booking/UI action phrases mistakenly stored as symptoms."""
    if not labels:
        return []
    cleaned = [
        label
        for label in labels
        if isinstance(label, str) and label.strip() and not is_non_symptom_message(label.strip())
    ]
    return _collapse_redundant_symptoms(cleaned)

def looks_like_health_complaint(text: str) -> bool:
    if is_non_symptom_message(text):
        return False
    if is_vague_wellness_complaint(text):
        return True

    symptoms = extract_symptoms_offline(text)

    return len(symptoms) > 0


def _split_complaint_phrases(phrase: str) -> list[str]:
    """Split compound complaints like 'fever and cold' into separate symptoms."""
    parts = re.split(r"\s+and\s+", phrase.strip(), flags=re.I)
    labels: list[str] = []
    for part in parts:
        cleaned = _clean_symptom_phrase(part)
        if cleaned and not is_non_symptom_message(cleaned):
            labels.append(cleaned)
    return labels


def extract_symptoms_offline(text: str, prior: list[str] | None = None) -> list[str]:
    """Minimal fallback when the LLM is unavailable — no symptom keyword catalog."""
    if is_non_symptom_message(text) or is_vague_wellness_complaint(text):
        return list(prior or [])

    for pattern in (_AND_HAD_RE, _HAVE_COMPLAINT_RE):
        match = pattern.search(text)
        if not match:
            continue
        labels = filter_vague_symptom_labels(_split_complaint_phrases(match.group(1)))
        if labels:
            return merge_symptom_lists(prior, labels)

    words = text.strip().split()
    if 1 <= len(words) <= 4 and not re.search(r"\d", text):
        phrase = _clean_symptom_phrase(text)
        if phrase and not is_non_symptom_message(phrase):
            labels = filter_vague_symptom_labels([phrase])
            if labels:
                return merge_symptom_lists(prior, labels)

    return list(prior or [])


async def _llm_extract_symptoms(text: str, prior: list[str] | None = None) -> list[str] | None:
    llm = _llm_client()
    if not llm.available:
        return None
    prior_json = json.dumps(prior or [])
    prompt = _SYMPTOM_EXTRACT_PROMPT.format(prior=prior_json, message=text.strip())
    try:
        result = await llm.json_prompt(prompt)
    except Exception as exc:
        logger.warning("LLM symptom extraction failed: %s", exc)
        return None
    if not result:
        return None
    labels = _normalize_llm_symptoms(result.get("symptoms"))
    return merge_symptom_lists(prior, labels)


async def _llm_extract_symptoms_from_history(user_messages: list[str]) -> list[str] | None:
    llm = _llm_client()
    if not llm.available or not user_messages:
        return None
    block = "\n".join(f"- {msg}" for msg in user_messages[-12:])
    prompt = _SYMPTOM_HISTORY_PROMPT.format(messages=block)
    try:
        result = await llm.json_prompt(prompt)
    except Exception as exc:
        logger.warning("LLM history symptom extraction failed: %s", exc)
        return None
    if not result:
        return None
    return _normalize_llm_symptoms(result.get("symptoms"))


async def extract_symptoms_from_message(text: str, prior: list[str] | None = None) -> list[str]:
    """Extract symptoms from one message using the LLM, with offline fallback."""
    if is_non_symptom_message(text):
        return list(prior or [])

    llm_result = await _llm_extract_symptoms(text, prior)
    if llm_result is not None:
        return llm_result
    return extract_symptoms_offline(text, prior)


async def extract_symptoms_from_history(messages: list[dict]) -> list[str]:
    """Rebuild detected symptoms from conversation user messages."""
    user_messages: list[str] = []
    for msg in messages:
        if str(msg.get("role", "")).lower() != "user":
            continue
        content = (msg.get("content") or "").strip()
        if content and not is_non_symptom_message(content):
            user_messages.append(content)

    if not user_messages:
        return []

    llm_result = await _llm_extract_symptoms_from_history(user_messages)
    if llm_result:
        return llm_result

    symptoms: list[str] = []
    for content in user_messages:
        symptoms = extract_symptoms_offline(content, symptoms)
    return symptoms


_MID_TRIAGE_AWAITING = frozenset({
    "pick_symptom",
    "pick_duration",
    "pick_severity",
    "more_symptoms",
    "list_more_symptoms",
    "urgent_consult",
    "free_text_symptoms",
    "symptom_image",
    "cardiac_emergency_screen",
})


async def update_session_symptoms(session: dict, text: str) -> list[str]:
    """Merge newly detected symptoms into session state."""
    if is_non_symptom_message(text):
        return list(session.get("detected_symptoms") or [])

    triage = session.get("triage_collected")
    awaiting = session.get("awaiting")
    mid_triage = awaiting in _MID_TRIAGE_AWAITING

    if looks_like_health_complaint(text) and not mid_triage:
        merged = await extract_symptoms_from_message(text, None)
        session["detected_symptoms"] = merged
        session["triage_collected"] = {
            "notes": [text.strip()] if text.strip() else [],
            "symptoms": merged,
            "questions_asked": ["symptoms"],
        }
        session.pop("awaiting", None)
        session.pop("assessment_shown", None)
        session.pop("triage_assessed", None)
        session.pop("booking_declined", None)
        session["care_goal"] = "symptom_assessment"
        session["active_specialist"] = "triage_agent"
        return merged

    prior = list(session.get("detected_symptoms") or [])
    if isinstance(triage, dict) and triage.get("symptoms"):
        prior = merge_symptom_lists(prior, list(triage["symptoms"]))

    merged = await extract_symptoms_from_message(text, prior)
    merged = filter_symptom_labels(merged)
    session["detected_symptoms"] = merged
    if isinstance(triage, dict):
        triage["symptoms"] = merged
        notes = list(triage.get("notes") or [])
        if text.strip() and not is_non_symptom_message(text):
            if not notes or notes[-1] != text.strip():
                notes.append(text.strip())
            triage["notes"] = notes[-8:]
        session["triage_collected"] = triage
    return merged


async def resolve_detected_symptoms(session: dict, messages: list[dict]) -> list[str]:
    """Prefer live session symptoms; fall back to LLM scan of message history."""
    from_session = session.get("detected_symptoms")
    if isinstance(from_session, list) and from_session:
        return filter_symptom_labels(from_session)
    triage = session.get("triage_collected")
    if isinstance(triage, dict) and triage.get("symptoms"):
        return filter_symptom_labels(list(triage["symptoms"]))
    return filter_symptom_labels(await extract_symptoms_from_history(messages))
