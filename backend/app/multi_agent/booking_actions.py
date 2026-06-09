"""Booking action execution — structural UI picks, not symptom workflows."""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Appointment, Doctor, User
from app.models.enums import AppointmentStatus
from app.services.appointment_service import format_apt_id
from app.services.agent_tools import (
    _match_doctor,
    match_slot_from_text,
    slot_for_storage,
    tool_book_slot,
    tool_cancel_appointment,
    tool_get_doctor_slots,
    tool_reschedule,
    tool_get_medications,
    tool_request_refill,
    tool_reschedule_alternatives,
    tool_schedule_reminder,
    tool_search_doctors,
)
from app.services.chat_ui import (
    build_appointment_confirmed_ui,
    build_booking_offer_ui,
    build_confirm_booking_ui,
    build_confirm_reschedule_ui,
    build_doctor_list_ui,
    build_slot_list_ui,
    build_yes_no_ui,
    doctor_list_intro,
    slot_list_intro,
)
from app.services.flow_state import clear_flow, set_flow
from app.services.symptom_service import assess_symptoms

from app.multi_agent.types import AgentContext, AgentResponse

SPECIALTY_ALIASES: dict[str, str] = {
    "general physician": "General Physician",
    "general doctor": "General Physician",
    "family doctor": "General Physician",
    "gp": "General Physician",
    "primary care": "General Physician",
    "cardiologist": "Cardiologist",
    "neurologist": "Neurologist",
    "dermatologist": "Dermatologist",
    "pediatrician": "Pediatrician",
    "gastroenterologist": "Gastroenterologist",
    "psychiatrist": "Psychiatrist",
    "orthopedist": "Orthopedist",
    "emergency": "Emergency",
}


def _yes(text: str) -> bool:
    return text.strip().lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "confirm", "please", "yes please"}


def _extract_apt_display_id(text: str) -> str | None:
    match = re.search(r"APT-[A-F0-9]{5}", text, re.I)
    return match.group(0).upper() if match else None


async def _find_appointment(ctx: AgentContext, apt_display: str | None = None) -> Appointment | None:
    if apt_display:
        result = await ctx.db.execute(
            select(Appointment).where(
                Appointment.patient_id == ctx.patient.id,
                Appointment.status == AppointmentStatus.confirmed,
            )
        )
        for appt in result.scalars().all():
            if format_apt_id(appt.id) == apt_display:
                return appt

    for key in ("manage_appointment_id", "last_appointment_id"):
        raw = ctx.session.get(key)
        if raw:
            result = await ctx.db.execute(
                select(Appointment).where(
                    Appointment.id == UUID(str(raw)),
                    Appointment.patient_id == ctx.patient.id,
                    Appointment.status == AppointmentStatus.confirmed,
                )
            )
            appt = result.scalar_one_or_none()
            if appt:
                return appt
    return None


def _wants_cancel_appointment(text: str) -> bool:
    t = text.strip().lower()
    return "cancel" in t and "appointment" in t


def _wants_reschedule_appointment(text: str) -> bool:
    t = text.strip().lower()
    return "reschedule" in t and "appointment" in t


async def _handle_cancel_appointment(ctx: AgentContext) -> AgentResponse | None:
    session = ctx.session
    awaiting = session.get("awaiting")

    if awaiting == "confirm_cancel":
        appt = await _find_appointment(ctx)
        if _yes(ctx.text) and appt:
            result = await tool_cancel_appointment(ctx.db, ctx.patient.id, appt.id)
            if result.get("success"):
                return AgentResponse(
                    reply=f"✅ Appointment **{result['apt_id']}** has been cancelled.\n\nWould you like to book a new appointment?",
                    agent="scheduling_agent",
                    session_patch={
                        "awaiting": None,
                        "care_goal": None,
                        "manage_appointment_id": None,
                        "last_appointment_id": None,
                    },
                )
        if _no(ctx.text):
            return AgentResponse(
                reply="No problem — your appointment is still confirmed.",
                agent="scheduling_agent",
                session_patch={"awaiting": None, "manage_appointment_id": None},
            )
        return AgentResponse(
            reply="Please reply **Yes** to cancel or **No** to keep your appointment.",
            agent="scheduling_agent",
        )

    if not _wants_cancel_appointment(ctx.text):
        return None

    appt = await _find_appointment(ctx, _extract_apt_display_id(ctx.text))
    if not appt:
        return AgentResponse(
            reply="I couldn't find an active appointment to cancel.",
            agent="scheduling_agent",
        )

    doctor = await ctx.db.get(Doctor, appt.doctor_id)
    doctor_user = await ctx.db.get(User, doctor.user_id) if doctor else None
    doctor_name = doctor_user.name if doctor_user else "your doctor"
    label = f"{appt.slot_date.strftime('%a %d %b')} {appt.slot_time.strftime('%I:%M %p').lstrip('0')}"

    return AgentResponse(
        reply=(
            f"Cancel this appointment?\n\n"
            f"**{format_apt_id(appt.id)}** with **{doctor_name}**\n"
            f"**{label}**\n\n"
            f"Reply **Yes** to cancel or **No** to keep it."
        ),
        agent="scheduling_agent",
        session_patch={
            "awaiting": "confirm_cancel",
            "manage_appointment_id": str(appt.id),
            "care_goal": "manage_appointment",
        },
    )


