"""Video consultation rooms linked to confirmed appointments (LiveKit)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from livekit.api import AccessToken, VideoGrants
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_settings
from app.models import Appointment, Doctor, Notification, Patient, User
from app.models.enums import AppointmentStatus, NotificationType
from app.services.appointment_service import appointment_supports_video_call, format_apt_id
from app.utils.clinic_time import clinic_now, clinic_tz


def video_room_id_for_appointment(appointment_id: UUID) -> str:
    return f"MediAI-{str(appointment_id).split('-')[0]}"


def _participant_name(name: str | None) -> str:
    value = (name or "").strip()
    if not value:
        return "Participant"
    return value.split()[0]


def _livekit_config() -> tuple[str, str, str]:
    settings = get_settings()
    return settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret


def _generate_livekit_token(
    room_id: str,
    participant_id: str,
    participant_name: str,
    role: str = "guest",
    ttl_seconds: int = 7200,
) -> str:
    livekit_url, livekit_api_key, livekit_api_secret = _livekit_config()

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        return ""

    # Role prefix avoids identity collisions when testing patient + doctor on one machine.
    identity = f"{role}:{participant_id}" if role in ("patient", "doctor") else participant_id

    video_grants = VideoGrants(
        room_join=True,
        room=room_id,
        can_publish=True,
        can_subscribe=True,
    )

    token = AccessToken(livekit_api_key, livekit_api_secret)
    token.with_identity(identity)
    token.with_name(participant_name)
    token.with_grants(video_grants)
    token.with_ttl(timedelta(seconds=ttl_seconds))
    token.with_metadata(json.dumps({"role": role}))
    return token.to_jwt()


def _require_livekit_credentials(token: str, livekit_url: str) -> None:
    if not token or not livekit_url:
        raise HTTPException(
            status_code=503,
            detail="Video service is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET.",
        )


def _video_window_enforced(bypass_time_window: bool) -> bool:
    settings = get_settings()
    if bypass_time_window or settings.is_dev or settings.video_bypass_time_window:
        return False
    return True


def _session_payload(
    appt: Appointment,
    *,
    room_id: str,
    token: str,
    livekit_url: str,
    doctor_name: str,
    patient_name: str | None = None,
) -> dict:
    payload = {
        "appointment_id": str(appt.id),
        "apt_id": format_apt_id(appt.id),
        "room_id": room_id,
        "token": token,
        "url": livekit_url,
        "doctor_name": doctor_name,
        "slot_date": str(appt.slot_date),
        "slot_time": str(appt.slot_time),
        "consultation_mode": appt.consultation_mode or "video",
    }
    if patient_name:
        payload["patient_name"] = patient_name
    return payload


async def _doctor_name_for_appointment(db: AsyncSession, doctor_id: UUID) -> str:
    doctor_row = await db.execute(
        select(User.name).join(Doctor, Doctor.user_id == User.id).where(Doctor.id == doctor_id)
    )
    return doctor_row.scalar_one_or_none() or "Doctor"


async def _patient_name_for_appointment(db: AsyncSession, patient_id: UUID) -> str:
    patient_row = await db.execute(
        select(User.name).join(Patient, Patient.user_id == User.id).where(Patient.id == patient_id)
    )
    return patient_row.scalar_one_or_none() or "Patient"


async def _ensure_video_room(
    db: AsyncSession,
    appt: Appointment,
    *,
    bypass_time_window: bool = False,
) -> str:
    start = datetime.combine(appt.slot_date, appt.slot_time, tzinfo=clinic_tz())
    now = clinic_now()
    if _video_window_enforced(bypass_time_window):
        window_start = start - timedelta(minutes=15)
        window_end = start + timedelta(hours=2)
        if now < window_start:
            raise HTTPException(
                status_code=400,
                detail=f"Video consultation opens 15 minutes before your appointment ({appt.slot_date} {appt.slot_time}).",
            )
        if now > window_end:
            raise HTTPException(status_code=400, detail="This appointment video window has ended.")

    room_id = appt.video_room_id or video_room_id_for_appointment(appt.id)
    appt.video_room_id = room_id
    if not appt.video_enabled_at:
        appt.video_enabled_at = datetime.now(timezone.utc)
    await db.flush()
    return room_id


async def get_patient_video_session(
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

    if not appt.video_room_id:
        return await enable_video_consultation(
            db,
            appointment_id,
            patient_id,
            user_id,
            patient_name=patient_name,
        )

    doctor_name = await _doctor_name_for_appointment(db, appt.doctor_id)
    room_id = appt.video_room_id
    token = _generate_livekit_token(
        room_id=room_id,
        participant_id=str(user_id),
        participant_name=_participant_name(patient_name),
        role="patient",
    )
    livekit_url, _, _ = _livekit_config()
    _require_livekit_credentials(token, livekit_url)
    return _session_payload(
        appt,
        room_id=room_id,
        token=token,
        livekit_url=livekit_url,
        doctor_name=doctor_name,
    )


async def get_doctor_video_session(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    doctor_user_id: UUID,
    *,
    doctor_name: str,
) -> dict:
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor_id,
            Appointment.status.in_(
                [AppointmentStatus.confirmed, AppointmentStatus.pending, AppointmentStatus.completed]
            ),
        )
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if not appointment_supports_video_call(appt):
        raise HTTPException(status_code=400, detail="Video is not available for this appointment.")

    room_id = await _ensure_video_room(db, appt, bypass_time_window=True)
    patient_name = await _patient_name_for_appointment(db, appt.patient_id)
    token = _generate_livekit_token(
        room_id=room_id,
        participant_id=str(doctor_user_id),
        participant_name=_participant_name(doctor_name),
        role="doctor",
    )
    livekit_url, _, _ = _livekit_config()
    _require_livekit_credentials(token, livekit_url)
    return _session_payload(
        appt,
        room_id=room_id,
        token=token,
        livekit_url=livekit_url,
        doctor_name=doctor_name,
        patient_name=patient_name,
    )


async def enable_video_consultation(
    db: AsyncSession,
    appointment_id: UUID,
    patient_id: UUID,
    user_id: UUID,
    *,
    patient_name: str,
    bypass_time_window: bool = False,
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

    room_id = await _ensure_video_room(db, appt, bypass_time_window=bypass_time_window)
    doctor_name = await _doctor_name_for_appointment(db, appt.doctor_id)

    db.add(
        Notification(
            user_id=user_id,
            type=NotificationType.video_consultation,
            message=f"Video consultation room ready for appointment {format_apt_id(appt.id)} with {doctor_name}.",
        )
    )
    await db.flush()

    token = _generate_livekit_token(
        room_id=room_id,
        participant_id=str(user_id),
        participant_name=_participant_name(patient_name),
        role="patient",
    )
    livekit_url, _, _ = _livekit_config()
    _require_livekit_credentials(token, livekit_url)
    return _session_payload(
        appt,
        room_id=room_id,
        token=token,
        livekit_url=livekit_url,
        doctor_name=doctor_name,
    )


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
        doctor_name = await _doctor_name_for_appointment(db, appt.doctor_id)
        token = _generate_livekit_token(
            room_id=appt.video_room_id,
            participant_id=str(user.id),
            participant_name=_participant_name(user.name),
            role="patient",
        )
        livekit_url, _, _ = _livekit_config()
        _require_livekit_credentials(token, livekit_url)
        payload = _session_payload(
            appt,
            room_id=appt.video_room_id,
            token=token,
            livekit_url=livekit_url,
            doctor_name=doctor_name,
        )
        payload["already_enabled"] = True
        return payload
    return await enable_video_consultation(
        db,
        appt.id,
        patient.id,
        user.id,
        patient_name=_participant_name(user.name),
    )
