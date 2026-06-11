"""Specialist agents — each owns a domain with LLM reasoning + allowed tools."""
from __future__ import annotations

import json

from app.emergency_detection import (
    build_emergency_reply,
    detect_emergency,
    detect_mental_health_crisis,
    is_confirmed_emergency,
)
from app.healthcare_policy import (
    HEALTH_QA_PROMPT,
    PLAIN_LANGUAGE_RULES,
    OFF_TOPIC_REPLY,
    build_greeting_reply,
    is_active_care_flow,
    is_short_flow_reply,
    patient_ctx_for_llm,
    patient_first_name,
    should_reset_to_greeting,
)
from app.services.chat_ui import infer_triage_quick_actions
from app.services.agent_tools import execute_agent_tool

from app.multi_agent.booking_actions import (
    format_report_reply,
    _booking_intent,
    _is_appointment_management_message,
    _self_care_response,
    _wants_reminder,
    has_identified_symptoms,
    infer_recommended_specialty,
    resolve_booking_session,
    resolve_refill_session,
    should_skip_booking_resolution,
    synthesize_tool_result,
)
from app.services.self_care_service import wants_self_care_advice
from app.multi_agent.llm import llm
from app.multi_agent.offline_fallback import (
    conversational_triage_turn,
    is_symptom_triage_kickoff,
    kickoff_symptom_triage_turn,
    offline_education_reply,
)
from app.multi_agent.types import AgentContext, AgentResponse

SPECIALIST_NAMES = (
    "education_agent",
    "triage_agent",
    "scheduling_agent",
    "report_agent",
    "followup_agent",
    "refill_agent",
    "safety_agent",
)

AGENT_TOOLS = {
    "education_agent": {"save_memory"},
    "triage_agent": {"assess_symptoms", "save_memory"},
    "scheduling_agent": {
        "search_doctors", "get_doctor_slots", "list_appointments", "book_slot",
        "cancel_appointment", "reschedule_alternatives", "reschedule_appointment", "schedule_reminder",
    },
    "report_agent": {"list_reports", "get_report_analysis", "analyze_report", "save_memory"},
    "followup_agent": {"save_memory", "search_doctors", "get_medications"},
    "refill_agent": {"get_medications", "request_refill"},
    "safety_agent": set(),
}

SPECIALIST_PROMPT = """You are the {name} in a multi-agent healthcare assistant team.

Patient context, session state, and tool results are provided. You reason dynamically — NO fixed symptom scripts or disease-specific decision trees.
""" + PLAIN_LANGUAGE_RULES + """

Allowed tools for you: {tools}

Return ONLY valid JSON:
{{
  "reply": "natural language to patient",
  "emergency": false,
  "off_topic": false,
  "tool": "tool_name or null",
  "tool_args": {{}},
  "session_patch": {{}},
  "handoff_to": "other_agent_name or null",
  "goal_complete": false
}}

Core rules:
- One tool call per turn maximum
- Never invent doctors, slots, labs, or appointments
- Ask ONE tailored follow-up when information is missing
- Be empathetic and conversational — this is a healthcare companion, not a form-filler
- Never address the patient as "Guest" or "Patient" — use their first name from context, or omit the name

Triage rules:
- Engage in natural two-way conversation before suggesting any action
- Gather symptoms thoroughly (2–4 exchanges minimum) before assessing
- ONLY count symptoms the patient explicitly stated — never assume they have a symptom because you
  listed it in a clarifying question (e.g. if you asked about fever or stomach pain and they say
  "yes, more symptoms", ask what those symptoms are — do not treat any option as confirmed)
- Accept duration in ANY natural form — "from yesterday", "since last night", "about 3 days",
  "almost a week", or a button choice like "1-3 days" — all equally valid; never re-ask if answered
- After triage assessment: FIRST give self-care advice, home remedies, and reassurance for low/medium risk
- ONLY suggest seeing a doctor after giving self-care guidance; NEVER as the first response
- For HIGH risk or EMERGENCY: immediately advise seeking urgent care — skip self-care tips
- Handoff to scheduling_agent ONLY after patient explicitly asks to book, or after self-care advice was given and patient still wants a doctor

Scheduling rules:
- scheduling_agent: NEVER ask patient what type of doctor — use recommended_specialty from triage session
- Confirm appointment details before booking
- goal_complete=true when this agent's objective is fulfilled
"""


