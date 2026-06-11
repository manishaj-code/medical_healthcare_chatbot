"""Video consultation rooms linked to confirmed appointments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, Notification, Patient, User
from app.models.enums import AppointmentStatus, NotificationType
from app.services.appointment_service import format_apt_id

JITSI_BASE = "https://meet.jit.si"


def video_room_id_for_appointment(appointment_id: UUID) -> str:
    return f"MediAI-{str(appointment_id).split('-')[0]}"


def build_join_url(room_id: str, display_name: str) -> str:
    safe_name = display_name.replace(" ", "%20")
    return f"{JITSI_BASE}/{room_id}#userInfo.displayName=%22{safe_name}%22"


async def enable_video_consultation(
    db: AsyncSession,
    appointment_id: UUID,
    patient_id: UUID,
    user_id: UUID,
    *,
    patient_name: str,
) -> dict:
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.patient_id == patient_id,
            Appointment.status == AppointmentStatus.confirmed,
        )
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Confirmed appointment not found.")

    start = datetime.combine(appt.slot_date, appt.slot_time).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    window_start = start - timedelta(minutes=15)
    window_end = start + timedelta(hours=2)
    if now < window_start:
        raise HTTPException(
            status_code=400,
            detail=f"Video consultation opens 15 minutes before your appointment ({appt.slot_date} {appt.slot_time}).",
        )
    if now > window_end:
        raise HTTPException(status_code=400, detail="This appointment video window has ended.")

    room_id = video_room_id_for_appointment(appt.id)
    appt.consultation_mode = "video"
    appt.video_room_id = room_id
    appt.video_enabled_at = now

    doctor_row = await db.execute(
        select(User.name).join(Doctor, Doctor.user_id == User.id).where(Doctor.id == appt.doctor_id)
    )
    doctor_name = doctor_row.scalar_one_or_none() or "your doctor"

    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.video_consultation,
            message=f"Video consultation room ready for appointment {format_apt_id(appt.id)} with {doctor_name}.",
        )
    )
    await db.flush()

    join_url = build_join_url(room_id, patient_name)
    return {
        "appointment_id": str(appt.id),
        "apt_id": format_apt_id(appt.id),
        "room_id": room_id,
        "join_url": join_url,
        "doctor_name": doctor_name,
        "slot_date": str(appt.slot_date),
        "slot_time": str(appt.slot_time),
        "consultation_mode": "video",
    }


async def get_upcoming_confirmed(
    db: AsyncSession,
    patient_id: UUID,
) -> Appointment | None:
    today = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status == AppointmentStatus.confirmed,
            Appointment.slot_date >= today,
        )
        .order_by(Appointment.slot_date, Appointment.slot_time)
    )
    return result.scalars().first()


async def resolve_video_for_patient(
    db: AsyncSession,
    patient: Patient,
    user: User,
) -> dict:
    appt = await get_upcoming_confirmed(db, patient.id)
    if not appt:
        raise HTTPException(status_code=404, detail="No upcoming confirmed appointment for video consultation.")
    if appt.video_room_id:
        return {
            "appointment_id": str(appt.id),
            "apt_id": format_apt_id(appt.id),
            "room_id": appt.video_room_id,
            "join_url": build_join_url(appt.video_room_id, user.name),
            "consultation_mode": appt.consultation_mode,
            "already_enabled": True,
        }
    return await enable_video_consultation(
        db,
        appt.id,
        patient.id,
        user.id,
        patient_name=user.name.split()[0],
    )
