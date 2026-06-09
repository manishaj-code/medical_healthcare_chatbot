import json
import re
from typing import Any

from app.database import get_settings
from app.healthcare_policy import OFF_TOPIC_REPLY, is_off_topic_fallback

settings = get_settings()

EMERGENCY_PATTERNS = [
    r"chest pain",
    r"heart attack",
    r"can'?t breathe",
    r"difficulty breathing",
    r"stroke",
    r"unconscious",
    r"suicid",
    r"self.?harm",
    r"severe bleeding",
    r"seizure",
]

PRESCRIPTION_PATTERNS = [
    r"prescribe",
    r"what (medicine|drug|antibiotic|dosage)",
    r"how much should i take",
]


class LLMClient:
    """Gemini client with rule-based fallback when API key missing."""

    def __init__(self) -> None:
        self._model = None
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel(settings.gemini_model)
            except Exception:
                self._model = None

    async def generate(self, system: str, user: str, history: list[dict] | None = None) -> str:
        prompt = f"{system}\n\n"
        if history:
            for h in history[-6:]:
                prompt += f"{h['role']}: {h['content']}\n"
        prompt += f"user: {user}\nassistant:"
        if self._model:
            try:
                response = self._model.generate_content(prompt)
                return response.text or self._fallback(system, user, history)
            except Exception:
                return self._fallback(system, user, history)
        return self._fallback(system, user, history)

    def _fallback(self, system: str, user: str, history: list[dict] | None) -> str:
        contextual = get_contextual_reply(user, history)
        if contextual:
            return contextual

        text = user.lower()
        if is_off_topic_fallback(user):
            return OFF_TOPIC_REPLY
        if any(re.search(p, text) for p in EMERGENCY_PATTERNS):
            return (
                "Your symptoms may require urgent medical attention. Please contact emergency "
                "services or seek immediate care at the nearest emergency department."
            )
        if any(re.search(p, text) for p in PRESCRIPTION_PATTERNS):
            return (
                "I cannot prescribe medications or recommend specific dosages. "
                "Please consult a licensed healthcare professional for treatment decisions."
            )
        if "fever" in text or "cough" in text:
            return "How long have you had these symptoms?"
        if "book" in text or "appointment" in text or text.strip() in {"yes", "yeah", "sure"}:
            return (
                "I can help you book an appointment. Please tell me your preferred doctor "
                "specialty or say 'recommended doctors' to see available options."
            )
        if "hemoglobin" in text or "report" in text or "cbc" in text:
            return (
                "I'd be happy to help explain your lab results. Values outside the reference "
                "range should be discussed with your physician. I can provide general education "
                "but cannot diagnose or prescribe treatment."
            )
        if "hello" in text or "hi" in text:
            return (
                "Hello! I'm your AI Healthcare Assistant. How can I help you today? "
                "You can describe symptoms, ask health questions, upload reports, or book appointments."
            )
        return (
            "I understand your concern. Could you tell me more about your symptoms or "
            "what you'd like help with today?"
        )


def detect_emergency(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in EMERGENCY_PATTERNS)


def detect_prescription_request(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in PRESCRIPTION_PATTERNS)


DURATION_PATTERN = re.compile(
    r"\d+\s*(day|days|week|weeks|hour|hours|month|months)|from\s+\d+|about\s+\d+|few\s+days|couple\s+of\s+days"
)
DURATION_UNIT_ONLY = re.compile(r"^(day|days|week|weeks|hour|hours|month|months)$")

CONDITION_ALIASES: dict[str, str] = {
    "diabetes": "diabetes",
    "diabete": "diabetes",
    "diabetis": "diabetes",
    "sugar": "diabetes",
    "asthma": "asthma",
    "astma": "asthma",
    "astama": "asthma",
    "asthama": "asthma",
    "hypertension": "hypertension",
    "high bp": "hypertension",
    "high blood pressure": "hypertension",
    "blood pressure": "hypertension",
    "bp": "hypertension",
}