class BaseSpecialist:
    name: str = "base"
    agent_label: str = "conversation"

    async def run(self, ctx: AgentContext) -> AgentResponse:
        if not should_skip_booking_resolution(ctx):
            booking = await resolve_booking_session(ctx)
            if booking:
                return booking

        if ctx.tool_result:
            synthesized = await synthesize_tool_result(ctx.tool_result, ctx)
            if synthesized:
                return synthesized

        decision = await self._decide(ctx)
        if not decision:
            decision = await self._fallback_decide(ctx)
        if not decision:
            if should_reset_to_greeting(ctx.text, ctx.session):
                pname = patient_first_name(ctx.patient_ctx.get("name"))
                return AgentResponse(reply=build_greeting_reply(pname), agent=self.agent_label)
            return AgentResponse(
                reply=(
                    "I'm here to help with your health. "
                    "You can describe how you're feeling, ask a health question, or say "
                    "\"book an appointment\" if you'd like to see a doctor."
                ),
                agent=self.agent_label,
            )

        if decision.get("off_topic"):
            return AgentResponse(reply=OFF_TOPIC_REPLY, agent="scope_guardrail")

        if decision.get("tool"):
            tool = decision["tool"]
            if tool not in AGENT_TOOLS.get(self.name, set()):
                return AgentResponse(
                    reply="Let me connect you with the right specialist for that request.",
                    agent=self.agent_label,
                    handoff_to=self._suggest_handoff(ctx.text),
                )
            result = await execute_agent_tool(
                ctx.db, ctx.patient, tool, decision.get("tool_args") or {}, ctx.conv_id, ctx.patient_ctx
            )
            ctx.tool_result = result
            follow = await synthesize_tool_result(result, ctx)
            if follow:
                if decision.get("handoff_to"):
                    follow.handoff_to = decision["handoff_to"]
                return follow
            second = await self._decide(ctx)
            if second and second.get("reply"):
                return AgentResponse(
                    reply=second["reply"].strip(),
                    agent=self.agent_label,
                    emergency=is_confirmed_emergency(ctx.text),
                    ui=second.get("ui"),
                    session_patch=second.get("session_patch"),
                    handoff_to=second.get("handoff_to"),
                )

        reply = (decision.get("reply") or "").strip()
        return AgentResponse(
            reply=reply or "How can I help you with your health today?",
            agent=self.agent_label,
            emergency=is_confirmed_emergency(ctx.text),
            ui=decision.get("ui"),
            session_patch=decision.get("session_patch"),
            handoff_to=decision.get("handoff_to"),
        )

    async def _decide(self, ctx: AgentContext) -> dict | None:
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in ctx.history[-12:])
        payload = json.dumps(
            {
                "patient": patient_ctx_for_llm(ctx.patient_ctx),
                "session": ctx.session,
                "tool_result": ctx.tool_result,
                "report_id": ctx.report_id,
                "care_goal": ctx.session.get("care_goal"),
            },
            default=str,
        )
        tools = ", ".join(sorted(AGENT_TOOLS.get(self.name, set()))) or "none"
        prompt = (
            f"{SPECIALIST_PROMPT.format(name=self.name, tools=tools)}\n\n"
            f"SPECIALIST ROLE: {self._role_description()}\n\n"
            f"CONTEXT:\n{payload}\n\nCHAT:\n{hist}\n\nPATIENT: {ctx.text}\n\nJSON:"
        )
        return await llm.json_prompt(prompt)

    async def _fallback_decide(self, ctx: AgentContext) -> dict | None:
        return None

    def _role_description(self) -> str:
        return "General healthcare assistance."

    def _suggest_handoff(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ("book", "appointment", "doctor", "slot", "cancel", "reschedule")):
            return "scheduling_agent"
        if any(w in t for w in ("report", "lab", "cbc", "blood test", "upload")):
            return "report_agent"
        if any(w in t for w in ("refill", "prescription", "medication")):
            return "refill_agent"
        return "education_agent"


class SafetyAgent(BaseSpecialist):
    name = "safety_agent"
    agent_label = "safety_agent"

    async def evaluate(self, ctx: AgentContext) -> AgentResponse | None:
        if detect_mental_health_crisis(ctx.text):
            return AgentResponse(
                reply=build_emergency_reply(mental_health_crisis=True),
                agent="emergency",
                emergency=True,
                clear_session=True,
            )
        if detect_emergency(ctx.text):
            return AgentResponse(
                reply=build_emergency_reply(),
                agent="emergency",
                emergency=True,
                clear_session=True,
            )
        return None


