import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, DoctorAvailability, Notification, User
from app.models.doctor_ops import AppointmentReminder
from app.models.enums import AppointmentStatus, NotificationType
from app.services.appointment_email_service import (
    send_appointment_cancelled_emails,
    send_appointment_rescheduled_emails,
    send_appointment_scheduled_emails,
)
from app.services.cache import get_redis

logger = logging.getLogger(__name__)


def format_apt_id(appointment_id: UUID) -> str:
    return f"APT-{appointment_id.hex[:5].upper()}"


def is_slot_past(slot_date: date, slot_time: time) -> bool:
    """True when the appointment slot start is before now (local server clock)."""
    return datetime.combine(slot_date, slot_time) < datetime.now()


def is_active_appointment_status(status: AppointmentStatus | str) -> bool:
    value = status.value if hasattr(status, "value") else str(status)
    return value.lower() not in {"cancelled", "canceled", "completed"}


def active_appointment_statuses() -> tuple[AppointmentStatus, ...]:
    """Statuses that still hold a doctor slot."""
    return (AppointmentStatus.confirmed, AppointmentStatus.pending, AppointmentStatus.rescheduled)


def reschedulable_appointment_statuses() -> tuple[AppointmentStatus, ...]:
    return (AppointmentStatus.confirmed, AppointmentStatus.rescheduled)


def normalize_slot_time(value: time | str) -> str:
    if isinstance(value, time):
        return value.isoformat()
    text = str(value).strip()
    if len(text) == 5:
        return f"{text}:00"
    return text


def appointment_supports_video_call(appt: Appointment) -> bool:
    """Any non-terminal appointment can start or join a video room."""
    return is_active_appointment_status(appt.status)


async def book_appointment(
    db: AsyncSession,
    patient_id: UUID,
    doctor_id: UUID,
    slot_date: date,
    slot_time: time,
    user_id: UUID,
    *,
    consultation_mode: str = "in_person",
    appointment_reason: str | None = None,
    linked_report_id: UUID | None = None,
) -> Appointment:
    if datetime.combine(slot_date, slot_time) < datetime.now():
        raise HTTPException(status_code=400, detail="Cannot book a past time slot")

    lock_key = f"lock:appt:{doctor_id}:{slot_date}:{slot_time}"
    try:
        redis = await get_redis()
        acquired = await redis.set(lock_key, "1", nx=True, ex=30)
        if not acquired:
            raise HTTPException(status_code=409, detail="Slot being booked by another user")
    except HTTPException:
        raise
    except Exception:
        pass

    existing = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.slot_date == slot_date,
            Appointment.slot_time == slot_time,
            Appointment.status.in_(list(active_appointment_statuses())),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slot already booked")

    slot = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.slot_date == slot_date,
            DoctorAvailability.slot_time == slot_time,
            DoctorAvailability.status == "available",
        )
    )
    availability = slot.scalar_one_or_none()
    if not availability:
        raise HTTPException(status_code=404, detail="Slot not available")

    availability.status = "booked"
    appt = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_date=slot_date,
        slot_time=slot_time,
        status=AppointmentStatus.confirmed,
        consultation_mode=consultation_mode,
        appointment_reason=appointment_reason,
        linked_report_id=linked_report_id,
    )
    from app.services.video_consultation_service import video_room_id_for_appointment

    appt.video_room_id = video_room_id_for_appointment(appt.id)
    db.add(appt)
    when_time = slot_time.strftime("%I:%M %p").lstrip("0")
    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.booking_confirmation,
            message=f"Appointment confirmed for {slot_date} at {when_time}",
        )
    )
    await db.flush()

    try:
        await send_appointment_scheduled_emails(db, appt)
    except Exception:
        logger.exception("Failed to send appointment emails for %s", appt.id)

    return appt


