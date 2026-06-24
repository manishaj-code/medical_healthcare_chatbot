"""Scheduled appointment reminders — fires notifications at the right time."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Appointment, AppointmentReminder, Doctor, Notification, User
from app.models.enums import AppointmentStatus, NotificationType
from app.services.appointment_service import format_apt_id

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


def _appointment_start(appt: Appointment) -> datetime:
    start = datetime.combine(appt.slot_date, appt.slot_time)
    return start.replace(tzinfo=timezone.utc)


async def schedule_appointment_reminder(
    db: AsyncSession,
    user_id: UUID,
    appointment_id: UUID,
    minutes: int = 30,
) -> dict:
    """Persist a future reminder and confirm scheduling to the patient."""
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        return {"success": False, "message": "Appointment not found."}

    start = _appointment_start(appt)
    remind_at = start - timedelta(minutes=minutes)
    now = datetime.now(timezone.utc)

    existing = await db.execute(
        select(AppointmentReminder).where(
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.sent.is_(False),
        )
    )
    if existing.scalar_one_or_none():
        return {"success": True, "message": "Reminder already scheduled.", "already_scheduled": True}

    if remind_at <= now:
        doctor_row = await db.execute(
            select(User.name)
            .join(Doctor, Doctor.user_id == User.id)
            .where(Doctor.id == appt.doctor_id)
        )
        doctor_name = doctor_row.scalar_one_or_none() or "your doctor"
        db.add(
            AppointmentReminder(
                appointment_id=appointment_id,
                user_id=user_id,
                remind_at=now,
                minutes_before=minutes,
                sent=True,
            )
        )
        db.add(
            Notification(
                user_id=user_id,
                type=NotificationType.reminder,
                message=(
                    f"Your appointment with {doctor_name} ({format_apt_id(appt.id)}) "
                    f"is coming up soon at {appt.slot_time.strftime('%I:%M %p').lstrip('0')}."
                ),
            )
        )
        await db.flush()
        return {"success": True, "message": "Reminder sent — your appointment is very soon."}

    db.add(
        AppointmentReminder(
            appointment_id=appointment_id,
            user_id=user_id,
            remind_at=remind_at,
            minutes_before=minutes,
        )
    )
    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.reminder_scheduled,
            message=(
                f"Reminder set! We'll notify you {minutes} minutes before appointment "
                f"{format_apt_id(appointment_id)}."
            ),
        )
    )
    await db.flush()
    return {
        "success": True,
        "message": f"Reminder scheduled {minutes} minutes before your appointment.",
        "remind_at": remind_at.isoformat(),
    }


async def process_due_reminders(db: AsyncSession) -> int:
    """Send notifications for reminders whose time has arrived."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AppointmentReminder, Appointment, User.name)
        .join(Appointment, Appointment.id == AppointmentReminder.appointment_id)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            AppointmentReminder.sent.is_(False),
            AppointmentReminder.remind_at <= now,
            Appointment.status.in_((AppointmentStatus.confirmed, AppointmentStatus.rescheduled)),
        )
    )
    sent_count = 0
    for reminder, appt, doctor_name in result.all():
        time_label = appt.slot_time.strftime("%I:%M %p").lstrip("0")
        db.add(
            Notification(
                user_id=reminder.user_id,
                type=NotificationType.reminder,
                message=(
                    f"⏰ Reminder: Your appointment with **{doctor_name}** "
                    f"({format_apt_id(appt.id)}) is in about {reminder.minutes_before} minutes "
                    f"at {time_label}."
                ),
            )
        )
        reminder.sent = True
        sent_count += 1
    if sent_count:
        await db.flush()
    return sent_count


async def reminder_worker_loop() -> None:
    """Background loop — checks for due reminders every minute."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                count = await process_due_reminders(db)
                await db.commit()
                if count:
                    logger.info("Sent %d appointment reminder(s)", count)
        except Exception as exc:
            logger.warning("Reminder worker error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