def _last_assistant_message(history: list[dict] | None) -> str:
    if not history:
        return ""
    for h in reversed(history):
        role = h.get("role", "")
        if str(role) == "assistant":
            return h.get("content", "").lower()
    return ""


def _last_user_message(history: list[dict] | None, skip_last: bool = False) -> str:
    if not history:
        return ""
    user_msgs = [h for h in history if str(h.get("role")) == "user"]
    if skip_last and user_msgs:
        user_msgs = user_msgs[:-1]
    return user_msgs[-1].get("content", "").strip() if user_msgs else ""


def _has_duration(text: str) -> bool:
    t = text.lower().strip()
    if DURATION_PATTERN.search(t):
        return True
    return bool(re.search(r"\b(days?|weeks?|hours?|months?)\b", t))


def _parse_condition(text: str) -> str | None:
    t = text.lower().strip()
    for alias, canonical in CONDITION_ALIASES.items():
        if alias in t or t == alias:
            return canonical
    return None


def _pending_duration_number(history: list[dict] | None) -> str | None:
    """Bare number user gave before unit clarification (e.g. user said '2' then 'days')."""
    if not history:
        return None
    units = {"day", "days", "hour", "hours", "week", "weeks", "month", "months"}
    user_msgs = [h.get("content", "").strip() for h in history if str(h.get("role")) == "user"]
    for content in reversed(user_msgs):
        if re.fullmatch(r"\d+", content):
            return content
        if content.lower() in units:
            continue
        break
    return None


def _extract_symptoms_from_history(history: list[dict] | None) -> list[str]:
    found: list[str] = []
    if not history:
        return found
    keywords = ("fever", "cough", "headache", "pain", "nausea", "cold", "sore throat", "fatigue")
    for h in history:
        if str(h.get("role")) != "user":
            continue
        text = h.get("content", "").lower()
        for s in keywords:
            if s in text and s not in found:
                found.append(s)
    return found


def _home_care_advice(history: list[dict] | None) -> str:
    """General self-care tips when patient declines appointment and has no chronic conditions."""
    symptoms = _extract_symptoms_from_history(history)
    tips: list[str] = []

    if "fever" in symptoms:
        tips.extend([
            "Drink plenty of water and fluids to stay hydrated.",
            "Get adequate rest and sleep.",
            "You can use a lukewarm sponge bath to help bring down fever.",
            "Wear light clothing and keep the room comfortably cool.",
        ])
    if "cough" in symptoms:
        tips.extend([
            "Drink warm water, tea, or soup to soothe your throat.",
            "Avoid smoke, dust, and cold air.",
            "Honey with warm water may help ease a cough (not for children under 1 year).",
        ])
    if "headache" in symptoms:
        tips.extend([
            "Rest in a quiet, dark room.",
            "Drink water — dehydration can worsen headaches.",
            "Avoid screen time and loud noise for a while.",
        ])
    if "nausea" in symptoms:
        tips.extend([
            "Take small sips of water or oral rehydration fluids.",
            "Eat light, bland foods when you feel able (e.g. rice, toast, banana).",
            "Avoid greasy or spicy food until you feel better.",
        ])
    if "cold" in symptoms or "sore throat" in symptoms:
        tips.extend([
            "Gargle with warm salt water for a sore throat.",
            "Stay warm and drink warm fluids.",
            "Use a humidifier or breathe steam to ease congestion.",
        ])

    if not tips:
        tips = [
            "Drink plenty of water and stay well hydrated.",
            "Get enough rest and avoid overexertion.",
            "Eat light, nutritious meals when you feel hungry.",
            "Monitor your symptoms and note any changes.",
        ]

    # dedupe while preserving order
    seen: set[str] = set()
    unique_tips: list[str] = []
    for tip in tips:
        if tip not in seen:
            seen.add(tip)
            unique_tips.append(tip)

    body = "\n".join(f"• {tip}" for tip in unique_tips[:6])
    return (
        "Understood. Based on what you've shared, here are some self-care suggestions that may help:\n\n"
        f"{body}\n\n"
        "Please watch your symptoms over the next 1–2 days. If they worsen, last more than 3 days, "
        "or you develop breathing difficulty, high fever, or severe pain, please see a doctor promptly. "
        "I'm here anytime if you'd like to book an appointment."
    )


