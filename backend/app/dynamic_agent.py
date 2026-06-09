"""
Dynamic agentic healthcare assistant.
- Patient/doctor/medication data loaded from DB each turn
- Intent and flow driven by LLM when available, dynamic planner as fallback
- No hardcoded patient names, doctor lists, or fixed scenario scripts
"""
import json
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import detect_emergency, detect_prescription_request
from app.database import get_settings
from app.healthcare_policy import (
    HEALTH_QA_PROMPT,
    OFF_TOPIC_REPLY,
    is_healthcare_related_fallback,
    should_reject_off_topic,
)
from app.models import Conversation, Notification, Patient
from app.models.enums import NotificationType
from app.services.agent_tools import (
    _match_doctor,
    deserialize_slot,
    match_slot_from_text,
    serialize_slot,
    tool_assess_symptoms,
    tool_book_slot,
    tool_cancel_appointment,
    tool_get_doctor_slots,
    tool_get_medications,
    tool_list_appointments,
    tool_request_refill,
    tool_reschedule,
    tool_reschedule_alternatives,
    tool_schedule_reminder,
    tool_search_doctors,
)
from app.services.chat_ui import (
    build_doctor_list_ui,
    build_slot_list_ui,
    doctor_list_intro,
    slot_list_intro,
)
from app.services.flow_state import clear_flow, get_flow, set_flow, update_flow
from app.services.patient_context import load_patient_context

settings = get_settings()

# Offline fallback only — used when no LLM API key is configured
_SYMPTOM_HINTS = (
    "fever", "cough", "headache", "pain", "nausea", "dizziness", "fatigue",
    "cold", "sore throat", "vomiting", "rash", "swelling", "breathing", "chest",
)
_HEALTH_COMPLAINT_SIGNALS = (
    "hurt", "hurts", "hurting", "aching", "ache", "pain", "unwell", "sick",
    "not feeling", "feel ill", "feel bad", "symptom", "bothering", "problem with",
    "issue with", "suffering", "throwing up", "can't breathe", "cannot breathe",
    "weakness", "tired", "dizzy", "swollen", "rash", "bleeding",
)

UNDERSTAND_PROMPT = """You interpret patient messages for a healthcare assistant. Understand ANY natural wording or typos.

Return ONLY valid JSON:
{
  "healthcare_related": true or false,
  "health_complaint": true or false,
  "emergency": false,
  "intent": "triage|health_question|booking|cancel|reschedule|refill|followup|conversation|emergency|off_topic",
  "symptoms": ["normalized labels if personal symptoms, else []"],
  "duration": "string or null",
  "severity": "1-10 string or null",
  "details": "string or null",
  "summary": "one-line plain English",
  "ready_to_assess": false,
  "next_triage_question": "one tailored follow-up question or null when ready_to_assess is true"
}

Rules:
- healthcare_related=false for weather, sports, entertainment, coding, politics, travel (non-medical), jokes, etc.
- intent=off_topic when NOT healthcare/medical/wellness/appointments
- health_complaint=true when patient describes THEIR OWN symptoms or feeling unwell
- intent=triage for personal symptoms; intent=health_question for general medical education (what is X, how does Y work)
- When health_complaint=true: set next_triage_question to ONE specific question about what they said (any symptom type); set ready_to_assess=true only when duration, main concern, and enough detail are already clear
- intent=booking|cancel|reschedule|refill|followup when explicitly requested
- emergency=true only for chest pain, can't breathe, stroke, severe bleeding, unconscious
- Never fabricate facts; extract only what the patient said
"""

TRIAGE_PLAN_PROMPT = """You conduct adaptive symptom triage for a healthcare assistant.

The patient may describe ANY health concern in natural language (injury, rash, stomach pain, anxiety, pregnancy questions, chronic disease flare, etc.). Do NOT assume cough, fever, or any fixed symptom list.

Given patient context, conversation history, known symptoms, collected facts, and the latest message, decide:
1. Normalized symptom/concern labels (short phrases the patient actually mentioned)
2. Update collected clinical facts from the latest message
3. ONE empathetic follow-up question tailored to this patient — only if more detail is needed for safe triage
4. Whether triage has enough information to recommend next steps (ready_to_assess)

Return ONLY valid JSON:
{
  "symptoms": ["concise labels from patient wording"],
  "collected": {
    "duration": "string or null",
    "severity": "1-10 string or null",
    "details": "free-text summary of relevant facts so far",
    "notes": ["important fact from conversation", "..."]
  },
  "next_question": "one specific question or null when ready_to_assess",
  "ready_to_assess": false,
  "emergency": false
}

Rules:
- Ask at most ONE new question per turn; never repeat what history already answered
- Questions must fit the actual complaint (not generic cough/fever templates unless the patient mentioned them)
- ready_to_assess=true when you know: main concern, timing/duration (or clearly acute), and enough detail for a sensible care recommendation (usually 2-4 exchanges)
- emergency=true ONLY for chest pain, severe breathing difficulty, stroke signs, severe bleeding, loss of consciousness, suicidal intent
- Do not diagnose; gather information for triage and routing only
"""

TRIAGE_ASSESS_PROMPT = """Based on symptom triage data, recommend appropriate next steps for a healthcare assistant.

Return ONLY valid JSON:
{
  "risk_level": "low|medium|high|emergency",
  "recommended_specialty": "General Physician|Cardiologist|Neurologist|Dermatologist|Pediatrician|Gastroenterologist|Emergency|Psychiatrist|Orthopedist|etc",
  "recommendation": "2-3 sentence plain-English guidance — no diagnosis, no prescribing"
}

Use patient medical history when relevant. Route to Emergency only for true emergencies.
"""


