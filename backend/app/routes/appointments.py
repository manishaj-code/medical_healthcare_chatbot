from datetime import date, time
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_current_user, get_patient_profile
from app.database import get_db
from app.models import Appointment, Doctor, Patient, User
from app.schemas.common import ResponseEnvelope
from app.services.appointment_service import book_appointment, cancel_appointment
from app.services.summary_service import generate_summary

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
            }
            for a, doctor_name in result.all()
        ]
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
