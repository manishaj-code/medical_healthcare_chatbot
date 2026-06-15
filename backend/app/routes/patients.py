from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_current_user, get_patient_profile, require_doctor
from app.database import get_db
from app.models import Allergy, Appointment, MedicalHistory, Medication, Patient, User
from app.schemas.common import ORMBase, ResponseEnvelope
from app.schemas.notifications import (
    MarkNotificationsReadRequest,
    MarkNotificationsReadResponse,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import (
    count_unread_notifications,
    list_notifications_for_user,
    mark_notifications_read,
)
from app.services.refill_service import list_refills_for_patient

router = APIRouter(prefix="/patients", tags=["patients"])


class HistoryCreate(BaseModel):
    condition: str
    diagnosed_year: int | None = None
    notes: str | None = None


class MedicationCreate(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None


class AllergyCreate(BaseModel):
    allergen: str
    severity: str = "moderate"
    reaction: str | None = None


class HistoryOut(ORMBase):
    id: UUID
    condition: str
    diagnosed_year: int | None
    notes: str | None


@router.get("/me/medical-history", response_model=ResponseEnvelope[list[HistoryOut]])
async def list_history(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MedicalHistory).where(MedicalHistory.patient_id == patient.id))
    return ResponseEnvelope(data=[HistoryOut.model_validate(h) for h in result.scalars().all()])


@router.post("/me/medical-history", response_model=ResponseEnvelope[HistoryOut])
async def add_history(
    data: HistoryCreate, patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)
):
    h = MedicalHistory(patient_id=patient.id, **data.model_dump())
    db.add(h)
    await db.flush()
    return ResponseEnvelope(data=HistoryOut.model_validate(h))


@router.get("/me/medications", response_model=ResponseEnvelope[list])
async def list_meds(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Medication).where(Medication.patient_id == patient.id))
    return ResponseEnvelope(data=[{"id": str(m.id), "name": m.name, "dosage": m.dosage} for m in result.scalars().all()])


@router.post("/me/medications")
async def add_med(
    data: MedicationCreate, patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)
):
    m = Medication(patient_id=patient.id, **data.model_dump())
    db.add(m)
    await db.flush()
    return ResponseEnvelope(data={"id": str(m.id)})


@router.get("/me/allergies")
async def list_allergies(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Allergy).where(Allergy.patient_id == patient.id))
    return ResponseEnvelope(data=[{"id": str(a.id), "allergen": a.allergen} for a in result.scalars().all()])


@router.post("/me/allergies")
async def add_allergy(
    data: AllergyCreate, patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)
):
    a = Allergy(patient_id=patient.id, **data.model_dump())
    db.add(a)
    await db.flush()
    return ResponseEnvelope(data={"id": str(a.id)})


@router.get("/me/refill-requests")
async def my_refill_requests(
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await list_refills_for_patient(db, patient.id)
    return ResponseEnvelope(data=data)


@router.get("/me/notifications")
async def my_notifications(
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await list_notifications_for_user(db, patient.user_id)
    return ResponseEnvelope(data=data)


@router.get("/me/notifications/unread-count", response_model=ResponseEnvelope[NotificationUnreadCountResponse])
async def my_notifications_unread_count(
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    count = await count_unread_notifications(db, patient.user_id)
    return ResponseEnvelope(data=NotificationUnreadCountResponse(count=count))


@router.post("/me/notifications/mark-read", response_model=ResponseEnvelope[MarkNotificationsReadResponse])
async def my_notifications_mark_read(
    data: MarkNotificationsReadRequest,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    marked = await mark_notifications_read(db, patient.user_id, data.ids)
    return ResponseEnvelope(data=MarkNotificationsReadResponse(marked=marked))


@router.get("/{patient_id}/profile")
async def doctor_view_patient(
    patient_id: UUID,
    user: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    from app.models import Doctor

    doc = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
    doctor = doc.scalar_one()
    appt = await db.execute(
        select(Appointment).where(
            Appointment.patient_id == patient_id, Appointment.doctor_id == doctor.id
        ).limit(1)
    )
    if not appt.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="No appointment relationship")
    history = await db.execute(select(MedicalHistory).where(MedicalHistory.patient_id == patient_id))
    return ResponseEnvelope(data={"history": [h.condition for h in history.scalars().all()]})
