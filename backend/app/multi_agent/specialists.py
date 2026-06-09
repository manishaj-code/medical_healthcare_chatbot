"""Specialist agents — each owns a domain with LLM reasoning + allowed tools."""
from __future__ import annotations

import json

from app.healthcare_policy import HEALTH_QA_PROMPT, OFF_TOPIC_REPLY
from app.services.agent_tools import execute_agent_tool

from app.multi_agent.booking_actions import (
    format_report_reply,
    _booking_intent,
    infer_recommended_specialty,
    resolve_booking_session,
    should_skip_booking_resolution,
    synthesize_tool_result,
)
from app.multi_agent.llm import llm
from app.multi_agent.offline_fallback import offline_education_reply, plan_triage_turn
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

Rules:
- One tool call per turn maximum
- Never invent doctors, slots, labs, or appointments
- Ask ONE tailored follow-up when information is missing
- scheduling_agent: NEVER ask patient what type of doctor — use recommended_specialty from triage session
- handoff_to scheduling_agent when patient is ready to book after triage
- handoff_to triage_agent when patient describes new symptoms during booking
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
            synthesized = synthesize_tool_result(ctx.tool_result, ctx)
            if synthesized:
                return synthesized

        decision = await self._decide(ctx)
        if not decision:
            decision = await self._fallback_decide(ctx)
        if not decision:
            return AgentResponse(
                reply=(
                    "I'm having temporary trouble reaching the AI service. "
                    "Please try again in a moment, or add a GROQ_API_KEY as fallback in your .env file."
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
            follow = synthesize_tool_result(result, ctx)
            if follow:
                if decision.get("handoff_to"):
                    follow.handoff_to = decision["handoff_to"]
                return follow
            second = await self._decide(ctx)
            if second and second.get("reply"):
                return AgentResponse(
                    reply=second["reply"].strip(),
                    agent=self.agent_label,
                    emergency=bool(second.get("emergency")),
                    ui=second.get("ui"),
                    session_patch=second.get("session_patch"),
                    handoff_to=second.get("handoff_to"),
                )

        reply = (decision.get("reply") or "").strip()
        return AgentResponse(
            reply=reply or "How can I help you with your health today?",
            agent=self.agent_label,
            emergency=bool(decision.get("emergency")),
            ui=decision.get("ui"),
            session_patch=decision.get("session_patch"),
            handoff_to=decision.get("handoff_to"),
        )

    async def _decide(self, ctx: AgentContext) -> dict | None:
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in ctx.history[-12:])
        payload = json.dumps(
            {
                "patient": ctx.patient_ctx,
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

    CRISIS_PROMPT = """Evaluate patient message for medical emergency or mental health crisis.

Return JSON:
{
  "emergency": false,
  "mental_health_crisis": false,
  "reply": "response if emergency/crisis, else null",
  "handoff_to": "triage_agent|education_agent|null"
}

emergency=true for: chest pain, can't breathe, stroke, severe bleeding, unconscious
mental_health_crisis=true for: suicide, self-harm, want to die, end my life

If mental_health_crisis: include crisis hotline (988 Suicide & Crisis Lifeline in US) and urge immediate help.
If emergency: urge calling emergency services now.
Otherwise handoff_to based on intent (symptoms→triage_agent, general question→education_agent).
"""

    async def evaluate(self, ctx: AgentContext) -> AgentResponse | None:
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in ctx.history[-6:])
        prompt = f"{self.CRISIS_PROMPT}\n\nPATIENT CONTEXT:\n{json.dumps(ctx.patient_ctx, default=str)}\n\nCHAT:\n{hist}\n\nMESSAGE: {ctx.text}\n\nJSON:"
        decision = await llm.json_prompt(prompt)
        if not decision:
            return None
        if decision.get("emergency") or decision.get("mental_health_crisis"):
            reply = decision.get("reply") or (
                "⚠️ This may be a medical emergency. Please call your local emergency number or go to the nearest emergency department immediately."
            )
            return AgentResponse(reply=reply, agent="emergency", emergency=True, clear_session=True)
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
            f"{HEALTH_QA_PROMPT}\n\nPATIENT:\n{json.dumps(ctx.patient_ctx, default=str)}\n\n"
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

    def _role_description(self) -> str:
        return (
            "Conduct adaptive symptom assessment for ANY patient complaint. "
            "Ask one intelligent follow-up at a time. When enough info gathered, call assess_symptoms "
            "then handoff_to scheduling_agent for booking offer."
        )

    async def _fallback_decide(self, ctx: AgentContext) -> dict | None:
        pname = ctx.patient_ctx.get("name", "there").split()[0]
        ctx.session["_patient_first_name"] = pname
        text = ctx.text.strip()
        if text.lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please", "go ahead"}:
            for msg in reversed(ctx.history):
                if msg.get("role") not in ("user", "User"):
                    continue
                prior = (msg.get("content") or "").strip()
                if prior.lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please"}:
                    continue
                if prior:
                    return plan_triage_turn(prior, ctx.session)
        return plan_triage_turn(text, ctx.session)


class SchedulingAgent(BaseSpecialist):
    name = "scheduling_agent"
    agent_label = "appointment"

    def _role_description(self) -> str:
        return (
            "Manage appointments: search doctors, show slots, book, cancel, reschedule, reminders. "
            "When patient wants to book, IMMEDIATELY call search_doctors using recommended_specialty "
            "from session or 'General Physician' — do NOT ask what type of doctor first. "
            "Use tools for all live data. Confirm before book_slot."
        )

    async def _fallback_decide(self, ctx: AgentContext) -> dict | None:
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
            "Use recent_visits from patient context. Offer to book if worsening."
        )


class RefillAgent(BaseSpecialist):
    name = "refill_agent"
    agent_label = "refill"

    def _role_description(self) -> str:
        return "Handle prescription refill requests using get_medications and request_refill tools."


AGENTS: dict[str, BaseSpecialist] = {
    "education_agent": EducationAgent(),
    "triage_agent": TriageAgent(),
    "scheduling_agent": SchedulingAgent(),
    "report_agent": ReportAgent(),
    "followup_agent": FollowUpAgent(),
    "refill_agent": RefillAgent(),
    "safety_agent": SafetyAgent(),
}
