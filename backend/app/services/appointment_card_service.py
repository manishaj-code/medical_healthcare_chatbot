"""Build enriched appointment confirmation cards for chat UI."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, DoctorSpecialization, Specialization, User
from app.models.enums import AppointmentStatus
from app.services.appointment_service import format_apt_id
from app.services.doctor_service import _day_label, _format_time


async def _doctor_specialty(db: AsyncSession, doctor_id: UUID) -> str:
    result = await db.execute(
        select(Specialization.name)
        .join(DoctorSpecialization, DoctorSpecialization.specialization_id == Specialization.id)
        .where(DoctorSpecialization.doctor_id == doctor_id)
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row or "General Physician"


async def _has_reminder(db: AsyncSession, appointment_id: UUID, user_id: UUID) -> bool:
    from app.models.doctor_ops import AppointmentReminder

    result = await db.execute(
        select(AppointmentReminder.id).where(
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.user_id == user_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def enrich_stored_appointment_ui(
    db: AsyncSession,
    ui: dict | None,
    user_id: UUID | None,
) -> dict | None:
    """Refresh reminder_set and live appointment status on persisted cards."""
    if not ui or ui.get("type") != "appointment_confirmed" or not user_id:
        return ui
    appt_id = ui.get("appointment_id")
    if not appt_id:
        return ui

    appt = await db.get(Appointment, UUID(str(appt_id)))
    if not appt:
        return ui

    status = _display_status(appt)
    reminder_set = await _has_reminder(db, appt.id, user_id)
    updates: dict = {}
    if ui.get("status") != status:
        updates["status"] = status
    if ui.get("reminder_set") != reminder_set:
        updates["reminder_set"] = reminder_set
    if status in ("cancelled", "completed") and not ui.get("actions_disabled"):
        updates["actions_disabled"] = True
    if not updates:
        return ui
    return {**ui, **updates}


async def mark_appointment_reminder_on_cards(
    db: AsyncSession,
    conversation_id: UUID,
    appointment_id: UUID,
) -> None:
    """Update stored appointment_confirmed UI blobs after a reminder is scheduled."""
    from app.models import Message

    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    appt_key = str(appointment_id)
    for message in result.scalars().all():
        payload = message.tool_calls_json
        if not isinstance(payload, dict):
            continue
        ui = payload.get("ui")
        if not isinstance(ui, dict) or ui.get("type") != "appointment_confirmed":
            continue
        if str(ui.get("appointment_id") or "") != appt_key:
            continue
        if ui.get("reminder_set"):
            continue
        message.tool_calls_json = {**payload, "ui": {**ui, "reminder_set": True}}


async def sync_appointment_status_on_patient_cards(
    db: AsyncSession,
    appointment_id: UUID,
) -> None:
    """Persist completed/cancelled status on in-chat appointment cards for the patient."""
    from app.models import Conversation, Message

    appt = await db.get(Appointment, appointment_id)
    if not appt:
        return

    status = _display_status(appt)
    terminal = status in ("cancelled", "completed")
    appt_key = str(appointment_id)

    result = await db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.patient_id == appt.patient_id)
    )
    for message in result.scalars().all():
        payload = message.tool_calls_json
        if not isinstance(payload, dict):
            continue
        ui = payload.get("ui")
        if not isinstance(ui, dict) or ui.get("type") != "appointment_confirmed":
            continue
        if str(ui.get("appointment_id") or "") != appt_key:
            continue
        updates: dict = {}
        if ui.get("status") != status:
            updates["status"] = status
        if terminal and not ui.get("actions_disabled"):
            updates["actions_disabled"] = True
        if not updates:
            continue
        message.tool_calls_json = {**payload, "ui": {**ui, **updates}}


def _display_status(appt: Appointment, override: str | None = None) -> str:
    if override:
        return override
    status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
    if status == AppointmentStatus.cancelled.value:
        return "cancelled"
    if status == AppointmentStatus.completed.value:
        return "completed"
    if status == AppointmentStatus.rescheduled.value:
        return "rescheduled"
    return "confirmed"


def build_appointment_confirmed_ui(
    *,
    appointment_id: str,
    apt_id: str,
    doctor_name: str,
    label: str,
    specialty: str = "General Physician",
    hospital_name: str | None = None,
    status: str = "confirmed",
    reminder_set: bool = False,
) -> dict:
    return {
        "type": "appointment_confirmed",
        "appointment_id": appointment_id,
        "apt_id": apt_id,
        "doctor_name": doctor_name,
        "label": label,
        "specialty": specialty,
        "hospital_name": hospital_name or "MediAI Healthcare Clinic",
        "status": status,
        "reminder_set": reminder_set,
    }


async def enrich_booking_result(db: AsyncSession, result: dict, user_id: UUID | None = None) -> dict:
    """Add doctor specialty, hospital, and reminder flag to a tool_book_slot result."""
    appt_id = result.get("appointment_id")
    if not appt_id:
        return result

    appt = await db.get(Appointment, UUID(str(appt_id)))
    if not appt:
        return result

    doctor = await db.get(Doctor, appt.doctor_id)
    doctor_user = await db.get(User, doctor.user_id) if doctor else None
    specialty = await _doctor_specialty(db, appt.doctor_id) if doctor else "General Physician"
    hospital = doctor.hospital_name if doctor else None
    reminder_set = False
    if user_id:
        reminder_set = await _has_reminder(db, appt.id, user_id)

    label = result.get("label") or f"{_day_label(appt.slot_date)}: {_format_time(appt.slot_time)}"
    return {
        **result,
        "doctor_name": result.get("doctor_name") or (doctor_user.name if doctor_user else "Doctor"),
        "label": label,
        "specialty": specialty,
        "hospital_name": hospital,
        "status": _display_status(appt),
        "reminder_set": reminder_set,
    }


async def build_card_from_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    *,
    user_id: UUID | None = None,
    display_status: str | None = None,
    reminder_set: bool | None = None,
) -> dict | None:
    appt = await db.get(Appointment, appointment_id)
    if not appt:
        return None

    doctor = await db.get(Doctor, appt.doctor_id)
    doctor_user = await db.get(User, doctor.user_id) if doctor else None
    specialty = await _doctor_specialty(db, appt.doctor_id) if doctor else "General Physician"
    if reminder_set is None and user_id:
        reminder_set = await _has_reminder(db, appt.id, user_id)
    reminder_set = bool(reminder_set)

    return build_appointment_confirmed_ui(
        appointment_id=str(appt.id),
        apt_id=format_apt_id(appt.id),
        doctor_name=doctor_user.name if doctor_user else "Doctor",
        label=f"{_day_label(appt.slot_date)}: {_format_time(appt.slot_time)}",
        specialty=specialty,
        hospital_name=doctor.hospital_name if doctor else None,
        status=_display_status(appt, display_status),
        reminder_set=reminder_set,
    )


async def complete_guest_resume_booking(
    db: AsyncSession,
    patient,
    conversation_id: UUID,
    session: dict,
) -> dict | None:
    """Book pending guest slot after portal auth — no redundant confirm message."""
    if not session.get("resume_after_auth"):
        return None

    action = session.get("guest_resume_action") or session.get("pending_auth_action") or "book"
    if action != "book":
        return None

    pending = session.get("pending_slot")
    if not pending:
        return None

    from app.services.agent_tools import slot_for_storage, tool_book_slot

    stored = slot_for_storage(pending) if not pending.get("slot_date") else pending
    booking_context = {
        "pending_consultation_mode": session.get("pending_consultation_mode", "in_person"),
        "appointment_reason": session.get("appointment_reason"),
        "linked_report_id": session.get("linked_report_id"),
    }
    try:
        result = await tool_book_slot(
            db,
            patient,
            patient.user_id,
            stored,
            conversation_id,
            booking_context=booking_context,
        )
    except Exception:
        return None

    enriched = await enrich_booking_result(db, result, patient.user_id)
    ui = build_appointment_confirmed_ui(
        appointment_id=str(enriched["appointment_id"]),
        apt_id=enriched.get("apt_id", ""),
        doctor_name=enriched.get("doctor_name", "Doctor"),
        label=enriched.get("label", ""),
        specialty=enriched.get("specialty", "General Physician"),
        hospital_name=enriched.get("hospital_name"),
        status="confirmed",
        reminder_set=False,
    )

    for key in (
        "pending_slot",
        "awaiting",
        "resume_after_auth",
        "pending_auth_action",
        "guest_resume_action",
        "guest_email",
    ):
        session.pop(key, None)
    session.update({
        "care_goal": "manage_appointment",
        "active_specialist": "scheduling_agent",
        "last_appointment_id": enriched.get("appointment_id"),
    })

    return {
        "reply": (
            f"✅ **Booking confirmed!** Your appointment with **{enriched.get('doctor_name', 'your doctor')}** "
            f"is set for **{enriched.get('label', '')}**."
        ),
        "agent": "scheduling_agent",
        "emergency": False,
        "ui": ui,
        "session": session,
    }
