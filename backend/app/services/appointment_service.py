import logging
from datetime import date, datetime, time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, DoctorAvailability, Notification, User
from app.models.enums import AppointmentStatus, NotificationType
from app.services.appointment_email_service import send_appointment_scheduled_emails
from app.services.cache import get_redis

logger = logging.getLogger(__name__)


def format_apt_id(appointment_id: UUID) -> str:
    return f"APT-{appointment_id.hex[:5].upper()}"


async def book_appointment(
    db: AsyncSession,
    patient_id: UUID,
    doctor_id: UUID,
    slot_date: date,
    slot_time: time,
    user_id: UUID,
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
            Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.pending]),
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
    )
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
            Appointment.status == AppointmentStatus.confirmed,
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
    if not appt or appt.status != AppointmentStatus.confirmed:
        raise HTTPException(status_code=404, detail="Appointment not found")

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
    when_time = new_time.strftime("%I:%M %p").lstrip("0")
    apt_id = format_apt_id(appt.id)
    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.booking_confirmation,
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
                type=NotificationType.booking_confirmation,
                message=f"Appointment {apt_id} rescheduled to {new_date} at {when_time}.",
            )
        )
    await db.flush()
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
    return appt