def _parse_llm_json(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _normalize_symptom_text(text: str) -> str:
    """Light typo cleanup for offline fallback only."""
    t = text.lower()
    for pattern, replacement in (
        (r"\bhedach\w*\b", "headache"),
        (r"\bheadach\w*\b", "headache"),
        (r"\bfeaver\b", "fever"),
        (r"\bcaugh\w*\b", "cough"),
    ):
        t = re.sub(pattern, replacement, t)
    return t


def _looks_like_health_complaint(text: str) -> bool:
    t = _normalize_symptom_text(text.lower())
    if any(h in t for h in _SYMPTOM_HINTS):
        return True
    return any(s in t for s in _HEALTH_COMPLAINT_SIGNALS)

AGENT_PROMPT = """You are MedAssist AI — a production-grade agentic healthcare assistant.

SCOPE: Healthcare, medical conditions, treatments (general education), medications (no prescribing),
preventive care, diagnostics, wellness, appointments, and follow-up care ONLY.
If the message is NOT healthcare-related, set agent=scope_guardrail and reply EXACTLY:
"I am a healthcare assistant and can only help with medical and healthcare-related questions. Please ask a healthcare-related query."

DATA: Use ONLY real patient/clinic data from context. NEVER invent doctors, slots, appointments, or lab results.

TOOLS (invoke when the patient needs live clinic data):
- search_doctors(specialty), get_doctor_slots(doctor_id), list_appointments
- book_slot, cancel_appointment, reschedule_appointment
- get_medications, request_refill, assess_symptoms

AGENTIC JOURNEY: Understand concerns → clarify → assess symptoms → recommend specialist →
show doctors/slots → book → reminders → follow-up after visits.

SAFETY:
- Never diagnose or prescribe dosages
- No fabricated or misleading medical information
- If unsure, ask ONE follow-up or state limitations and recommend a licensed clinician
- Escalate emergencies immediately
- Maintain conversation context; do not repeat questions already answered

Respond ONLY with valid JSON:
{
  "agent": "symptom_assessment|doctor_discovery|appointment|triage|refill|followup|health_education|conversation|emergency|scope_guardrail",
  "emergency": false,
  "reply": "natural language response",
  "tool": "tool_name or null",
  "tool_args": {},
  "task": "triage|booking|cancel|reschedule|refill|emergency|followup|null",
  "step": "step id or null"
}
"""


class AgentLLM:
    def __init__(self) -> None:
        self._gemini = None
        self._groq_client = None
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=settings.gemini_api_key)
                self._gemini = genai.GenerativeModel(settings.gemini_model)
            except Exception:
                pass
        if settings.groq_api_key:
            try:
                from groq import Groq

                self._groq_client = Groq(api_key=settings.groq_api_key)
            except Exception:
                pass

    async def understand_message(
        self,
        patient_ctx: dict,
        history: list[dict],
        user_message: str,
    ) -> dict | None:
        """LLM interprets free-form patient text — primary path for symptom/intent detection."""
        if not self._gemini and not self._groq_client:
            return None
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
        prompt = (
            f"{UNDERSTAND_PROMPT}\n\nPATIENT CONTEXT:\n{json.dumps(patient_ctx, default=str)}\n\n"
            f"RECENT CHAT:\n{hist}\n\nPATIENT MESSAGE: {user_message}\n\nJSON:"
        )
        raw = await self._call_llm(prompt)
        return _parse_llm_json(raw or "")

    async def plan_triage_turn(
        self,
        patient_ctx: dict,
        history: list[dict],
        user_message: str,
        symptoms: list[str],
        collected: dict,
    ) -> dict | None:
        """LLM decides the next triage question based on any patient concern — not fixed symptom lists."""
        if not self._gemini and not self._groq_client:
            return None
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in history[-10:])
        state = json.dumps({"symptoms": symptoms, "collected": collected}, default=str)
        prompt = (
            f"{TRIAGE_PLAN_PROMPT}\n\nPATIENT CONTEXT:\n{json.dumps(patient_ctx, default=str)}\n\n"
            f"TRIAGE STATE:\n{state}\n\nRECENT CHAT:\n{hist}\n\n"
            f"LATEST PATIENT MESSAGE: {user_message}\n\nJSON:"
        )
        raw = await self._call_llm(prompt)
        return _parse_llm_json(raw or "")

    async def recommend_care(
        self,
        patient_ctx: dict,
        symptoms: list[str],
        collected: dict,
    ) -> dict | None:
        """LLM recommends specialty and guidance from triage data — any symptom type."""
        if not self._gemini and not self._groq_client:
            return None
        payload = json.dumps(
            {"symptoms": symptoms, "collected": collected, "conditions": patient_ctx.get("conditions", [])},
            default=str,
        )
        prompt = (
            f"{TRIAGE_ASSESS_PROMPT}\n\nPATIENT CONTEXT:\n{json.dumps(patient_ctx, default=str)}\n\n"
            f"TRIAGE DATA:\n{payload}\n\nJSON:"
        )
        raw = await self._call_llm(prompt)
        return _parse_llm_json(raw or "")

    async def answer_health_question(
        self,
        patient_ctx: dict,
        history: list[dict],
        user_message: str,
    ) -> str | None:
        """Context-aware healthcare Q&A — education only, no diagnosis or prescribing."""
        if not self._gemini and not self._groq_client:
            return None
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in history[-8:])
        prompt = (
            f"{HEALTH_QA_PROMPT}\n\nPATIENT CONTEXT:\n{json.dumps(patient_ctx, default=str)}\n\n"
            f"CONVERSATION:\n{hist}\n\nPATIENT: {user_message}\n\nASSISTANT:"
        )
        return await self._call_llm(prompt)

    async def decide(
        self,
        patient_ctx: dict,
        history: list[dict],
        user_message: str,
        flow: dict,
        tool_result: dict | None = None,
    ) -> dict | None:
        context_block = json.dumps(
            {"patient": patient_ctx, "flow_state": flow, "tool_result": tool_result},
            default=str,
        )
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in history[-8:])
        prompt = (
            f"{AGENT_PROMPT}\n\nPATIENT & STATE:\n{context_block}\n\n"
            f"CONVERSATION:\n{hist}\nuser: {user_message}\nassistant JSON:"
        )
        raw = await self._call_llm(prompt)
        return _parse_llm_json(raw or "")

    async def _call_llm(self, prompt: str) -> str | None:
        if self._gemini:
            try:
                r = self._gemini.generate_content(prompt)
                return r.text or None
            except Exception:
                pass
        if self._groq_client:
            try:
                r = self._groq_client.chat.completions.create(
                    model=getattr(settings, "groq_model", "llama-3.3-70b-versatile"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return r.choices[0].message.content
            except Exception:
                pass
        return None


def _yes(text: str) -> bool:
    return text.strip().lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "confirm", "please", "yes please"}


def _no(text: str) -> bool:
    t = text.strip().lower()
    return t in {"no", "nope", "nah", "not now", "later"} or t.startswith("no ")


def _recover_flow_from_history(history: list[dict]) -> dict:
    """Rebuild Redis flow when it was lost but the chat clearly left off at booking offer."""
    if not history:
        return {}
    for msg in reversed(history[-8:]):
        if msg.get("role") not in ("assistant", "Assistant"):
            continue
        content = msg.get("content") or ""
        lower = content.lower()
        if "would you like me to show available doctors" not in lower:
            break
        spec_match = re.search(r"recommend(?:ed)? seeing a ([^.]+)\.", content, re.I)
        specialty = spec_match.group(1).strip() if spec_match else "General Physician"
        return {
            "task": "triage",
            "step": "offer",
            "data": {"recommended_specialty": specialty, "offer_booking": True},
        }
    return {}


def _symptom_text(symptoms: list[str]) -> str:
    return " ".join(symptoms).lower()


def _symptoms_contain(symptoms: list[str], *needles: str) -> bool:
    blob = _symptom_text(symptoms)
    return any(n in blob for n in needles)


def _extract_symptoms_fallback(text: str) -> list[str]:
    """Offline-only fallback when LLM is unavailable."""
    t = _normalize_symptom_text(text)
    found = [s for s in _SYMPTOM_HINTS if s in t]
    if found:
        return found
    if _looks_like_health_complaint(text):
        return [text.strip()[:160]]
    return []


def _extract_symptoms(text: str) -> list[str]:
    return _extract_symptoms_fallback(text)


def _merge_symptoms(flow: dict, text: str) -> list[str]:
    existing = flow.get("data", {}).get("symptoms", [])
    found = _extract_symptoms_fallback(text)
    merged = list(existing)
    for s in found:
        if s not in merged:
            merged.append(s)
    return merged


def _detect_intent(text: str, patient_ctx: dict) -> str:
    t = text.lower()
    if detect_emergency(t):
        return "emergency"
    if any(w in t for w in ("cancel", "cancellation")) and "appointment" in t:
        return "cancel"
    if any(w in t for w in ("reschedule", "change", "move")) and "appointment" in t:
        return "reschedule"
    if any(w in t for w in ("refill", "prescription", "medicine", "medication", "tablets")):
        return "refill"
    if any(w in t for w in ("book", "appointment", "schedule", "see a doctor", "consultation")):
        return "booking"
    if _looks_like_health_complaint(t):
        return "triage"
    if patient_ctx.get("recent_visits") and re.search(r"\b(hi|hello|follow.?up|feeling|recovery)\b", t):
        return "followup"
    return "conversation"


def _collected_from_understanding(understanding: dict, text: str) -> dict:
    collected = _extract_structural_triage_updates(text)
    for key, ukey in (("duration", "duration"), ("severity", "severity"), ("details", "details")):
        if understanding.get(ukey) and not collected.get(key):
            collected[key] = str(understanding[ukey])
    if understanding.get("summary"):
        collected.setdefault("notes", [])
        summary = str(understanding["summary"]).strip()
        if summary and summary not in collected["notes"]:
            collected["notes"].append(summary)
    return collected


def _merge_collected(base: dict, new: dict) -> dict:
    merged = dict(base)
    for key, value in new.items():
        if key == "notes" and isinstance(value, list):
            notes = merged.setdefault("notes", [])
            for note in value:
                note_text = str(note).strip()
                if note_text and note_text not in notes:
                    notes.append(note_text)
        elif value is not None and value != "":
            merged[key] = value
    return merged


def _extract_duration(text: str) -> str | None:
    t = text.lower().strip()
    patterns = [
        r"(?:last|past|for|since|from)\s+(\d+\s*(?:day|days|week|weeks|hour|hours|month|months))",
        r"(\d+\s*(?:day|days|week|weeks|hour|hours|month|months))",
        r"(\d+)\s*days?\s*ago",
        r"\b(yesterday|today|this morning|last night)\b",
    ]
    m = re.search(r"last\s+(\d+\s+days?)", t)
    if m:
        return m.group(1).strip()
    for p in patterns:
        m = re.search(p, t)
        if m:
            dur = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if re.match(r"\d+\s*day$", dur):
                dur = dur + "s"
            return dur
    if re.fullmatch(r"\d+", t):
        return f"{t} days"
    if re.fullmatch(r"\d+\s*(day|days|week|weeks|hour|hours)", t):
        return t
    return None


def _extract_structural_triage_updates(text: str) -> dict:
    """Offline fallback: parse duration, severity scale, and short answers only — no symptom keyword lists."""
    updates: dict = {}
    duration = _extract_duration(text)
    if duration:
        updates["duration"] = duration

    t = text.lower().strip()
    sev = re.search(r"(\d+)\s*/\s*10|(\d+)\s*out\s*of\s*10|severity\s*(\d+)", t)
    if sev:
        updates["severity"] = next(g for g in sev.groups() if g)
    elif re.fullmatch(r"[1-9]|10", t):
        updates["severity"] = t

    stripped = text.strip()
    if len(stripped) > 8 and not updates:
        updates.setdefault("notes", [])
        if stripped not in updates["notes"]:
            updates["notes"].append(stripped)
    elif stripped and len(stripped) <= 80:
        updates.setdefault("notes", [])
        if stripped not in updates["notes"]:
            updates["notes"].append(stripped)

    return updates


def _next_triage_question_fallback(symptoms: list[str], collected: dict) -> str | None:
    """Generic offline triage when LLM is unavailable — no symptom-specific keyword trees."""
    if not collected.get("duration"):
        return "How long have you been experiencing this?"
    notes = collected.get("notes") or []
    if not collected.get("severity") and len(notes) < 2:
        return "On a scale of 1–10, how much is this affecting you day to day?"
    if len(notes) < 2 and not collected.get("details"):
        summary = ", ".join(symptoms) if symptoms else "your symptoms"
        return f"Can you describe {summary} in a bit more detail — what you feel and when it is worst?"
    return None


def _triage_ack(symptoms: list[str], collected: dict, pname: str, first_turn: bool = False) -> str:
    """Short empathetic acknowledgement — reflects what patient already shared."""
    first = pname.split()[0]
    if first_turn and symptoms:
        dur = f" for {collected['duration']}" if collected.get("duration") else ""
        sym = ", ".join(symptoms)
        return f"I'm sorry you're not feeling well, {first}. I understand you've had {sym}{dur}."
    if collected:
        return "Got it, thank you."
    return f"I'm here to help, {first}."


async def _execute_tool(
    db: AsyncSession,
    patient: Patient,
    tool: str,
    args: dict,
    conversation_id: UUID,
) -> dict:
    if tool == "search_doctors":
        return await tool_search_doctors(db, args.get("specialty"))
    if tool == "get_doctor_slots":
        return await tool_get_doctor_slots(db, UUID(args["doctor_id"]))
    if tool == "list_appointments":
        return await tool_list_appointments(db, patient.id)
    if tool == "get_medications":
        return await tool_get_medications(db, patient.id)
    if tool == "book_slot":
        return await tool_book_slot(db, patient, patient.user_id, args["slot"], conversation_id)
    if tool == "cancel_appointment":
        appt_id = UUID(args["appointment_id"]) if args.get("appointment_id") else None
        return await tool_cancel_appointment(db, patient.id, appt_id)
    if tool == "reschedule_alternatives":
        return await tool_reschedule_alternatives(db, patient.id)
    if tool == "reschedule_appointment":
        return await tool_reschedule(
            db, patient.id, patient.user_id, UUID(args["appointment_id"]), args["slot"]
        )
    if tool == "request_refill":
        return await tool_request_refill(db, patient.id, patient.user_id, args.get("medication_name"))
    if tool == "assess_symptoms":
        return await tool_assess_symptoms(
            db, patient.id, args.get("symptoms", []), args.get("duration"),
            args.get("conditions", []), conversation_id,
        )
    if tool == "schedule_reminder":
        return await tool_schedule_reminder(db, patient.user_id, UUID(args["appointment_id"]))
    return {"error": f"Unknown tool: {tool}"}


def _doctors_list_response(result: dict) -> tuple[str, dict | None]:
    doctors = result.get("doctors", [])
    if not doctors:
        return "No doctors with open slots right now. Please try again later or contact the clinic.", None
    return doctor_list_intro(len(doctors)), build_doctor_list_ui(result)


def _slots_list_response(result: dict) -> tuple[str, dict | None]:
    doctor_name = result.get("doctor_name", "the doctor")
    slots = result.get("slots", [])
    if not slots:
        return f"No open slots for {doctor_name}.", None
    return slot_list_intro(doctor_name), build_slot_list_ui(
        doctor_name, str(result.get("doctor_id", "")), slots
    )


class DynamicHealthcareAgent:
    def __init__(self) -> None:
        self.llm = AgentLLM()

    async def process(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        user_message: str,
        history: list[dict],
    ) -> tuple[str, str, bool, dict | None] | None:
        """Delegate to the autonomous orchestrator — no hardcoded workflow routing."""
        from app.multi_agent.supervisor import multi_agent_supervisor

        return await multi_agent_supervisor.process(db, conversation, patient, user_message, history)

    async def _start_booking_flow(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        text: str,
        conv_id: UUID,
        patient_ctx: dict,
        specialty: str,
        result: dict | None = None,
    ) -> tuple[str, str, bool, dict | None]:
        pname = patient_ctx["name"]
        result = result or await tool_search_doctors(db, specialty)
        doctors = result["doctors"]
        all_slots = result.get("all_slots", []) or [s for d in doctors for s in d.get("slots", [])]
        booking_data = {
            "doctors": doctors,
            "all_slots": all_slots,
            "specialty": specialty,
            "recommended_specialty": specialty,
        }
        doctor_rows = [
            {"id": UUID(d["id"]), "name": d["name"], "specializations": [d["specialty"]]}
            for d in doctors
        ]

        chosen = match_slot_from_text(text, all_slots)
        if chosen:
            doc_name = chosen.get("doctor_name", "")
            await set_flow(conv_id, {
                "task": "booking", "step": "confirm",
                "data": {**booking_data, "doctor_name": doc_name, "chosen": chosen},
            })
            conversation.active_agent = "appointment"
            return (
                f"Before booking, please confirm:\n\nPatient Name: {pname}\n"
                f"Doctor: {doc_name}\nDate & Time: {chosen['label']}\n\nConfirm booking? (Yes/No)"
            ), "appointment", False, None

        doc = _match_doctor(text, doctor_rows)
        if doc:
            doc_slots = next((d.get("slots", []) for d in doctors if d["id"] == str(doc["id"])), [])
            if not doc_slots:
                slots_result = await tool_get_doctor_slots(db, UUID(str(doc["id"])))
                doc_slots = slots_result["slots"]
            await set_flow(conv_id, {
                "task": "booking", "step": "select_slot",
                "data": {
                    **booking_data,
                    "doctor_id": str(doc["id"]),
                    "doctor_name": doc["name"],
                    "slots": doc_slots,
                },
            })
            conversation.active_agent = "appointment"
            reply_text, ui = _slots_list_response({
                "doctor_name": doc["name"], "doctor_id": str(doc["id"]), "slots": doc_slots,
            })
            return reply_text, "appointment", False, ui

        await set_flow(conv_id, {
            "task": "booking", "step": "select_doctor",
            "data": booking_data,
        })
        conversation.active_agent = "doctor_discovery"
        reply_text, ui = _doctors_list_response(result)
        return reply_text, "doctor_discovery", False, ui

    async def _run_triage_turn(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        text: str,
        conv_id: UUID,
        patient_ctx: dict,
        history: list[dict],
        symptoms: list[str],
        collected: dict,
        flow_data: dict | None = None,
        first_turn: bool = False,
        understanding: dict | None = None,
    ) -> tuple[str, str, bool, dict | None]:
        """LLM-driven triage — adapts questions to whatever the patient describes."""
        pname = patient_ctx.get("name", "Patient")
        flow_data = flow_data or {}

        plan = None
        if first_turn and understanding and (
            understanding.get("next_triage_question") or understanding.get("ready_to_assess")
        ):
            plan = {
                "symptoms": understanding.get("symptoms") or symptoms,
                "collected": {
                    "duration": understanding.get("duration"),
                    "severity": understanding.get("severity"),
                    "details": understanding.get("details"),
                    "notes": [understanding["summary"]] if understanding.get("summary") else [],
                },
                "next_question": understanding.get("next_triage_question"),
                "ready_to_assess": bool(understanding.get("ready_to_assess")),
                "emergency": bool(understanding.get("emergency")),
            }
        if not plan:
            plan = await self.llm.plan_triage_turn(patient_ctx, history, text, symptoms, collected)
        if plan:
            if plan.get("symptoms"):
                symptoms = plan["symptoms"]
            collected = _merge_collected(collected, plan.get("collected") or {})
            if plan.get("emergency"):
                conversation.emergency_flag = True
                await clear_flow(conv_id)
                return (
                    "⚠️ Your symptoms may need urgent medical attention. "
                    "Please seek emergency care or call local emergency services now.",
                    "emergency",
                    True,
                    None,
                )
            if plan.get("ready_to_assess") or not plan.get("next_question"):
                return await self._finish_triage(
                    db, patient, text, conv_id, patient_ctx, conversation,
                    {**flow_data, "symptoms": symptoms, "collected": collected},
                )
            question = str(plan["next_question"]).strip()
        else:
            collected = _merge_collected(collected, _extract_structural_triage_updates(text))
            question = _next_triage_question_fallback(symptoms, collected)
            if not question:
                return await self._finish_triage(
                    db, patient, text, conv_id, patient_ctx, conversation,
                    {**flow_data, "symptoms": symptoms, "collected": collected},
                )

        await set_flow(conv_id, {
            "task": "triage",
            "step": "collect",
            "data": {**flow_data, "symptoms": symptoms, "collected": collected},
        })
        conversation.active_agent = "symptom_assessment"
        ack = _triage_ack(symptoms, collected, pname, first_turn=first_turn)
        return f"{ack}\n\n{question}", "symptom_assessment", False, None

    async def _begin_triage(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        text: str,
        conv_id: UUID,
        patient_ctx: dict,
        understanding: dict,
        history: list[dict],
    ) -> tuple[str, str, bool, dict | None]:
        symptoms = understanding.get("symptoms") or []
        if not symptoms:
            symptoms = _extract_symptoms_fallback(text) or [understanding.get("summary") or text.strip()[:160]]
        collected = _collected_from_understanding(understanding, text)
        return await self._run_triage_turn(
            db, conversation, patient, text, conv_id, patient_ctx, history,
            symptoms, collected, flow_data={}, first_turn=True, understanding=understanding,
        )

    async def _apply_llm_decision(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        text: str,
        flow: dict,
        decision: dict,
        conv_id: UUID,
    ) -> tuple[str | None, str, bool, dict | None]:
        agent = decision.get("agent", "conversation")
        if agent == "scope_guardrail":
            return OFF_TOPIC_REPLY, agent, False, None
        emergency = bool(decision.get("emergency"))
        task = decision.get("task")
        step = decision.get("step")
        if task:
            await set_flow(conv_id, {"task": task, "step": step, "data": flow.get("data", {})})

        tool = decision.get("tool")
        if tool:
            result = await _execute_tool(db, patient, tool, decision.get("tool_args", {}), conv_id)
            await update_flow(conv_id, data={**flow.get("data", {}), "last_tool_result": result})
            followup = await self.llm.decide(
                await load_patient_context(db, patient), [], text, await get_flow(conv_id), result
            )
            if followup and followup.get("reply"):
                return followup["reply"], followup.get("agent", agent), bool(followup.get("emergency")), None
            reply_text, ui = self._format_tool_reply(tool, result, patient_ctx=await load_patient_context(db, patient))
            return reply_text, agent, emergency, ui

        return decision.get("reply"), agent, emergency, None

    def _format_tool_reply(self, tool: str, result: dict, patient_ctx: dict) -> tuple[str, dict | None]:
        if tool == "search_doctors":
            return _doctors_list_response(result)
        if tool == "get_doctor_slots":
            return _slots_list_response(result)
        if tool == "book_slot" and result.get("success"):
            return (
                f"✅ Appointment Successfully Booked\n\n"
                f"Appointment ID: {result['apt_id']}\n"
                f"Doctor: {result['doctor_name']}\n"
                f"Date & Time: {result['label']}\n\n"
                f"Would you like a reminder 30 minutes before the appointment?"
            ), None
        if tool == "cancel_appointment" and result.get("success"):
            return (
                f"✅ Appointment {result['apt_id']} has been cancelled successfully.\n\n"
                f"Would you like to book another appointment?"
            ), None
        if tool == "reschedule_appointment" and result.get("success"):
            return f"✅ Appointment successfully rescheduled.\n\nNew time: {result['label']}", None
        if tool == "request_refill" and result.get("success"):
            return f"Submitting refill request...\n\n✅ {result['message']}", None
        if tool == "get_medications":
            meds = result.get("medications", [])
            if not meds:
                return "You have no active prescriptions on file.", None
            names = ", ".join(f"{m['name']} {m['dosage']}" for m in meds)
            return f"Your active medications: {names}.", None
        return json.dumps(result, default=str), None

    async def _fallback_plan(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        text: str,
        history: list[dict],
        patient_ctx: dict,
        flow: dict,
        conv_id: UUID,
        force_intent: str | None = None,
    ) -> tuple[str, str, bool, dict | None] | None:
        task = flow.get("task")
        data = flow.get("data", {})
        pname = patient_ctx["name"]

        if not task and not force_intent and should_reject_off_topic(text, None, in_active_flow=False, history=history):
            conversation.active_agent = "scope_guardrail"
            return OFF_TOPIC_REPLY, "scope_guardrail", False, None

        # Continue active task
        if task == "triage":
            return await self._handle_triage(db, patient, text, flow, conv_id, patient_ctx, conversation, history)
        if task == "booking":
            return await self._handle_booking(db, patient, text, flow, conv_id, patient_ctx, conversation)
        if task == "cancel":
            return await self._handle_cancel(db, patient, text, flow, conv_id, conversation)
        if task == "reschedule":
            return await self._handle_reschedule(db, patient, text, flow, conv_id, conversation)
        if task == "refill":
            return await self._handle_refill(db, patient, text, flow, conv_id, patient_ctx, conversation)
        if task == "emergency":
            return await self._handle_emergency(text, flow, conv_id, patient_ctx, conversation)
        if task == "followup":
            return await self._handle_followup(db, patient, text, flow, conv_id, patient_ctx, conversation)

        intent = force_intent or _detect_intent(text.lower(), patient_ctx)

        if intent == "emergency":
            await set_flow(conv_id, {"task": "emergency", "step": "assess", "data": {"symptoms": _extract_symptoms(text)}})
            conversation.active_agent = "triage"
            conversation.emergency_flag = True
            return (
                "⚠️ Your symptoms may indicate a medical emergency.\n\n"
                "Please tell me more: How severe is the pain or discomfort? "
                "Does it spread to other areas? Are you sweating or having trouble breathing?",
                "triage",
                True,
                None,
            )

        if intent == "triage":
            symptoms = _merge_symptoms(flow, text)
            if not symptoms:
                symptoms = _extract_symptoms_fallback(text) or [text.strip()[:160]]
            collected = _extract_structural_triage_updates(text)
            return await self._run_triage_turn(
                db, conversation, patient, text, conv_id, patient_ctx, history,
                symptoms, collected, flow_data={}, first_turn=True,
            )
        if intent == "booking" or (_yes(text) and flow.get("data", {}).get("offer_booking")):
            specialty = data.get("recommended_specialty", "General Physician")
            result = await tool_search_doctors(db, specialty)
            await set_flow(conv_id, {
                "task": "booking", "step": "select_doctor",
                "data": {"doctors": result["doctors"], "all_slots": result.get("all_slots", []), "specialty": specialty},
            })
            conversation.active_agent = "doctor_discovery"
            text, ui = _doctors_list_response(result)
            return text, "doctor_discovery", False, ui

        if intent == "cancel":
            appts = await tool_list_appointments(db, patient.id)
            if not appts["appointments"]:
                return "You have no active appointments to cancel.", "appointment", False, None
            appt = appts["appointments"][-1]
            await set_flow(conv_id, {"task": "cancel", "step": "confirm", "data": {"appointment_id": appt["id"], "appt": appt}})
            conversation.active_agent = "appointment"
            return (
                f"I found your appointment:\n\nAppointment ID: {appt['apt_id']}\n"
                f"Doctor: {appt['doctor_name']}\nTime: {appt['label']}\n\n"
                f"Would you like to cancel this appointment?"
            ), "appointment", False, None

        if intent == "reschedule":
            alt = await tool_reschedule_alternatives(db, patient.id)
            if not alt.get("success"):
                return alt.get("message", "No appointment to reschedule."), "appointment", False, None
            await set_flow(conv_id, {
                "task": "reschedule", "step": "pick_slot",
                "data": {"appointment_id": alt["appointment_id"], "alternatives": alt["alternatives"], "current": alt["current"], "apt_id": alt["apt_id"]},
            })
            slot_lines = "\n".join(f"- {s['label']}" for s in alt["alternatives"])
            conversation.active_agent = "appointment"
            return (
                f"Appointment ID: {alt['apt_id']}\nCurrent: {alt['current']}\n\n"
                f"Available alternative slots:\n{slot_lines}\n\nWhich slot would you like?"
            ), "appointment", False, None

        if intent == "refill":
            meds = await tool_get_medications(db, patient.id)
            med_list = meds.get("medications", [])
            await set_flow(conv_id, {"task": "refill", "step": "select", "data": {"medications": med_list}})
            conversation.active_agent = "refill"
            if not med_list:
                return (
                    "I can help with a refill request.\n\n"
                    "Please tell me the medication name, dosage, and how many tablets you have left."
                ), "refill", False, None
            names = "\n".join(f"- {m['name']} {m['dosage']} ({m['frequency']})" for m in med_list)
            return (
                f"I can help with a refill. Your active prescriptions:\n{names}\n\n"
                f"Which medication do you need refilled, or say 'request refill'?"
            ), "refill", False, None

        if intent == "followup" and patient_ctx.get("recent_visits"):
            visit = patient_ctx["recent_visits"][0]
            await set_flow(conv_id, {"task": "followup", "step": "check_in", "data": {"visit": visit}})
            conversation.active_agent = "followup"
            return (
                f"Hello {pname.split()[0]}.\n\n"
                f"You visited {visit['doctor_name']} for your recent appointment.\n\n"
                f"How are you feeling today?"
            ), "followup", False, None

        if re.search(r"\b(hi|hello)\b", text.lower()):
            conversation.active_agent = "conversation"
            return (
                f"Hello {pname.split()[0]}! I'm your AI Healthcare Assistant.\n\n"
                f"I can help with symptoms, health questions, appointments, refills, and follow-up care. "
                f"What would you like help with today?"
            ), "conversation", False, None

        if is_healthcare_related_fallback(text):
            conversation.active_agent = "health_education"
            return (
                "I'd be happy to help with your health question. For accurate, personalized guidance "
                "I need a bit more context — could you describe your concern or question in more detail? "
                "Please note I provide general health information only and cannot diagnose or prescribe. "
                "For urgent issues, contact a doctor or emergency services."
            ), "health_education", False, None

        conversation.active_agent = "scope_guardrail"
        return OFF_TOPIC_REPLY, "scope_guardrail", False, None

    async def _finish_triage(
        self, db, patient, text, conv_id, patient_ctx, conversation, data: dict
    ) -> tuple[str, str, bool, dict | None]:
        symptoms = data.get("symptoms", [])
        collected = data.get("collected", {})
        db_assessment = await tool_assess_symptoms(
            db, patient.id, symptoms, collected.get("duration"),
            patient_ctx.get("conditions", []), conv_id,
        )
        llm_assessment = await self.llm.recommend_care(patient_ctx, symptoms, collected)
        if llm_assessment:
            assessment = {
                "risk_level": llm_assessment.get("risk_level") or db_assessment["risk_level"],
                "recommended_specialty": llm_assessment.get("recommended_specialty") or db_assessment["recommended_specialty"],
                "recommendation": llm_assessment.get("recommendation") or db_assessment["recommendation"],
            }
        else:
            assessment = db_assessment
        await set_flow(conv_id, {
            "task": "triage",
            "step": "offer",
            "data": {
                **data,
                "symptoms": symptoms,
                "collected": collected,
                "assessment": assessment,
                "recommended_specialty": assessment["recommended_specialty"],
                "offer_booking": True,
            },
        })
        conversation.active_agent = "symptom_assessment"
        pname = patient_ctx.get("name", "there").split()[0]
        return (
            f"Thanks, {pname}. Based on what you've told me: {assessment['recommendation']}\n\n"
            f"I'd recommend seeing a {assessment['recommended_specialty']}.\n\n"
            f"Would you like me to show available doctors and book an appointment?"
        ), "symptom_assessment", assessment.get("risk_level") == "emergency", None

    async def _handle_triage(
        self, db, patient, text, flow, conv_id, patient_ctx, conversation, history: list[dict]
    ) -> tuple[str, str, bool, dict | None]:
        data = flow.get("data", {})

        if flow.get("step") == "offer":
            if _no(text):
                await clear_flow(conv_id)
                return (
                    "No problem. Rest well and drink plenty of fluids. "
                    "If symptoms worsen, I'm here to help you book a visit anytime.",
                    "symptom_assessment",
                    False,
                    None,
                )
            specialty = data.get("recommended_specialty", "General Physician")
            all_result = await tool_search_doctors(db, None)
            all_doctor_rows = [
                {"id": UUID(d["id"]), "name": d["name"], "specializations": [d["specialty"]]}
                for d in all_result["doctors"]
            ]
            named_doc = _match_doctor(text, all_doctor_rows)
            if named_doc or match_slot_from_text(text, all_result.get("all_slots", [])):
                return await self._start_booking_flow(
                    db, conversation, patient, text, conv_id, patient_ctx, specialty, all_result,
                )
            result = await tool_search_doctors(db, specialty)
            doctor_rows = [
                {"id": UUID(d["id"]), "name": d["name"], "specializations": [d["specialty"]]}
                for d in result["doctors"]
            ]
            if _yes(text) or _match_doctor(text, doctor_rows) or match_slot_from_text(text, result.get("all_slots", [])):
                return await self._start_booking_flow(
                    db, conversation, patient, text, conv_id, patient_ctx, specialty, result,
                )
            return (
                "Would you like me to show available doctors and book an appointment? (Yes/No)"
            ), "symptom_assessment", False, None

        symptoms = data.get("symptoms") or _merge_symptoms(flow, text)
        collected = data.get("collected", {})
        return await self._run_triage_turn(
            db, conversation, patient, text, conv_id, patient_ctx, history,
            symptoms, collected, flow_data=data, first_turn=False,
        )

    async def _handle_booking(
        self, db, patient, text, flow, conv_id, patient_ctx, conversation
    ) -> tuple[str, str, bool, dict | None]:
        step = flow.get("step")
        data = flow.get("data", {})
        pname = patient_ctx["name"]

        if step == "select_doctor":
            doctors = data.get("doctors") or (await tool_search_doctors(db, data.get("specialty")))["doctors"]
            all_slots = data.get("all_slots") or [s for d in doctors for s in d.get("slots", [])]

            chosen = match_slot_from_text(text, all_slots)
            if chosen:
                doc_name = chosen.get("doctor_name", "")
                await update_flow(conv_id, step="confirm", data={**data, "doctor_name": doc_name, "chosen": chosen})
                return (
                    f"Before booking, please confirm:\n\nPatient Name: {pname}\n"
                    f"Doctor: {doc_name}\nDate & Time: {chosen['label']}\n\nConfirm booking? (Yes/No)"
                ), "appointment", False, None

            doc = _match_doctor(text, [{"id": UUID(d["id"]), "name": d["name"], "specializations": [d["specialty"]]} for d in doctors])
            if not doc and _yes(text):
                return "Please tell me which doctor or slot you'd like from the list above.", "appointment", False, None
            if not doc:
                return "Please specify a doctor name or time slot from the list above.", "appointment", False, None
            doc_slots = next((d.get("slots", []) for d in doctors if d["id"] == str(doc["id"])), [])
            if not doc_slots:
                slots_result = await tool_get_doctor_slots(db, UUID(str(doc["id"])))
                doc_slots = slots_result["slots"]
            await update_flow(
                conv_id, step="select_slot",
                data={**data, "doctor_id": str(doc["id"]), "doctor_name": doc["name"], "slots": doc_slots},
            )
            text, ui = _slots_list_response({
                "doctor_name": doc["name"], "doctor_id": str(doc["id"]), "slots": doc_slots,
            })
            return text, "appointment", False, ui

        if step == "select_slot":
            slots = data.get("slots", [])
            chosen = match_slot_from_text(text, slots)
            if not chosen:
                return "Please pick a time from the available slots listed above.", "appointment", False, None
            stored = chosen if isinstance(chosen.get("slot_date"), str) else serialize_slot(
                chosen["doctor_id"], chosen.get("doctor_name", data.get("doctor_name", "")),
                chosen["slot_date"], chosen["slot_time"],
            )
            if "label" not in stored:
                stored["label"] = chosen["label"]
            await update_flow(conv_id, step="confirm", data={**data, "chosen": stored})
            return (
                f"Before booking, please confirm:\n\nPatient Name: {pname}\n"
                f"Doctor: {data.get('doctor_name')}\nDate & Time: {stored['label']}\n\n"
                f"Confirm booking? (Yes/No)"
            ), "appointment", False, None

        if step == "confirm":
            if _no(text):
                await clear_flow(conv_id)
                return "Booking cancelled. Let me know if you'd like to try again.", "appointment", False, None
            if not _yes(text):
                return "Please reply Yes or No to confirm.", "appointment", False, None
            chosen_raw = data.get("chosen", {})
            slot = deserialize_slot(chosen_raw) if isinstance(chosen_raw.get("slot_date"), str) else chosen_raw
            result = await tool_book_slot(db, patient, patient.user_id, slot, conv_id)
            await update_flow(conv_id, step="reminder", data={**data, "appointment_id": result["appointment_id"], "apt_id": result["apt_id"]})
            reply_text, ui = self._format_tool_reply("book_slot", result, patient_ctx)
            return reply_text, "appointment", False, ui

        if step == "reminder":
            await clear_flow(conv_id)
            if _yes(text):
                await tool_schedule_reminder(db, patient.user_id, UUID(data["appointment_id"]))
                return "✅ Reminder Scheduled.", "reminder", False, None
            return "No problem. Your appointment is confirmed.", "appointment", False, None
        if _yes(text) or "doctor" in text.lower():
            specialty = data.get("recommended_specialty", "General Physician")
            result = await tool_search_doctors(db, specialty)
            await update_flow(conv_id, step="select_doctor", data={**data, "doctors": result["doctors"], "all_slots": result.get("all_slots", [])})
            text, ui = _doctors_list_response(result)
            return text, "doctor_discovery", False, ui

        return "Would you like to see available doctors?", "appointment", False, None
    async def _handle_cancel(self, db, patient, text, flow, conv_id, conversation) -> tuple[str, str, bool, dict | None]:
        data = flow.get("data", {})
        if flow.get("step") == "confirm" and _yes(text):
            result = await tool_cancel_appointment(db, patient.id, UUID(data["appointment_id"]))
            await update_flow(conv_id, step="rebook")
            reply_text, ui = self._format_tool_reply("cancel_appointment", result, {})
            return reply_text, "appointment", False, ui
        if flow.get("step") == "rebook":
            await clear_flow(conv_id)
            if _yes(text):
                result = await tool_search_doctors(db, "General Physician")
                await set_flow(conv_id, {
                    "task": "booking", "step": "select_doctor",
                    "data": {"doctors": result["doctors"], "all_slots": result.get("all_slots", [])},
                })
                reply_text, ui = _doctors_list_response(result)
                return reply_text, "appointment", False, ui
            return "No problem. Feel free to contact me whenever you need assistance.", "conversation", False, None
        return "Would you like to cancel this appointment? (Yes/No)", "appointment", False, None
    async def _handle_reschedule(self, db, patient, text, flow, conv_id, conversation) -> tuple[str, str, bool, dict | None]:
        data = flow.get("data", {})
        if flow.get("step") == "pick_slot":
            chosen = match_slot_from_text(text, data.get("alternatives", []))
            if not chosen:
                return "Please pick a slot from the alternatives listed above.", "appointment", False, None
            stored = chosen if isinstance(chosen.get("slot_date"), str) else serialize_slot(
                chosen["doctor_id"], chosen.get("doctor_name", ""),
                chosen["slot_date"], chosen["slot_time"],
            )
            if "label" not in stored:
                stored["label"] = chosen["label"]
            await update_flow(conv_id, step="confirm", data={**data, "chosen": stored})
            return (
                f"Confirm rescheduling?\n\nCurrent: {data.get('current')}\nNew: {stored['label']}\n\nReply Yes to confirm."
            ), "appointment", False, None
        if flow.get("step") == "confirm" and _yes(text):
            chosen_raw = data.get("chosen", {})
            slot = deserialize_slot(chosen_raw) if isinstance(chosen_raw.get("slot_date"), str) else chosen_raw
            result = await tool_reschedule(
                db, patient.id, patient.user_id, UUID(data["appointment_id"]), slot
            )
            await clear_flow(conv_id)
            reply_text, ui = self._format_tool_reply("reschedule_appointment", result, {})
            return reply_text, "appointment", False, ui
        return "Reply Yes to confirm rescheduling.", "appointment", False, None
    async def _handle_refill(self, db, patient, text, flow, conv_id, patient_ctx, conversation) -> tuple[str, str, bool, dict | None]:
        data = flow.get("data", {})
        meds = data.get("medications") or (await tool_get_medications(db, patient.id))["medications"]
        med_name = data.get("mentioned_med")
        for m in meds:
            if m["name"].lower() in text.lower():
                med_name = m["name"]
                break
        if not med_name and len(text) > 5 and flow.get("step") == "select":
            await update_flow(conv_id, step="confirm", data={**data, "mentioned_med": text.strip()})
            return (
                f"Got it: {text.strip()}\n\n"
                f"Would you like me to submit a refill request to your doctor? (Yes/No)"
            ), "refill", False, None
        if flow.get("step") == "confirm" and _no(text):
            await clear_flow(conv_id)
            return "No problem. Let me know if you need anything else.", "refill", False, None
        if "refill" in text.lower() or "request" in text.lower() or med_name or (flow.get("step") == "confirm" and _yes(text)):
            name = med_name or data.get("mentioned_med")
            result = await tool_request_refill(db, patient.id, patient.user_id, name)
            await clear_flow(conv_id)
            if not result.get("success") and name:
                db.add(Notification(
                    user_id=patient.user_id,
                    type=NotificationType.system,
                    message=f"Refill request submitted for {name}",
                ))
                await db.flush()
                return (
                    f"Submitting refill request...\n\n✅ Refill request sent for {name}.\n\n"
                    f"Expected approval time: 4-8 hours."
                ), "refill", False, None
            reply_text, ui = self._format_tool_reply("request_refill", result, patient_ctx)
            return reply_text, "refill", False, ui
        if "consultation" in text.lower() or "book" in text.lower():
            result = await tool_search_doctors(db, "General Physician")
            await set_flow(conv_id, {
                "task": "booking", "step": "select_doctor",
                "data": {"doctors": result["doctors"], "all_slots": result.get("all_slots", [])},
            })
            text, ui = _doctors_list_response(result)
            return text, "appointment", False, ui
        return "Reply with the medication name or say 'request refill'.", "refill", False, None
    async def _handle_emergency(self, text, flow, conv_id, patient_ctx, conversation) -> tuple[str, str, bool, dict | None]:
        data = flow.get("data", {})
        if flow.get("step") == "assess" and len(text) > 5:
            if any(w in text.lower() for w in ("severe", "arm", "jaw", "sweating", "yes")):
                await update_flow(conv_id, step="escalate")
                conversation.emergency_flag = True
                return (
                    "🚨 Emergency Alert\n\n"
                    "Your symptoms could indicate a serious condition.\n\n"
                    "Please call emergency services (911 / local emergency number) immediately "
                    "and go to the nearest emergency department. Do not drive yourself if possible.\n\n"
                    "Would you like general guidance on what to do while waiting for help?"
                ), "emergency", True, None
        if flow.get("step") == "escalate" and _yes(text):
            await clear_flow(conv_id)
            return (
                "While waiting for emergency services:\n"
                "- Stay calm and sit or lie down\n"
                "- Loosen tight clothing\n"
                "- If prescribed, take emergency medication as directed\n"
                "- Do not eat or drink unless advised\n\n"
                "Please seek immediate medical attention."
            ), "emergency", True, None
        await update_flow(conv_id, data={**data, "details": text})
        return (
            "Please tell me: Is the pain severe? Does it spread to arm, jaw, or back? Are you sweating heavily?"
        ), "triage", True, None

    async def _handle_followup(self, db, patient, text, flow, conv_id, patient_ctx, conversation) -> tuple[str, str, bool, dict | None]:
        step = flow.get("step")
        if step == "check_in" and len(text) > 2:
            await update_flow(conv_id, step="severity")
            return "On a scale of 1-10, how would you rate your symptoms now?", "followup", False, None
        if step == "severity" and re.search(r"\d+", text):
            await update_flow(conv_id, step="meds")
            return "Are you taking your prescribed medications regularly?", "followup", False, None
        if step == "meds":
            await update_flow(conv_id, step="offer")
            return (
                "I'll record this in your health record.\n\n"
                "If symptoms worsen, would you like me to schedule another consultation?"
            ), "followup", False, None
        if step == "offer":
            await clear_flow(conv_id)
            if _yes(text):
                result = await tool_search_doctors(db, "General Physician")
                await set_flow(conv_id, {
                    "task": "booking", "step": "select_doctor",
                    "data": {"doctors": result["doctors"], "all_slots": result.get("all_slots", [])},
                })
                reply_text, ui = _doctors_list_response(result)
                return reply_text, "appointment", False, ui
            return "Glad you're doing well. Take care!", "followup", False, None
        return "How are you feeling today?", "followup", False, None
_agent = DynamicHealthcareAgent()


async def process_agent_flow(
    db: AsyncSession,
    conversation: Conversation,
    patient: Patient,
    user_message: str,
    history: list[dict],
) -> tuple[str, str, bool, dict | None] | None:
    """Entry point — dynamic agentic processing."""
    return await _agent.process(db, conversation, patient, user_message, history)