async def get_latest_confirmed(db: AsyncSession, patient_id: UUID) -> Appointment | None:
    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status.in_(list(reschedulable_appointment_statuses())),
        )
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def reschedule_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    patient_id: UUID,
    new_date: date,
    new_time: time,
    user_id: UUID,
) -> Appointment:
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id, Appointment.patient_id == patient_id)
    )
    appt = result.scalar_one_or_none()
    if not appt or appt.status not in reschedulable_appointment_statuses():
        raise HTTPException(status_code=404, detail="Appointment not found")

    previous_date = appt.slot_date
    previous_time = appt.slot_time

    if new_date == appt.slot_date and normalize_slot_time(new_time) == normalize_slot_time(appt.slot_time):
        raise HTTPException(status_code=400, detail="That is already your current appointment time")

    taken = await db.execute(
        select(Appointment.id).where(
            Appointment.doctor_id == appt.doctor_id,
            Appointment.slot_date == new_date,
            Appointment.slot_time == new_time,
            Appointment.id != appointment_id,
            Appointment.status.in_(list(active_appointment_statuses())),
        )
    )
    if taken.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slot already booked")

    new_slot = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == appt.doctor_id,
            DoctorAvailability.slot_date == new_date,
            DoctorAvailability.slot_time == new_time,
            DoctorAvailability.status == "available",
        )
    )
    if not new_slot.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Slot not available")

    old_slot = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == appt.doctor_id,
            DoctorAvailability.slot_date == appt.slot_date,
            DoctorAvailability.slot_time == appt.slot_time,
        )
    )
    old = old_slot.scalar_one_or_none()
    if old:
        old.status = "available"

    new_slot_row = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == appt.doctor_id,
            DoctorAvailability.slot_date == new_date,
            DoctorAvailability.slot_time == new_time,
        )
    )
    ns = new_slot_row.scalar_one_or_none()
    if ns:
        ns.status = "booked"

    appt.slot_date = new_date
    appt.slot_time = new_time
    appt.status = AppointmentStatus.rescheduled

    pending_reminder = await db.execute(
        select(AppointmentReminder).where(
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.sent.is_(False),
        )
    )
    reminder_row = pending_reminder.scalar_one_or_none()
    if reminder_row:
        new_start = datetime.combine(new_date, new_time).replace(tzinfo=timezone.utc)
        reminder_row.remind_at = new_start - timedelta(minutes=reminder_row.minutes_before or 30)

    when_time = new_time.strftime("%I:%M %p").lstrip("0")
    apt_id = format_apt_id(appt.id)
    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.appointment_rescheduled,
            message=f"Appointment {apt_id} rescheduled to {new_date} at {when_time}",
        )
    )
    doctor_user_row = await db.execute(
        select(User.id, User.name)
        .join(Doctor, Doctor.user_id == User.id)
        .where(Doctor.id == appt.doctor_id)
    )
    doctor_user = doctor_user_row.one_or_none()
    if doctor_user:
        doctor_user_id, _doctor_name = doctor_user
        db.add(
            Notification(
                user_id=doctor_user_id,
                type=NotificationType.appointment_rescheduled,
                message=f"Appointment {apt_id} rescheduled to {new_date} at {when_time}.",
            )
        )
    await db.flush()

    from app.services.appointment_card_service import sync_appointment_status_on_patient_cards

    await sync_appointment_status_on_patient_cards(db, appt.id)

    try:
        await send_appointment_rescheduled_emails(
            db,
            appt,
            previous_date=previous_date,
            previous_time=previous_time,
        )
    except Exception:
        logger.exception("Failed to send reschedule emails for %s", appt.id)

    return appt


async def schedule_reminder(db: AsyncSession, user_id: UUID, appointment_id: UUID, minutes: int = 30) -> dict:
    from app.services.reminder_scheduler_service import schedule_appointment_reminder

    return await schedule_appointment_reminder(db, user_id, appointment_id, minutes)


async def cancel_appointment(db: AsyncSession, appointment_id: UUID, patient_id: UUID, reason: str | None) -> Appointment:
    result = await db.execute(
        select(Appointment).where(Appointment.id == appointment_id, Appointment.patient_id == patient_id)
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    cancelled_date = appt.slot_date
    cancelled_time = appt.slot_time

    appt.status = AppointmentStatus.cancelled
    appt.cancellation_reason = reason
    avail = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == appt.doctor_id,
            DoctorAvailability.slot_date == appt.slot_date,
            DoctorAvailability.slot_time == appt.slot_time,
        )
    )
    slot = avail.scalar_one_or_none()
    if slot:
        slot.status = "available"
    await db.flush()

    try:
        await send_appointment_cancelled_emails(
            db,
            appt,
            slot_date=cancelled_date,
            slot_time=cancelled_time,
            reason=reason,
        )
    except Exception:
        logger.exception("Failed to send cancellation emails for %s", appt.id)

    return appt


async def cancel_appointment_by_doctor(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    reason: str | None = None,
) -> Appointment:
    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor_id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    cancelled_date = appt.slot_date
    cancelled_time = appt.slot_time

    appt.status = AppointmentStatus.cancelled
    appt.cancellation_reason = reason or "Cancelled by doctor"
    avail = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == appt.doctor_id,
            DoctorAvailability.slot_date == appt.slot_date,
            DoctorAvailability.slot_time == appt.slot_time,
        )
    )
    slot = avail.scalar_one_or_none()
    if slot:
        slot.status = "available"
    await db.flush()

    try:
        await send_appointment_cancelled_emails(
            db,
            appt,
            slot_date=cancelled_date,
            slot_time=cancelled_time,
            reason=appt.cancellation_reason,
        )
    except Exception:
        logger.exception("Failed to send cancellation emails for %s", appt.id)

    return appt