async def _handle_reschedule_appointment(ctx: AgentContext) -> AgentResponse | None:
    session = ctx.session
    awaiting = session.get("awaiting")

    if awaiting == "confirm_reschedule" and _yes(ctx.text):
        pending = session.get("pending_slot")
        appt_id = session.get("manage_appointment_id")
        if pending and appt_id:
            try:
                result = await tool_reschedule(
                    ctx.db,
                    ctx.patient.id,
                    ctx.patient.user_id,
                    UUID(str(appt_id)),
                    pending,
                )
            except HTTPException as exc:
                return AgentResponse(
                    reply=f"Sorry, that slot is no longer available ({exc.detail}). Please pick another time.",
                    agent="scheduling_agent",
                    session_patch={"awaiting": "reschedule_pick_slot"},
                )
            if result.get("success"):
                ui = build_appointment_confirmed_ui(
                    {
                        "appointment_id": appt_id,
                        "apt_id": result.get("apt_id"),
                        "doctor_name": session.get("reschedule_doctor_name", "Doctor"),
                        "label": result.get("label", ""),
                    }
                )
                return AgentResponse(
                    reply=(
                        f"✅ Appointment rescheduled to **{result.get('label', 'the new time')}**.\n\n"
                        f"Appointment ID: **{result.get('apt_id', '')}**"
                    ),
                    agent="scheduling_agent",
                    ui=ui,
                    session_patch={
                        "awaiting": None,
                        "care_goal": None,
                        "pending_slot": None,
                        "manage_appointment_id": appt_id,
                        "last_appointment_id": appt_id,
                    },
                )
        return AgentResponse(reply="Something went wrong. Please pick a time again.", agent="scheduling_agent")

    if awaiting == "confirm_reschedule" and _no(ctx.text):
        return AgentResponse(
            reply="Reschedule cancelled. Your original appointment time is unchanged.",
            agent="scheduling_agent",
            session_patch={"awaiting": None, "pending_slot": None},
        )

    if awaiting == "reschedule_pick_slot":
        alt = session.get("reschedule_alternatives") or []
        doctor_id = session.get("reschedule_doctor_id")
        chosen = match_slot_from_text(ctx.text, alt, doctor_id=str(doctor_id) if doctor_id else None)
        if chosen:
            stored = slot_for_storage(chosen)
            current = session.get("reschedule_current", "your current time")
            return AgentResponse(
                reply=(
                    f"Confirm rescheduling?\n\n"
                    f"Current: **{current}**\n"
                    f"New: **{stored['label']}**"
                ),
                agent="scheduling_agent",
                ui=build_confirm_reschedule_ui(current, stored["label"]),
                session_patch={"awaiting": "confirm_reschedule", "pending_slot": stored},
            )
        return AgentResponse(
            reply="Please pick one of the available times shown above.",
            agent="scheduling_agent",
        )

    if not _wants_reschedule_appointment(ctx.text):
        return None

    appt = await _find_appointment(ctx, _extract_apt_display_id(ctx.text))
    if not appt:
        return AgentResponse(
            reply="I couldn't find an active appointment to reschedule.",
            agent="scheduling_agent",
        )

    alt_result = await tool_reschedule_alternatives(ctx.db, ctx.patient.id, appt.id)
    if not alt_result.get("success"):
        return AgentResponse(
            reply=alt_result.get("message", "No appointment available to reschedule."),
            agent="scheduling_agent",
        )

    alternatives = alt_result.get("alternatives", [])
    if not alternatives:
        return AgentResponse(
            reply=f"No other open slots for **{alt_result.get('doctor_name', 'this doctor')}** right now. Try again later.",
            agent="scheduling_agent",
        )

    return AgentResponse(
        reply=(
            f"Reschedule **{alt_result.get('apt_id', '')}** with **{alt_result.get('doctor_name', 'Doctor')}**\n\n"
            f"Current time: **{alt_result.get('current', '')}**\n\n"
            f"Pick a new time:"
        ),
        agent="scheduling_agent",
        ui=build_slot_list_ui(
            alt_result.get("doctor_name", "Doctor"),
            str(appt.doctor_id),
            alternatives,
        ),
        session_patch={
            "awaiting": "reschedule_pick_slot",
            "manage_appointment_id": str(appt.id),
            "reschedule_doctor_id": str(appt.doctor_id),
            "reschedule_doctor_name": alt_result.get("doctor_name", "Doctor"),
            "reschedule_current": alt_result.get("current", ""),
            "reschedule_alternatives": alternatives,
            "care_goal": "manage_appointment",
        },
    )


