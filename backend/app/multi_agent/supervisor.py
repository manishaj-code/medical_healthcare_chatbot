"""Supervisor — routes patient messages to specialist agents and manages care goals."""
from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import detect_prescription_request
from app.healthcare_policy import OFF_TOPIC_REPLY
from app.models import Conversation, Patient
from app.services.flow_state import clear_flow, get_flow, set_flow
from app.services.patient_context import load_patient_context

from app.multi_agent.booking_actions import (
    _affirmative_booking,
    _booking_intent,
    infer_recommended_specialty,
    resolve_booking_session,
    should_skip_booking_resolution,
)
from app.multi_agent.llm import llm
from app.multi_agent.specialists import AGENTS, SafetyAgent, SPECIALIST_NAMES
from app.multi_agent.types import AgentContext, AgentResponse

ROUTER_PROMPT = """You are the Supervisor of a multi-agent healthcare assistant team.

Specialists:
- education_agent: general health questions, disease info, wellness (NOT personal symptom triage)
- triage_agent: patient's own symptoms, feeling unwell, pain, illness assessment
- scheduling_agent: book, cancel, reschedule appointments, find doctors/slots
- report_agent: lab reports, medical documents, test results
- followup_agent: recovery after visit, check-in after appointment
- refill_agent: prescription refills
- safety_agent: emergencies (usually automatic)

Given patient message, history, active specialist, and care_goal, pick the BEST specialist.

Return ONLY JSON:
{
  "specialist": "education_agent|triage_agent|scheduling_agent|report_agent|followup_agent|refill_agent",
  "care_goal": "short label of patient objective or null",
  "reason": "one line"
}

Keep active specialist if patient is mid-flow unless intent clearly changed.
If patient uploaded report or asks about lab results → report_agent.
If personal symptoms → triage_agent.
If appointment action → scheduling_agent.
"""