def _is_negative_reply(text: str) -> bool:
    return text in {"no", "nope", "not now", "later", "not really", "nah", "no thanks", "not yet"} or text.startswith("no ")


def _is_thanks_reply(text: str) -> bool:
    t = text.lower().strip()
    if t in {"thanks", "thank you", "thankyou", "thx", "ty", "ok thanks", "ok thank you", "okay thanks", "got it", "alright", "ok", "okay"}:
        return True
    return bool(re.search(r"\b(thank|thanks|thank you|thx)\b", t))


def _is_closure_message(last_bot: str) -> bool:
    return any(
        phrase in last_bot
        for phrase in (
            "self-care suggestions",
            "appointment booked successfully",
            "i'm here anytime if you'd like to book",
            "i can help book an appointment anytime",
            "please watch your symptoms",
        )
    )


def _symptoms_in_history(history: list[dict] | None) -> bool:
    if not history:
        return False
    symptoms = ("fever", "cough", "pain", "headache", "nausea", "symptom")
    return any(
        any(s in h.get("content", "").lower() for s in symptoms)
        for h in history
        if h.get("role") == "user"
    )


def get_contextual_reply(user: str, history: list[dict] | None) -> str | None:
    """Multi-turn triage follow-ups per doc1.txt conversation flow."""
    text = user.lower().strip()
    last_bot = _last_assistant_message(history)

    if last_bot and _is_closure_message(last_bot) and _is_thanks_reply(text):
        return (
            "You're welcome! Take care and get plenty of rest. "
            "If your symptoms change or you'd like to book a doctor visit, just let me know."
        )

    if last_bot and _is_closure_message(last_bot) and text in {"bye", "goodbye", "see you", "see ya"}:
        return (
            "Goodbye! Wishing you a speedy recovery. "
            "Come back anytime if you need health guidance or want to book an appointment."
        )

    if last_bot and "urgent care" in last_bot:
        if text in {"yes", "yeah", "sure", "ok", "okay", "please"}:
            return None  # orchestrator → show doctors in chat
        if _is_negative_reply(text):
            return (
                "Please monitor your symptoms closely. If breathing difficulty worsens, "
                "seek emergency care immediately. Rest, stay hydrated, and avoid strenuous activity. "
                "I can help book an appointment anytime if you change your mind."
            )

    if last_bot and ("book an appointment" in last_bot or "would you like to book" in last_bot):
        if text in {"yes", "yeah", "sure", "ok", "okay", "please"}:
            return None  # orchestrator → shows doctors in chat
        if _is_negative_reply(text):
            return _home_care_advice(history)

    # User gave unit only after we asked "2 days, 2 hours, or 2 months?"
    if last_bot and "just to confirm" in last_bot:
        if DURATION_UNIT_ONLY.match(text):
            num = _pending_duration_number(history)
            if num:
                return "Do you have any breathing difficulty or shortness of breath?"
            return f"How many {text} have you had these symptoms?"
        if _has_duration(text):
            return "Do you have any breathing difficulty or shortness of breath?"

    if last_bot and "how long" in last_bot and _has_duration(text):
        return "Do you have any breathing difficulty or shortness of breath?"

    # Bare number (e.g. "2") → ask days / hours / months
    if last_bot and "how long" in last_bot and re.fullmatch(r"\d+", text):
        return f"Just to confirm: is that {text} days, {text} hours, or {text} months?"

    # Match only the breathing question, not follow-up messages that mention breathing
    if last_bot and "do you have any breathing" in last_bot:
        if text in {"no", "nope", "not really", "none"} or text.startswith("no "):
            return "Do you have any existing conditions like diabetes, asthma, or hypertension?"
        if text in {"yes", "yeah", "yep"} or text.startswith("yes"):
            return (
                "Breathing difficulty can be serious. Please seek medical attention promptly. "
                "Would you like help finding urgent care?"
            )

    if last_bot and ("existing conditions" in last_bot or "diabetes, asthma" in last_bot):
        condition = _parse_condition(text)
        if condition:
            label = condition.replace("hypertension", "hypertension (high blood pressure)")
            return (
                f"Thank you for sharing that you have {label}. Based on your symptoms and medical "
                "history, a physician consultation is recommended within 24–48 hours. "
                "Would you like to book an appointment?"
            )
        if text in {"no", "nope", "none", "no conditions"} or text.startswith("no "):
            return (
                "Thank you for the information. A physician consultation may still be helpful "
                "for your symptoms. Would you like to book an appointment?"
            )
        return (
            "I didn't catch a specific condition. Do you have diabetes, asthma, hypertension, "
            "or any other chronic condition? You can say the name or reply 'no'."
        )

    if _symptoms_in_history(history) and _has_duration(text):
        return "Do you have any breathing difficulty or shortness of breath?"

    return None


