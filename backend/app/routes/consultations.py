"""Clinical consultation API — doctor workflow + patient health records (all visit modes)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_doctor_profile, get_patient_profile
from app.models import Appointment, Consultation, Doctor, Patient, User
from app.schemas.common import ResponseEnvelope
from app.schemas.consultation import CompleteConsultationIn, ConsultationDraftIn
from app.services.consultation_ai_service import generate_clinical_suggestions
from app.services.consultation_service import (
    complete_consultation,
    get_consultation_prep,
    get_patient_consultation_detail,
    list_patient_consultations,
    save_consultation_draft,
    start_consultation,
)
from app.services.lab_catalog_service import list_active_lab_catalog

router = APIRouter(tags=["consultations"])


@router.get("/doctor/lab-catalog")
async def doctor_lab_catalog(
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    """Active orderable lab tests for consultations."""
    data = await list_active_lab_catalog(db)
    return ResponseEnvelope(data=data)


@router.get("/doctor/appointments/{appointment_id}/consultation-prep")
async def doctor_consultation_prep(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await get_consultation_prep(db, appointment_id, doctor.id)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/consultation/start")
async def doctor_start_consultation(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await start_consultation(db, appointment_id, doctor.id)
    return ResponseEnvelope(data=data)


@router.put("/doctor/appointments/{appointment_id}/consultation")
async def doctor_save_consultation_draft(
    appointment_id: UUID,
    body: ConsultationDraftIn,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await save_consultation_draft(db, appointment_id, doctor.id, body)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/consultation/ai-suggestions")
async def doctor_ai_suggestions(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor.id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    result = await db.execute(
        select(Consultation).where(Consultation.appointment_id == appointment_id)
    )
    consultation = result.scalar_one_or_none()
    if not consultation:
        raise HTTPException(status_code=400, detail="Start consultation first")

    patient = await db.get(Patient, appt.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    user = await db.get(User, doctor.user_id)
    doctor_name = user.name if user else "Doctor"
    data = await generate_clinical_suggestions(db, consultation, patient, doctor_name)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/complete-consultation")
async def doctor_complete_consultation(
    appointment_id: UUID,
    body: CompleteConsultationIn,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await complete_consultation(db, appointment_id, doctor.id, body)
    return ResponseEnvelope(data=data)


@router.get("/patients/me/consultations")
async def patient_list_consultations(
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await list_patient_consultations(db, patient.id)
    return ResponseEnvelope(data=data)


@router.get("/patients/me/consultations/{consultation_id}")
async def patient_consultation_detail(
    consultation_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await get_patient_consultation_detail(db, patient.id, consultation_id)
    return ResponseEnvelope(data=data)
