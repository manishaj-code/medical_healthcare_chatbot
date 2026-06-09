"""Prescription refill requests — patient submit, doctor approve/deny."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    Doctor,
    Medication,
    Notification,
    Patient,
    RefillRequest,
    User,
)
from app.models.enums import NotificationType, RefillRequestStatus

DEFAULT_GP_EMAIL = "dr.sharma@clinic.com"


async def _notify(db: AsyncSession, user_id: UUID, ntype: NotificationType, message: str) -> None:
    db.add(Notification(user_id=user_id, type=ntype, message=message))
    await db.flush()


async def assign_doctor_for_patient(db: AsyncSession, patient_id: UUID) -> Doctor:
    appt_row = await db.execute(
        select(Doctor)
        .join(Appointment, Appointment.doctor_id == Doctor.id)
        .where(Appointment.patient_id == patient_id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
        .limit(1)
    )
    doctor = appt_row.scalar_one_or_none()
    if doctor:
        return doctor

    gp_row = await db.execute(
        select(Doctor)
        .join(User, Doctor.user_id == User.id)
        .where(User.email == DEFAULT_GP_EMAIL)
        .limit(1)
    )
    doctor = gp_row.scalar_one_or_none()
    if doctor:
        return doctor

    any_doc = await db.execute(select(Doctor).limit(1))
    doctor = any_doc.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=503, detail="No doctor available for refill routing.")
    return doctor


def _serialize_refill(
    req: RefillRequest,
    patient_name: str,
    doctor_name: str,
) -> dict:
    return {
        "id": str(req.id),
        "patient_id": str(req.patient_id),
        "patient_name": patient_name,
        "doctor_id": str(req.doctor_id),
        "doctor_name": doctor_name,
        "medication_name": req.medication_name,
        "medication_dosage": req.medication_dosage,
        "medication_frequency": req.medication_frequency,
        "status": req.status,
        "denial_reason": req.denial_reason,
        "requested_at": req.requested_at.isoformat() if req.requested_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }


async def create_refill_request(
    db: AsyncSession,
    patient: Patient,
    medication_name: str | None,
) -> dict:
    med_rows = await db.execute(
        select(Medication).where(Medication.patient_id == patient.id, Medication.is_active.is_(True))
    )
    meds = med_rows.scalars().all()
    if not meds:
        return {"success": False, "message": "No active prescriptions on file."}

    target = None
    if medication_name:
        for m in meds:
            if medication_name.lower() in m.name.lower():
                target = m
                break
    target = target or meds[0]

    doctor = await assign_doctor_for_patient(db, patient.id)
    doctor_user = await db.get(User, doctor.user_id)
    patient_user = await db.get(User, patient.user_id)

    req = RefillRequest(
        patient_id=patient.id,
        doctor_id=doctor.id,
        medication_id=target.id,
        medication_name=target.name,
        medication_dosage=target.dosage,
        medication_frequency=target.frequency,
        status=RefillRequestStatus.pending.value,
    )
    db.add(req)
    await db.flush()

    med_label = f"{target.name} {target.dosage or ''}".strip()
    patient_name = patient_user.name if patient_user else "Patient"
    doctor_name = doctor_user.name if doctor_user else "your doctor"

    await _notify(
        db,
        patient.user_id,
        NotificationType.system,
        f"Refill request submitted for {med_label}. Your physician will review it shortly.",
    )
    if doctor_user:
        await _notify(
            db,
            doctor_user.id,
            NotificationType.refill_request,
            f"New refill request from {patient_name} for {med_label}.",
        )

    return {
        "success": True,
        "request_id": str(req.id),
        "medication": med_label,
        "doctor_name": doctor_name,
        "message": (
            f"Refill request sent to {doctor_name}. "
            "You will be notified when it is approved or if more information is needed."
        ),
    }


async def list_refills_for_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    status: str | None = None,
) -> list[dict]:
    query = (
        select(RefillRequest, Patient, User)
        .join(Patient, RefillRequest.patient_id == Patient.id)
        .join(User, Patient.user_id == User.id)
        .where(RefillRequest.doctor_id == doctor_id)
        .order_by(RefillRequest.requested_at.desc())
    )
    if status:
        query = query.where(RefillRequest.status == status)

    rows = await db.execute(query)
    doctor = await db.get(Doctor, doctor_id)
    doctor_user = await db.get(User, doctor.user_id) if doctor else None
    doctor_name = doctor_user.name if doctor_user else "Doctor"

    return [
        _serialize_refill(req, user.name, doctor_name)
        for req, _patient, user in rows.all()
    ]


async def list_refills_for_patient(db: AsyncSession, patient_id: UUID) -> list[dict]:
    rows = await db.execute(
        select(RefillRequest, Doctor, User)
        .join(Doctor, RefillRequest.doctor_id == Doctor.id)
        .join(User, Doctor.user_id == User.id)
        .where(RefillRequest.patient_id == patient_id)
        .order_by(RefillRequest.requested_at.desc())
    )
    patient = await db.get(Patient, patient_id)
    patient_user = await db.get(User, patient.user_id) if patient else None
    patient_name = patient_user.name if patient_user else "Patient"

    return [
        _serialize_refill(req, patient_name, doc_user.name)
        for req, _doc, doc_user in rows.all()
    ]


async def approve_refill_request(db: AsyncSession, doctor_id: UUID, request_id: UUID) -> dict:
    req = await db.get(RefillRequest, request_id)
    if not req or req.doctor_id != doctor_id:
        raise HTTPException(status_code=404, detail="Refill request not found")
    if req.status != RefillRequestStatus.pending.value:
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    patient = await db.get(Patient, req.patient_id)
    doctor = await db.get(Doctor, doctor_id)
    doctor_user = await db.get(User, doctor.user_id) if doctor else None

    req.status = RefillRequestStatus.approved.value
    req.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    med_label = f"{req.medication_name} {req.medication_dosage or ''}".strip()
    doctor_name = doctor_user.name if doctor_user else "Your doctor"
    if patient:
        await _notify(
            db,
            patient.user_id,
            NotificationType.refill_approved,
            (
                f"✅ Refill approved by {doctor_name} for {med_label}. "
                "You can pick up your prescription at your pharmacy."
            ),
        )

    return {"success": True, "status": "approved", "medication": med_label}


async def deny_refill_request(
    db: AsyncSession,
    doctor_id: UUID,
    request_id: UUID,
    reason: str | None = None,
) -> dict:
    req = await db.get(RefillRequest, request_id)
    if not req or req.doctor_id != doctor_id:
        raise HTTPException(status_code=404, detail="Refill request not found")
    if req.status != RefillRequestStatus.pending.value:
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    patient = await db.get(Patient, req.patient_id)
    doctor = await db.get(Doctor, doctor_id)
    doctor_user = await db.get(User, doctor.user_id) if doctor else None

    req.status = RefillRequestStatus.denied.value
    req.denial_reason = (reason or "Please schedule a visit to discuss your medication.").strip()
    req.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    med_label = f"{req.medication_name} {req.medication_dosage or ''}".strip()
    doctor_name = doctor_user.name if doctor_user else "Your doctor"
    if patient:
        await _notify(
            db,
            patient.user_id,
            NotificationType.refill_denied,
            (
                f"Refill request for {med_label} was not approved by {doctor_name}. "
                f"Reason: {req.denial_reason}"
            ),
        )

    return {"success": True, "status": "denied", "reason": req.denial_reason}


async def list_notifications_for_user(db: AsyncSession, user_id: UUID, limit: int = 30) -> list[dict]:
    rows = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.sent_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(n.id),
            "type": n.type.value if hasattr(n.type, "value") else str(n.type),
            "message": n.message,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        }
        for n in rows.scalars().all()
    ]