class MultiAgentSupervisor:
    async def process(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient,
        user_message: str,
        history: list[dict],
        report_id: str | None = None,
    ) -> tuple[str, str, bool, dict | None]:
        text = user_message.strip()
        conv_id = conversation.id
        patient_ctx = await load_patient_context(db, patient)
        flow = await get_flow(conv_id)
        session: dict = dict(flow.get("session") or {})

        self._migrate_legacy_flow(flow, session, history)

        if detect_prescription_request(text) and "refill" not in text.lower():
            return (
                "I cannot prescribe medications or recommend dosages. "
                "I can help request a refill for your existing prescriptions — would you like that?",
                "safety_guardrail",
                False,
                None,
            )

        if not llm.available:
            name = patient_ctx.get("name", "there").split()[0]
            return (
                f"Hi {name}, please configure GEMINI_API_KEY or GROQ_API_KEY for the multi-agent assistant.",
                "conversation",
                False,
                None,
            )

        ctx = AgentContext(
            db=db,
            conversation=conversation,
            patient=patient,
            conv_id=conv_id,
            text=text,
            history=history,
            patient_ctx=patient_ctx,
            session=session,
            report_id=report_id,
        )

        if _booking_intent(text, history):
            session.setdefault("recommended_specialty", infer_recommended_specialty(session, history))
            session["care_goal"] = "appointment"

        if not should_skip_booking_resolution(ctx):
            booking = await resolve_booking_session(ctx)
            if booking:
                await self._apply_session(conv_id, session, booking)
                return self._finalize(conversation, conv_id, booking, session)

        safety = await SafetyAgent().evaluate(ctx)
        if safety:
            return self._finalize(conversation, conv_id, safety, session)

        if report_id:
            ctx.session["active_specialist"] = "report_agent"
            ctx.session["care_goal"] = "analyze_report"
        elif not ctx.session.get("active_specialist"):
            route = await self._route(ctx)
            if route.get("off_topic"):
                conversation.active_agent = "scope_guardrail"
                return OFF_TOPIC_REPLY, "scope_guardrail", False, None
            ctx.session["active_specialist"] = route.get("specialist", "education_agent")
            if route.get("care_goal"):
                ctx.session["care_goal"] = route["care_goal"]
        else:
            switch = await self._should_switch(ctx)
            if switch:
                ctx.session["active_specialist"] = switch
                if switch == "triage_agent":
                    self._seed_triage_from_history(ctx)

        specialist_name = ctx.session.get("active_specialist", "education_agent")
        if specialist_name not in AGENTS:
            specialist_name = "education_agent"

        ctx.session["active_specialist"] = specialist_name
        await set_flow(conv_id, {"session": ctx.session})

        agent = AGENTS[specialist_name]
        response = await agent.run(ctx)

        if response.handoff_to and response.handoff_to in AGENTS:
            ctx.session["active_specialist"] = response.handoff_to
            if response.session_patch:
                ctx.session.update(response.session_patch)
            await set_flow(conv_id, {"session": ctx.session})
            handoff_agent = AGENTS[response.handoff_to]
            response = await handoff_agent.run(ctx)

        await self._apply_session(conv_id, ctx.session, response)
        return self._finalize(conversation, conv_id, response, ctx.session)

    async def _route(self, ctx: AgentContext) -> dict:
        if ctx.report_id:
            return {"specialist": "report_agent", "care_goal": "analyze_report"}
        hist = "\n".join(f"{h['role']}: {h['content']}" for h in ctx.history[-8:])
        payload = json.dumps(
            {"patient": ctx.patient_ctx, "session": ctx.session, "history": hist[-500:]},
            default=str,
        )
        prompt = f"{ROUTER_PROMPT}\n\nCONTEXT:\n{payload}\n\nMESSAGE: {ctx.text}\n\nJSON:"
        decision = await llm.json_prompt(prompt)
        if not decision:
            return self._route_fallback(ctx.text)
        if decision.get("specialist") not in SPECIALIST_NAMES:
            decision["specialist"] = self._route_fallback(ctx.text)["specialist"]
        return decision

    async def _should_switch(self, ctx: AgentContext) -> str | None:
        t = ctx.text.lower()
        active = ctx.session.get("active_specialist")
        if active == "triage_agent" and (
            _booking_intent(ctx.text, ctx.history)
            or (
                ctx.session.get("awaiting") == "offer_booking"
                and (self._affirmative(t) or _affirmative_booking(ctx.text) or any(w in t for w in ("book", "appointment", "doctor")))
            )
        ):
            ctx.session.setdefault(
                "recommended_specialty", infer_recommended_specialty(ctx.session, ctx.history)
            )
            return "scheduling_agent"
        if active in ("education_agent", "followup_agent") and _booking_intent(ctx.text, ctx.history):
            return "scheduling_agent"
        if active == "education_agent":
            if any(w in t for w in ("hurt", "pain", "fever", "symptom", "sick", "cough", "feel unwell", "not feeling")):
                return "triage_agent"
            if self._affirmative(t) and self._assessment_offered(ctx.history):
                return "triage_agent"
        if active == "scheduling_agent" and any(w in t for w in ("symptom", "pain", "fever", "hurt", "feel")):
            if not ctx.session.get("awaiting"):
                return "triage_agent"
        if any(w in t for w in ("report", "lab result", "blood test", "cbc")):
            return "report_agent"
        if any(w in t for w in ("refill", "prescription refill")):
            return "refill_agent"
        if any(w in t for w in ("follow up", "follow-up", "how am i doing", "recovery")):
            return "followup_agent"
        return None

    @staticmethod
    def _affirmative(text: str) -> bool:
        return text.strip().lower() in {
            "yes", "yeah", "sure", "ok", "okay", "yep", "please", "yes please", "go ahead",
        }

    @staticmethod
    def _assessment_offered(history: list[dict]) -> bool:
        for msg in reversed(history[-6:]):
            if msg.get("role") not in ("assistant", "Assistant"):
                continue
            content = (msg.get("content") or "").lower()
            if "assess your symptoms" in content or "symptom assessment" in content:
                return True
            break
        return False

    def _seed_triage_from_history(self, ctx: AgentContext) -> None:
        from app.multi_agent.offline_fallback import extract_duration, extract_symptoms

        collected = ctx.session.setdefault("triage_collected", {})
        notes = list(collected.get("notes") or [])
        for msg in reversed(ctx.history):
            if msg.get("role") not in ("user", "User"):
                continue
            content = (msg.get("content") or "").strip()
            if not content or self._affirmative(content):
                continue
            symptoms = extract_symptoms(content, collected.get("symptoms"))
            if symptoms and symptoms != ["unspecified symptoms"]:
                if content not in notes:
                    notes.append(content)
                collected["notes"] = notes[-6:]
                collected["symptoms"] = symptoms
                duration = extract_duration(content) or extract_duration(" ".join(notes))
                if duration:
                    collected["duration"] = duration
                break

    def _route_fallback(self, text: str) -> dict:
        t = text.lower()
        if any(w in t for w in ("book", "appointment", "cancel", "reschedule", "doctor")):
            return {"specialist": "scheduling_agent", "care_goal": "appointment"}
        if any(w in t for w in ("report", "lab", "cbc", "blood test")):
            return {"specialist": "report_agent", "care_goal": "report"}
        if any(w in t for w in ("refill", "prescription")):
            return {"specialist": "refill_agent", "care_goal": "refill"}
        if any(w in t for w in ("follow up", "recovery", "feeling after")):
            return {"specialist": "followup_agent", "care_goal": "followup"}
        if any(w in t for w in ("hurt", "pain", "fever", "symptom", "sick", "cough", "feel")):
            return {"specialist": "triage_agent", "care_goal": "symptom_assessment"}
        return {"specialist": "education_agent", "care_goal": "health_question"}

    def _migrate_legacy_flow(self, flow: dict, session: dict, history: list[dict]) -> None:
        if flow.get("task") == "triage" and flow.get("step") == "offer":
            data = flow.get("data") or {}
            session.setdefault("awaiting", "offer_booking")
            session.setdefault("recommended_specialty", data.get("recommended_specialty", "General Physician"))
            session.setdefault("active_specialist", "scheduling_agent")
        elif flow.get("task") == "booking":
            session.setdefault("active_specialist", "scheduling_agent")
            session.setdefault("last_doctor_search", {
                "doctors": (flow.get("data") or {}).get("doctors", []),
                "all_slots": (flow.get("data") or {}).get("all_slots", []),
            })
        if not session.get("awaiting"):
            for msg in reversed(history[-8:]):
                if msg.get("role") not in ("assistant", "Assistant"):
                    continue
                content = (msg.get("content") or "").lower()
                if "would you like me to show available doctors" in content:
                    session["awaiting"] = "offer_booking"
                    session.setdefault("active_specialist", "scheduling_agent")
                    spec = re.search(r"recommend(?:ed)? seeing a ([^.]+)\.", msg.get("content") or "", re.I)
                    if spec:
                        session.setdefault("recommended_specialty", spec.group(1).strip())
                break

    def _finalize(
        self,
        conversation: Conversation,
        conv_id,
        response: AgentResponse,
        session: dict | None = None,
    ) -> tuple[str, str, bool, dict | None]:
        conversation.active_agent = response.agent
        if response.emergency:
            conversation.emergency_flag = True
        return response.reply, response.agent, response.emergency, response.ui

    async def _apply_session(
        self,
        conv_id,
        session: dict,
        response: AgentResponse,
    ) -> None:
        if response.clear_session:
            await clear_flow(conv_id)
            return
        if response.session_patch:
            for key, value in response.session_patch.items():
                if value is None:
                    session.pop(key, None)
                else:
                    session[key] = value
        if response.agent == "scheduling_agent":
            session["active_specialist"] = "scheduling_agent"
        await set_flow(conv_id, {"session": session})


multi_agent_supervisor = MultiAgentSupervisor()
