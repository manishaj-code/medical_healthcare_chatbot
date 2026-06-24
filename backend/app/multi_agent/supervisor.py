"""Supervisor — routes patient messages to specialist agents and manages care goals."""
from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import detect_prescription_request, get_contextual_reply
from app.emergency_detection import detect_mental_health_crisis, detect_urgent_consult
from app.healthcare_policy import (
    OFF_TOPIC_REPLY,
    build_greeting_reply,
    build_thanks_reply,
    is_active_care_flow,
    is_thanks_message,
    patient_ctx_for_llm,
    patient_first_name,
    should_reset_to_greeting,
    should_use_legacy_contextual_reply,
)
from app.models import Conversation, Patient
from app.services.flow_state import clear_flow, get_flow, set_flow
from app.services.patient_context import load_patient_context
from app.services.symptom_extraction import update_session_symptoms

from app.multi_agent.booking_actions import (
    _affirmative_booking,
    _booking_intent,
    infer_recommended_specialty,
    resolve_booking_session,
    resolve_refill_session,
    should_skip_booking_resolution,
    start_urgent_consult_from_message,
)
from app.multi_agent.llm import llm
from app.multi_agent.specialists import AGENTS, SafetyAgent, SPECIALIST_NAMES
from app.multi_agent.types import AgentContext, AgentResponse

ROUTER_PROMPT = """You are the Supervisor of a multi-agent healthcare assistant team.

Specialists:
- education_agent: general health questions, disease info, wellness (NOT personal symptom triage)
- triage_agent: patient's own symptoms, feeling unwell, pain, illness — always starts with conversation and self-care advice before any booking suggestion
- scheduling_agent: ONLY when patient explicitly asks to book, cancel, or reschedule an appointment
- report_agent: lab reports, medical documents, test results
- followup_agent: recovery check-ins after visit, post-appointment wellbeing
- refill_agent: prescription refills
- safety_agent: emergencies (usually automatic)

Given patient message, history, active specialist, and care_goal, pick the BEST specialist.

Return ONLY JSON:
{
  "specialist": "education_agent|triage_agent|scheduling_agent|report_agent|followup_agent|refill_agent",
  "care_goal": "short label of patient objective or null",
  "reason": "one line"
}

Critical routing rules:
- NEVER route to scheduling_agent just because patient described symptoms — route to triage_agent first
- Only route to scheduling_agent when patient EXPLICITLY says "book appointment", "see a doctor", "find a doctor", "cancel", or "reschedule"
- Keep active specialist if patient is mid-flow unless intent clearly changed
- If patient uploaded report or asks about lab results → report_agent
- If personal symptoms → triage_agent (even if patient might eventually want a booking)
- If appointment action explicitly requested → scheduling_agent
"""


