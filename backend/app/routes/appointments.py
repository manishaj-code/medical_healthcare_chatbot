from datetime import date, time
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_current_user, get_patient_profile
from app.database import get_db
from app.models import Appointment, Doctor, Patient, User
from app.schemas.common import ResponseEnvelope
from app.services.appointment_service import book_appointment, cancel_appointment, format_apt_id
from app.services.summary_service import prepare_appointment_summary
from app.services.video_consultation_service import (
    enable_video_consultation,
    get_patient_video_session,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])
logger = logging.getLogger(__name__)


def _participant_name(name: str | None) -> str:
    value = (name or "").strip()
    if not value:
        return "Patient"
    return value.split()[0]


class BookRequest(BaseModel):
    doctor_id: UUID
    slot_date: date
    slot_time: time


class CancelRequest(BaseModel):
    reason: str | None = None


@router.post("")
async def book(
    data: BookRequest,
    patient: Patient = Depends(get_patient_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    appt = await book_appointment(db, patient.id, data.doctor_id, data.slot_date, data.slot_time, user.id)
    try:
        await prepare_appointment_summary(db, appt.id)
    except Exception:
        pass
    return ResponseEnvelope(data={"id": str(appt.id), "status": appt.status.value})


@router.get("")
async def list_appointments(
    user: User = Depends(get_current_user),
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Appointment, User.name)
        .join(Doctor, Appointment.doctor_id == Doctor.id)
        .join(User, Doctor.user_id == User.id)
        .where(Appointment.patient_id == patient.id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )
    return ResponseEnvelope(
        data=[
            {
                "id": str(a.id),
                "doctor_id": str(a.doctor_id),
                "doctor_name": doctor_name,
                "date": str(a.slot_date),
                "time": str(a.slot_time),
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "consultation_mode": getattr(a, "consultation_mode", "in_person") or "in_person",
                "video_room_id": a.video_room_id,
                "apt_id": format_apt_id(a.id),
            }
            for a, doctor_name in result.all()
        ]
    )


@router.post("/{appointment_id}/video")
async def start_video_consultation(
    appointment_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await enable_video_consultation(
            db,
            appointment_id,
            patient.id,
            user.id,
            patient_name=_participant_name(user.name),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to start video consultation", extra={"appointment_id": str(appointment_id)})
        raise HTTPException(status_code=500, detail="Could not start video consultation.") from exc
    return ResponseEnvelope(data=data)


@router.get("/{appointment_id}/video")
async def get_video_consultation(
    appointment_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await get_patient_video_session(
        db,
        appointment_id,
        patient.id,
        user.id,
        patient_name=_participant_name(user.name),
    )
    return ResponseEnvelope(data=data)


@router.patch("/{appointment_id}/cancel")
async def cancel(
    appointment_id: UUID,
    data: CancelRequest,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    appt = await cancel_appointment(db, appointment_id, patient.id, data.reason)
    return ResponseEnvelope(data={"id": str(appt.id), "status": appt.status.value})