def classify_intent(text: str, history: list[dict] | None = None) -> str:
    t = text.lower().strip()
    last_bot = _last_assistant_message(history)
    if detect_emergency(t):
        return "emergency"
    in_triage = _symptoms_in_history(history) or (
        last_bot and ("how long" in last_bot or "breathing" in last_bot or "existing conditions" in last_bot or "just to confirm" in last_bot)
    )
    if get_contextual_reply(text, history) or (
        in_triage
        and (_has_duration(t) or DURATION_UNIT_ONLY.match(t) or re.fullmatch(r"\d+", t) or t in {"no", "yes", "yeah"} or _parse_condition(t))
    ):
        return "triage"
    if any(w in t for w in ["fever", "pain", "cough", "symptom", "headache", "nausea"]):
        return "triage"
    if any(w in t for w in ["book", "appointment", "reschedule", "cancel", "slot", "doctor"]):
        return "appointment"
    if any(w in t for w in ["report", "hemoglobin", "lab", "cbc", "blood test"]):
        return "report"
    return "conversation"


from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationMemory, Message, Patient
from app.models.enums import MessageRole

SYSTEM_PROMPT = """You are MedAssist AI, a production-grade healthcare assistant.
SCOPE: Only medical, healthcare, wellness, and appointment topics.
If the question is NOT healthcare-related, respond EXACTLY:
"I am a healthcare assistant and can only help with medical and healthcare-related questions. Please ask a healthcare-related query."
- Never diagnose or prescribe medications.
- Never fabricate medical information; state limitations when unsure.
- Ask one follow-up question at a time.
- Be empathetic, context-aware, and professional.
- Recommend doctor consultation when appropriate.
- Escalate emergencies immediately."""


class ChatOrchestrator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.llm = LLMClient()

    async def process_message(
        self, conversation: Conversation, patient: Patient, user_message: str
    ) -> tuple[str, str, bool, dict | None]:
        history = await self._get_history(conversation.id)
        memory = await self._get_memory(patient.id)

        # Dynamic agentic assistant — live patient/doctor data, LLM + tool orchestration
        from app.agent_flows import process_agent_flow

        agentic = await process_agent_flow(self.db, conversation, patient, user_message, history)
        if agentic:
            return agentic

        # Deep fallback if dynamic agent returns nothing
        context = SYSTEM_PROMPT
        if memory:
            context += f"\nPatient memory: {memory}"
        reply = await self.llm.generate(context, user_message, history)
        return reply, "conversation", False, None

    async def _get_history(self, conversation_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        )
        return [
            {"role": m.role.value if hasattr(m.role, "value") else str(m.role), "content": m.content}
            for m in result.scalars().all()
        ]

    async def _get_memory(self, patient_id: UUID) -> str:
        result = await self.db.execute(
            select(ConversationMemory).where(ConversationMemory.patient_id == patient_id).limit(10)
        )
        facts = [m.fact for m in result.scalars().all()]
        return "; ".join(facts) if facts else ""