class MultiAgentSupervisor:
    async def process(
        self,
        db: AsyncSession,
        conversation: Conversation,
        patient: Patient | None,
        user_message: str,
        history: list[dict],
        report_id: str | None = None,
        *,
        is_guest: bool = False,
        guest_session_id: str | None = None,
        patient_ctx: dict | None = None,
    ) -> tuple[str, str, bool, dict | None]:
        text = user_message.strip()
        conv_id = conversation.id
        if patient_ctx is None:
            if patient is None:
                raise ValueError("patient or patient_ctx required")
            patient_ctx = await load_patient_context(db, patient)
        flow = await get_flow(conv_id)
        session: dict = dict(flow.get("session") or {})

        self._migrate_legacy_flow(flow, session, history)

        if patient is not None:
            from app.services.report_discussion_service import rehydrate_report_discussion_session

            await rehydrate_report_discussion_session(db, session, history, patient.id, user_text=text)
            await set_flow(conv_id, {"session": session})

        if should_reset_to_greeting(text, session):
            self._reset_stale_flow_on_greeting(session)
            await set_flow(conv_id, {"session": session})
            pname = patient_first_name(patient_ctx.get("name"))
            conversation.active_agent = "health_education"
            return build_greeting_reply(pname), "health_education", False, None

        urgent_info = detect_urgent_consult(text)
        if urgent_info:
            session["skip_triage"] = True
            session["care_goal"] = "urgent_consult"
            session["active_specialist"] = "scheduling_agent"
            session["detected_symptoms"] = urgent_info.get("symptoms") or []
            session["recommended_specialty"] = urgent_info["specialty"]
            await set_flow(conv_id, {"session": session})

        contextual = (
            get_contextual_reply(text, history)
            if should_use_legacy_contextual_reply(session) and not urgent_info
            else None
        )
        if contextual:
            if not is_active_care_flow(session):
                self._reset_stale_flow_on_greeting(session)
            ui = None
            from app.services.chat_ui import (
                build_post_assessment_ui,
                build_yes_no_ui,
                infer_triage_quick_actions,
            )

            triage_ui, triage_patch = infer_triage_quick_actions(contextual, session)
            if triage_ui:
                ui = triage_ui
                session.update(triage_patch)
            elif "would you like to book an appointment" in contextual.lower():
                ui = build_post_assessment_ui()
                session["awaiting"] = "offer_booking"
                session.setdefault("care_goal", "symptom_assessment")
            elif "would you like me to show available doctors" in contextual.lower():
                ui = build_yes_no_ui(
                    yes_label="Yes, show doctors",
                    yes_message="Yes",
                    no_label="No thanks",
                    no_message="No",
                )
                session["awaiting"] = "offer_booking"
            elif "do you have any breathing" in contextual.lower():
                ui = build_yes_no_ui()
            elif "existing conditions" in contextual.lower() or "diabetes, asthma" in contextual.lower():
                ui = build_yes_no_ui(no_label="No conditions", no_message="No")
            agent = "symptom_assessment" if ui else "health_education"
            await set_flow(conv_id, {"session": session})
            conversation.active_agent = agent
            return contextual, agent, False, ui

        if is_thanks_message(text) and (
            not is_active_care_flow(session) or session.get("triage_assessed")
        ):
            self._reset_stale_flow_on_greeting(session)
            await set_flow(conv_id, {"session": session})
            pname = patient_first_name(patient_ctx.get("name"))
            conversation.active_agent = "health_education"
            return build_thanks_reply(pname), "health_education", False, None

        if session.get("detected_symptoms") and not session.get("care_goal") and not urgent_info:
            session["care_goal"] = "symptom_assessment"
            session.setdefault("active_specialist", "triage_agent")

        if not urgent_info:
            await update_session_symptoms(session, text)
        await set_flow(conv_id, {"session": session})

        if detect_prescription_request(text) and "refill" not in text.lower():
            return (
                "I cannot prescribe medications or recommend dosages. "
                "I can help request a refill for your existing prescriptions — would you like that?",
                "safety_guardrail",
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
            is_guest=is_guest,
            guest_session_id=guest_session_id,
        )

        in_refill_flow = (
            session.get("awaiting") in ("confirm_refill", "pick_refill_med")
            or (
                session.get("care_goal") == "refill"
                and session.get("active_specialist") == "refill_agent"
            )
        )
        if not in_refill_flow and _booking_intent(text, history) and not session.get("resume_after_auth"):
            from app.services.report_discussion_service import is_in_report_discussion_flow

            if not is_in_report_discussion_flow(session, history):
                session.setdefault("recommended_specialty", infer_recommended_specialty(session, history))
                session["care_goal"] = "appointment"

        if detect_mental_health_crisis(text):
            safety = await SafetyAgent().evaluate(ctx)
            if safety:
                await self._apply_session(conv_id, session, safety)
                return self._finalize(conversation, conv_id, safety, session)

        if urgent_info:
            urgent_response = await start_urgent_consult_from_message(ctx, urgent_info)
            await self._apply_session(conv_id, session, urgent_response)
            await ctx.db.commit()
            return self._finalize(conversation, conv_id, urgent_response, session)

        safety = await SafetyAgent().evaluate(ctx)
        if safety:
            return self._finalize(conversation, conv_id, safety, session)

        refill = await resolve_refill_session(ctx)
        if refill:
            await self._apply_session(conv_id, session, refill)
            return self._finalize(conversation, conv_id, refill, session)

        if not should_skip_booking_resolution(ctx):
            booking = await resolve_booking_session(ctx)
            if booking:
                await self._apply_session(conv_id, session, booking)
                return self._finalize(conversation, conv_id, booking, session)

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
            {"patient": patient_ctx_for_llm(ctx.patient_ctx), "session": ctx.session, "history": hist[-500:]},
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

        # From triage → scheduling: only when patient explicitly wants to book
        # (not just after triage assessment — self-care advice must come first)
        if active == "triage_agent":
            explicit_booking = any(w in t for w in (
                "book", "appointment", "see a doctor", "find a doctor",
                "show doctors", "available doctors", "schedule",
            ))
            offered_booking = ctx.session.get("awaiting") == "offer_booking"
            affirmative_after_offer = (
                offered_booking and (
                    self._affirmative(t) or _affirmative_booking(ctx.text) or
                    any(w in t for w in ("book", "appointment", "doctor"))
                )
            )
            if explicit_booking or affirmative_after_offer:
                ctx.session.setdefault(
                    "recommended_specialty", infer_recommended_specialty(ctx.session, ctx.history)
                )
                return "scheduling_agent"

        if active in ("education_agent", "followup_agent") and _booking_intent(ctx.text, ctx.history):
            return "scheduling_agent"

        if active == "education_agent":
            if any(w in t for w in ("hurt", "pain", "fever", "symptom", "sick", "cough", "feel unwell", "not feeling", "feel ill", "feel bad")):
                return "triage_agent"
            if self._affirmative(t) and self._assessment_offered(ctx.history):
                return "triage_agent"

        if active == "scheduling_agent" and any(w in t for w in ("symptom", "pain", "fever", "hurt", "feel unwell", "not feeling", "feel ill", "feel bad")):
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
            symptoms = ctx.session.get("detected_symptoms") or extract_symptoms(
                content, collected.get("symptoms"), session=ctx.session
            )
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
        if any(w in t for w in ("book", "appointment", "cancel", "reschedule", "reminder", "doctor")):
            return {"specialist": "scheduling_agent", "care_goal": "appointment"}
        if any(w in t for w in ("report", "lab", "cbc", "blood test")):
            return {"specialist": "report_agent", "care_goal": "report"}
        if any(w in t for w in ("refill", "prescription")):
            return {"specialist": "refill_agent", "care_goal": "refill"}
        if any(w in t for w in ("follow up", "recovery", "feeling after")):
            return {"specialist": "followup_agent", "care_goal": "followup"}
        if any(w in t for w in ("hurt", "pain", "fever", "symptom", "sick", "cough", "feel unwell", "not feeling", "feel ill", "feel bad")):
            return {"specialist": "triage_agent", "care_goal": "symptom_assessment"}
        return {"specialist": "education_agent", "care_goal": "health_question"}

    @staticmethod
    def _reset_stale_flow_on_greeting(session: dict) -> None:
        """Clear stuck refill/triage state so greetings get a friendly reply."""
        for key in (
            "active_specialist",
            "care_goal",
            "awaiting",
            "refill_medication",
            "detected_symptoms",
            "triage_collected",
            "assessment_shown",
            "triage_assessed",
            "booking_declined",
        ):
            session.pop(key, None)

    def _migrate_legacy_flow(self, flow: dict, session: dict, history: list[dict]) -> None:
        from app.services.report_discussion_service import history_has_report_discussion_offer

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
            if history_has_report_discussion_offer(history):
                session["awaiting"] = "report_followup"
                session["care_goal"] = "report_discussion"
                session.setdefault("active_specialist", "report_agent")
            else:
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
        patch = response.session_patch or {}
        if response.agent == "scheduling_agent":
            session["active_specialist"] = "scheduling_agent"
        elif response.agent == "refill_agent" and patch.get("care_goal") is not None:
            session["active_specialist"] = "refill_agent"
        await set_flow(conv_id, {"session": session})


multi_agent_supervisor = MultiAgentSupervisor()