def _wants_reminder(text: str) -> bool:
    t = text.strip().lower()
    return "reminder" in t


def _affirmative_booking(text: str, history: list[dict] | None = None) -> bool:
    """Yes/affirmative phrasing that includes booking intent (not exact 'yes' only)."""
    t = text.strip().lower()
    if history and _last_assistant_offered_reminder(history) and _yes(t):
        return False
    if history and _last_assistant_awaiting_confirm(history) and _yes(t):
        return False
    if history and _last_assistant_refill_confirm(history) and _yes(t):
        return False
    if _yes(t):
        return True
    if t.startswith(("yes ", "yes,", "yeah ", "sure ", "ok ", "okay ")):
        return any(w in t for w in ("book", "appointment", "doctor", "schedule", "show"))
    return False


def _last_assistant_content(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg.get("role") in ("assistant", "Assistant"):
            return (msg.get("content") or "").lower()
    return ""


def _last_assistant_awaiting_confirm(history: list[dict]) -> bool:
    content = _last_assistant_content(history)
    return "before booking, please confirm" in content or (
        "confirm booking" in content and ("yes/no" in content or "please confirm" in content)
    )


def _last_assistant_refill_confirm(history: list[dict]) -> bool:
    content = _last_assistant_content(history)
    return "refill request" in content or "submit a refill" in content or "submit this to your doctor" in content


def _last_assistant_offered_reminder(history: list[dict]) -> bool:
    content = _last_assistant_content(history)
    return "reminder" in content and "30 minutes" in content


def _recover_pending_slot(ctx: AgentContext) -> dict | None:
    pending = ctx.session.get("pending_slot")
    if pending:
        return slot_for_storage(pending)

    search = ctx.session.get("last_doctor_search") or {}
    all_slots = search.get("all_slots") or [
        s for d in search.get("doctors", []) for s in d.get("slots", [])
    ]
    selected = ctx.session.get("selected_doctor")
    doctor_id = str(selected["id"]) if selected else None
    if doctor_id:
        all_slots = [s for s in all_slots if str(s.get("doctor_id")) == doctor_id]
    if not all_slots:
        return None

    for msg in reversed(ctx.history):
        if msg.get("role") not in ("user", "User"):
            continue
        content = (msg.get("content") or "").strip()
        if not content or _yes(content):
            continue
        chosen = match_slot_from_text(content, all_slots, doctor_id=doctor_id)
        if chosen:
            return slot_for_storage(chosen)
        break
    return None


def _booking_intent(text: str, history: list[dict] | None = None) -> bool:
    """Patient wants to book or see available doctors."""
    t = text.strip().lower()
    if history and _last_assistant_offered_reminder(history) and _yes(t):
        return False
    if history and _last_assistant_awaiting_confirm(history) and _yes(t):
        return False
    if history and _last_assistant_refill_confirm(history) and _yes(t):
        return False
    if any(w in t for w in ("cancel", "reschedule")):
        return False
    phrases = (
        "book appointment", "book an appointment", "want to book", "wanna book",
        "schedule appointment", "make appointment", "show doctors", "show available doctors",
        "see a doctor", "find a doctor", "list doctors", "available doctors",
    )
    if any(p in t for p in phrases):
        return True
    return _affirmative_booking(t, history)


def _no(text: str) -> bool:
    t = text.strip().lower()
    return t in {"no", "nope", "nah", "not now", "later"} or t.startswith("no ")


def _last_assistant_was_booking_offer(history: list[dict]) -> bool:
    for msg in reversed(history[-6:]):
        if msg.get("role") not in ("assistant", "Assistant"):
            continue
        content = (msg.get("content") or "").lower()
        return "show available doctors" in content or "book an appointment" in content
    return False


def _parse_specialty_from_text(text: str) -> str | None:
    t = text.strip().lower()
    for alias, canonical in sorted(SPECIALTY_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in t:
            return canonical
    return None


def infer_recommended_specialty(session: dict, history: list[dict]) -> str:
    """Pick specialist type from triage — patient should never need to choose."""
    if session.get("recommended_specialty"):
        return session["recommended_specialty"]

    collected = session.get("triage_collected") or {}
    symptoms = collected.get("symptoms") or []
    if symptoms and symptoms != ["unspecified symptoms"]:
        return assess_symptoms(symptoms, collected.get("duration"), None)["recommended_specialty"]

    from app.multi_agent.offline_fallback import extract_symptoms

    user_text = " ".join(
        m.get("content", "") for m in history if m.get("role") in ("user", "User")
    )
    symptoms = extract_symptoms(user_text)
    if symptoms and symptoms != ["unspecified symptoms"]:
        return assess_symptoms(symptoms, None, None)["recommended_specialty"]

    return "General Physician"


async def _show_doctor_list(
    ctx: AgentContext,
    specialty: str,
    *,
    intro: str | None = None,
) -> AgentResponse:
    search = await tool_search_doctors(ctx.db, specialty)
    doctors = search.get("doctors", [])
    if not doctors:
        return AgentResponse(
            reply="I couldn't find doctors with open slots right now. Would you like me to search all specialties?",
            agent="scheduling_agent",
        )
    pname = ctx.patient_ctx.get("name", "there").split()[0]
    list_line = doctor_list_intro(len(doctors))
    reply = f"{intro} {list_line}".strip() if intro else (
        f"Based on your symptoms, {pname}, I recommend a **{specialty}**. {list_line}"
    )
    return AgentResponse(
        reply=reply,
        agent="scheduling_agent",
        ui=build_doctor_list_ui(search),
        session_patch={
            "last_doctor_search": search,
            "awaiting": "pick_doctor",
            "care_goal": "appointment",
            "recommended_specialty": specialty,
        },
    )


def should_skip_booking_resolution(ctx: AgentContext) -> bool:
    """Triage answers like 'no' must not be treated as booking decline."""
    if (
        ctx.session.get("care_goal") == "refill"
        or ctx.session.get("awaiting") in ("confirm_refill", "pick_refill_med")
        or ctx.session.get("active_specialist") == "refill_agent"
        or _last_assistant_refill_confirm(ctx.history)
    ):
        return True
    if (
        ctx.session.get("care_goal") in ("post_booking_reminder", "manage_appointment")
        or ctx.session.get("awaiting") in ("confirm_cancel", "reschedule_pick_slot", "confirm_reschedule")
        or _wants_reminder(ctx.text)
        or _wants_cancel_appointment(ctx.text)
        or _wants_reschedule_appointment(ctx.text)
        or _last_assistant_offered_reminder(ctx.history)
        or _last_assistant_awaiting_confirm(ctx.history)
        or _booking_intent(ctx.text, ctx.history)
        or _parse_specialty_from_text(ctx.text)
    ):
        return False
    if ctx.session.get("care_goal") == "symptom_assessment":
        return True
    if _no(ctx.text) and ctx.session.get("awaiting") != "offer_booking":
        return True
    return False


async def resolve_booking_session(ctx: AgentContext) -> AgentResponse | None:
    session = ctx.session
    awaiting = session.get("awaiting")
    pname = ctx.patient_ctx.get("name", "Patient").split()[0]

    cancel_resp = await _handle_cancel_appointment(ctx)
    if cancel_resp:
        return cancel_resp
    reschedule_resp = await _handle_reschedule_appointment(ctx)
    if reschedule_resp:
        return reschedule_resp

    if should_skip_booking_resolution(ctx):
        return None

    specialty_input = _parse_specialty_from_text(ctx.text)
    if specialty_input and awaiting not in ("confirm_booking", "pick_slot"):
        return await _show_doctor_list(ctx, specialty_input)

    if _booking_intent(ctx.text, ctx.history) and awaiting not in ("confirm_booking", "pick_slot"):
        specialty = infer_recommended_specialty(session, ctx.history)
        return await _show_doctor_list(
            ctx,
            specialty,
            intro=f"Of course, {pname}! Based on your symptoms, I recommend a **{specialty}**.",
        )

    if session.get("care_goal") == "post_booking_reminder" or _last_assistant_offered_reminder(ctx.history) or _wants_reminder(ctx.text):
        apt_display = _extract_apt_display_id(ctx.text)
        appt = await _find_appointment(ctx, apt_display)
        apt_id = appt.id if appt else session.get("last_appointment_id")
        if apt_id and (_yes(ctx.text) or _wants_reminder(ctx.text)):
            await tool_schedule_reminder(ctx.db, ctx.patient.user_id, UUID(str(apt_id)))
            return AgentResponse(
                reply="✅ Reminder set! You'll be notified 30 minutes before your appointment.",
                agent="scheduling_agent",
                session_patch={
                    "care_goal": None,
                    "awaiting": None,
                    "pending_slot": None,
                    "last_appointment_id": None,
                },
            )
        if _no(ctx.text):
            return AgentResponse(
                reply="No problem! Your appointment is confirmed. Take care!",
                agent="scheduling_agent",
                session_patch={
                    "care_goal": None,
                    "awaiting": None,
                    "pending_slot": None,
                },
            )

    confirming = (
        awaiting == "confirm_booking" or _last_assistant_awaiting_confirm(ctx.history)
    ) and session.get("care_goal") != "post_booking_reminder"
    if confirming and _yes(ctx.text):
        pending = _recover_pending_slot(ctx)
        if pending:
            try:
                result = await tool_book_slot(ctx.db, ctx.patient, ctx.patient.user_id, pending, ctx.conv_id)
            except HTTPException as exc:
                return AgentResponse(
                    reply=(
                        f"Sorry, that slot could not be booked ({exc.detail}). "
                        "Please pick another time from the list."
                    ),
                    agent="scheduling_agent",
                    session_patch={"awaiting": "pick_slot", "pending_slot": None},
                )
            if result.get("success"):
                return AgentResponse(
                    reply=(
                        f"✅ Appointment Successfully Booked\n\n"
                        f"Appointment ID: {result['apt_id']}\n"
                        f"Doctor: {result['doctor_name']}\n"
                        f"Date & Time: {result['label']}\n\n"
                        f"Use the **Reminder**, **Reschedule**, or **Cancel** buttons beside your appointment details."
                    ),
                    agent="scheduling_agent",
                    ui=build_appointment_confirmed_ui(result),
                    session_patch={
                        "care_goal": "post_booking_reminder",
                        "last_appointment_id": result.get("appointment_id"),
                        "awaiting": "offer_reminder",
                        "pending_slot": None,
                    },
                )

    if awaiting == "confirm_booking" and _no(ctx.text):
            await clear_flow(ctx.conv_id)
            return AgentResponse(
                reply="Booking cancelled. Let me know if you'd like to choose another time.",
                agent="scheduling_agent",
                clear_session=True,
            )

    if awaiting == "pick_slot" and session.get("selected_doctor"):
        doc = session["selected_doctor"]
        slots_result = await tool_get_doctor_slots(ctx.db, UUID(doc["id"]))
        chosen = match_slot_from_text(
            ctx.text,
            slots_result.get("slots", []),
            doctor_id=str(doc["id"]),
        )
        if chosen:
            stored = slot_for_storage(chosen)
            doc_name = stored.get("doctor_name", doc["name"])
            return AgentResponse(
                reply=(
                    f"Before booking, please confirm:\n\nPatient Name: {ctx.patient_ctx['name']}\n"
                    f"Doctor: {doc_name}\n"
                    f"Date & Time: {stored['label']}"
                ),
                agent="scheduling_agent",
                ui=build_confirm_booking_ui(ctx.patient_ctx["name"], doc_name, stored["label"]),
                session_patch={"awaiting": "confirm_booking", "pending_slot": stored},
            )

    if awaiting in ("offer_booking", "pick_doctor"):
        specialty = session.get("recommended_specialty") or infer_recommended_specialty(session, ctx.history)
        search = session.get("last_doctor_search")
        if not search:
            search = await tool_search_doctors(ctx.db, specialty)
            session["last_doctor_search"] = search
            await set_flow(ctx.conv_id, {"session": session})

        doctors = search.get("doctors", [])
        all_slots = search.get("all_slots") or [s for d in doctors for s in d.get("slots", [])]
        doctor_rows = [
            {"id": UUID(d["id"]), "name": d["name"], "specializations": [d["specialty"]]}
            for d in doctors
        ]

        if _no(ctx.text) and awaiting == "offer_booking" and _last_assistant_was_booking_offer(ctx.history):
            await clear_flow(ctx.conv_id)
            return AgentResponse(
                reply=f"No problem, {pname}. Rest well. I'm here whenever you need to book a visit.",
                agent="triage_agent",
                clear_session=True,
            )

        chosen = match_slot_from_text(ctx.text, all_slots)
        if chosen:
            stored = slot_for_storage(chosen)
            session["pending_slot"] = stored
            session["awaiting"] = "confirm_booking"
            await set_flow(ctx.conv_id, {"session": session})
            doc_name = stored.get("doctor_name", "")
            return AgentResponse(
                reply=(
                    f"Before booking, please confirm:\n\nPatient Name: {ctx.patient_ctx['name']}\n"
                    f"Doctor: {doc_name}\nDate & Time: {stored['label']}"
                ),
                agent="scheduling_agent",
                ui=build_confirm_booking_ui(ctx.patient_ctx["name"], doc_name, stored["label"]),
                session_patch={"awaiting": "confirm_booking", "pending_slot": stored},
            )

        doc = _match_doctor(ctx.text, doctor_rows)
        if doc:
            slots_result = await tool_get_doctor_slots(ctx.db, UUID(str(doc["id"])))
            slots = slots_result.get("slots", [])
            if not slots:
                return AgentResponse(reply=f"No open slots for {doc['name']} right now.", agent="scheduling_agent")
            return AgentResponse(
                reply=slot_list_intro(doc["name"]),
                agent="scheduling_agent",
                ui=build_slot_list_ui(doc["name"], str(doc["id"]), slots),
                session_patch={
                    "awaiting": "pick_slot",
                    "selected_doctor": {"id": str(doc["id"]), "name": doc["name"]},
                },
            )

        if (_yes(ctx.text) or _affirmative_booking(ctx.text, ctx.history)) and awaiting == "offer_booking":
            return await _show_doctor_list(
                ctx,
                specialty,
                intro=(
                    f"Great, {pname}! Based on your symptoms, here are available "
                    f"**{specialty}** doctors. {doctor_list_intro(len(doctors))}"
                ),
            )

    if awaiting == "pick_doctor":
        search = session.get("last_doctor_search") or {}
        doctors = search.get("doctors", [])
        doctor_rows = [
            {"id": UUID(d["id"]), "name": d["name"], "specializations": [d["specialty"]]}
            for d in doctors
        ]
        doc = _match_doctor(ctx.text, doctor_rows)
        if doc:
            slots_result = await tool_get_doctor_slots(ctx.db, UUID(str(doc["id"])))
            slots = slots_result.get("slots", [])
            return AgentResponse(
                reply=slot_list_intro(doc["name"]),
                agent="scheduling_agent",
                ui=build_slot_list_ui(doc["name"], str(doc["id"]), slots),
                session_patch={
                    "awaiting": "pick_slot",
                    "selected_doctor": {"id": str(doc["id"]), "name": doc["name"]},
                },
            )

    return None


def format_report_reply(analysis: dict, user_text: str) -> str:
    summary = (analysis.get("summary") or "Report analyzed.").strip()
    abnormal = analysis.get("abnormal") or []
    text = user_text.lower()

    if "summarize" in text or "simple terms" in text:
        lines = ["**Report summary**", "", summary]
        if abnormal:
            lines.extend(["", "Key markers reviewed:"])
            for item in abnormal[:5]:
                lines.append(f"• {item.get('test', 'Test')}: {item.get('value', '—')}")
        lines.extend(
            [
                "",
                "_This is an educational summary — your doctor can interpret results in full context._",
            ]
        )
        return "\n".join(lines)

    if "abnormal" in text or "out-of-range" in text or "out of range" in text:
        if not abnormal:
            return (
                "**Abnormal results**\n\n"
                "No values were flagged as clearly out of range in this report. "
                "If you have symptoms, please discuss the full report with your physician."
            )
        lines = ["**Abnormal or out-of-range values**", ""]
        for item in abnormal[:8]:
            flag = item.get("flag", "")
            test = item.get("test", "Test")
            value = item.get("value", "—")
            suffix = f" ({flag})" if flag else ""
            lines.append(f"• **{test}**: {value}{suffix}")
        lines.extend(["", "Please review these findings with your physician for personalized guidance."])
        return "\n".join(lines)

    if "risk" in text and "assessment" in text:
        count = len(abnormal)
        if count == 0:
            level, note = "Low", "No urgent abnormalities were flagged in the uploaded report."
        elif count == 1:
            level, note = (
                "Low to moderate",
                "One marker is outside the reference range; clinical follow-up is recommended.",
            )
        else:
            level, note = (
                "Moderate",
                "Multiple markers are outside reference ranges; timely physician review is advised.",
            )
        lines = [f"**Risk assessment: {level}**", "", note, "", summary]
        if abnormal:
            lines.extend(["", "Contributing factors:"])
            for item in abnormal[:5]:
                lines.append(f"• {item.get('test', 'Test')}: {item.get('value', '—')} ({item.get('flag', '')})")
        lines.extend(["", "_Not a medical diagnosis — seek professional care for urgent symptoms._"])
        return "\n".join(lines)

    lines = [summary]
    if abnormal:
        lines.append("\nNotable findings:")
        for item in abnormal[:5]:
            lines.append(f"- {item.get('test', 'Test')}: {item.get('value', '')} ({item.get('flag', '')})")
    lines.append("\nPlease discuss these results with your physician for personalized guidance.")
    return "\n".join(lines)


_REFILL_START_RE = re.compile(
    r"\b(refill|prescription refill|running low|tablets left|pills left|need more (?:pills|tablets|medication))\b",
    re.I,
)

_EMERGENCY_BLOCK_RE = re.compile(
    r"\b(chest pain|can't breathe|cannot breathe|difficulty breathing|stroke|severe bleeding|unconscious)\b",
    re.I,
)


def _refill_intent(text: str) -> bool:
    return bool(_REFILL_START_RE.search(text))


def _blocks_refill(text: str) -> bool:
    return bool(_EMERGENCY_BLOCK_RE.search(text))


def _match_medication_name(text: str, meds: list[dict]) -> str | None:
    for med in meds:
        if med["name"].lower() in text.lower():
            return med["name"]
    return None


async def resolve_refill_session(ctx: AgentContext) -> AgentResponse | None:
    """Deterministic refill flow — load meds, confirm, submit request_refill."""
    if _blocks_refill(ctx.text):
        return None

    session = ctx.session
    active = session.get("active_specialist")
    care_goal = session.get("care_goal")
    awaiting = session.get("awaiting")
    in_refill_flow = (
        care_goal == "refill"
        or active == "refill_agent"
        or awaiting in ("confirm_refill", "pick_refill_med")
        or _refill_intent(ctx.text)
    )
    if not in_refill_flow:
        return None

    meds = (await tool_get_medications(ctx.db, ctx.patient.id)).get("medications") or []
    if not meds:
        return AgentResponse(
            reply=(
                "I don't see any active prescriptions on your account. "
                "Please contact your clinic to add medications before requesting a refill."
            ),
            agent="refill_agent",
            session_patch={"care_goal": None, "awaiting": None, "refill_medication": None},
        )

    med_name = session.get("refill_medication") or _match_medication_name(ctx.text, meds)
    if not med_name and len(meds) == 1 and (_refill_intent(ctx.text) or awaiting == "pick_refill_med"):
        med_name = meds[0]["name"]

    if awaiting == "confirm_refill":
        if _no(ctx.text):
            return AgentResponse(
                reply="No problem. Let me know whenever you need a refill.",
                agent="refill_agent",
                session_patch={"care_goal": None, "awaiting": None, "refill_medication": None},
            )
        if _yes(ctx.text) and med_name:
            result = await tool_request_refill(ctx.db, ctx.patient.id, ctx.patient.user_id, med_name)
            if result.get("success"):
                doctor_name = result.get("doctor_name", "your physician")
                return AgentResponse(
                    reply=(
                        f"✅ **Refill request submitted**\n\n"
                        f"**Medication:** {result.get('medication', med_name)}\n"
                        f"**Assigned to:** {doctor_name}\n\n"
                        f"{result.get('message', 'Your physician will review this request.')}"
                    ),
                    agent="refill_agent",
                    session_patch={"care_goal": None, "awaiting": None, "refill_medication": None},
                )
            return AgentResponse(
                reply=result.get("message", "Could not submit refill request."),
                agent="refill_agent",
            )

    if med_name and (_match_medication_name(ctx.text, meds) or session.get("refill_medication")):
        return AgentResponse(
            reply=(
                f"I found **{med_name}** on your active prescription list. "
                f"Would you like me to submit a refill request to your doctor?"
            ),
            agent="refill_agent",
            ui=build_yes_no_ui(
                yes_label="Yes, submit refill",
                yes_message="Yes",
                no_label="Not now",
                no_message="No",
            ),
            session_patch={
                "care_goal": "refill",
                "active_specialist": "refill_agent",
                "awaiting": "confirm_refill",
                "refill_medication": med_name,
            },
        )

    if _refill_intent(ctx.text):
        if len(meds) == 1:
            only = meds[0]
            return AgentResponse(
                reply=(
                    f"You have **{only['name']} {only['dosage']}** ({only['frequency']}) on file. "
                    f"Would you like me to submit a refill request?"
                ),
                agent="refill_agent",
                ui=build_yes_no_ui(
                    yes_label="Yes, submit refill",
                    yes_message="Yes",
                    no_label="Not now",
                    no_message="No",
                ),
                session_patch={
                    "care_goal": "refill",
                    "active_specialist": "refill_agent",
                    "awaiting": "confirm_refill",
                    "refill_medication": only["name"],
                },
            )

        names = ", ".join(f"**{m['name']}** ({m['dosage']})" for m in meds)
        return AgentResponse(
            reply=(
                f"I can help with a refill. Your active prescriptions: {names}.\n\n"
                "Which medication do you need refilled?"
            ),
            agent="refill_agent",
            session_patch={
                "care_goal": "refill",
                "active_specialist": "refill_agent",
                "awaiting": "pick_refill_med",
            },
        )

    if awaiting == "pick_refill_med" and len(ctx.text.strip()) > 2:
        guessed = _match_medication_name(ctx.text, meds) or ctx.text.strip()
        for med in meds:
            if guessed.lower() in med["name"].lower() or med["name"].lower() in guessed.lower():
                return AgentResponse(
                    reply=(
                        f"I'll request a refill for **{med['name']} {med['dosage']}**. "
                        f"Submit this to your doctor?"
                    ),
                    agent="refill_agent",
                    ui=build_yes_no_ui(
                        yes_label="Yes, submit refill",
                        yes_message="Yes",
                        no_label="Not now",
                        no_message="No",
                    ),
                    session_patch={
                        "care_goal": "refill",
                        "active_specialist": "refill_agent",
                        "awaiting": "confirm_refill",
                        "refill_medication": med["name"],
                    },
                )

    return None


def synthesize_tool_result(tool_result: dict, ctx: AgentContext) -> AgentResponse | None:
    if tool_result.get("doctors") is not None and "total" in tool_result:
        doctors = tool_result.get("doctors", [])
        if not doctors:
            return AgentResponse(
                reply="I couldn't find doctors with open slots right now. Would you like me to search all specialties?",
                agent="scheduling_agent",
            )
        return AgentResponse(
            reply=doctor_list_intro(len(doctors)),
            agent="scheduling_agent",
            ui=build_doctor_list_ui(tool_result),
            session_patch={"last_doctor_search": tool_result, "awaiting": "pick_doctor"},
        )

    if tool_result.get("slots") is not None and tool_result.get("doctor_name"):
        doc_name = tool_result["doctor_name"]
        return AgentResponse(
            reply=slot_list_intro(doc_name),
            agent="scheduling_agent",
            ui=build_slot_list_ui(doc_name, str(tool_result.get("doctor_id", "")), tool_result.get("slots", [])),
            session_patch={"awaiting": "pick_slot"},
        )

    if tool_result.get("recommended_specialty"):
        pname = ctx.patient_ctx.get("name", "there").split()[0]
        specialty = tool_result["recommended_specialty"]
        return AgentResponse(
            reply=(
                f"Thanks, {pname}. {tool_result.get('recommendation', '')}\n\n"
                f"Based on your symptoms, I recommend a **{specialty}** — you don't need to "
                f"choose a specialist yourself.\n\n"
                f"Would you like me to show available doctors and book an appointment?"
            ),
            agent="triage_agent",
            emergency=tool_result.get("risk_level") == "emergency",
            ui=build_booking_offer_ui(),
            session_patch={
                "recommended_specialty": specialty,
                "awaiting": "offer_booking",
                "care_goal": "book_after_triage",
                "active_specialist": "triage_agent",
                "triage_assessed": True,
            },
            handoff_to=None,
        )

    if tool_result.get("analysis") is not None or (tool_result.get("success") and tool_result.get("analysis")):
        analysis = tool_result.get("analysis") or {}
        return AgentResponse(reply=format_report_reply(analysis, ctx.text), agent="report_agent")

    if tool_result.get("success") and tool_result.get("apt_id"):
        return AgentResponse(
            reply=(
                f"✅ Appointment Successfully Booked\n\n"
                f"Appointment ID: {tool_result['apt_id']}\n"
                f"Doctor: {tool_result.get('doctor_name', '')}\n"
                f"Date & Time: {tool_result.get('label', '')}\n\n"
                f"Use the buttons below to **Cancel** or **Reschedule** if you need to change your booking."
            ),
            agent="scheduling_agent",
            ui=build_appointment_confirmed_ui(tool_result),
            session_patch={
                "last_appointment_id": tool_result.get("appointment_id"),
                "care_goal": "manage_appointment",
            },
        )

    if tool_result.get("success") and tool_result.get("medication"):
        doctor_name = tool_result.get("doctor_name", "your physician")
        return AgentResponse(
            reply=(
                f"✅ **Refill request submitted**\n\n"
                f"**Medication:** {tool_result.get('medication')}\n"
                f"**Assigned to:** {doctor_name}\n\n"
                f"{tool_result.get('message', 'Your physician will review this request.')}"
            ),
            agent="refill_agent",
            session_patch={"care_goal": None, "awaiting": None, "refill_medication": None},
        )

    if tool_result.get("medications") is not None:
        meds = tool_result.get("medications") or []
        if not meds:
            return AgentResponse(
                reply="I don't see any active prescriptions on your account.",
                agent="refill_agent",
            )
        if len(meds) == 1:
            only = meds[0]
            return AgentResponse(
                reply=(
                    f"You have **{only['name']} {only['dosage']}** on file. "
                    f"Would you like me to submit a refill request?"
                ),
                agent="refill_agent",
                ui=build_yes_no_ui(
                    yes_label="Yes, submit refill",
                    yes_message="Yes",
                    no_label="Not now",
                    no_message="No",
                ),
                session_patch={
                    "care_goal": "refill",
                    "awaiting": "confirm_refill",
                    "refill_medication": only["name"],
                },
            )
        names = ", ".join(f"**{m['name']}** ({m['dosage']})" for m in meds)
        return AgentResponse(
            reply=f"Your active prescriptions: {names}. Which medication needs a refill?",
            agent="refill_agent",
            session_patch={"care_goal": "refill", "awaiting": "pick_refill_med"},
        )

    return None