class EducationAgent(BaseSpecialist):
    name = "education_agent"
    agent_label = "health_education"

    def _role_description(self) -> str:
        return (
            "Provide evidence-based health EDUCATION for general medical questions "
            "(diseases, symptoms info, treatments in general, wellness). Never diagnose or prescribe."
        )

    async def run(self, ctx: AgentContext) -> AgentResponse:
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in ctx.history[-10:])
        prompt = (
            f"{HEALTH_QA_PROMPT}\n\nPATIENT:\n{json.dumps(patient_ctx_for_llm(ctx.patient_ctx), default=str)}\n\n"
            f"CHAT:\n{hist}\n\nQUESTION: {ctx.text}\n\nASSISTANT:"
        )
        answer = await llm.text_prompt(prompt)
        if answer:
            return AgentResponse(reply=answer.strip(), agent=self.agent_label)
        offline = offline_education_reply(ctx.text)
        if offline:
            return AgentResponse(reply=offline, agent=self.agent_label)
        return await super().run(ctx)


class TriageAgent(BaseSpecialist):
    name = "triage_agent"
    agent_label = "symptom_assessment"

    async def run(self, ctx: AgentContext) -> AgentResponse:
        from app.services.patient_context import resolve_patient_first_name

        pname = await resolve_patient_first_name(ctx.db, ctx.patient_ctx, ctx.patient)
        ctx.session["_patient_first_name"] = pname
        triage = ctx.session.get("triage_collected") or {}
        has_symptoms = bool(
            ctx.session.get("detected_symptoms")
            or triage.get("symptoms")
        )
        if is_symptom_triage_kickoff(ctx.text) and not has_symptoms:
            decision = kickoff_symptom_triage_turn(ctx.session)
            return AgentResponse(
                reply=decision["reply"],
                agent=self.agent_label,
                ui=decision.get("ui"),
                session_patch=decision.get("session_patch"),
            )

        if wants_self_care_advice(ctx.text) and (
            ctx.session.get("triage_assessed") or has_identified_symptoms(ctx.session, ctx.history)
        ):
            return await _self_care_response(ctx)

        if (
            not ctx.session.get("triage_assessed")
            and (
                has_symptoms
                or is_active_care_flow(ctx.session)
                or ctx.session.get("care_goal") == "symptom_assessment"
            )
        ):
            decision = conversational_triage_turn(ctx.text, ctx.session, ctx.history)
            return await self._response_from_decision(decision, ctx)

        response = await super().run(ctx)
        if response.ui or response.emergency or ctx.session.get("triage_assessed"):
            return response
        ui, patch = infer_triage_quick_actions(response.reply, ctx.session)
        if ui:
            response.ui = ui
            merged = dict(response.session_patch or {})
            merged.update(patch)
            response.session_patch = merged
        return response

    async def _response_from_decision(self, decision: dict, ctx: AgentContext) -> AgentResponse:
        """Apply structured triage decision, including assess_symptoms tool calls."""
        if decision.get("tool"):
            tool = decision["tool"]
            if tool in AGENT_TOOLS.get(self.name, set()):
                result = await execute_agent_tool(
                    ctx.db,
                    ctx.patient,
                    tool,
                    decision.get("tool_args") or {},
                    ctx.conv_id,
                    ctx.patient_ctx,
                )
                ctx.tool_result = result
                follow = await synthesize_tool_result(result, ctx)
                if follow:
                    patch = dict(decision.get("session_patch") or {})
                    if follow.session_patch:
                        patch.update(follow.session_patch)
                    if patch:
                        follow.session_patch = patch
                    return follow
        return AgentResponse(
            reply=(decision.get("reply") or "").strip() or "How can I help you with your health today?",
            agent=self.agent_label,
            ui=decision.get("ui"),
            session_patch=decision.get("session_patch"),
        )

    def _role_description(self) -> str:
        return (
            "Conduct adaptive, empathetic symptom assessment through natural two-way conversation. "
            "Never assume the patient has a symptom you suggested — only symptoms they explicitly named count. "
            "Step 1 — Understand: Ask ONE tailored follow-up question at a time to understand the complaint fully (2–4 exchanges). "
            "Step 2 — Assess: When enough info is collected, call assess_symptoms to determine risk level. "
            "Step 3 — Advise FIRST: For low/medium risk, provide specific self-care tips, home remedies, and reassurance before mentioning doctors. "
            "Only AFTER giving self-care advice, gently ask: 'Would you like me to help book an appointment if symptoms persist?' "
            "Step 4 — Book ONLY on patient request: handoff_to scheduling_agent ONLY when patient explicitly wants to see a doctor. "
            "For HIGH risk: strongly recommend prompt medical attention and offer to book immediately. "
            "For EMERGENCY: skip all steps and immediately advise calling emergency services (911) or going to the ER."
        )

    async def _fallback_decide(self, ctx: AgentContext) -> dict | None:
        pname = patient_first_name(ctx.patient_ctx.get("name"))
        ctx.session["_patient_first_name"] = pname
        ctx.session.setdefault("care_goal", "symptom_assessment")
        ctx.session.setdefault("active_specialist", "triage_agent")
        text = ctx.text.strip()
        tl = text.lower()
        if tl in {"yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please", "go ahead"}:
            for msg in reversed(ctx.history):
                if msg.get("role") not in ("user", "User"):
                    continue
                prior = (msg.get("content") or "").strip()
                if prior.lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please"}:
                    continue
                if prior:
                    return conversational_triage_turn(prior, ctx.session, ctx.history)
        if is_short_flow_reply(text) and (
            is_active_care_flow(ctx.session) or ctx.session.get("detected_symptoms")
        ):
            return conversational_triage_turn(text, ctx.session, ctx.history)
        return conversational_triage_turn(text, ctx.session, ctx.history)


