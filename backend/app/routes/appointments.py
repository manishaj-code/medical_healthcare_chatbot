from datetime import date, time
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
from app.services.summary_service import generate_summary
from app.services.video_consultation_service import enable_video_consultation, video_room_id_for_appointment

router = APIRouter(prefix="/appointments", tags=["appointments"])


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
        await generate_summary(db, appt.id)
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
            patient_name=user.name.split()[0],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not start video consultation.") from exc
    return ResponseEnvelope(data=data)


@router.get("/{appointment_id}/video")
async def get_video_consultation(
    appointment_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.video_consultation_service import build_join_url

    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    room_id = appt.video_room_id or video_room_id_for_appointment(appt.id)
    return ResponseEnvelope(
        data={
            "appointment_id": str(appt.id),
            "apt_id": format_apt_id(appt.id),
            "room_id": room_id,
            "join_url": build_join_url(room_id, user.name),
            "consultation_mode": appt.consultation_mode or "in_person",
        }
    )


@router.patch("/{appointment_id}/cancel")
async def cancel(
    appointment_id: UUID,
    data: CancelRequest,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    appt = await cancel_appointment(db, appointment_id, patient.id, data.reason)
    return ResponseEnvelope(data={"id": str(appt.id), "status": appt.status.value})