class SchedulingAgent(BaseSpecialist):
    name = "scheduling_agent"
    agent_label = "appointment"

    def _role_description(self) -> str:
        return (
            "Manage appointments: search doctors, show slots, book, cancel, reschedule, reminders. "
            "You handle scheduling ONLY when the patient has explicitly asked to book, cancel, or reschedule. "
            "Never push booking unsolicited — wait for patient request. "
            "When patient wants to book, call search_doctors using recommended_specialty from session "
            "or 'General Physician' — do NOT ask what type of doctor first. "
            "Use tools for all live data. Always confirm appointment details before calling book_slot."
        )

    async def _fallback_decide(self, ctx: AgentContext) -> dict | None:
        if _wants_reminder(ctx.text) or _is_appointment_management_message(ctx.text):
            return None
        if _booking_intent(ctx.text, ctx.history) or ctx.session.get("awaiting") == "offer_booking":
            specialty = infer_recommended_specialty(ctx.session, ctx.history)
            return {"tool": "search_doctors", "tool_args": {"specialty": specialty}}
        return None


class ReportAgent(BaseSpecialist):
    name = "report_agent"
    agent_label = "report_analysis"

    def _role_description(self) -> str:
        return (
            "Analyze lab/medical reports using get_report_analysis or analyze_report. "
            "Explain findings in plain language. Recommend follow-up with physician."
        )

    async def run(self, ctx: AgentContext) -> AgentResponse:
        if ctx.report_id:
            result = await execute_agent_tool(
                ctx.db,
                ctx.patient,
                "get_report_analysis",
                {"report_id": ctx.report_id},
                ctx.conv_id,
                ctx.patient_ctx,
            )
            if not result.get("success") or not result.get("analysis"):
                result = await execute_agent_tool(
                    ctx.db,
                    ctx.patient,
                    "analyze_report",
                    {"report_id": ctx.report_id},
                    ctx.conv_id,
                    ctx.patient_ctx,
                )
            if result.get("success") and result.get("analysis"):
                reply = format_report_reply(result["analysis"], ctx.text)
                return AgentResponse(reply=reply, agent="report_agent")
        return await super().run(ctx)


class FollowUpAgent(BaseSpecialist):
    name = "followup_agent"
    agent_label = "followup"

    def _role_description(self) -> str:
        return (
            "Post-visit follow-up: check recovery, symptom improvement, medication adherence. "
            "Use recent_visits from patient context. "
            "Provide encouragement and self-care guidance first. "
            "Only offer to book if symptoms are worsening or patient asks."
        )


class RefillAgent(BaseSpecialist):
    name = "refill_agent"
    agent_label = "refill"

    def _role_description(self) -> str:
        return "Handle prescription refill requests using get_medications and request_refill tools."

    async def run(self, ctx: AgentContext) -> AgentResponse:
        refill = await resolve_refill_session(ctx)
        if refill:
            return refill
        return await super().run(ctx)


AGENTS: dict[str, BaseSpecialist] = {
    "education_agent": EducationAgent(),
    "triage_agent": TriageAgent(),
    "scheduling_agent": SchedulingAgent(),
    "report_agent": ReportAgent(),
    "followup_agent": FollowUpAgent(),
    "refill_agent": RefillAgent(),
    "safety_agent": SafetyAgent(),
}
